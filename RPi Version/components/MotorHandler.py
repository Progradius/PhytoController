# controller/components/MotorHandler.py
# Author  : Progradius (refacto)
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique (manuel / auto)
en fonction de la température mesurée via BME280, à partir d'une AppConfig.
"""

import asyncio
from time import sleep

import RPi.GPIO as GPIO

from model.Motor import Motor
from controllers.SensorController import SensorController
from param.config import AppConfig
from ui.pretty_console import info, warning, clock, error, success


class MotorHandler:
    """Encapsule les opérations bas niveau sur le moteur."""

    def __init__(self, config: AppConfig):
        self.config = config

        # Instancie le moteur avec les 4 broches tirées de la config
        pins = [
            config.gpio.motor_pin1,
            config.gpio.motor_pin2,
            config.gpio.motor_pin3,
            config.gpio.motor_pin4,
        ]
        # configure chaque broche en sortie et initialement HIGH (moteur coupé)
        for p in pins:
            GPIO.setup(p, GPIO.OUT, initial=GPIO.HIGH)

        self.motor = Motor(pin1=pins[0], pin2=pins[1], pin3=pins[2], pin4=pins[3])
        info(f"MotorHandler initialisé sur pins {pins}")

        # vitesse et mode initiaux depuis la config
        self.mode  = config.motor.motor_mode.lower()
        self.speed = config.motor.motor_user_speed
        info(f"Mode moteur initial : {self.mode}, vitesse : {self.speed}")

    # ──────────────────────────────────────────────────────────
    #  Helpers internes
    # ──────────────────────────────────────────────────────────
    def all_pin_down(self):
        """Met toutes les sorties GPIO à l'état HIGH (moteur coupé)."""
        for setter in (
            self.motor.set_pin1_value,
            self.motor.set_pin2_value,
            self.motor.set_pin3_value,
            self.motor.set_pin4_value
        ):
            setter(1)
        warning("Moteur sécurisé : toutes les broches à HIGH")

    # ---------------------------------------------------------
    def set_motor_speed(self, speed: int):
        """
        Positionne la vitesse (0 - 4) ; coupe d'abord le moteur 1 s
        pour éviter un court-circuit entre deux pas.
        """
        speed = max(0, min(speed, 4))  # clamp entre 0 et 4
        self.all_pin_down()
        sleep(1)

        if speed == 0:
            warning("Vitesse moteur : 0 (OFF)")
        elif speed == 1:
            self.motor.set_pin1_value(0)
        elif speed == 2:
            self.motor.set_pin2_value(0)
        elif speed == 3:
            self.motor.set_pin3_value(0)
        elif speed == 4:
            self.motor.set_pin4_value(0)

        if speed:
            success(f"Vitesse moteur réglée : {speed}")
        sleep(1)
        self.speed = speed

    # ---------------------------------------------------------
    def current_speed(self) -> int:
        """
        Renvoie la vitesse supposée à partir de l'état des broches.
        (0 = toutes HIGH, sinon index de la broche LOW)
        """
        states = (
            self.motor.get_pin1_state(),
            self.motor.get_pin2_state(),
            self.motor.get_pin3_state(),
            self.motor.get_pin4_state(),
        )
        try:
            return states.index(0) + 1
        except ValueError:
            return 0


async def temp_control(
    motor_handler: MotorHandler,
    config: AppConfig,
    sampling_time: int = 15
):
    """
    • manual : vitesse imposée par l'utilisateur (config.motor.motor_user_speed)
    • auto   : calcul de la vitesse selon la température BME280
    """
    sensor_handler = SensorController(config)

    while True:
        mode = config.motor.motor_mode.lower()

        if mode == "manual":
            speed = config.motor.motor_user_speed
            info(f"[MANUAL] Vitesse demandée : {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(60)

        elif mode == "auto":
            temp = sensor_handler.get_sensor_value("BME280T")
            try:
                temp_val = round(float(temp), 1)
            except (TypeError, ValueError):
                error(f"Valeur température invalide : {temp}")
                await asyncio.sleep(sampling_time)
                continue

            target    = config.motor.target_temp
            hyst      = config.motor.hysteresis
            min_sp    = max(0, min(4, config.motor.min_speed))
            max_sp    = max(0, min(4, config.motor.max_speed))

            # échelonnement 4 crans
            if temp_val < target:
                speed = min_sp
            elif temp_val < target + hyst:
                speed = min(min_sp + 1, max_sp)
            elif temp_val < target + 2 * hyst:
                speed = min(min_sp + 2, max_sp)
            else:
                speed = max_sp

            clock(f"[AUTO] {temp_val} °C → speed {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(sampling_time)

        else:
            warning(f"Mode moteur inconnu : '{mode}'")
            await asyncio.sleep(sampling_time)
