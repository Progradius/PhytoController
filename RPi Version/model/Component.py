# controller/model/Component.py
# Author : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Abstraction d'un composant commandé par une sortie GPIO
# -------------------------------------------------------------

import RPi.GPIO as GPIO
from ui.pretty_console import action, info

# ─────────────────────────── init GPIO global ─────────────────
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

class Component:
    """
    Petite sur-couche autour de *RPi.GPIO* :

    • `pin` (BCM) mémorisé dans l'attr. public **pin**  
    • `set_state(value)`   →  1 = HIGH, 0 = LOW  
    • `get_state()`        →  lit l'état actuel
    """

    def __init__(self, pin: int):
        self.pin: int = pin                       # rendu public pour DailyTimer
        GPIO.setup(self.pin, GPIO.OUT)

        # Par défaut composant désactivé (niveau HIGH avec relais actif niveau bas)
        GPIO.output(self.pin, GPIO.HIGH)
        info(f"Component initialisé sur GPIO {self.pin} (état HIGH)")

    # ───────────────────────── setters / getters ──────────────
    def set_state(self, value: int) -> None:
        """
        Force l'état de la broche :
          • 0 → LOW   (généralement *ON* si relais actif bas)
          • 1 → HIGH  (généralement *OFF*)
        """
        GPIO.output(self.pin, GPIO.LOW if value == 0 else GPIO.HIGH)
        state_txt = "LOW (ON)" if value == 0 else "HIGH (OFF)"
        action(f"GPIO {self.pin} ← {state_txt}")

    def get_state(self) -> int:
        """Retourne 0 (LOW) ou 1 (HIGH)."""
        return GPIO.input(self.pin)
