# components/dailytimer_handler.py
from datetime import datetime, timedelta
from time import monotonic, time

from utils import pretty_console as ui
from utils.overrides import shared_overrides
from utils.supervisor import beat, sleep as hb_sleep
from utils.operational_state import publish
from utils.schedule import clock_in_range
from utils.time_reliability import time_reliability

LOGGER_NAME = "timer.daily"


async def timer_daily(dailytimer, sampling_time: int = 60):
    """
    La configuration arrive par `dailytimer.refresh_from_config()`, qui
    interroge le magasin partagé : rien à passer en argument.
    """
    tid = str(dailytimer.timer_id)
    disabled_reported = False
    equipment_id = f"daily_{tid}"
    since_mono = None

    while True:
        beat()
        now_dt = datetime.now()
        ui.debug(f"DailyTimer #{tid} – vérification @ {now_dt:%H:%M:%S}", name=LOGGER_NAME)

        # recharger conf
        if hasattr(dailytimer, "refresh_from_config"):
            try:
                dailytimer.refresh_from_config()
            except Exception as e:
                ui.warning(f"Échec refresh_from_config #{tid} → {e}", name=LOGGER_NAME)

        # si désactivé → on force OFF et on dort (un seul log à la transition)
        if not getattr(dailytimer, "enabled", True):
            if not disabled_reported:
                ui.info(f"DailyTimer #{tid} désactivé → OFF", name=LOGGER_NAME)
                disabled_reported = True
            try:
                dailytimer.component.set_state(0)
            except Exception as e:
                # Relais potentiellement resté fermé : c'est une vraie erreur
                ui.error(
                    f"DailyTimer #{tid} : extinction du GPIO "
                    f"{getattr(dailytimer.component, 'pin', '?')} échouée → {e}",
                    name=LOGGER_NAME,
                )
            publish(equipment_id, stale_after=2 * sampling_time, requested="off",
                    mode="désactivé", reason="minuterie désactivée", since_mono=since_mono,
                    next_transition={"type": "none"})
            await hb_sleep(sampling_time)
            continue

        if disabled_reported:
            ui.info(f"DailyTimer #{tid} réactivé", name=LOGGER_NAME)
            disabled_reported = False

        # Forçage « arrêt » opérateur : lu en tête de boucle, jamais persisté
        # ici. La tranche de sommeil est courte pour que l'expiration reprenne
        # la main sans mécanisme supplémentaire ; une création ou une levée
        # passe en plus par `supervisor.request_reload()` côté HTTP.
        overrides = shared_overrides()
        if overrides.is_forced_off(equipment_id):
            record = overrides.active().get(equipment_id)
            dailytimer.component.set_state(0)
            publish(equipment_id, stale_after=2 * sampling_time, requested="off",
                    mode="forçage opérateur", reason="forçage opérateur : arrêt",
                    since_mono=since_mono,
                    next_transition={
                        "type": "safety_deadline",
                        "in_seconds": round(
                            record.remaining_seconds(time(), monotonic()), 1
                        ) if record is not None else None,
                    })
            await hb_sleep(min(sampling_time, 30))
            continue

        reliability = time_reliability()
        if reliability.daily_suspended():
            dailytimer.component.set_state(0)
            publish(equipment_id, stale_after=2 * sampling_time, requested="suspended",
                    mode="journalier", reason="heure inconnue : suspension bornée",
                    since_mono=reliability.boot_mono,
                    next_transition={"type": "safety_deadline",
                                     "in_seconds": round(max(0, 900 - reliability.unknown_seconds), 1)})
            await hb_sleep(min(sampling_time, 30))
            continue

        active = clock_in_range(
            now_dt, dailytimer.start_hour, dailytimer.start_minute,
            dailytimer.stop_hour, dailytimer.stop_minute,
        )
        before = bool(dailytimer.component.get_state())
        changed = dailytimer.toggle_state_daily()
        after = bool(dailytimer.component.get_state())
        if before != after or since_mono is None:
            since_mono = monotonic()
        if changed:
            state_on = bool(dailytimer.component.get_state())
            ui.info(f"DailyTimer #{tid} basculé sur {'ON' if state_on else 'OFF'}",
                    name=LOGGER_NAME)
        else:
            ui.debug("Aucun changement demandé par le planning.", name=LOGGER_NAME)

        boundary = (
            f"{dailytimer.stop_hour:02d}:{dailytimer.stop_minute:02d}"
            if active else f"{dailytimer.start_hour:02d}:{dailytimer.start_minute:02d}"
        )
        publish(equipment_id, stale_after=2 * sampling_time,
                requested="on" if active else "off", mode="journalier",
                reason="dans la plage [début, fin)" if active else "hors plage [début, fin)",
                since_mono=since_mono,
                next_transition={"type": "clock", "at": boundary})

        next_dt = now_dt + timedelta(seconds=sampling_time)
        ui.debug(f"Prochaine vérification : {next_dt:%H:%M:%S}", name=LOGGER_NAME)

        await hb_sleep(sampling_time)
