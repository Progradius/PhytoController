# components/dailytimer_handler.py
from datetime import datetime, timedelta

from utils import pretty_console as ui
from utils.supervisor import beat, sleep as hb_sleep

LOGGER_NAME = "timer.daily"


async def timer_daily(dailytimer, sampling_time: int = 60):
    """
    La configuration arrive par `dailytimer.refresh_from_config()`, qui
    interroge le magasin partagé : rien à passer en argument.
    """
    tid = str(dailytimer.timer_id)
    disabled_reported = False

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
            await hb_sleep(sampling_time)
            continue

        if disabled_reported:
            ui.info(f"DailyTimer #{tid} réactivé", name=LOGGER_NAME)
            disabled_reported = False

        changed = dailytimer.toggle_state_daily()
        if changed:
            state_on = bool(dailytimer.component.get_state())
            ui.info(f"DailyTimer #{tid} basculé sur {'ON' if state_on else 'OFF'}",
                    name=LOGGER_NAME)
        else:
            ui.debug("Aucun changement demandé par le planning.", name=LOGGER_NAME)

        next_dt = now_dt + timedelta(seconds=sampling_time)
        ui.debug(f"Prochaine vérification : {next_dt:%H:%M:%S}", name=LOGGER_NAME)

        await hb_sleep(sampling_time)
