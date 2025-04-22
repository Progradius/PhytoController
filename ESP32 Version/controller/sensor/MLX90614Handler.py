# Author: Progradius
# License: AGPL 3.0

from lib.sensors.MLX90614 import MLX90614


class MLX90614Handler:
    """
    Class used for abstraction of library
    """
    def __init__(self, i2c):
        self.mlx = MLX90614(i2c=i2c)

    def get_ambient_temp(self):
        try:
            return self.mlx.read_ambient_temp()
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)

    def get_object_temp(self):
        try:
            return self.mlx.read_object_temp()
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)
