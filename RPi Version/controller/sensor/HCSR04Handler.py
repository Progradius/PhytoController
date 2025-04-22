# controller/sensor/HCSR04Handler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

from lib.sensors.HCSR04 import HCSR04

class HCSR04Handler:
    """
    Handler pour le capteur ultrasons HC-SR04 sous Python 3.
    Fournit get_distance_cm().
    """

    def __init__(self, trigger_pin, echo_pin, echo_timeout_us=1_000_000):
        """
        trigger_pin     : GPIO BCM du trigger
        echo_pin        : GPIO BCM de l'echo
        echo_timeout_us : timeout en µs
        """
        try:
            self.sensor = HCSR04(
                trigger_pin     = trigger_pin,
                echo_pin        = echo_pin,
                echo_timeout_us = echo_timeout_us
            )
            self.available = True
        except Exception as e:
            print("⚠️ Erreur init HC-SR04 :", e)
            self.available = False
            self.sensor = None

    def get_distance_cm(self):
        """
        Renvoie la distance en cm (float) ou None en cas d'erreur.
        """
        if not self.available:
            print("⚠️ HC-SR04 indisponible")
            return None
        try:
            return self.sensor.distance_cm()
        except Exception as e:
            print("Erreur lecture HC-SR04 :", e)
            return None

    def cleanup(self):
        """
        Libère les GPIO du capteur (optionnel).
        """
        if self.sensor:
            self.sensor.cleanup()
