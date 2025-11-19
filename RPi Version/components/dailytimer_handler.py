# components/dailytimer_handler.py
import asyncio
from datetime import datetime, timedelta

from utils import pretty_console as ui
from param.config import AppConfig

async def timer_daily(
    dailytimer,
    config: AppConfig | None = None,
    sampling_time: int = 60
):
    tid = str(dailytimer.timer_id)

    while True:
        now_dt = datetime.now()
        ui.clock(f"DailyTimer #{tid}  –  check @ {now_dt:%H:%M:%S}")

        # recharger conf
        if hasattr(dailytimer, "refresh_from_config"):
            try:
                dailytimer.refresh_from_config()
            except Exception as e:
                ui.warning(f"Échec refresh_from_config #{tid} → {e}")

        # si désactivé → on force OFF et on dort
        if not getattr(dailytimer, "enabled", True):
            ui.info(f"DailyTimer #{tid} désactivé → OFF")
            try:
                dailytimer.component.set_state(0)
            except Exception:
                pass
            await asyncio.sleep(sampling_time)
            continue

        changed = dailytimer.toggle_state_daily()
        if changed:
            state_on = bool(dailytimer.component.get_state())
            txt = "ON" if state_on else "OFF"
            ui.action(f"DailyTimer #{tid} switched {txt}")
        else:
            ui.info("Aucun changement demandé par le planning.")

        next_dt = now_dt + timedelta(seconds=sampling_time)
        ui.info(f"Prochaine vérif : {next_dt:%H:%M:%S}")

        await asyncio.sleep(sampling_time)
