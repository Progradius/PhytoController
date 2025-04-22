# Author: Progradius
# License: AGPL 3.0

from lib.sensors.VEML6075 import VEML6075


class VEMLHandler:
    """
    Class used for abstraction of library
    """
    def __init__(self, i2c):
        self.veml = VEML6075(i2c=i2c)

    def get_veml_uv_index(self):
        try:
            return self.veml.uv_index
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)

    def get_veml_uva(self):
        try:
            return self.veml.uva
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)

    def get_veml_uvb(self):
        try:
            return self.veml.uvb
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)
