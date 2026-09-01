# components/climate_control.py
# Author  : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Arbitre thermique — application de la décision (audit C9)
# -------------------------------------------------------------
"""
Coroutine unique de régulation thermique. Elle remplace les deux boucles
indépendantes `temp_control` (moteur) et `heat_control` (chauffage), qui
lisaient la même température sans se connaître et se contredisaient.

Le déroulé d'un tick est volontairement plat :

  1. demander la configuration au magasin partagé (repli intégré) ;
  2. lire T/RH **une seule fois** ;
  3. resynchroniser la mémoire sur l'état **réel** des sorties (audit E8) ;
  4. appeler `climate_policy.decide()` — toute la logique est là, et elle est
     pure ;
  5. appliquer la décision aux deux organes, vérifier que l'écriture a pris ;
  6. persister les budgets hiver (audit E10).

Rien d'autre : pas de décision prise ici, pas de seuil calculé ici. Une règle de
régulation qui ne se trouverait pas dans `climate_policy` serait invisible aux
relectures et aux rejeux.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from time import monotonic, time

from components import climate_policy
from components.climate_policy import (
    ClimateInputs,
    ClimateMemory,
    decide,
    settings_from_config,
)
from utils.log_dedup import StateLogger
from utils.pretty_console import critical, debug, error, info, warning
from param.config_store import shared_config
from utils.overrides import shared_overrides
from utils.state_store import shared_store
from utils.supervisor import beat, sleep as hb_sleep
from utils.operational_state import publish
from utils.schedule import is_day as scheduled_day
from utils.time_reliability import time_reliability

LOGGER_NAME = "climate"

STATE_SECTION = "climate"

# Alarme persistante, lisible depuis l'extérieur (destinée à /status et à l'IHM).
_alarm: str | None = None
_alarm_code: str | None = None
# Dernier instantané publié — l'API le sert sans jamais déclencher de lecture.
_snapshot: dict = {
    "state": None,
    "reason": None,
    "heater_on": False,
    "motor_speed": 0,
    "temperature": None,
    "humidity": None,
    "temp_min": None,
    "temp_max": None,
    "alarm": None,
    "alarm_code": None,
    "vent_threshold": None,
    "heater_off_threshold": None,
    "renew_minutes_used": 0.0,
    "renew_minutes_quota": 0.0,
    "humidity_minutes_used": 0.0,
    "humidity_minutes_quota": 0.0,
    "updated_at": None,
}


def get_climate_alarm() -> str | None:
    """Motif de l'alarme thermique en cours, ou None."""
    return _alarm


def get_climate_alarm_status() -> dict:
    """Forme structurée pour le centre d'alarmes, sans casser l'alias legacy."""
    return {"code": _alarm_code, "message": _alarm}


# L'API publique et le runbook parlent d'« alarme chauffage » depuis la Phase 0 :
# on garde le nom historique en alias plutôt que de casser des scripts d'exploitation.
get_heater_alarm = get_climate_alarm


def get_climate_snapshot() -> dict:
    """Copie du dernier état publié par l'arbitre."""
    return dict(_snapshot)


def _set_alarm(code: str, reason: str) -> None:
    global _alarm, _alarm_code
    if _alarm != reason or _alarm_code != code:
        _alarm = reason
        _alarm_code = code
        error(f"ALARME thermique : {reason}", name=LOGGER_NAME)


def _clear_alarm() -> None:
    global _alarm, _alarm_code
    if _alarm is not None:
        info(f"Alarme thermique levée ({_alarm})", name=LOGGER_NAME)
        _alarm = None
        _alarm_code = None


# ─────────────────────────────────────────────────────────────
#  Persistance des budgets
# ─────────────────────────────────────────────────────────────
def _restore_memory(store) -> ClimateMemory:
    """
    Reprend les budgets hiver là où le processus précédent les avait laissés.
    Sans cela, chaque redémarrage réaccorde une fenêtre complète de
    renouvellement — le défaut E10.

    `motor_speed_since` est volontairement laissé à sa valeur par défaut (0) :
    le temps de maintien ne doit pas retarder la **première** décision d'une
    tâche qui redémarre, sinon une relance du superviseur suspendrait la
    ventilation pendant deux minutes.
    """
    saved = store.load(STATE_SECTION)
    try:
        window = saved.get("quota_window_start")
        memory = ClimateMemory(
            quota_window_start=float(window) if window is not None else None,
            renew_minutes_used=float(saved.get("renew_minutes_used", 0.0)),
            humidity_minutes_used=float(saved.get("humidity_minutes_used", 0.0)),
        )
    except (TypeError, ValueError):
        warning("Budgets hiver persistés illisibles → repartis de zéro",
                name=LOGGER_NAME)
        return ClimateMemory()
    debug(
        f"Budgets hiver repris : renouvellement {memory.renew_minutes_used:.1f} min, "
        f"déshumidification {memory.humidity_minutes_used:.1f} min",
        name=LOGGER_NAME,
    )
    return memory


