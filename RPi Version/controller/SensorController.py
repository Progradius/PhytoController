# controller/sensor/SensorController.py
# Author : Progradius
# License : AGPL-3.0
# --------------------------------------------------------------------
#  Gestion unifiée de tous les capteurs matériels pour Raspberry Pi
# --------------------------------------------------------------------

import smbus2

# Handlers spécialisés
from controller.sensor.BME280Handler   import BME280Handler
from controller.sensor.DS18Handler     import DS18Handler
from controller.sensor.VEML6075Handler import VEMLHandler
from controller.sensor.VL53L0XHandler  import VL53L0XHandler
from controller.sensor.MLX90614Handler import MLX90614Handler
from controller.sensor.TSL2591Handler  import TSL2591Handler
from controller.sensor.HCSR04Handler   import HCSR04Handler

# Affichage « Pretty »
from ui.pretty_console import info, warning, error


class SensorController:
    """
    Abstraction d'accès à tous les capteurs du projet.
    Instancie chaque driver **uniquement si** le capteur est marqué « enabled »
    dans *param.json*.
    """

    def __init__(self, parameters):
        self.parameters = parameters

        # ── Bus I²C principal /dev/i2c-1 ──────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)
            info("Bus I²C /dev/i2c-1 ouvert")
        except FileNotFoundError as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 → {e}")
            self.i2c = None

        # ── Instanciation conditionnelle des capteurs ─────────────────
        self.bme  = BME280Handler(i2c=self.i2c)  if parameters.get_bme_state()  == "enabled" else None
        self.ds18 = DS18Handler()                if parameters.get_ds18_state() == "enabled" else None
        self.veml = VEMLHandler(i2c=self.i2c)    if parameters.get_veml_state() == "enabled" else None
        self.vl53 = VL53L0XHandler(parameters)   if parameters.get_vl53_state() == "enabled" else None
        self.mlx  = MLX90614Handler(i2c=self.i2c)if parameters.get_mlx_state()  == "enabled" else None
        self.tsl  = TSL2591Handler(i2c=self.i2c) if parameters.get_tsl_state()  == "enabled" else None
        self.hcsr = HCSR04Handler(
                        trigger_pin = parameters.get_hcsr_trigger_pin(),
                        echo_pin    = parameters.get_hcsr_echo_pin()
                    )                            if parameters.get_hcsr_state() == "enabled" else None

        # Dictionnaire {measurement: [noms_capteurs]}
        self.sensor_dict = parameters.sensor_dict
        info("SensorController initialisé")

    # ----------------------------------------------------------------
    def get_sensor_value(self, chosen_sensor):
        """
        Retourne la mesure demandée ou **None** en cas d'erreur/inactivité.
        Les libellés doivent correspondre à ceux déclarés dans *sensor_dict*.
        """
        try:
            # ----- DS18B20 --------------------------------------------------
            if chosen_sensor.startswith("DS18") and self.ds18:
                idx = int(chosen_sensor[-1])
                return self.ds18.get_ds18_temp(idx)

            # ----- BME280 ---------------------------------------------------
            if chosen_sensor.startswith("BME") and self.bme:
                return {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }.get(chosen_sensor, lambda: None)()

            # ----- TSL2591 --------------------------------------------------
            if chosen_sensor.startswith("TSL") and self.tsl:
                return {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR" : self.tsl.get_ir
                }.get(chosen_sensor, lambda: None)()

            # ----- VEML6075 -------------------------------------------------
            if chosen_sensor.startswith("VEML") and self.veml:
                return {
                    "VEML-UVA"    : self.veml.get_veml_uva,
                    "VEML-UVB"    : self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_veml_uv_index
                }.get(chosen_sensor, lambda: None)()

            # ----- MLX90614 -------------------------------------------------
            if chosen_sensor.startswith("MLX") and self.mlx:
                return {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }.get(chosen_sensor, lambda: None)()

            # ----- VL53L0X --------------------------------------------------
            if chosen_sensor == "VL53-DIST" and self.vl53:
                return self.vl53.get_vl53_reading()

            # ----- HC-SR04 --------------------------------------------------
            if chosen_sensor == "HCSR-DIST" and self.hcsr:
                return self.hcsr.get_distance_cm()

        except Exception as e:
            error(f"Lecture capteur {chosen_sensor} : {e}")

        warning(f"{chosen_sensor} désactivé ou introuvable")
        return None
