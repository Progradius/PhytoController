# Author: Progradius
# License: AGPL 3.0

from lib.sensors.BME280 import BME280


class BME280Handler:
    """
    BME280 class used for abstraction
    """

    def __init__(self, i2c):
        self.bme = BME280(i2c=i2c)

    def get_bme_temp(self):
        try:
            bme_temp = self.bme.values[0]
            return bme_temp
        except OSError as e:
            print("Can't read BME280T ", e)

    def get_bme_hygro(self):
        try:
            bme_hygro = self.bme.values[2]
            return bme_hygro
        except OSError as e:
            print("Can't read BME280HR ", e)

    def get_bme_pressure(self):
        try:
            bme_pressure = self.bme.values[1]
            return bme_pressure
        except OSError as e:
            print("Can't read BME280PR ", e)
