# components/MotorHandler.py
# Author  : Progradius
# Licence : AGPL-3.0
"""
Pilotage bas niveau d'un moteur 4 vitesses sur CARTE RELAIS ACTIVE-HAUT.

Règle matérielle :
    - OFF / état sûr  → toutes les pins moteur à LOW
    - Vitesse N (1..4) → d'abord tout LOW, puis SEULEMENT la pin N à HIGH

Ça évite les courts-circuits si plusieurs relais sont fermés.

**Aucune régulation ici** : la décision de vitesse appartient à l'arbitre
thermique (`components/climate_policy.py`), qui la prend en même temps que celle
du chauffage. Ce module ne fait qu'appliquer une consigne.
"""

from time import sleep

import RPi.GPIO as GPIO

from model.Motor import Motor
from param.config import AppConfig
from utils.pretty_console import error, info

LOGGER_NAME = "motor"


class MotorHandler:
    """Encapsule les opérations bas niveau sur le moteur (active-HIGH)."""

    def __init__(self, config: AppConfig):
        self.config = config
        pins = [
            config.gpio.motor_pin1,
            config.gpio.motor_pin2,
            config.gpio.motor_pin3,
            config.gpio.motor_pin4,
        ]

        # sécurité : on force les 4 en LOW ici
        for p in pins:
            GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)

        self.motor = Motor(*pins)
        self.speed = 0  # dernière vitesse appliquée
        info(f"MotorHandler (active-HIGH) initialisé sur pins {pins}", name=LOGGER_NAME)

    # ──────────────────────────────────────────────────────────
    def all_off(self):
        """État sûr : toutes les sorties moteur à LOW."""
        self.motor.all_off()
        self.speed = 0

    # ──────────────────────────────────────────────────────────
    def set_motor_speed(self, speed: int) -> bool:
        """
        speed 0..4
        0 → tout LOW
        N → d'abord tout LOW, puis une seule pin HIGH

        Retourne True si la vitesse a réellement changé (le message INFO est
        laissé à l'appelant, qui connaît la raison du changement).
        """
        speed = max(0, min(speed, 4))

        # pas de changement → ne rien faire
        if speed == self.speed:
            return False

        # 1) état sûr
        self.all_off()
        # petit délai matériel
        sleep(0.05)

        # 2) activer la bonne pin si > 0
        if speed > 0:
            try:
                getattr(self.motor, f"set_pin{speed}_value")(True)  # True → HIGH → ON
            except AttributeError:
                error(f"Pin de vitesse {speed} inexistante ?", name=LOGGER_NAME)
                return False

        self.speed = speed
        return True