def _persist(store, memory: ClimateMemory, *, force: bool) -> None:
    store.save(
        STATE_SECTION,
        {
            "quota_window_start": memory.quota_window_start,
            "renew_minutes_used": round(memory.renew_minutes_used, 3),
            "humidity_minutes_used": round(memory.humidity_minutes_used, 3),
        },
        force=force,
    )


# ─────────────────────────────────────────────────────────────
#  Application aux organes
# ─────────────────────────────────────────────────────────────
def _sync_heater(heater_component, memory: ClimateMemory,
                 now_mono: float) -> ClimateMemory:
    """
    Recale la mémoire sur l'état **réel** de la sortie (audit E8).

    L'ancienne boucle chauffage ne lisait le GPIO qu'une fois, au démarrage, et
    n'agissait ensuite que sur transition : une écriture perdue désynchronisait
    le cache et le chauffage ne se rallumait plus jamais.
    """
    try:
        real = bool(heater_component.get_state())
    except Exception as exc:
        warning(f"État du chauffage illisible ({exc.__class__.__name__}) → "
                "mémoire conservée", name=LOGGER_NAME)
        return memory
    if real == memory.heater_on:
        return memory
    warning(
        f"Chauffage : état réel {'ON' if real else 'OFF'} ≠ état attendu "
        f"{'ON' if memory.heater_on else 'OFF'} → resynchronisation",
        name=LOGGER_NAME,
    )
    return replace(
        memory,
        heater_on=real,
        heater_on_since=now_mono if real else None,
    )


def _sync_motor(motor_handler, memory: ClimateMemory) -> ClimateMemory:
    """
    Même principe côté moteur : le cache de vitesse est reconfronté aux quatre
    broches. Un écart force la réapplication complète de la consigne au lieu
    d'être court-circuité par le « pas de changement → ne rien faire ».
    """
    try:
        real = motor_handler.motor.get_motor_speed()
    except Exception as exc:
        warning(f"Vitesse moteur illisible ({exc.__class__.__name__}) → "
                "mémoire conservée", name=LOGGER_NAME)
        return memory
    if real != motor_handler.speed:
        warning(
            f"Moteur : état réel {real} ≠ cache {motor_handler.speed} → "
            "réapplication de la consigne",
            name=LOGGER_NAME,
        )
        motor_handler.speed = real
    if real == memory.motor_speed:
        return memory
    return replace(memory, motor_speed=real)


