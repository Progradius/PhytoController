# Author: Progradius
# License: AGPL 3.0

from lib.sensors.TSL2591 import Tsl2591


class TSL2591Handler:
    """
    Handler pour le capteur de luminosité TSL2591.
    Fournit les mesures infrarouges et la conversion en lux.
    """

    def __init__(self, i2c):
        self.tsl = Tsl2591(i2c=i2c, sensor_id=1)

    def get_ir(self):
        """
        Retourne la luminosité infrarouge brute (sans unité).
        """
        try:
            return self.tsl.get_luminosity(channel="INFRARED")
        except Exception as e:
            print("Erreur de lecture IR TSL2591 :", e)
            return None

    def calculate_lux(self):
        """
        Calcule la luminosité en lux à partir des valeurs brutes.
        """
        try:
            full, ir = self.tsl.get_full_luminosity()
            return self.tsl.calculate_lux(full, ir)
        except Exception as e:
            print("Erreur de lecture Lux TSL2591 :", e)
            return None
