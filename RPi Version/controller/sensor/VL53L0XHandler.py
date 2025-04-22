# Author: Progradius (adapted)
# License: AGPL 3.0

from lib.sensors.VL53L0X import VL53L0X


class VL53L0XHandler:
    """
    Handler pour le capteur de distance VL53L0X.
    """

    def __init__(self, i2c):
        self.vl53 = VL53L0X(i2c=i2c)

    def get_vl53_reading(self):
        """
        Renvoie la distance mesurée en millimètres.
        """
        try:
            # Dans une implémentation standard (ex: Adafruit), start/stop ne sont pas nécessaires.
            return self.vl53.read()
        except Exception as e:
            print("Erreur de lecture VL53L0X :", e)
            return None
