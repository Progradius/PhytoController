# controller/sensor/HCSR04Handler.py
# Author : Progradius
# License: AGPL-3.0
"""
Handler pour le capteur ultrason HC-SR04 (distance).
- Dépend du driver « lib.sensors.HCSR04 » portant le même nom de classe.
"""

from lib.sensors.HCSR04 import HCSR04
from ui import pretty_console as pc


class HCSR04Handler:
    """
    Fournit :
        • get_distance_cm()  → distance en cm   (float | None)
        • cleanup()          → libération propre des GPIO
    """

    def __init__(self, trigger_pin: int, echo_pin: int, *, echo_timeout_us: int = 1_000_000):
        """
        Parameters
        ----------
        trigger_pin      GPIO BCM relié à TRIG
        echo_pin         GPIO BCM relié à ECHO
        echo_timeout_us  Timeout micro-secondes (défaut 1 s)
        """
        try:
            self.sensor = HCSR04(trigger_pin=trigger_pin,
                                 echo_pin=echo_pin,
                                 echo_timeout_us=echo_timeout_us)
            self.available = True
            pc.success(f"HC-SR04 initialisé (TRIG {trigger_pin} / ECHO {echo_pin})")
        except Exception as exc:
            pc.error(f"Impossible d'initialiser le HC-SR04 : {exc}")
            self.available = False
            self.sensor = None

    # ------------------------------------------------------------------
    # Mesure
    # ------------------------------------------------------------------
    def get_distance_cm(self):
        """Renvoie la distance en cm, None en cas d'erreur ou de capteur absent."""
        if not self.available:
            pc.warning("HC-SR04 indisponible")
            return None
        try:
            dist = self.sensor.distance_cm()
            pc.info(f"Distance mesurée : {dist:.1f} cm")
            return dist
        except Exception as exc:
            pc.error(f"Lecture HC-SR04 échouée : {exc}")
            return None

    # ------------------------------------------------------------------
    # Nettoyage
    # ------------------------------------------------------------------
    def cleanup(self):
        """Libère les ressources matérielles si nécessaire (optionnel)."""
        try:
            if self.sensor and hasattr(self.sensor, "cleanup"):
                self.sensor.cleanup()
                pc.success("GPIO HC-SR04 libérés")
        except Exception as exc:
            pc.error(f"Problème durant cleanup HC-SR04 : {exc}")