def _apply_heater(heater_component, wanted: bool) -> bool:
    """Écrit puis **vérifie**. Retourne False si la sortie n'a pas suivi."""
    heater_component.set_state(1 if wanted else 0)
    try:
        return bool(heater_component.get_state()) == wanted
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
#  Coroutine supervisée
# ─────────────────────────────────────────────────────────────
async def climate_control(*, heater_component, motor_handler, sensor_handler,
                          sampling_time: int = 30, store=None) -> None:
    """
    Arbitre thermique : une lecture, une décision, deux organes cohérents.

    La configuration ne se passe plus en argument : le magasin partagé
    (`param.config_store`) la détient et rend l'instance à jour à chaque tick,
    sans I/O quand le fichier n'a pas changé et sans jamais lever.
    """
    store = store if store is not None else shared_store()
    config_store = shared_config()
    memory = _restore_memory(store)
    temp_state = StateLogger(
        "Lecture de la température ambiante", name=LOGGER_NAME, level="warning"
    )
    previous_signature = None
    # Seuil de ventilation relevé déjà signalé : on journalise le changement de
    # valeur, pas chaque tick. Ce n'est pas une panne — `StateLogger` parlerait
    # d'« échec » et de « rétablissement », vocabulaire trompeur pour un
    # ajustement volontaire.
    reported_raised_threshold: float | None = None
    previous_window = memory.quota_window_start

    while True:
        beat()

        # 1) configuration ------------------------------------------------
        # Aucune I/O tant que le fichier n'a pas bougé, et aucune exception
        # possible : un `param.json` illisible rend la dernière configuration
        # valide (audit C7, E7).
        cfg = config_store.refresh()

        # Le climat emploie les consignes nuit jusqu'à une preuve NTP. Cette
        # décision temporelle reste extérieure à la politique thermique pure.
        is_day = time_reliability().use_day_settings() and scheduled_day(cfg)
        settings = settings_from_config(cfg, is_day)
        if settings.vent_threshold_raised:
            if reported_raised_threshold != settings.vent_threshold:
                reported_raised_threshold = settings.vent_threshold
                warning(
                    f"Consigne haute ({settings.temp_max:.1f}°C) trop basse pour "
                    f"laisser une zone morte : la ventilation démarrera à "
                    f"{settings.vent_threshold:.1f}°C, le chauffage s'éteignant à "
                    f"{settings.heater_off_threshold:.1f}°C. Relever "
                    "« Jour/Nuit · maximum » ou réduire « Zone morte » pour "
                    "piloter ce seuil.",
                    name=LOGGER_NAME,
                )
        elif reported_raised_threshold is not None:
            reported_raised_threshold = None
            info(
                f"Consignes cohérentes : la ventilation démarre à la consigne "
                f"haute ({settings.vent_threshold:.1f}°C), seuil non relevé",
                name=LOGGER_NAME,
            )

        # 2) lecture capteurs (une seule fois pour les deux organes) -------
        temperature_reading = await sensor_handler.fresh_reading("BME280T")
        humidity_reading = await sensor_handler.fresh_reading("BME280H")
        temperature = (
            temperature_reading.get("observed_value")
            if temperature_reading and temperature_reading.get("control_usable") else None
        )
        humidity = (
            humidity_reading.get("observed_value")
            if humidity_reading and humidity_reading.get("control_usable") else None
        )

        # 3) resynchronisation sur le matériel ----------------------------
        now_mono = monotonic()
        memory = _sync_heater(heater_component, memory, now_mono)
        memory = _sync_motor(motor_handler, memory)

        # 4) décision -----------------------------------------------------
        # Forçages « arrêt » : une seule lecture du magasin en mémoire par tick,
        # avec les horloges du tick. On transmet les **échéances**, pas un
        # verdict : c'est `decide()` qui tranche l'expiration.
        now_epoch = time()
        overrides = shared_overrides()
        heater_until, heater_deadline = overrides.deadlines(
            "heater", now_epoch=now_epoch, now_mono=now_mono)
        motor_until, motor_deadline = overrides.deadlines(
            "motor", now_epoch=now_epoch, now_mono=now_mono)

        inputs = ClimateInputs(
            now_mono=now_mono,
            now_epoch=now_epoch,
            temperature=temperature,
            humidity=humidity,
            is_day=is_day,
            temperature_inconsistent=bool(
                temperature_reading
                and temperature_reading.get("status") == "inconsistent"
                and temperature_reading.get("enforcement_mode") == "enforce"
            ),
            temperature_quality_reason=(
                ", ".join(temperature_reading.get("reason_codes", []))
                if temperature_reading else None
            ),
            heater_forced_off_until_epoch=heater_until,
            heater_forced_off_deadline_mono=heater_deadline,
            motor_forced_off_until_epoch=motor_until,
            motor_forced_off_deadline_mono=motor_deadline,
        )
        decision, memory = decide(settings, inputs, memory)

        if decision.temperature is None:
            temp_state.fail()
        else:
            temp_state.ok()

        # 5) application --------------------------------------------------
        if not _apply_heater(heater_component, decision.heater_on):
            critical(
                f"Chauffage : la sortie n'a pas suivi la consigne "
                f"{'ON' if decision.heater_on else 'OFF'} — intervention requise",
                name=LOGGER_NAME,
            )
            _set_alarm("heater_gpio_mismatch", "écriture GPIO du chauffage sans effet")
            # La mémoire est recalée au tick suivant par `_sync_heater` : on ne
            # prétend pas connaître un état qu'on n'a pas obtenu.
        elif decision.alarm:
            _set_alarm(decision.alarm_code or "climate_safety", decision.alarm)
        else:
            _clear_alarm()

        if decision.motor_speed == 0:
            # `all_off()` réécrit les quatre broches **inconditionnellement**,
            # là où `set_motor_speed(0)` s'arrête au cache : c'est le seul
            # chemin qui rattrape un état multi-relais (que `get_motor_speed()`
            # rapporte comme 0). Un arrêt doit être un arrêt effectif.
            motor_handler.all_off()
        else:
            motor_handler.set_motor_speed(decision.motor_speed)

        # 6) journalisation des transitions uniquement --------------------
        signature = (decision.state, decision.heater_on, decision.motor_speed)
        message = (
            f"{decision.state} · chauffage "
            f"{'ON' if decision.heater_on else 'OFF'} · vitesse "
            f"{decision.motor_speed} — {decision.reason}"
        )
        if signature != previous_signature:
            info(message, name=LOGGER_NAME)
            previous_signature = signature
        else:
            debug(message, name=LOGGER_NAME)

        # 7) publication et persistance -----------------------------------
        _publish(decision, memory, now_mono, sampling_time)
        window_changed = memory.quota_window_start != previous_window
        previous_window = memory.quota_window_start
        _persist(store, memory, force=window_changed)

        await hb_sleep(sampling_time)


