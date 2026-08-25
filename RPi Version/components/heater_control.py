# controller/components/heater_control.py
from __future__ import annotations

from datetime import datetime
from time import monotonic

from utils.pretty_console import debug, error, info, warning
from utils.log_dedup import StateLogger
from utils.supervisor import beat, sleep as hb_sleep

LOGGER_NAME = "heater"

# ─────────────────────────────────────────────────────────────
#  Garde-fous de sécurité (audit C10)
# ─────────────────────────────────────────────────────────────
# Plage physiquement plausible sous serre : hors de ces bornes, la valeur vient
# d'un bus perturbé, pas d'une vraie mesure. On la traite comme une lecture
# manquée plutôt que de réguler dessus.
TEMP_VALID_MIN = -20.0
TEMP_VALID_MAX = 60.0

# Nombre de lectures invalides consécutives tolérées avant de couper. À
# `sampling_time=60 s`, cela laisse 5 minutes au capteur pour se rétablir.
MAX_CONSECUTIVE_SENSOR_FAILURES = 5

# Durée maximale d'allumage continu, **indépendante du capteur** : même avec
# une température parfaitement valide mais bloquée sur une valeur basse
# (défaut classique du BME280 sur bus perturbé), le chauffage ne peut pas
# rester ON indéfiniment.
MAX_CONTINUOUS_ON_MINUTES = 120
# Repos imposé après une coupure sur durée max, sinon la condition
# `temp <= temp_min` rallumerait au tick suivant.
FORCED_OFF_COOLDOWN_MINUTES = 15

# Alarme persistante, lisible depuis l'extérieur (destinée à /status).
_alarm: str | None = None


def get_heater_alarm():
    """Motif de l'alarme chauffage en cours, ou None."""
    return _alarm


def _set_alarm(reason: str) -> None:
    global _alarm
    if _alarm != reason:
        _alarm = reason
        error(f"ALARME chauffage : {reason}", name=LOGGER_NAME)


def _clear_alarm() -> None:
    global _alarm
    if _alarm is not None:
        info(f"Alarme chauffage levée ({_alarm})", name=LOGGER_NAME)
        _alarm = None


