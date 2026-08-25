# controller/model/Component.py
# Author : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Abstraction d'un composant commandé par une sortie GPIO
# -------------------------------------------------------------

import RPi.GPIO as GPIO
from utils.pretty_console import debug, error, info

# ─────────────────────────── init GPIO global ─────────────────
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

LOGGER_NAME = "gpio"

class Component:
    """
    Abstraction d'un composant commandé par un relais actif à l'état bas.

    • `pin` (BCM) exposé publiquement
    • `set_state(1)` → Active le composant (GPIO LOW)
    • `set_state(0)` → Désactive le composant (GPIO HIGH)
    • `get_state()`  → Retourne 1 (ON) si GPIO LOW, sinon 0 (OFF)
    """

    def __init__(self, pin: int):
        self.pin: int = pin  # rendu public pour accès externe (ex: DailyTimer)
        GPIO.setup(self.pin, GPIO.OUT)

        # Par défaut, le composant est désactivé (GPIO HIGH pour relais actif bas)
        GPIO.output(self.pin, GPIO.HIGH)
        info(f"Initialisé sur GPIO {self.pin} → état par défaut : OFF (niveau HIGH)",
             name=LOGGER_NAME)

    def set_state(self, value: int) -> None:
        """
        Définit l'état du composant :
        - 1 = ON (GPIO LOW, active le relais)
        - 0 = OFF (GPIO HIGH, coupe le relais)

        On ne journalise que les *transitions* réelles : réécrire le même niveau
        est un non-évènement (c'est l'amplificateur n°1 du volume de logs).
        """
        wanted = 1 if value == 1 else 0
        try:
            changed = self.get_state() != wanted
            GPIO.output(self.pin, GPIO.LOW if wanted == 1 else GPIO.HIGH)
        except (RuntimeError, ValueError, OSError) as e:
            error(f"Écriture impossible sur GPIO {self.pin} : {e}", name=LOGGER_NAME)
            return

        state_txt = "ON  (LOW - actif)" if wanted == 1 else "OFF (HIGH - inactif)"
        if changed:
            info(f"GPIO {self.pin} ← {state_txt}", name=LOGGER_NAME)
        else:
            debug(f"GPIO {self.pin} déjà {state_txt}", name=LOGGER_NAME)

    def get_state(self) -> int:
        """
        Retourne l'état logique du composant :
        - 1 = ON  (si GPIO LOW → relais actif)
        - 0 = OFF (si GPIO HIGH → relais inactif)
        """
        return 1 if GPIO.input(self.pin) == GPIO.LOW else 0
