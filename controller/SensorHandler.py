# Author: Progradius (adapted)
# License: AGPL 3.0

import board
import busio

from controller.sensor.BME280Handler import BME280Handler
from controller.sensor.DS18Handler import DS18Handler
from controller.sensor.VEML6075Handler import VEMLHandler
from controller.sensor.VL53L0XHandler import VL53L0XHandler
from controller.sensor.MLX90614Handler import MLX90614Handler
from controller.sensor.TSL2591Handler import TSL2591Handler
from controller.sensor.HCSR04Handler import HCSR04Handler


class SensorHandler:
    """
    Classe Python 3 pour Raspberry Pi permettant d’abstraire l'accès à l’ensemble des capteurs.
    Initialise les capteurs activés dans les paramètres.
    """

    def __init__(self, parameters):
        self.parameters = parameters

        # Initialisation du bus I2C standard Raspberry Pi (SCL/SDA par défaut)
        self.i2c = busio.I2C(board.SCL, board.SDA)

        # Capteur BME280 (temp/humidité/pression)
        self.bme = BME280Handler(i2c=self.i2c) if parameters.get_bme_state() == "enabled" else None

        # Capteur DS18B20 (température)
        self.ds18 = DS18Handler(pin=parameters.get_ds18_pin()) if parameters.get_ds18_state() == "enabled" else None

        # Capteur VEML6075 (UV)
        self.veml = VEMLHandler(i2c=self.i2c) if parameters.get_veml_state() == "enabled" else None

        # Capteur VL53L0X (distance laser)
        self.vl53 = VL53L0XHandler(i2c=self.i2c) if parameters.get_vl53_state() == "enabled" else None

        # Capteur MLX90614 (température IR)
        self.mlx = MLX90614Handler(i2c=self.i2c) if parameters.get_mlx_state() == "enabled" else None

        # Capteur TSL2591 (lumière visible/infrarouge)
        self.tsl = TSL2591Handler(i2c=self.i2c) if parameters.get_tsl_state() == "enabled" else None

        # Capteur ultrason HC-SR04
        self.hcsr = HCSR04Handler(
            trigger_pin=parameters.get_hcsr_trigger_pin(),
            echo_pin=parameters.get_hcsr_echo_pin()
        ) if parameters.get_hcsr_state() == "enabled" else None

        # Dictionnaire des capteurs activés pour les mesures
        self.sensor_dict = parameters.sensor_dict

    def get_sensor_value(self, chosen_sensor):
        """
        Retourne la valeur du capteur correspondant au nom fourni (format chaîne).
        """

        try:
            # DS18B20 (température)
            if chosen_sensor.startswith("DS18") and self.ds18:
                index = int(chosen_sensor[-1])
                return self.ds18.get_ds18_temp(index)

            # BME280 (T/H/P)
            if chosen_sensor.startswith("BME") and self.bme:
                if chosen_sensor == "BME280T":
                    return self.bme.get_bme_temp()
                elif chosen_sensor == "BME280H":
                    return self.bme.get_bme_hygro()
                elif chosen_sensor == "BME280P":
                    return self.bme.get_bme_pressure()

            # TSL2591 (lumière)
            if chosen_sensor.startswith("TSL") and self.tsl:
                if chosen_sensor == "TSL-LUX":
                    return self.tsl.calculate_lux()
                elif chosen_sensor == "TSL-IR":
                    return self.tsl.get_ir()

            # VEML6075 (UV)
            if chosen_sensor.startswith("VEML") and self.veml:
                if chosen_sensor == "VEML-UVA":
                    return self.veml.get_veml_uva()
                elif chosen_sensor == "VEML-UVB":
                    return self.veml.get_veml_uvb()
                elif chosen_sensor == "VEML-UVINDEX":
                    return self.veml.get_veml_uv_index()

            # MLX90614 (température IR)
            if chosen_sensor.startswith("MLX") and self.mlx:
                return self.mlx.get_object_temp()

            # VL53L0X (distance laser)
            if chosen_sensor.startswith("VL53") and self.vl53:
                return self.vl53.get_vl53_reading()

            # HC-SR04 (ultrason)
            if chosen_sensor.startswith("HCSR") and self.hcsr:
                return self.hcsr.get_distance_cm()

        except Exception as e:
            print(f"Erreur lors de la lecture du capteur {chosen_sensor} :", e)

        print(f"{chosen_sensor} est désactivé ou introuvable.")
        return None
