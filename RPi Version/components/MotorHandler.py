# controller/components/MotorHandler.py
# Author  : Progradius (refacto)
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique (manuel / auto)
en fonction de la température mesurée via BME280 et des Temperature_Settings,
en déduisant jour/nuit depuis DailyTimer1.

Auto‐mode granulaire :
 • temp < tmin → ventil 15 min/h (speed=1 les 15 premières minutes, sinon 0)
 • tmin ≤ temp ≤ tmax → low vitesse de base (1)
 • tmax < temp ≤ tmax+hyst → speed=2
 • tmax+hyst < temp ≤ tmax+2·hyst → speed=3
 • temp > tmax+2·hyst → speed=4
Aucun saut de plus d’un cran d’un cycle à l’autre.
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
            try:
                setter(True)
            except Exception as e:
                warning(f"Erreur lors de la mise à HIGH : {e}")

    def set_motor_speed(self, speed: int):
        """
        Positionne la vitesse (0 - 4) ; coupe d'abord le moteur 1 s
        pour éviter un court-circuit entre deux pas.
        """
        speed = max(0, min(speed, 4))
        self.all_pin_down()
        sleep(1)
        if speed == 0:
            warning("Vitesse moteur : 0 (OFF)")
        else:
            getattr(self.motor, f"set_pin{speed}_value")(False)
            success(f"Vitesse moteur réglée : {speed}")
        sleep(1)
        self.speed = speed

    def current_speed(self) -> int:
        """Renvoie la vitesse actuelle (0-4) d'après l'état des broches."""
        return self.motor.get_motor_speed()


async def temp_control(
    motor_handler: MotorHandler,
    config: AppConfig,
    sampling_time: int = 15
):
    """
    • manual : vitesse imposée par l'utilisateur (config.motor.motor_user_speed)
    • auto   : vitesse granulaire selon Temperature_Settings et horaire jour/nuit.
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
            continue

        # ─── MODE AUTOMATIQUE ────────────────────────────────────
        if mode == "auto":
            raw = sensor_handler.get_sensor_value("BME280T")
            try:
                temp_val = float(raw)
            except (TypeError, ValueError):
                error(f"Valeur température invalide : {raw}")
                await asyncio.sleep(sampling_time)
                continue

            # 1) Déterminer jour/nuit via DailyTimer1
            dt1   = config.daily_timer1
            start = convert_time_to_minutes(dt1.start_hour, dt1.start_minute)
            stop  = convert_time_to_minutes(dt1.stop_hour,  dt1.stop_minute)
            now_m = convert_time_to_minutes(datetime.now().hour, datetime.now().minute)
            is_day = (start <= now_m <= stop) if start <= stop else (now_m >= start or now_m <= stop)

            # 2) Choix des bornes selon jour/nuit
            ts = config.temperature_settings
            if is_day:
                tmin = ts.target_temp_min_day
                tmax = ts.target_temp_max_day
            else:
                tmin = ts.target_temp_min_night
                tmax = ts.target_temp_max_night
            hyst = ts.hysteresis_offset

            # 3) Calcul de la vitesse désirée (0–4) par paliers
            if temp_val < tmin:
                # ventilation périodique 15 min/h
                minute = datetime.now().minute
                speed = 1 if (minute % 60) < 15 else 0
                clock(f"[AUTO] {temp_val:.1f}°C < {tmin} → ventilation, speed {speed}")
            elif temp_val <= tmax:
                speed = 1
                clock(f"[AUTO] {temp_val:.1f}°C dans [{tmin},{tmax}] → speed 1")
            elif temp_val <= tmax + hyst:
                speed = 2
                clock(f"[AUTO] {temp_val:.1f}°C ≤ {tmax+hyst:.1f} → speed 2")
            elif temp_val <= tmax + 2*hyst:
                speed = 3
                clock(f"[AUTO] {temp_val:.1f}°C ≤ {tmax+2*hyst:.1f} → speed 3")
            else:
                speed = 4
                clock(f"[AUTO] {temp_val:.1f}°C > {tmax+2*hyst:.1f} → speed 4")

            # 4) Empêcher les sauts de plus d'un cran
            prev = motor_handler.speed
            delta = speed - prev
            if abs(delta) > 1:
                speed = prev + (1 if delta > 0 else -1)
                clock(f"[AUTO] Limitation saut → nouveau speed {speed}")

            # Appliquer
            motor_handler.set_motor_speed(speed)
            await asyncio.sleep(sampling_time)
            continue

        # ─── MODE INCONNU ────────────────────────────────────────
        warning(f"Mode moteur inconnu : '{mode}'")
        await asyncio.sleep(sampling_time)
