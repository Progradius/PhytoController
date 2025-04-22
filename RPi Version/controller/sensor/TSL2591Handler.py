# controller/sensor/TSL2591Handler.py
# Author: Progradius
# License: AGPL 3.0

class TSL2591Handler:
    """
    Handler pour le capteur de luminosité TSL2591.
    Fournit get_ir() et calculate_lux().
    """

    def __init__(self, i2c):
        """
        i2c : instance smbus2.SMBus(1)
        """
        from lib.sensors.TSL2591 import Tsl2591
        self.available = False
        try:
            # sensor_id n'est plus utilisé dans ce driver
            self.tsl = Tsl2591(i2c_bus=i2c)
            self.available = True
        except Exception as e:
            print("⚠️ Erreur init TSL2591 :", e)
            self.tsl = None

    def get_ir(self):
        """
        Retourne la lecture infrarouge brute, ou None si indisponible.
        """
        if not self.available:
            print("⚠️ TSL2591 indisponible (IR)")
            return None
        try:
            return self.tsl.get_luminosity(channel="INFRARED")
        except Exception as e:
            print("Erreur lecture IR TSL2591 :", e)
            return None

    def calculate_lux(self):
        """
        Calcule et retourne la luminosité en lux, ou None si erreur.
        """
        if not self.available:
            print("⚠️ TSL2591 indisponible (lux)")
            return None
        try:
            full, ir = self.tsl.get_full_luminosity()
            return self.tsl.calculate_lux(full, ir)
        except Exception as e:
            print("Erreur lecture Lux TSL2591 :", e)
            return None
