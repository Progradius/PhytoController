# controller/components/MotorHandler.py
# Author  : Progradius (adapted)
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique
(en fonction de la température mesurée via BME280).
"""

import asyncio
from time import sleep

from model.Motor                 import Motor
from controller.SensorHandler     import SensorHandler
from controller.ui import pretty_console as ui


class MotorHandler:
    """Encapsule les opérations bas niveau sur le moteur."""

    def __init__(self, parameters):
        self.parameters = parameters
        self.motor = Motor(
            pin1=parameters.get_motor_pin1(),
            pin2=parameters.get_motor_pin2(),
            pin3=parameters.get_motor_pin3(),
            pin4=parameters.get_motor_pin4()
        )
        self.all_pin_down()

    # ──────────────────────────────────────────────────────────
    #  Helpers internes
    # ──────────────────────────────────────────────────────────
    def all_pin_down(self):
        """Met toutes les sorties GPIO à l'état *HIGH* (moteur coupé)."""
        for fn in (self.motor.set_pin1_value,
                   self.motor.set_pin2_value,
                   self.motor.set_pin3_value,
                   self.motor.set_pin4_value):
            fn(1)
        ui.action("Moteur sécurisé : toutes les broches à HIGH")

    # ---------------------------------------------------------
    def set_motor_speed(self, speed: int):
        """
        Positionne la vitesse (0 - 4) ; coupe d'abord le moteur 1 s
        pour éviter un court-circuit entre deux pas.
        """
        speed = max(0, min(speed, 4))          # clamp
        self.all_pin_down()
        sleep(1)

        # Activation sélective d'une broche
        if   speed == 0:
            ui.warning("Vitesse moteur : 0 (OFF)")
        elif speed == 1:
            self.motor.set_pin1_value(0)
        elif speed == 2:
            self.motor.set_pin2_value(0)
        elif speed == 3:
            self.motor.set_pin3_value(0)
        elif speed == 4:
            self.motor.set_pin4_value(0)

        if speed:
            ui.success(f"Vitesse moteur réglée : {speed}")
        sleep(1)

    # ---------------------------------------------------------
    #  Lecture courante (facultatif)
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


# ───────────────────────────────────────────────────────────────
#  Régulation automatique asynchrone
# ───────────────────────────────────────────────────────────────
async def temp_control(motor_handler: MotorHandler,
                       parameters,
                       sampling_time: int = 15):
    """
    • *manual* : vitesse imposée par l'utilisateur (paramètres)
    • *auto* : calcul de la vitesse selon la température BME280
    """
    sensor_handler = SensorHandler(parameters=parameters)

    while True:
        mode = parameters.get_motor_mode().lower()

        # ─────── MODE MANUEL ─────────────────────────────────
        if mode == "manual":
            speed = parameters.get_motor_user_speed()
            ui.info(f"[MANUAL] Vitesse demandée : {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(60)

        # ─────── MODE AUTO  ─────────────────────────────────
        elif mode == "auto":
            temp = sensor_handler.get_sensor_value("BME280T")

            # convert & validation
            try:
                temp_val = round(float(temp), 1)
            except (TypeError, ValueError):
                ui.error(f"Valeur température invalide : {temp}")
                await asyncio.sleep(sampling_time)
                continue

            target      = parameters.get_target_temp()
            hyst        = parameters.get_hysteresis()
            min_speed   = max(0, min(4, parameters.get_motor_min_speed()))
            max_speed   = max(0, min(4, parameters.get_motor_max_speed()))

            # simple échelonnage à 4 crans
            if temp_val < target:
                speed = min_speed
            elif temp_val < target + hyst:
                speed = min(min_speed + 1, max_speed)
            elif temp_val < target + 2 * hyst:
                speed = min(min_speed + 2, max_speed)
            elif temp_val < target + 3 * hyst:
                speed = max_speed
            else:
                speed = max_speed

            ui.clock(f"[AUTO] {temp_val} °C  →  speed {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(sampling_time)

        # ─────── MODE INCONNU ───────────────────────────────
        else:
            ui.warning(f"Mode moteur inconnu : « {mode} »")
            await asyncio.sleep(sampling_time)
