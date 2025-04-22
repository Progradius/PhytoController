# controller/sensor/SensorController.py
# Author : Progradius
# License : AGPL‑3.0
# --------------------------------------------------------------------
#  Gestion unifiée de tous les capteurs matériels pour Raspberry Pi
# --------------------------------------------------------------------

import smbus2

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


class SensorController:
    """
    Abstraction d'accès à tous les capteurs du projet.
    Instancie chaque driver **uniquement si** le capteur est marqué « enabled »
    dans `parameters.sensor_state`.
    """

    def __init__(self, parameters):
        self.parameters = parameters

        # ── Bus I2C (/dev/i2c-1) ───────────────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)
            info("Bus I²C /dev/i2c-1 ouvert")
        except FileNotFoundError as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 → {e}")
            self.i2c = None

        # ── Instanciation conditionnelle des capteurs ─────────────────
        self.bme  = BME280Handler(i2c=self.i2c)  if parameters.get_bme_state()   == "enabled" else None
        self.ds18 = DS18Handler()                if parameters.get_ds18_state()  == "enabled" else None
        self.veml = VEMLHandler(i2c=self.i2c)    if parameters.get_veml_state() == "enabled" else None
        self.vl53 = VL53L0XHandler(parameters)   if parameters.get_vl53_state()  == "enabled" else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if parameters.get_mlx_state()   == "enabled" else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if parameters.get_tsl_state()   == "enabled" else None
        self.hcsr = HCSR04Handler(
                        trigger_pin=parameters.get_hcsr_trigger_pin(),
                        echo_pin=   parameters.get_hcsr_echo_pin()
                    )                                        if parameters.get_hcsr_state() == "enabled" else None

        # Dictionnaire de mesures → listes de capteurs (utilisé pour Influx, autres boucles…)
        self.sensor_dict = parameters.sensor_dict

        info("SensorController initialisé")

    def get_sensor_value(self, sensor_key: str):
        """
        Retourne la mesure demandée (float ou int) ou None si désactivé/erreur.
        Les clés (`sensor_key`) doivent correspondre à celles de `sensor_dict` :
          - "BME280T", "BME280H", "BME280P"
          - "DS18B#1" / "DS18B#2" / "DS18B#3"
          - "TSL-LUX", "TSL-IR"
          - "VEML-UVA", "VEML-UVB", "VEML-UVINDEX"
          - "MLX-AMB", "MLX-OBJ"
          - "VL53L0X"
          - "HCSR04"
        """
        try:
            # DS18B20
            if sensor_key.startswith("DS18B#") and self.ds18:
                idx = int(sensor_key.split("#")[1])
                return self.ds18.get_ds18_temp(idx)

            # BME280
            if sensor_key.startswith("BME280") and self.bme:
                return {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }[sensor_key]()

            # TSL2591
            if sensor_key.startswith("TSL-") and self.tsl:
                return {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR" : self.tsl.get_ir
                }[sensor_key]()

            # VEML6075
            if sensor_key.startswith("VEML-") and self.veml:
                return {
                    "VEML-UVA"   : self.veml.get_veml_uva,
                    "VEML-UVB"   : self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_veml_uv_index
                }[sensor_key]()

            # MLX90614 (ambiant / objet)
            if sensor_key in ("MLX-AMB", "MLX-OBJ") and self.mlx:
                return {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }[sensor_key]()

            # VL53L0X (ToF mm)
            if sensor_key == "VL53L0X" and self.vl53:
                return self.vl53.get_vl53_reading()

            # HC‑SR04 (cm)
            if sensor_key == "HCSR04" and self.hcsr:
                return self.hcsr.get_distance_cm()

        except Exception as e:
            error(f"Erreur lecture capteur {sensor_key}: {e}")

        warning(f"{sensor_key} désactivé ou introuvable")
        return None
