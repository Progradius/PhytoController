# Author: Progradius
# License: AGPL 3.0

from lib.sensors.BME280 import BME280


class BME280Handler:
    """
    Handler du capteur BME280 pour extraire température, humidité et pression.
    """

    def __init__(self, i2c):
        self.bme = BME280(i2c=i2c)

    def get_bme_temp(self):
        try:
            return self.bme.values[0]
        except Exception as e:
            print("Can't read BME280 temperature:", e)
            return None

    def get_bme_hygro(self):
        try:
            return self.bme.values[2]
        except Exception as e:
            print("Can't read BME280 hygrometry:", e)
            return None

    def get_bme_pressure(self):
        try:
            return self.bme.values[1]
        except Exception as e:
            print("Can't read BME280 pressure:", e)
            return None
