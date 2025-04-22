# controller/sensor/TSL2591Handler.py
# Author : Progradius
# License : AGPL-3.0
"""
Handler haut-niveau pour le capteur de luminosité TSL2591.

Expose deux méthodes :
    • get_ir()         → lecture brute du canal IR
    • calculate_lux()  → lux calculés (canaux complets + IR)

"""

from ui import pretty_console as pc


class TSL2591Handler:
    """
    Wrapper « pythonic » autour du driver low-level Tsl2591
    (situé dans lib/sensors/TSL2591.py).
    """

    # ──────────────────────────────────────────────────────────
    def __init__(self, i2c):
        """
        Paramètres
        ----------
        i2c : instance déjà ouverte de `smbus2.SMBus(1)`
        """
        try:
            # Le constructeur du driver maison accepte un argument nommé `i2c`
            # (cf. version que nous avons adaptée précédemment).
            from lib.sensors.TSL2591 import Tsl2591
            self.tsl = Tsl2591(i2c=i2c)
            self.available = True
            pc.success("TSL2591 détecté et initialisé")
        except Exception as e:  # ImportError, OSError, ...
            self.available = False
            self.tsl = None
            pc.error(f"TSL2591 indisponible : {e}")

    # ──────────────────────────────────────────────────────────
    def get_ir(self):
        """
        Retourne la mesure infrarouge brute (int) ou `None` si erreur/indispo.
        """
        if not self.available:
            pc.warning("Demande IR → capteur non initialisé")
            return None
        try:
            return self.tsl.get_luminosity(channel="INFRARED")
        except Exception as e:
            pc.error(f"Lecture IR TSL2591 échouée : {e}")
            return None

    # ──────────────────────────────────────────────────────────
    def calculate_lux(self):
        """
        Calcule la luminosité en lux via l'algo interne du driver.
        Retourne un float ou `None` si indisponible.
        """
        if not self.available:
            pc.warning("Demande lux → capteur non initialisé")
            return None
        try:
            full, ir = self.tsl.get_full_luminosity()
            lux = self.tsl.calculate_lux(full, ir)
            return lux
        except Exception as e:
            pc.error(f"Calcul lux TSL2591 échoué : {e}")
            return None
