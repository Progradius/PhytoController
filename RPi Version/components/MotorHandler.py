# components/MotorHandler.py
# Author  : Progradius
# Licence : AGPL-3.0
"""
Pilotage d'un moteur 4 pas + régulation automatique (manuel / auto / winter)
pour une CARTE RELAIS ACTIVE-HAUT.

Règle matérielle :
    - OFF / état sûr  → toutes les pins moteur à LOW
    - Vitesse N (1..4) → d'abord tout LOW, puis SEULEMENT la pin N à HIGH

Ça évite les courts-circuits si plusieurs relais sont fermés.
"""

import asyncio
from time import sleep
from datetime import datetime, timedelta

import RPi.GPIO as GPIO

from model.Motor import Motor
from param.config import AppConfig
from utils.pretty_console import info, warning, success, error, action


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
        N → d'abord tout LOW, puis une seule pin HIGH
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
                getattr(self.motor, f"set_pin{speed}_value")(True)  # True → HIGH → ON
                success(f"Vitesse moteur réglée : {speed}")
            except AttributeError:
                error(f"[MOTOR] pin de vitesse {speed} inexistante ?")

        self.speed = speed


# ─────────────────────────────────────────────────────────────
#  Contrôle moteur (manual / auto / winter)
# ─────────────────────────────────────────────────────────────
async def temp_control(
    motor_handler: MotorHandler,
    config: AppConfig,
    sensor_handler,
    sampling_time: int = 15,
):
    """
    • manual : vitesse imposée par l'utilisateur (config.motor.motor_user_speed)
    • auto   : vitesse décidée à partir de BME280 (hystérésis)
    • winter : limite les entrées d’air + renouvellement régulier + gestion humidité

    IMPORTANT :
    - On recharge la config à chaque boucle (prise en compte à chaud).
    - On comptabilise un quota de minutes de ventilation par heure en mode winter.
    """

    def _is_day_from(cfg: AppConfig) -> bool:
        now = datetime.now()
        start = cfg.daily_timer1.start_hour * 60 + cfg.daily_timer1.start_minute
        stop  = cfg.daily_timer1.stop_hour  * 60 + cfg.daily_timer1.stop_minute
        now_m = now.hour * 60 + now.minute
        return (start <= now_m <= stop) if start <= stop else (now_m >= start or now_m <= stop)

    # État interne du quota « minutes par heure » pour winter
    refresh_window_start: datetime | None = None
    refresh_minutes_done_this_hour: float = 0.0

    async def _apply_once():
        nonlocal refresh_window_start, refresh_minutes_done_this_hour

        # recharge dynamique
        cfg = config.__class__.load()
        ms  = cfg.motor

        # clamp utilitaire
        def clamp_speed(x: int) -> int:
            lo, hi = max(0, ms.min_speed), min(4, ms.max_speed)
            return max(lo, min(hi, x))

        # lecture capteurs
        T  = sensor_handler.get_sensor_value("BME280T")
        RH = sensor_handler.get_sensor_value("BME280H")

        # fallback capteurs
        try:
            T = float(T)
        except (TypeError, ValueError):
            T = None
        try:
            RH = float(RH)
        except (TypeError, ValueError):
            RH = None

        mode = (ms.motor_mode or "").lower()

        if mode == "manual":
            s = clamp_speed(ms.motor_user_speed)
            action(f"[MOTOR][MANUAL] Vitesse demandée : {s}")
            motor_handler.set_motor_speed(s)
            return

        if mode == "auto":
            if T is None:
                warning("[MOTOR][AUTO] Temp indisponible → fallback 1")
                motor_handler.set_motor_speed(clamp_speed(1))
                return

            tmin = cfg.temperature.target_temp_min_day if _is_day_from(cfg) else cfg.temperature.target_temp_min_night
            tmax = cfg.temperature.target_temp_max_day if _is_day_from(cfg) else cfg.temperature.target_temp_max_night
            hyst = cfg.temperature.hysteresis_offset

            if T < tmin:
                wanted = 0
                info(f"[MOTOR][AUTO] {T:.1f}°C < {tmin}°C → OFF")
            elif T <= tmax:
                wanted = 1
                info(f"[MOTOR][AUTO] {T:.1f}°C dans [{tmin},{tmax}] → speed 1")
            elif T <= tmax + hyst:
                wanted = 2
                info(f"[MOTOR][AUTO] {T:.1f}°C ≤ {tmax+hyst:.1f} → speed 2")
            elif T <= tmax + 2 * hyst:
                wanted = 3
                info(f"[MOTOR][AUTO] {T:.1f}°C ≤ {tmax+2*hyst:.1f} → speed 3")
            else:
                wanted = 4
                info(f"[MOTOR][AUTO] {T:.1f}°C > {tmax+2*hyst:.1f} → speed 4")

            motor_handler.set_motor_speed(clamp_speed(wanted))
            return

        if mode == "winter":
            # Fenêtre « heure civile »
            now = datetime.now()
            if refresh_window_start is None or now - refresh_window_start >= timedelta(hours=1):
                refresh_window_start = datetime(now.year, now.month, now.day, now.hour, 0, 0)
                refresh_minutes_done_this_hour = 0.0

            add_minutes = sampling_time / 60.0

            # bornes hiver
            is_day = _is_day_from(cfg)
            tmin = cfg.temperature.target_temp_min_day if is_day else cfg.temperature.target_temp_min_night
            tmax = cfg.temperature.target_temp_max_day if is_day else cfg.temperature.target_temp_max_night
            hyst = cfg.temperature.hysteresis_offset

            temp_margin = ms.winter_temp_margin
            default_speed = clamp_speed(ms.winter_default_speed)
            refresh_speed = clamp_speed(ms.winter_refresh_speed)
            refresh_quota = float(ms.winter_refresh_minutes_per_hour)
            humidity_thr  = float(ms.winter_humidity_threshold)

            too_hot  = (T is not None and T > (tmax + hyst))
            too_cold = (T is not None and T < (tmin - temp_margin))
            humidity_high = (RH is not None and RH >= humidity_thr)

            # Priorités
            if too_hot:
                # sécurité : ventiler fort
                desired = clamp_speed(max(3, ms.min_speed))
                action(f"[MOTOR][WINTER] Sécurité haute T (T={T:.1f}°C) → speed {desired}")
                motor_handler.set_motor_speed(desired)

            elif too_cold:
                # on ferme, sauf si humidité haute ou quota pas atteint
                if humidity_high or refresh_minutes_done_this_hour < refresh_quota:
                    desired = refresh_speed
                    motor_handler.set_motor_speed(desired)
                    refresh_minutes_done_this_hour += add_minutes
                    action(f"[MOTOR][WINTER] Froid + renouvellement (T={T:.1f}°C, RH={RH if RH is not None else 0:.1f}%) "
                           f"→ speed {desired} | quota {refresh_minutes_done_this_hour:.1f}/{refresh_quota} min")
                else:
                    desired = 0
                    motor_handler.set_motor_speed(desired)
                    action(f"[MOTOR][WINTER] Froid, quota atteint → speed 0")

            else:
                # T ok → humidité prioritaire, sinon renouvellement régulier, sinon vitesse par défaut
                if humidity_high:
                    desired = refresh_speed
                    motor_handler.set_motor_speed(desired)
                    refresh_minutes_done_this_hour += add_minutes
                    action(f"[MOTOR][WINTER] Humidité {RH:.1f}% ≥ {humidity_thr:.1f}% → speed {desired} "
                           f"(quota {refresh_minutes_done_this_hour:.1f}/{refresh_quota} min)")
                else:
                    if refresh_minutes_done_this_hour < refresh_quota:
                        desired = refresh_speed
                        motor_handler.set_motor_speed(desired)
                        refresh_minutes_done_this_hour += add_minutes
                        action(f"[MOTOR][WINTER] Renouvellement régulier → speed {desired} "
                               f"(quota {refresh_minutes_done_this_hour:.1f}/{refresh_quota} min)")
                    else:
                        desired = default_speed
                        motor_handler.set_motor_speed(desired)
                        action(f"[MOTOR][WINTER] Par défaut → speed {desired}")

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
