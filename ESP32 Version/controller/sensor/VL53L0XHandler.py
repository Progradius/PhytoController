# Author: Progradius
# License: AGPL 3.0

from lib.sensors.VL53L0X import VL53L0X


class VL53L0XHandler:
    """
    Class used for abstraction of library
    """
    def __init__(self, i2c):
        self.vl53 = VL53L0X(i2c=i2c)

    def get_vl53_reading(self):
        try:
            self.vl53.start(18)
            result = self.vl53.read()
            self.vl53.stop()
            return result
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)