async def heat_control(
    *,
    heater_component,
    sensor_handler,
    config,             # AppConfig
    sampling_time: int = 60
):
    """
    Pilote le chauffage avec hystérésis stricte :
      • Chauffage forcé OFF si désactivé manuellement
      • Sinon :
          - Allume si T ≤ temp_min
          - Éteint si T > temp_min + hysteresis
          - Sinon conserve l'état précédent

    Garde-fous (audit C10) :
      • une température hors plage plausible compte comme une lecture manquée ;
      • après MAX_CONSECUTIVE_SENSOR_FAILURES lectures manquées, le chauffage
        est coupé et une alarme persistante est levée — sans capteur, on ne
        peut plus garantir qu'on ne chauffe pas à l'infini ;
      • un allumage ne peut pas dépasser MAX_CONTINUOUS_ON_MINUTES, suivi d'un
        repos de FORCED_OFF_COOLDOWN_MINUTES.
    """
    current_state = heater_component.get_state()  # récupération initiale
    temp_state = StateLogger("Lecture de la température ambiante (chauffage)",
                             name=LOGGER_NAME, level="warning")

    # `monotonic()` et non `datetime.now()` : ces durées ne doivent pas sauter
    # avec une resynchronisation NTP ou un changement d'heure.
    sensor_failures = 0
    on_since = monotonic() if current_state else None
    cooldown_until = None

    def _switch(state: int, message: str) -> None:
        nonlocal current_state, on_since
        heater_component.set_state(state)
        current_state = state
        on_since = monotonic() if state else None
        info(message, name=LOGGER_NAME)

    while True:
        beat()
        if not config.heater_settings.enabled:
            if current_state != 0:
                _switch(0, "Chauffage désactivé manuellement → OFF")
            sensor_failures = 0
            _clear_alarm()
            await hb_sleep(sampling_time)
            continue

        now_mono = monotonic()

        # ── Garde-fou 1 : durée maximale d'allumage continu ──────────────
        if current_state == 1 and on_since is not None \
                and now_mono - on_since >= MAX_CONTINUOUS_ON_MINUTES * 60:
            _switch(0, f"Chauffage → OFF (durée max de {MAX_CONTINUOUS_ON_MINUTES} min atteinte)")
            cooldown_until = now_mono + FORCED_OFF_COOLDOWN_MINUTES * 60
            _set_alarm(
                f"allumage continu de {MAX_CONTINUOUS_ON_MINUTES} min atteint → "
                f"repos forcé de {FORCED_OFF_COOLDOWN_MINUTES} min "
                "(capteur bloqué ? puissance de chauffe insuffisante ?)"
            )
            await hb_sleep(sampling_time)
            continue

        in_cooldown = cooldown_until is not None and now_mono < cooldown_until
        if cooldown_until is not None and not in_cooldown:
            cooldown_until = None
            _clear_alarm()

        # Détermination jour/nuit
        now_m = datetime.now().hour * 60 + datetime.now().minute
        start = config.daily_timer1.start_hour * 60 + config.daily_timer1.start_minute
        stop  = config.daily_timer1.stop_hour  * 60 + config.daily_timer1.stop_minute
        is_day = start <= now_m <= stop if start <= stop else now_m >= start or now_m <= stop

        # Plage de consigne
        temp_min = config.temperature.target_temp_min_day if is_day else config.temperature.target_temp_min_night
        hysteresis = config.temperature.hysteresis_offset

        # Lecture température
        temp = await sensor_handler.fresh_value("BME280T", max_age=20.0)

        # ── Garde-fou 2 : validation de plage ────────────────────────────
        if temp is not None and not (TEMP_VALID_MIN < temp < TEMP_VALID_MAX):
            warning(
                f"Température aberrante ({temp:.1f}°C hors ]{TEMP_VALID_MIN} ; "
                f"{TEMP_VALID_MAX}[) → traitée comme lecture manquée",
                name=LOGGER_NAME,
            )
            temp = None

        if temp is None:
            temp_state.fail()
            sensor_failures += 1

            # ── Garde-fou 3 : repli sur perte durable du capteur ─────────
            if sensor_failures >= MAX_CONSECUTIVE_SENSOR_FAILURES:
                if current_state != 0:
                    _switch(0, f"Chauffage → OFF (repli : {sensor_failures} lectures manquées)")
                # Motif volontairement figé (pas de compteur) : `_set_alarm` ne
                # doit journaliser qu'à l'entrée en panne, pas à chaque tick.
                _set_alarm(
                    "température ambiante illisible → chauffage coupé, "
                    "régulation impossible"
                )
            else:
                debug(
                    f"Lecture manquée {sensor_failures}/{MAX_CONSECUTIVE_SENSOR_FAILURES} "
                    f"→ état conservé ({'ON' if current_state else 'OFF'})",
                    name=LOGGER_NAME,
                )
        else:
            temp_state.ok()
            if sensor_failures:
                sensor_failures = 0
                _clear_alarm()

            seuil_off = temp_min + hysteresis
            debug(f"T={temp:.1f}°C, min={temp_min:.1f}, seuil OFF={seuil_off:.1f}",
                  name=LOGGER_NAME)

            if temp <= temp_min and current_state == 0 and not in_cooldown:
                _switch(1, f"Chauffage → ON (T={temp:.1f}°C ≤ {temp_min:.1f}°C)")

            elif temp > seuil_off and current_state == 1:
                _switch(0, f"Chauffage → OFF (T={temp:.1f}°C > {seuil_off:.1f}°C)")

            elif in_cooldown:
                debug("Repos forcé en cours → allumage inhibé", name=LOGGER_NAME)

            else:
                debug(f"État conservé : {'ON' if current_state else 'OFF'}", name=LOGGER_NAME)

        await hb_sleep(sampling_time)
