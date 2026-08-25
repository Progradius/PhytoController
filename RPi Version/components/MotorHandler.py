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
from utils.pretty_console import debug, info, warning, error
from utils.supervisor import beat, sleep as hb_sleep

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
    # Mode invalide déjà signalé (pour ne pas répéter le warning à chaque tick)
    unknown_mode_reported: str | None = None
    # Dernière config valide : si param.json est momentanément illisible (POST
    # /conf en cours, fichier tronqué…), on continue de réguler sur la
    # précédente plutôt que de laisser la JSONDecodeError tuer la tâche — un
    # moteur figé sur sa dernière vitesse ne serait plus jamais repiloté.
    last_cfg = config

    async def _apply_once():
        nonlocal refresh_window_start, refresh_minutes_done_this_hour
        nonlocal unknown_mode_reported, last_cfg
        beat()

        # recharge dynamique
        try:
            cfg = config.__class__.load()
        except Exception:
            # AppConfig.load() a déjà journalisé (dédupliqué) la cause.
            cfg = last_cfg
        else:
            last_cfg = cfg
        ms  = cfg.motor

        # clamp utilitaire
        def clamp_speed(x: int) -> int:
            lo, hi = max(0, ms.min_speed), min(4, ms.max_speed)
            return max(lo, min(hi, x))

        def apply(speed: int, reason: str) -> None:
            """Applique la vitesse : INFO seulement si elle change, DEBUG sinon."""
            if motor_handler.set_motor_speed(speed):
                info(f"Vitesse {speed} ← {reason}", name=LOGGER_NAME)
            else:
                debug(f"Vitesse maintenue à {speed} ({reason})", name=LOGGER_NAME)

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
        if mode in ("manual", "auto", "winter"):
            unknown_mode_reported = None

        if mode == "manual":
            apply(clamp_speed(ms.motor_user_speed), "consigne manuelle")
            return

        if mode == "auto":
            if T is None:
                apply(clamp_speed(1), "auto : température indisponible → repli")
                return

            tmin = cfg.temperature.target_temp_min_day if _is_day_from(cfg) else cfg.temperature.target_temp_min_night
            tmax = cfg.temperature.target_temp_max_day if _is_day_from(cfg) else cfg.temperature.target_temp_max_night
            hyst = cfg.temperature.hysteresis_offset

            if T < tmin:
                wanted, reason = 0, f"auto : {T:.1f}°C < {tmin}°C"
            elif T <= tmax:
                wanted, reason = 1, f"auto : {T:.1f}°C dans [{tmin},{tmax}]"
            elif T <= tmax + hyst:
                wanted, reason = 2, f"auto : {T:.1f}°C ≤ {tmax+hyst:.1f}°C"
            elif T <= tmax + 2 * hyst:
                wanted, reason = 3, f"auto : {T:.1f}°C ≤ {tmax+2*hyst:.1f}°C"
            else:
                wanted, reason = 4, f"auto : {T:.1f}°C > {tmax+2*hyst:.1f}°C"

            apply(clamp_speed(wanted), reason)
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
                apply(desired, f"hiver : sécurité haute T ({T:.1f}°C)")

            elif too_cold:
                # on ferme, sauf si humidité haute ou quota pas atteint
                if humidity_high or refresh_minutes_done_this_hour < refresh_quota:
                    refresh_minutes_done_this_hour += add_minutes
                    apply(refresh_speed,
                          f"hiver : froid + renouvellement ({T:.1f}°C, "
                          f"RH={RH if RH is not None else 0:.1f}%, quota "
                          f"{refresh_minutes_done_this_hour:.1f}/{refresh_quota} min)")
                else:
                    apply(default_speed, "hiver : froid, quota de renouvellement atteint")

            else:
                # T ok → humidité prioritaire, sinon renouvellement régulier, sinon vitesse par défaut
                if humidity_high:
                    refresh_minutes_done_this_hour += add_minutes
                    apply(refresh_speed,
                          f"hiver : humidité {RH:.1f}% ≥ {humidity_thr:.1f}% (quota "
                          f"{refresh_minutes_done_this_hour:.1f}/{refresh_quota} min)")
                else:
                    if refresh_minutes_done_this_hour < refresh_quota:
                        refresh_minutes_done_this_hour += add_minutes
                        apply(refresh_speed,
                              f"hiver : renouvellement régulier (quota "
                              f"{refresh_minutes_done_this_hour:.1f}/{refresh_quota} min)")
                    else:
                        apply(default_speed, "hiver : vitesse par défaut")

            return

        # mode inconnu → une seule alerte tant que la conf ne change pas
        if unknown_mode_reported != mode:
            unknown_mode_reported = mode
            warning(f"Mode moteur inconnu : {mode!r} → arrêt", name=LOGGER_NAME)
        apply(0, "mode inconnu")

    # 1er passage IMMÉDIAT
    await _apply_once()

    # puis boucle régulière
    while True:
        await hb_sleep(sampling_time)
        await _apply_once()
