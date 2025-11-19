# components/cyclic_timer_handler.py
# Author  : Progradius
# License : AGPL-3.0

import asyncio
from datetime import datetime, timedelta, time, date

from utils.pretty_console import box, warning
from param.config import AppConfig

aSYNC_DAY = 24 * 3600

aSYNC_COL_ACT  = "green"
aSYNC_COL_OFF  = "yellow"
aSYNC_COL_INFO = "cyan"
aSYNC_COL_WARN = "red"

aSYNC_SLEEP_TEMPLATE = "[J] #{tid} SLEEP {msg}"


async def timer_cyclic(cyclic_timer) -> None:
    """Coroutine de pilotage du CyclicTimer (mode journalier ou séquentiel)."""

    tid    = cyclic_timer.timer_id
    comp   = cyclic_timer.component

    while True:
        # recharger complètement la conf
        cfg = AppConfig.load()
        if cyclic_timer.timer_id == "1":
            cyc_conf = cfg.cyclic1
            gpio_pin = cfg.gpio.cyclic1_pin
        else:
            cyc_conf = cfg.cyclic2
            gpio_pin = cfg.gpio.cyclic2_pin

        # ----- gestion du enabled -----
        enabled = getattr(cyc_conf, "enabled", True)
        if not enabled:
            # on force OFF et on redort un peu
            box(f"Cyclic #{tid} désactivé → GPIO {gpio_pin} OFF", color=aSYNC_COL_INFO)
            try:
                comp.set_state(0)
            except Exception as e:
                warning(f"Cyclic #{tid} OFF échoué: {e}")
            await asyncio.sleep(5)
            continue
        # ------------------------------

        # si activé → on réinjecte la conf dans l'instance existante
        cyclic_timer._config = cfg
        cyclic_timer._load_from_config_block()

        mode = cyclic_timer.get_mode().lower()

        if mode == "journalier":
            period_days       = cyclic_timer.get_period_days()
            triggers_per_day  = cyclic_timer.get_triggers_per_day()
            first_hour        = cyclic_timer.get_first_trigger_hour()
            action_duration   = cyclic_timer.get_action_duration()
            interval_seconds  = aSYNC_DAY // triggers_per_day

            today_ord   = date.today().toordinal()
            days_offset = (period_days - (today_ord % period_days)) % period_days
            if days_offset:
                msg = f"{days_offset} jour{'s' if days_offset > 1 else ''}"
                box(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=msg), color=aSYNC_COL_INFO)
                await asyncio.sleep(days_offset * aSYNC_DAY)

            # on refait la journée
            day0 = date.today()
            trigger0 = datetime.combine(day0, time(first_hour, 0))
            for n in range(triggers_per_day):
                trig_time = trigger0 + timedelta(seconds=n * interval_seconds)
                now = datetime.now()
                if trig_time > now:
                    delay = (trig_time - now).total_seconds()
                    box(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=f"{int(delay)} s"), color=aSYNC_COL_INFO)
                    await asyncio.sleep(delay)

                # ON
                box(f"[J] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT)
                try:
                    comp.set_state(1)
                except Exception as e:
                    warning(f"CyclicTimer #{tid} activation échouée : {e}")

                await asyncio.sleep(action_duration)

                # OFF
                box(f"[J] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF)
                try:
                    comp.set_state(0)
                except Exception as e:
                    warning(f"CyclicTimer #{tid} désactivation échouée : {e}")

            # fin de journée
            box(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=f"{period_days} jour(s)"), color=aSYNC_COL_INFO)
            await asyncio.sleep(period_days * aSYNC_DAY)

        elif mode == "séquentiel":
            if _is_day_from(cfg):
                on_d  = cyclic_timer.get_on_time_day()
                off_d = cyclic_timer.get_off_time_day()
                phase = "Jour"
            else:
                on_d  = cyclic_timer.get_on_time_night()
                off_d = cyclic_timer.get_off_time_night()
                phase = "Nuit"

            # ON
            box(f"[S][{phase}] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT)
            try:
                comp.set_state(1)
            except Exception as e:
                warning(f"CyclicTimer #{tid} activation échouée : {e}")
            await asyncio.sleep(on_d)

            # OFF
            box(f"[S][{phase}] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF)
            try:
                comp.set_state(0)
            except Exception as e:
                warning(f"CyclicTimer #{tid} désactivation échouée : {e}")
            await asyncio.sleep(off_d)

        else:
            warning(f"CyclicTimer #{tid} mode inconnu : « {mode} » → arrêt du timer")
            return


def _is_day_from(cfg: AppConfig) -> bool:
    from datetime import datetime
    now      = datetime.now()
    start_h  = cfg.daily_timer1.start_hour
    start_m  = cfg.daily_timer1.start_minute
    stop_h   = cfg.daily_timer1.stop_hour
    stop_m   = cfg.daily_timer1.stop_minute

    start = start_h * 60 + start_m
    stop  = stop_h  * 60 + stop_m
    now_m = now.hour * 60 + now.minute

    return (start <= now_m <= stop) if start <= stop else (now_m >= start or now_m <= stop)
