# controller/sensor/SensorHandler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import smbus2

from controller.sensor.BME280Handler      import BME280Handler
from controller.sensor.DS18Handler        import DS18Handler
from controller.sensor.VEML6075Handler    import VEMLHandler
from controller.sensor.VL53L0XHandler     import VL53L0XHandler
from controller.sensor.MLX90614Handler    import MLX90614Handler
from controller.sensor.TSL2591Handler     import TSL2591Handler
from controller.sensor.HCSR04Handler      import HCSR04Handler


class SensorHandler:
    """
    Classe Python 3 pour Raspberry Pi : abstrait l'accès à tous les capteurs.
    Utilise smbus2 pour l'I²C (/dev/i2c-1).
    """

    def __init__(self, parameters):
        self.parameters = parameters

        # → Initialise le bus I2C 1 via smbus2
        try:
            self.i2c = smbus2.SMBus(1)
        except FileNotFoundError as e:
            print("⚠️ Impossible d'ouvrir /dev/i2c-1 :", e)
            self.i2c = None

        # Instanciation conditionnelle de chaque capteur
        self.bme  = BME280Handler(i2c=self.i2c)  if parameters.get_bme_state()  == "enabled" else None
        self.ds18 = DS18Handler()                 if parameters.get_ds18_state() == "enabled" else None
        self.veml = VEMLHandler(i2c=self.i2c)     if parameters.get_veml_state() == "enabled" else None
        self.vl53 = VL53L0XHandler(i2c=self.i2c)  if parameters.get_vl53_state()  == "enabled" else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if parameters.get_mlx_state()   == "enabled" else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if parameters.get_tsl_state()  == "enabled" else None
        self.hcsr = HCSR04Handler(
                        trigger_pin=parameters.get_hcsr_trigger_pin(),
                        echo_pin=   parameters.get_hcsr_echo_pin()
                    )                                        if parameters.get_hcsr_state() == "enabled" else None

        # Pour parcourir les capteurs activés
        self.sensor_dict = parameters.sensor_dict

    def get_sensor_value(self, chosen_sensor):
        """
        Retourne la valeur du capteur (ou None si désactivé/introuvable).
        """
        try:
            if chosen_sensor.startswith("DS18") and self.ds18:
                idx = int(chosen_sensor[-1])
                return self.ds18.get_ds18_temp(idx)

            if chosen_sensor.startswith("BME") and self.bme:
                return {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }.get(chosen_sensor, lambda: None)()

            if chosen_sensor.startswith("TSL") and self.tsl:
                return {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR":  self.tsl.get_ir
                }.get(chosen_sensor, lambda: None)()

            if chosen_sensor.startswith("VEML") and self.veml:
                return {
                    "VEML-UVA":    self.veml.get_veml_uva,
                    "VEML-UVB":    self.veml.get_veml_uvb,
                    "VEML-UVINDEX":self.veml.get_veml_uv_index
                }.get(chosen_sensor, lambda: None)()

            if chosen_sensor.startswith("MLX") and self.mlx:
                return self.mlx.get_object_temp()

            if chosen_sensor.startswith("VL53") and self.vl53:
                return self.vl53.get_vl53_reading()

            if chosen_sensor.startswith("HCSR") and self.hcsr:
                return self.hcsr.get_distance_cm()

        except Exception as e:
            print(f"⚠️ Erreur lors de la lecture du capteur {chosen_sensor} :", e)

        print(f"⚠️ {chosen_sensor} est désactivé ou introuvable.")
        return None
