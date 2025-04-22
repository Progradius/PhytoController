# model/Motor.py
# Author : Progradius (adapted)
# License : AGPL‑3.0
# -------------------------------------------------------------
#  Pilotage d’un moteur 4 fils via RPi.GPIO
# -------------------------------------------------------------

import RPi.GPIO as GPIO
from controller.ui.pretty_console import info, warning   # log coloré

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

    Toutes les broches sont initialisées en HIGH pour garantir l’arrêt
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
        GPIO.output(pin, GPIO.HIGH if value else GPIO.LOW)

    # ───────────────────────── setters ────────────────────────
    def set_pin1_value(self, value: bool): self._set_pin(self.pin1, value)
    def set_pin2_value(self, value: bool): self._set_pin(self.pin2, value)
    def set_pin3_value(self, value: bool): self._set_pin(self.pin3, value)
    def set_pin4_value(self, value: bool): self._set_pin(self.pin4, value)

    # ───────────────────────── getters ────────────────────────
    def get_motor_speed(self) -> int:
        """
        Analyse l’état des GPIO pour déduire la vitesse demandée.

        Retour : 0‑4  
        (0 = arrêt ou combinaisons invalides, 1‑4 = broche active LOW)
        """
        states = (
            GPIO.input(self.pin1) == GPIO.LOW,
            GPIO.input(self.pin2) == GPIO.LOW,
            GPIO.input(self.pin3) == GPIO.LOW,
            GPIO.input(self.pin4) == GPIO.LOW,
        )

        if sum(states) > 1:             # sécurité : plusieurs broches basses
            warning("Plusieurs broches moteur actives ! (état invalide)")
            return 0

        if   states[0]: return 1
        elif states[1]: return 2
        elif states[2]: return 3
        elif states[3]: return 4
        else:           return 0        # aucune broche active