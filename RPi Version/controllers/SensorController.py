# controller/sensor/SensorController.py
# Author : Progradius
# License : AGPL-3.0
# --------------------------------------------------------------------
#  Gestion unifiée de tous les capteurs matériels pour Raspberry Pi
#  (refactoré pour utiliser AppConfig au lieu de Parameter)
# --------------------------------------------------------------------

import smbus2
from typing import Dict, List

# Handlers spécialisés
from sensor_handlers.BME280Handler   import BME280Handler
from sensor_handlers.DS18Handler     import DS18Handler
from sensor_handlers.VEML6075Handler import VEMLHandler
from sensor_handlers.VL53L0XHandler  import VL53L0XHandler
from sensor_handlers.MLX90614Handler import MLX90614Handler
from sensor_handlers.TSL2591Handler  import TSL2591Handler
from sensor_handlers.HCSR04Handler   import HCSR04Handler

# Affichage « Pretty »
from ui.pretty_console import info, warning, error

# Votre modèle de config
from param.config import AppConfig


class SensorController:
    """
    Regroupe tous les capteurs sous des measurements « métier » :
      • air          : BME280 + MLX90614 ambiant
      • surface_temp : MLX90614 objet
      • water        : DS18B#3 (température d'eau)
      • distance     : VL53L0X + HC-SR04
      • lux          : TSL2591
    """

    def __init__(self, config: AppConfig):
        self.config = config

        # ── Bus I2C (/dev/i2c-1) ───────────────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)
            info("Bus I²C /dev/i2c-1 ouvert")
        except FileNotFoundError as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 → {e}")
            self.i2c = None

        # ── Activation selon AppConfig.sensors ─────────────────────────
        s = self.config.sensors
        self.bme_enabled  = s.bme280_state
        self.ds18_enabled = s.ds18b20_state
        self.veml_enabled = s.veml6075_state
        self.vl53_enabled = s.vl53L0x_state
        self.mlx_enabled  = s.mlx90614_state
        self.tsl_enabled  = s.tsl2591_state
        self.hcsr_enabled = s.hcsr04_state

        # Instanciation conditionnelle
        self.bme  = BME280Handler(i2c=self.i2c)   if self.bme_enabled else None
        self.ds18 = DS18Handler()                 if self.ds18_enabled else None
        self.veml = VEMLHandler(i2c=self.i2c)     if self.veml_enabled else None
        self.vl53 = VL53L0XHandler(config)        if self.vl53_enabled else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if self.mlx_enabled else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if self.tsl_enabled else None
        self.hcsr = HCSR04Handler(
            trigger_pin=self.config.gpio.hcsr_trigger_pin,
            echo_pin=self.config.gpio.hcsr_echo_pin
        ) if self.hcsr_enabled else None

        # ── Dictionnaire de mesures pour Influx / Web ─────────────────
        self.sensor_dict = self._build_sensor_dict()
        info(f"SensorController initialisé avec : {self.sensor_dict}")

    def _is_sensor_enabled(self, sensor_name: str) -> bool:
        sensor_mapping = {
            "BME280T": self.bme_enabled, "BME280H": self.bme_enabled, "BME280P": self.bme_enabled,
            "DS18B#1": self.ds18_enabled, "DS18B#2": self.ds18_enabled, "DS18B#3": self.ds18_enabled,
            "TSL-LUX": self.tsl_enabled, "TSL-IR": self.tsl_enabled,
            "VEML-UVA": self.veml_enabled, "VEML-UVB": self.veml_enabled, "VEML-UVINDEX": self.veml_enabled,
            "MLX-AMB": self.mlx_enabled, "MLX-OBJ": self.mlx_enabled,
            "VL53L0X": self.vl53_enabled,
            "HCSR04": self.hcsr_enabled,
        }
        return sensor_mapping.get(sensor_name, False)

    def _build_sensor_dict(self) -> Dict[str, List[str]]:
        """
        Construit le dictionnaire des capteurs activés, utilisé pour l'export.
        """
        base_sensor_dict: Dict[str, List[str]] = {
            "air":          ["BME280T", "BME280H", "BME280P", "MLX-AMB", "DS18B#1", "DS18B#2"],
            "surface_temp": ["MLX-OBJ"],
            "water":        ["DS18B#3"],
            "distance":     ["VL53L0X", "HCSR04"],
            "lux":          ["TSL-LUX", "TSL-IR"],
        }

        sensor_dict: Dict[str, List[str]] = {}
        for measurement, sensor_keys in base_sensor_dict.items():
            enabled_sensors = [
                sensor for sensor in sensor_keys
                if self._is_sensor_enabled(sensor)
            ]
            if enabled_sensors:
                sensor_dict[measurement] = enabled_sensors

        return sensor_dict

    def get_sensor_value(self, sensor_key: str):
        """
        Retourne la mesure demandée (float ou int) ou None si désactivé/erreur.
        """
        try:
            result = None

            if sensor_key.startswith("DS18B#") and self.ds18:
                idx = int(sensor_key.split("#")[1])
                result = self.ds18.get_ds18_temp(idx)

            elif sensor_key.startswith("BME280") and self.bme:
                result = {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }[sensor_key]()

            elif sensor_key.startswith("TSL-") and self.tsl:
                result = {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR": self.tsl.get_ir
                }[sensor_key]()

            elif sensor_key.startswith("VEML-") and self.veml:
                result = {
                    "VEML-UVA": self.veml.get_veml_uva,
                    "VEML-UVB": self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_uv_index
                }[sensor_key]()

            elif sensor_key in ("MLX-AMB", "MLX-OBJ") and self.mlx:
                result = {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }[sensor_key]()

            elif sensor_key == "VL53L0X" and self.vl53:
                result = self.vl53.get_vl53_reading()

            elif sensor_key == "HCSR04" and self.hcsr:
                result = self.hcsr.get_distance_cm()

        except Exception as e:
            error(f"Erreur lecture capteur {sensor_key}: {e}")
            result = None

        if result is None:
            warning(f"{sensor_key} désactivé ou introuvable")
            return None

        stats = getattr(self, "stats", None)
        if stats and sensor_key in stats.KEYS:
            try:
                stats.update(sensor_key, float(result))
            except Exception:
                pass

        return result
