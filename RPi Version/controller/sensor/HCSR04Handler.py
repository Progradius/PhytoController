# Author: Progradius (adapted)
# License: AGPL 3.0

from lib.sensors.HCSR04 import HCSR04


class HCSR04Handler:
    """
    Handler du capteur de distance à ultrasons HC-SR04 pour Raspberry Pi.
    """

    def __init__(self, trigger_pin, echo_pin, echo_timeout_us=1000000):
        self.hcsr = HCSR04(trigger_pin=trigger_pin, echo_pin=echo_pin, echo_timeout_us=echo_timeout_us)

    def get_distance_cm(self):
        try:
            return self.hcsr.distance_cm()
        except Exception as e:
            print("Erreur de lecture (connexion ou capteur HS) :", e)
            return None
