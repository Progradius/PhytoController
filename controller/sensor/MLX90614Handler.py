# Author: Progradius
# License: AGPL 3.0

from lib.sensors.MLX90614 import MLX90614


class MLX90614Handler:
    """
    Handler pour le capteur de température infrarouge MLX90614.
    Ce handler permet d'obtenir la température ambiante et celle de l'objet mesuré.
    """

    def __init__(self, i2c):
        self.mlx = MLX90614(i2c=i2c)

    def get_ambient_temp(self):
        try:
            return self.mlx.read_ambient_temp()
        except Exception as e:
            print("Erreur, vérifiez la connexion/intégrité du MLX90614 (ambiante) :", e)
            return None

    def get_object_temp(self):
        try:
            return self.mlx.read_object_temp()
        except Exception as e:
            print("Erreur, vérifiez la connexion/intégrité du MLX90614 (objet) :", e)
            return None
