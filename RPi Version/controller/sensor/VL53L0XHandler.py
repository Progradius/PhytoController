# controller/sensor/VL53L0XHandler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import smbus2
from lib.sensors.VL53L0X import VL53L0X, TimeoutError

class VL53L0XHandler:
    """
    Handler pour le capteur de distance VL53L0X sous Python 3.
    Démarre en mode single shot, lit la distance via read().
    """

    def __init__(self, parameters):
        # parameters n'est pas utilisé ici, mais on reste cohérent avec les autres handlers
        self.available = False
        try:
            bus = smbus2.SMBus(1)  # /dev/i2c-1
            self.vl53 = VL53L0X(i2c_bus=bus, address=parameters.get_vl53_address() if hasattr(parameters, 'get_vl53_address') else 0x29)
            self.available = True
        except Exception as e:
            print("⚠️ Erreur initialisation VL53L0X :", e)
            self.vl53 = None

    def get_vl53_reading(self):
        """
        Renvoie la distance mesurée en mm, ou None en cas d'erreur.
        """
        if not self.available:
            print("⚠️ VL53L0X indisponible")
            return None
        try:
            # Une mesure unique :
            return self.vl53.read()
        except TimeoutError:
            print("⚠️ Timeout lecture VL53L0X")
            return None
        except Exception as e:
            print("⚠️ Erreur lecture VL53L0X :", e)
            return None
