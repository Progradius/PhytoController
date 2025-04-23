# controller/sensor/SensorController.py
# Author : Progradius (adapted for AppConfig)
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

# Votre nouveau modèle de config
from param.config import AppConfig


class SensorController:
    """
    Abstraction d'accès à tous les capteurs du projet.
    Instancie chaque driver **uniquement si** le capteur est activé
    dans `config.sensors`. Met aussi à jour les stats si injectées.
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
        # Pydantic booleans issus de "enabled"/"disabled"
        s = self.config.sensors
        self.bme_enabled   = s.bme280_state
        self.ds18_enabled  = s.ds18b20_state
        self.veml_enabled  = s.veml6075_state
        self.vl53_enabled  = s.vl53L0x_state
        self.mlx_enabled   = s.mlx90614_state
        self.tsl_enabled   = s.tsl2591_state
        self.hcsr_enabled  = s.hcsr04_state

        # Instanciation conditionnelle
        self.bme  = BME280Handler(i2c=self.i2c)  if self.bme_enabled  else None
        self.ds18 = DS18Handler()                if self.ds18_enabled else None
        self.veml = VEMLHandler(i2c=self.i2c)    if self.veml_enabled else None
        self.vl53 = VL53L0XHandler(config)       if self.vl53_enabled else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if self.mlx_enabled  else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if self.tsl_enabled  else None
        self.hcsr = HCSR04Handler(
                        trigger_pin=self.config.gpio.hcsr_trigger_pin,
                        echo_pin=   self.config.gpio.hcsr_echo_pin
                    ) if self.hcsr_enabled else None

        # ── Dictionnaire de mesures pour Influx / Web ─────────────────
        # On regroupe les clés de mesure par « measurement » Influx
        self.sensor_dict: Dict[str, List[str]] = {
            "BME280":   ["BME280T", "BME280H", "BME280P"] if self.bme else [],
            "DS18B20":  [f"DS18B#{i}" for i in (1,2,3)] if self.ds18 else [],
            "TSL2591":  ["TSL-LUX", "TSL-IR"] if self.tsl else [],
            "VEML6075": ["VEML-UVA", "VEML-UVB", "VEML-UVINDEX"] if self.veml else [],
            "MLX90614":["MLX-AMB", "MLX-OBJ"] if self.mlx else [],
            "VL53L0X":  ["VL53L0X"] if self.vl53 else [],
            "HCSR04":   ["HCSR04"] if self.hcsr else []
        }

        info("SensorController initialisé")

    def get_sensor_value(self, sensor_key: str):
        """
        Retourne la mesure demandée (float ou int) ou None si désactivé/erreur.
        """
        try:
            result = None

            # DS18B20
            if sensor_key.startswith("DS18B#") and self.ds18:
                idx = int(sensor_key.split("#")[1])
                result = self.ds18.get_ds18_temp(idx)

            # BME280
            elif sensor_key.startswith("BME280") and self.bme:
                result = {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }[sensor_key]()

            # TSL2591
            elif sensor_key.startswith("TSL-") and self.tsl:
                result = {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR":  self.tsl.get_ir
                }[sensor_key]()

            # VEML6075
            elif sensor_key.startswith("VEML-") and self.veml:
                result = {
                    "VEML-UVA":    self.veml.get_veml_uva,
                    "VEML-UVB":    self.veml.get_veml_uvb,
                    "VEML-UVINDEX":self.veml.get_uv_index
                }[sensor_key]()

            # MLX90614
            elif sensor_key in ("MLX-AMB", "MLX-OBJ") and self.mlx:
                result = {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }[sensor_key]()

            # VL53L0X (Time-of-Flight)
            elif sensor_key == "VL53L0X" and self.vl53:
                result = self.vl53.get_vl53_reading()

            # HC-SR04 (ultrason)
            elif sensor_key == "HCSR04" and self.hcsr:
                result = self.hcsr.get_distance_cm()

        except Exception as e:
            error(f"Erreur lecture capteur {sensor_key}: {e}")
            result = None

        if result is None:
            warning(f"{sensor_key} désactivé ou introuvable")
            return None

        # Mise à jour des stats si injectées
        stats = getattr(self, "stats", None)
        if stats and sensor_key in stats.KEYS:
            try:
                stats.update(sensor_key, float(result))
            except Exception:
                pass

        return result