def _publish(decision, memory: ClimateMemory, now_mono: float,
             sampling_time: int) -> None:
    global _snapshot
    _snapshot = {
        "state": decision.state,
        "reason": decision.reason,
        "heater_on": decision.heater_on,
        "motor_speed": decision.motor_speed,
        "motor_speed_requested": decision.motor_speed_requested,
        "dwell_remaining_seconds": decision.dwell_remaining_seconds,
        "temperature": decision.temperature,
        "humidity": decision.humidity,
        "temp_min": decision.temp_min,
        "temp_max": decision.temp_max,
        "alarm": decision.alarm,
        "alarm_code": decision.alarm_code,
        "vent_threshold": round(decision.vent_threshold, 2),
        "heater_off_threshold": round(decision.heater_off_threshold, 2),
        "renew_minutes_used": decision.renew_minutes_used,
        "renew_minutes_quota": decision.renew_minutes_quota,
        "humidity_minutes_used": decision.humidity_minutes_used,
        "humidity_minutes_quota": decision.humidity_minutes_quota,
        "heater_on_seconds": (
            round(max(0.0, now_mono - memory.heater_on_since), 1)
            if decision.heater_on and memory.heater_on_since is not None else 0.0
        ),
        "heater_limit_seconds": climate_policy.MAX_CONTINUOUS_ON_MINUTES * 60,
        "heater_forced_off": decision.heater_forced_off,
        "motor_forced_off": decision.motor_forced_off,
        "cooldown_remaining_seconds": (
            round(max(0.0, memory.heater_cooldown_until - now_mono), 1)
            if memory.heater_cooldown_until is not None else 0.0
        ),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    heater_since = memory.heater_on_since if decision.heater_on else None
    publish(
        "heater", stale_after=2 * sampling_time,
        requested="on" if decision.heater_on else "off",
        # Le temps restant du forçage n'est pas répété ici : `/api/v1/state`
        # porte la clé `overrides`, seule source d'échéance, et l'IHM la joint
        # sur l'identifiant d'équipement.
        mode="forçage opérateur" if decision.heater_forced_off
        else "automatique" if decision.state != climate_policy.STATE_DISABLED
        else "désactivé",
        reason=decision.reason.split(" · ventilation :", 1)[0].replace("chauffage : ", ""),
        since_mono=heater_since,
        next_transition={
            "type": "safety_deadline" if decision.heater_on else "condition",
            "in_seconds": max(0.0, climate_policy.MAX_CONTINUOUS_ON_MINUTES * 60 - _snapshot["heater_on_seconds"])
            if decision.heater_on else None,
            "condition": f"température > {decision.heater_off_threshold:.1f} °C" if decision.heater_on else None,
        },
        heater_off_threshold=round(decision.heater_off_threshold, 2),
        on_seconds=_snapshot["heater_on_seconds"],
        continuous_limit_seconds=_snapshot["heater_limit_seconds"],
        cooldown_remaining_seconds=_snapshot["cooldown_remaining_seconds"],
    )
    publish(
        "motor", stale_after=2 * sampling_time,
        requested=decision.motor_speed_requested,
        applied=decision.motor_speed,
        mode="forçage opérateur" if decision.motor_forced_off else decision.state,
        reason=decision.reason.split("ventilation : ", 1)[-1],
        since_mono=memory.motor_speed_since,
        next_transition={"type": "condition"},
        dwell_remaining_seconds=decision.dwell_remaining_seconds,
        renew_minutes_used=decision.renew_minutes_used,
        renew_minutes_quota=decision.renew_minutes_quota,
        humidity_minutes_used=decision.humidity_minutes_used,
        humidity_minutes_quota=decision.humidity_minutes_quota,
    )


# Ré-exports pratiques pour les consommateurs (API, documentation).
STATES = (
    climate_policy.STATE_DISABLED,
    climate_policy.STATE_HEAT,
    climate_policy.STATE_NEUTRAL,
    climate_policy.STATE_VENT,
    climate_policy.STATE_RENEW,
    climate_policy.STATE_DEHUMIDIFY,
    climate_policy.STATE_OVERHEAT,
    climate_policy.STATE_FLOOR,
    climate_policy.STATE_SENSOR_FALLBACK,
    climate_policy.STATE_MANUAL,
)
