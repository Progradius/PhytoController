# components/MotorHandler.py
# Author  : Progradius
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique (manuel / auto)
pour une CARTE RELAIS ACTIVE-HAUT.

Règle matérielle :
    - OFF / état sûr  → toutes les pins moteur à LOW
    - Vitesse N (1..4) → d'abord tout LOW, puis SEULEMENT la pin N à HIGH

Ça évite les courts-circuits si plusieurs relais sont fermés.
"""

import asyncio
from time import sleep

import RPi.GPIO as GPIO

from model.Motor import Motor
from param.config import AppConfig
from utils.pretty_console import info, warning, success, error


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
        info(f"MotorHandler (active-HIGH) initialisé sur pins {pins}")

    # ──────────────────────────────────────────────────────────
    def all_off(self):
        """État sûr : toutes les sorties moteur à LOW."""
        self.motor.all_off()
        self.speed = 0

    # ──────────────────────────────────────────────────────────
    def set_motor_speed(self, speed: int):
        """
        speed 0..4
        0 → tout LOW
        N → d’abord tout LOW, puis une seule pin HIGH
        """
        speed = max(0, min(speed, 4))

        # pas de changement → ne rien faire
        if speed == self.speed:
            return

        # 1) état sûr
        self.all_off()
        # petit délai matériel
        sleep(0.05)

        # 2) activer la bonne pin si > 0
        if speed == 0:
            warning("Vitesse moteur : 0 (tout OFF)")
        else:
            try:
                # nom de la méthode dans Motor : set_pin{n}_value(True/False)
                getattr(self.motor, f"set_pin{speed}_value")(True)  # True → HIGH → ON
                success(f"Vitesse moteur réglée : {speed}")
            except AttributeError:
                error(f"[MOTOR] pin de vitesse {speed} inexistante ?")

        self.speed = speed


# ─────────────────────────────────────────────────────────────
#  Contrôle température (version qui réutilise le SensorController du main)
# ─────────────────────────────────────────────────────────────
async def temp_control(
    motor_handler: MotorHandler,
    config: AppConfig,
    sensor_handler,
    sampling_time: int = 15,
):
    """
    • manual : vitesse imposée par l'utilisateur (config.motor.motor_user_speed)
    • auto   : vitesse décidée à partir de BME280 (day/night possible + hyst)
    On réutilise le sensor_handler existant → pas de 3e ouverture I2C,
    pas de double init, pas de doublons dans les logs.

    IMPORTANT : on fait un PREMIER CHECK avant le premier sleep.
    """

    async def _apply_once():
        mode = (config.motor.motor_mode or "").lower()

        if mode == "manual":
            s = config.motor.motor_user_speed
            info(f"[MOTOR] [MANUAL] Vitesse demandée : {s}")
            motor_handler.set_motor_speed(s)
            return

        if mode == "auto":
            raw = sensor_handler.get_sensor_value("BME280T")
            try:
                temp_val = float(raw)
            except (TypeError, ValueError):
                error(f"[MOTOR] Temp invalide pour le contrôle moteur : {raw}")
                motor_handler.set_motor_speed(0)
                return

            ts = config.temperature
            tmin = ts.target_temp_min_day
            tmax = ts.target_temp_max_day
            hyst = ts.hysteresis_offset

            if temp_val < tmin:
                wanted = 0
                info(f"[MOTOR] [AUTO] {temp_val:.1f}°C < {tmin}°C → OFF")
            elif temp_val <= tmax:
                wanted = 1
                info(f"[MOTOR] [AUTO] {temp_val:.1f}°C dans [{tmin},{tmax}] → speed 1")
            elif temp_val <= tmax + hyst:
                wanted = 2
                info(f"[MOTOR] [AUTO] {temp_val:.1f}°C ≤ {tmax+hyst:.1f} → speed 2")
            elif temp_val <= tmax + 2 * hyst:
                wanted = 3
                info(f"[MOTOR] [AUTO] {temp_val:.1f}°C ≤ {tmax+2*hyst:.1f} → speed 3")
            else:
                wanted = 4
                info(f"[MOTOR] [AUTO] {temp_val:.1f}°C > {tmax+2*hyst:.1f} → speed 4")

            motor_handler.set_motor_speed(wanted)
            return

        # mode inconnu
        warning(f"[MOTOR] Mode moteur inconnu : {mode!r} → OFF")
        motor_handler.set_motor_speed(0)

    # 1er passage IMMÉDIAT
    await _apply_once()

    # puis boucle régulière
    while True:
        await asyncio.sleep(sampling_time)
        await _apply_once()
