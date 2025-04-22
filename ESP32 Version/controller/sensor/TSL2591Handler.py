# Author: Progradius
# License: AGPL 3.0

from lib.sensors.TSL2591 import Tsl2591


class TSL2591Handler:
    """
    Class used for abstraction of library
    """

    def __init__(self, i2c):
        self.tsl = Tsl2591(i2c=i2c, sensor_id=1)

    # Get only IR value (no unit)
    def get_ir(self):
        try:
            return self.tsl.get_luminosity(channel="INFRARED")
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)

    # Convert raw value. Result is in Lux
    def calculate_lux(self):
        try:
            full, ir = self.tsl.get_full_luminosity()
            return self.tsl.calculate_lux(full, ir)
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)
