# controller/sensor/SensorHandler.py
# Author : Progradius (adapted)
# License : AGPL-3.0
# -------------------------------------------------------------
#  Accès unifié à tous les capteurs disponibles sur le Raspberry Pi
# -------------------------------------------------------------

import re
import smbus2

# Handlers individuels
from controller.sensor.BME280Handler   import BME280Handler
from controller.sensor.DS18Handler     import DS18Handler
from controller.sensor.VEML6075Handler import VEMLHandler
from controller.sensor.VL53L0XHandler  import VL53L0XHandler
from controller.sensor.MLX90614Handler import MLX90614Handler
from controller.sensor.TSL2591Handler  import TSL2591Handler
from controller.sensor.HCSR04Handler   import HCSR04Handler

# Console « jolie »
from controller.ui.pretty_console import info, warning, error


# ----------------------------------------------------------------
class SensorHandler:
    """
    Abstraction haute-niveau des capteurs.

    • Instancie chaque handler selon l'état stocké dans *parameters*
    • Expose `get_sensor_value(code)` pour récupérer n'importe quelle mesure
      via un identifiant : « BME280T », « DS18B#1 », « TSL-LUX », etc.
    """

    def __init__(self, parameters):
        self.parameters = parameters

        # ── Bus I²C PRINCIPAL ─────────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)                     # /dev/i2c-1
            info("Bus I²C initialisé (/dev/i2c-1)")
        except FileNotFoundError as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 : {e}")
            self.i2c = None

        # ── Instantiation conditionnelle des handlers ───────
        self.bme  = BME280Handler(i2c=self.i2c)              if parameters.get_bme_state()  == "enabled" else None
        self.ds18 = DS18Handler()                            if parameters.get_ds18_state() == "enabled" else None
        self.veml = VEMLHandler(i2c=self.i2c)                if parameters.get_veml_state() == "enabled" else None
        self.vl53 = VL53L0XHandler(parameters)               if parameters.get_vl53_state() == "enabled" else None
        self.mlx  = MLX90614Handler(i2c=self.i2c)            if parameters.get_mlx_state()  == "enabled" else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)             if parameters.get_tsl_state()  == "enabled" else None
        self.hcsr = (
            HCSR04Handler(
                trigger_pin=parameters.get_hcsr_trigger_pin(),
                echo_pin   =parameters.get_hcsr_echo_pin(),
            ) if parameters.get_hcsr_state() == "enabled" else None
        )

        # Dictionnaire des capteurs → utilisé par influx_handler
        self.sensor_dict = parameters.sensor_dict

    # ==============================================================

    @staticmethod
    def _extract_index(name: str) -> int:
        """
        Extrait le numéro en fin de chaîne (ex : « DS18B#3 » → 3).
        Renvoie 1 si rien trouvé.
        """
        m = re.search(r'(\d+)$', name)
        return int(m.group(1)) if m else 1

    # -------------------------------------------------------------
    def get_sensor_value(self, code: str):
        """
        Lit la valeur correspondant au *code* fourni :
        retourne le type Python natif ou `None` en cas d'erreur.
        """
        try:
            # ── DS18B20 ──────────────────────────────────────
            if code.startswith("DS18") and self.ds18:
                return self.ds18.get_ds18_temp(self._extract_index(code))

            # ── BME280 ──────────────────────────────────────
            if code.startswith("BME") and self.bme:
                return {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure,
                }.get(code, lambda: None)()

            # ── TSL2591 ─────────────────────────────────────
            if code.startswith("TSL") and self.tsl:
                return {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR" : self.tsl.get_ir,
                }.get(code, lambda: None)()

            # ── VEML6075 ───────────────────────────────────
            if code.startswith("VEML") and self.veml:
                return {
                    "VEML-UVA"    : self.veml.get_veml_uva,
                    "VEML-UVB"    : self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_veml_uv_index,
                }.get(code, lambda: None)()

            # ── MLX90614 (temp IR) ─────────────────────────
            if code.startswith("MLX") and self.mlx:
                return self.mlx.get_object_temp()

            # ── VL53L0X (distance ToF) ─────────────────────
            if code.startswith("VL53") and self.vl53:
                return self.vl53.get_vl53_reading()

            # ── HC-SR04 (ultrason) ─────────────────────────
            if code.startswith("HCSR") and self.hcsr:
                return self.hcsr.get_distance_cm()

        except Exception as e:
            error(f"Lecture capteur {code} impossible : {e}")

        warning(f"{code} désactivé ou introuvable.")
        return None
