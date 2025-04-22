# Author: Progradius
# License: AGPL 3.0

from machine import Pin
from lib.sensors.DS18B20 import DS18


class DS18Handler:
    """
    Class used for abstraction of library
    """
    def __init__(self, pin):
        # Create sensor instance
        self.pin = Pin(pin)
        self.ds18 = DS18(ds_pin=self.pin)

    def get_address_list(self):
        try:
            # Get DS18 address List
            return self.ds18.get_address_list()
        except OSError as e:
            print("Can't read DS18B20 ", e)

    def get_ds18_temp(self, sensor_number):
        try:
            sensor_number = sensor_number - 1
            address_list = self.get_address_list()
            ds18_temp = self.ds18.read_ds_sensor_individually(address_list[sensor_number])
            return ds18_temp
        except OSError as e:
            print("Can't read DS18B20 n°" + str(sensor_number) + " ", e)
