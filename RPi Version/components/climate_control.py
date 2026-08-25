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

  1. recharger la configuration (repli sur la dernière valide) ;
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
from utils.state_store import shared_store
from utils.supervisor import beat, sleep as hb_sleep

LOGGER_NAME = "climate"

STATE_SECTION = "climate"

# Alarme persistante, lisible depuis l'extérieur (destinée à /status et à l'IHM).
_alarm: str | None = None
# Dernier instantané publié — l'API le sert sans jamais déclencher de lecture.
_snapshot: dict = {
    "state": None,
    "reason": None,
    "heater_on": False,
    "motor_speed": 0,
    "temperature": None,
    "humidity": None,
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


# L'API publique et le runbook parlent d'« alarme chauffage » depuis la Phase 0 :
# on garde le nom historique en alias plutôt que de casser des scripts d'exploitation.
get_heater_alarm = get_climate_alarm


def get_climate_snapshot() -> dict:
    """Copie du dernier état publié par l'arbitre."""
    return dict(_snapshot)


def _set_alarm(reason: str) -> None:
    global _alarm
    if _alarm != reason:
        _alarm = reason
        error(f"ALARME thermique : {reason}", name=LOGGER_NAME)


def _clear_alarm() -> None:
    global _alarm
    if _alarm is not None:
        info(f"Alarme thermique levée ({_alarm})", name=LOGGER_NAME)
        _alarm = None


def _is_day(cfg) -> bool:
    """
    Phase jour/nuit, calée sur la plage du minuteur journalier n°1 (l'éclairage).
    Sémantique inchangée depuis l'origine : c'est la lumière qui définit le jour,
    pas l'horloge solaire.
    """
    now = datetime.now()
    start = cfg.daily_timer1.start_hour * 60 + cfg.daily_timer1.start_minute
    stop = cfg.daily_timer1.stop_hour * 60 + cfg.daily_timer1.stop_minute
    now_m = now.hour * 60 + now.minute
    return (start <= now_m <= stop) if start <= stop else (now_m >= start or now_m <= stop)


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
                          config, sampling_time: int = 30, store=None) -> None:
    """
    Arbitre thermique : une lecture, une décision, deux organes cohérents.

    `config` sert de repli : la configuration est rechargée depuis le disque à
    chaque tick (prise en compte à chaud des modifications de l'IHM), et une
    lecture impossible fait retomber sur la dernière version valide plutôt que
    de tuer la régulation.
    """
    store = store if store is not None else shared_store()
    memory = _restore_memory(store)
    last_cfg = config
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
        try:
            cfg = config.__class__.load()
        except Exception:
            # AppConfig.load() a déjà journalisé (dédupliqué) la cause.
            cfg = last_cfg
        else:
            last_cfg = cfg

        is_day = _is_day(cfg)
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
        temperature = await sensor_handler.fresh_value("BME280T", max_age=20.0)
        humidity = await sensor_handler.fresh_value("BME280H", max_age=20.0)

        # 3) resynchronisation sur le matériel ----------------------------
        now_mono = monotonic()
        memory = _sync_heater(heater_component, memory, now_mono)
        memory = _sync_motor(motor_handler, memory)

        # 4) décision -----------------------------------------------------
        inputs = ClimateInputs(
            now_mono=now_mono,
            now_epoch=time(),
            temperature=temperature,
            humidity=humidity,
            is_day=is_day,
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
            _set_alarm("écriture GPIO du chauffage sans effet")
            # La mémoire est recalée au tick suivant par `_sync_heater` : on ne
            # prétend pas connaître un état qu'on n'a pas obtenu.
        elif decision.alarm:
            _set_alarm(decision.alarm)
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
        _publish(decision)
        window_changed = memory.quota_window_start != previous_window
        previous_window = memory.quota_window_start
        _persist(store, memory, force=window_changed)

        await hb_sleep(sampling_time)


def _publish(decision) -> None:
    global _snapshot
    _snapshot = {
        "state": decision.state,
        "reason": decision.reason,
        "heater_on": decision.heater_on,
        "motor_speed": decision.motor_speed,
        "temperature": decision.temperature,
        "humidity": decision.humidity,
        "vent_threshold": round(decision.vent_threshold, 2),
        "heater_off_threshold": round(decision.heater_off_threshold, 2),
        "renew_minutes_used": decision.renew_minutes_used,
        "renew_minutes_quota": decision.renew_minutes_quota,
        "humidity_minutes_used": decision.humidity_minutes_used,
        "humidity_minutes_quota": decision.humidity_minutes_quota,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


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
