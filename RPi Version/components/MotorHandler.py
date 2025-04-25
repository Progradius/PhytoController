# controller/components/MotorHandler.py
# Author  : Progradius (refacto)
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique (manuel / auto)
en fonction de la température mesurée via BME280 et des Temperature_Settings,
en déduisant jour/nuit depuis DailyTimer1.
"""

import asyncio
from time import sleep
from datetime import datetime

import RPi.GPIO as GPIO

from function import convert_time_to_minutes
from model.Motor import Motor
from controllers.SensorController import SensorController
from param.config import AppConfig
from ui.pretty_console import info, warning, clock, error, success


class MotorHandler:
    """Encapsule les opérations bas niveau sur le moteur."""
    def __init__(self, config: AppConfig):
        self.config = config
        pins = [
            config.gpio.motor_pin1,
            config.gpio.motor_pin2,
            config.gpio.motor_pin3,
            config.gpio.motor_pin4,
        ]
        for p in pins:
            GPIO.setup(p, GPIO.OUT, initial=GPIO.HIGH)
        self.motor = Motor(*pins)
        info(f"MotorHandler initialisé sur pins {pins}")

        # vitesse et mode initiaux depuis la config
        self.mode  = config.motor.motor_mode.lower()
        self.speed = config.motor.motor_user_speed
        info(f"Mode moteur initial : {self.mode}, vitesse : {self.speed}")

    def all_pin_down(self):
        for setter in (
            self.motor.set_pin1_value,
            self.motor.set_pin2_value,
            self.motor.set_pin3_value,
            self.motor.set_pin4_value
        ):
            setter(True)
        warning("Moteur sécurisé : toutes les broches à HIGH")

    def set_motor_speed(self, speed: int):
        speed = max(0, min(speed, 4))
        self.all_pin_down()
        sleep(1)
        if speed == 0:
            warning("Vitesse moteur : 0 (OFF)")
        else:
            # active la broche correspondante en LOW (=False)
            getattr(self.motor, f"set_pin{speed}_value")(False)
            success(f"Vitesse moteur réglée : {speed}")
        sleep(1)
        self.speed = speed

    def current_speed(self) -> int:
        return self.motor.get_motor_speed()


async def temp_control(
    motor_handler: MotorHandler,
    config: AppConfig,
    sampling_time: int = 15
):
    """
    • manual : vitesse imposée par l'utilisateur (config.motor.motor_user_speed)
    • auto   : calcul de la vitesse selon la Temperature_Settings,
               avec hystérésis et distinction jour/nuit via DailyTimer1.
    """
    sensor_handler = SensorController(config)

    while True:
        mode = config.motor.motor_mode.lower()

        # ─── MODE MANUEL ─────────────────────────────────────────
        if mode == "manual":
            speed = config.motor.motor_user_speed
            info(f"[MANUAL] Vitesse demandée : {speed}")
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(60)

        # ─── MODE AUTOMATIQUE ────────────────────────────────────
        elif mode == "auto":
            raw = sensor_handler.get_sensor_value("BME280T")
            try:
                temp_val = float(raw)
            except (TypeError, ValueError):
                error(f"Valeur température invalide : {raw}")
                await asyncio.sleep(sampling_time)
                continue

            # 1) jour/nuit via DailyTimer1
            dt1 = config.daily_timer1
            start = convert_time_to_minutes(dt1.start_hour, dt1.start_minute)
            stop  = convert_time_to_minutes(dt1.stop_hour,  dt1.stop_minute)
            now_m = convert_time_to_minutes(datetime.now().hour, datetime.now().minute)
            is_day = (start <= now_m <= stop) if start <= stop else (now_m >= start or now_m <= stop)

            # 2) sélection des bornes
            ts = config.temperature_settings
            if is_day:
                tmin = ts.target_temp_min_day
                tmax = ts.target_temp_max_day
            else:
                tmin = ts.target_temp_min_night
                tmax = ts.target_temp_max_night
            hyst = ts.hysteresis_offset

            # 3) calcul de la vitesse désirée (0–4)
            span = tmax - tmin
            if span <= 0:
                desired = 0
            else:
                ratio = (temp_val - tmin) / span
                desired = round(ratio * 4)
                desired = max(0, min(4, desired))

            # 4) hystérésis simple : on change *vraiment* que si
            #    on sort de la bande [borne-hyst ; borne+hyst]
            #    où 'borne' = tmin + desired*(span/4)
            if span > 0 and desired != motor_handler.speed:
                threshold = tmin + (desired / 4) * span
                if abs(temp_val - threshold) >= hyst:
                    speed = desired
                else:
                    speed = motor_handler.speed
                clock(f"[AUTO] {temp_val:.1f}°C → désiré {desired}, appliqué {speed}")
            else:
                speed = desired
                clock(f"[AUTO] {temp_val:.1f}°C → speed {speed}")

            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(sampling_time)

        # ─── MODE INCONNU ────────────────────────────────────────
        else:
            warning(f"Mode moteur inconnu : '{mode}'")
            await asyncio.sleep(sampling_time)
