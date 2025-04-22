# Author: Progradius
# License: AGPL 3.0

from machine import Pin, I2C
from controller.sensor.BME280Handler import BME280Handler
from controller.sensor.DS18Handler import DS18Handler
from controller.sensor.VEML6075Handler import VEMLHandler
from controller.sensor.VL53L0XHandler import VL53L0XHandler
from controller.sensor.MLX90614Handler import MLX90614Handler
from controller.sensor.TSL2591Handler import TSL2591Handler
from controller.sensor.HCSR04Handler import HCSR04Handler


class SensorHandler:
    """
    Class used to handle all the sensors and access their parameters/values
    Also provide a method to choose a sensor using a string
    """

    def __init__(self, parameters):
        # Parameter instance holding system settings
        self.parameters = parameters
        # Main I2C instance
        self.i2c = I2C(sda=Pin(self.parameters.get_i2c_sda()),
                       scl=Pin(self.parameters.get_i2c_scl()), )
        # BME280
        if self.parameters.get_bme_state() == "enabled":
            self.bme = BME280Handler(i2c=self.i2c)
        else:
            self.bme = None
        # DS18
        if self.parameters.get_ds18_state() == "enabled":
            self.ds18 = DS18Handler(pin=self.parameters.get_ds18_pin())
        else:
            self.ds18 = None
        # VEML
        if self.parameters.get_veml_state() == "enabled":
            self.veml = VEMLHandler(i2c=self.i2c)
        else:
            self.veml = None
        # VL53
        if self.parameters.get_vl53_state() == "enabled":
            self.vl53 = VL53L0XHandler(i2c=self.i2c)
        else:
            self.vl53 = None
        # MLX90614 IR temp sensor
        if self.parameters.get_mlx_state() == "enabled":
            self.mlx = MLX90614Handler(i2c=self.i2c)
        else:
            self.mlx = None
        # TSL2591 Lux sensor
        if self.parameters.get_tsl_state() == "enabled":
            self.tsl = TSL2591Handler(i2c=self.i2c)
        else:
            self.tsl = None
        if self.parameters.get_hcsr_state() == "enabled":
            self.hcsr = HCSR04Handler(trigger_pin=parameters.get_hcsr_trigger_pin(),
                                      echo_pin=parameters.get_hcsr_echo_pin())
        else:
            self.hcsr = None
        # Normalized sensor names and measurements
        self.sensor_dict = parameters.sensor_dict

    def get_sensor_value(self, chosen_sensor):
        """ Choose a Sensor using a string and return the corresponding value """

        # DS18 onewire temp sensor
        if chosen_sensor.find("DS18") == 0 and self.parameters.get_ds18_state() == "enabled":
            try:
                if chosen_sensor == "DS18B#1":
                    return self.ds18.get_ds18_temp(1)
                if chosen_sensor == "DS18B#2":
                    return self.ds18.get_ds18_temp(2)
                if chosen_sensor == "DS18B#3":
                    return self.ds18.get_ds18_temp(3)
            except NameError:
                print(chosen_sensor + " Sensor Error")

        # BME280 temp/hr/pressure sensor
        if chosen_sensor.find("BME") == 0 and self.parameters.get_bme_state() == "enabled":
            try:
                if chosen_sensor == "BME280T":
                    return self.bme.get_bme_temp()
                if chosen_sensor == "BME280H":
                    return self.bme.get_bme_hygro()
                if chosen_sensor == "BME280P":
                    return self.bme.get_bme_pressure()
            except NameError:
                print(chosen_sensor + " Sensor Error")

        # TSL2591 lux sensor
        if chosen_sensor.find("TSL") == 0 and self.parameters.get_tsl_state() == "enabled":
            try:
                if chosen_sensor == "TSL-LUX":
                    return self.tsl.calculate_lux()
                if chosen_sensor == "TSL-IR":
                    return self.tsl.get_ir()
            except NameError:
                print(chosen_sensor + " Sensor Error")

        if chosen_sensor.find("VEML") == 0 and self.parameters.get_veml_state() == "enabled":
            try:
                if chosen_sensor == "VEML-UVA":
                    return self.veml.get_veml_uva()
                if chosen_sensor == "VEML-UVB":
                    return self.veml.get_veml_uvb()
                if chosen_sensor == "VEML-UVINDEX":
                    return self.veml.get_veml_uv_index()
            except NameError:
                print(chosen_sensor + " Sensor error")

        else:
            print(chosen_sensor + " is Deactivated")
            return None
