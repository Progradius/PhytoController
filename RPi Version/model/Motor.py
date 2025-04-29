# model/Motor.py
# Author : Progradius (adapted)
# License : AGPL‑3.0
# -------------------------------------------------------------
#  Pilotage d'un moteur 4 fils via RPi.GPIO
# -------------------------------------------------------------

import RPi.GPIO as GPIO
from ui.pretty_console import info, warning, error   # log coloré

# Configuration globale (une seule fois dans tout le programme)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)


class Motor:
    """
    Vitesse simulée → 4 niveaux (broches exclusives) :

    ============  ==========  ============
        Vitesse      Broche       État
    ------------  ---------- -------------
          0        (aucune)      HIGH
          1          pin1        LOW
          2          pin2        LOW
          3          pin3        LOW
          4          pin4        LOW
    ============  ==========  ============

    Toutes les broches sont initialisées en HIGH pour garantir l'arrêt
    au démarrage.  
    Les setters attendent un booléen : `True` → HIGH, `False` → LOW.
    """

    # ─────────────────────────── init ─────────────────────────
    def __init__(self, pin1: int, pin2: int, pin3: int, pin4: int):
        self.pin1, self.pin2, self.pin3, self.pin4 = pin1, pin2, pin3, pin4

        for p in (self.pin1, self.pin2, self.pin3, self.pin4):
            GPIO.setup(p, GPIO.OUT, initial=GPIO.HIGH)

        info(f"Moteur initialisé sur broches BCM {pin1}, {pin2}, {pin3}, {pin4}")

    # ───────────────────── helpers internes ──────────────────
    def _set_pin(self, pin: int, value: bool) -> None:
        try:
            GPIO.setup(pin, GPIO.OUT)  # ← forcer la configuration ici si nécessaire
            GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)
        except RuntimeError as e:
            warning(f"[MOTOR] GPIO {pin} non prêt : {e}")

    # ───────────────────────── setters ────────────────────────
    def set_pin1_value(self, value: bool): self._set_pin(self.pin1, value)
    def set_pin2_value(self, value: bool): self._set_pin(self.pin2, value)
    def set_pin3_value(self, value: bool): self._set_pin(self.pin3, value)
    def set_pin4_value(self, value: bool): self._set_pin(self.pin4, value)

    # ───────────────────────── getters ────────────────────────
    def get_motor_speed(self) -> int:
        """Renvoie la vitesse actuelle (0 à 4). Force arrêt immédiat si plusieurs pins actifs."""
        states = {
            1: GPIO.input(self.pin1) == GPIO.LOW,
            2: GPIO.input(self.pin2) == GPIO.LOW,
            3: GPIO.input(self.pin3) == GPIO.LOW,
            4: GPIO.input(self.pin4) == GPIO.LOW,
        }
        active = [speed for speed, is_on in states.items() if is_on]

        if len(active) == 1:
            return active[0]
        elif len(active) == 0:
            return 0
        else:
            # sécurité : forcer tout à HIGH
            for p in (self.pin1, self.pin2, self.pin3, self.pin4):
                GPIO.output(p, GPIO.HIGH)
            error(f"⚠️ Motor - état dangereux détecté : plusieurs vitesses actives {active} → arrêt forcé")
            raise RuntimeError("Danger électrique : plusieurs pins moteur actifs en même temps")