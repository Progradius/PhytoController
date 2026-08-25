# components/cyclic_timer_handler.py
# Author  : Progradius
# License : AGPL-3.0

from datetime import datetime, timedelta, time, date
from time import time as epoch_now

from utils.pretty_console import box, debug, info, error
from utils.state_store import shared_store
from utils.supervisor import beat, sleep as hb_sleep
from param.config import AppConfig

LOGGER_NAME = "timer.cyclic"

aSYNC_DAY = 24 * 3600

aSYNC_COL_ACT  = "green"
aSYNC_COL_OFF  = "yellow"
aSYNC_COL_INFO = "cyan"
aSYNC_COL_WARN = "red"

aSYNC_SLEEP_TEMPLATE = "[J] #{tid} SLEEP {msg}"


def _save_phase(store, section: str, phase: str, duration: float) -> None:
    """
    Note la phase en cours et son échéance.

    L'écriture est **throttlée** par le magasin (une par minute au plus) : ces
    phases peuvent durer quelques secondes, et graver la carte SD à chaque
    bascule l'userait pour rien. La conséquence est bornée et va dans le bon
    sens : un enregistrement pas encore écrit est simplement échu au
    redémarrage, donc ignoré — on repart d'un cycle complet, jamais d'une
    attente fantôme.
    """
    store.save(section, {"phase": phase, "ends_at": epoch_now() + duration})


def _resume_sequential(saved: dict) -> tuple[str, float] | None:
    """
    Reprend la phase séquentielle interrompue par un redémarrage (audit E6).

    Sans cette reprise, chaque relance de tâche (superviseur, `systemctl
    restart`, coupure secteur) redémarrait une phase ON **complète** : un
    arrosage de 15 min pouvait être rejoué plusieurs fois d'affilée.

    Retourne `(phase, secondes_restantes)` ou `None` si l'enregistrement est
    absent, illisible ou déjà échu — l'échéance dépassée est le cas nominal
    d'un long arrêt, et la reprise doit alors être un cycle normal.
    """
    phase = saved.get("phase")
    if phase not in ("on", "off"):
        return None
    try:
        remaining = float(saved.get("ends_at", 0.0)) - epoch_now()
    except (TypeError, ValueError):
        return None
    # Une échéance très lointaine trahit une horloge fausse (pas de RTC sur ce
    # Pi) : on repart d'un cycle propre plutôt que d'attendre des heures.
    if remaining <= 0 or remaining > 24 * 3600:
        return None
    return phase, remaining


async def timer_cyclic(cyclic_timer) -> None:
    """Coroutine de pilotage du CyclicTimer (mode journalier ou séquentiel)."""

    tid    = cyclic_timer.timer_id
    comp   = cyclic_timer.component
    disabled_reported = False
    store = shared_store()
    state_section = f"cyclic_{tid}"
    # La reprise n'a de sens qu'au tout premier passage : ensuite, c'est cette
    # boucle elle-même qui tient la phase.
    pending_resume = _resume_sequential(store.load(state_section))
    # Dernière config valide : filet quand param.json est momentanément
    # illisible (POST /conf en cours, fichier tronqué…). Sans ce repli, la
    # JSONDecodeError tue la tâche définitivement — plus rien ne repilote la
    # sortie cyclique.
    last_cfg = getattr(cyclic_timer, "_config", None)

    while True:
        beat()
        # recharger complètement la conf
        try:
            cfg = AppConfig.load()
        except Exception:
            # AppConfig.load() a déjà journalisé (dédupliqué) la cause.
            if last_cfg is None:
                await hb_sleep(5)
                continue
            cfg = last_cfg
        else:
            last_cfg = cfg

        if cyclic_timer.timer_id == "1":
            cyc_conf = cfg.cyclic1
            gpio_pin = cfg.gpio.cyclic1_pin
        else:
            cyc_conf = cfg.cyclic2
            gpio_pin = cfg.gpio.cyclic2_pin

        # ----- gestion du enabled -----
        enabled = getattr(cyc_conf, "enabled", True)
        if not enabled:
            # on force OFF puis on redort : un seul log à la transition
            if not disabled_reported:
                info(f"Cyclic #{tid} désactivé → GPIO {gpio_pin} OFF", name=LOGGER_NAME)
                disabled_reported = True
            try:
                comp.set_state(0)
            except Exception as e:
                error(f"Cyclic #{tid} : extinction du GPIO {gpio_pin} échouée → {e}",
                      name=LOGGER_NAME)
            await hb_sleep(5)
            continue

        if disabled_reported:
            info(f"Cyclic #{tid} réactivé", name=LOGGER_NAME)
            disabled_reported = False
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
                debug(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=msg), name=LOGGER_NAME)
                await hb_sleep(days_offset * aSYNC_DAY)

            # on refait la journée
            day0 = date.today()
            trigger0 = datetime.combine(day0, time(first_hour, 0))
            for n in range(triggers_per_day):
                trig_time = trigger0 + timedelta(seconds=n * interval_seconds)
                now = datetime.now()
                if trig_time > now:
                    delay = (trig_time - now).total_seconds()
                    debug(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=f"{int(delay)} s"), name=LOGGER_NAME)
                    await hb_sleep(delay)

                # ON → attente → OFF garanti : le `finally` du contexte coupe
                # la sortie même si la tâche est annulée ou lève pendant
                # l'attente (audit E5).
                box(f"[J] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT, name=LOGGER_NAME)
                with comp.energized():
                    await hb_sleep(action_duration)
                box(f"[J] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF, name=LOGGER_NAME)

            # fin de journée
            debug(aSYNC_SLEEP_TEMPLATE.format(tid=tid, msg=f"{period_days} jour(s)"), name=LOGGER_NAME)
            await hb_sleep(period_days * aSYNC_DAY)

        elif mode == "séquentiel":
            if _is_day_from(cfg):
                on_d  = cyclic_timer.get_on_time_day()
                off_d = cyclic_timer.get_off_time_day()
                phase = "Jour"
            else:
                on_d  = cyclic_timer.get_on_time_night()
                off_d = cyclic_timer.get_off_time_night()
                phase = "Nuit"

            # Reprise éventuelle de la phase interrompue par un redémarrage.
            on_remaining, off_remaining = on_d, off_d
            if pending_resume is not None:
                resumed_phase, remaining = pending_resume
                pending_resume = None
                info(f"Cyclic #{tid} : reprise de la phase {resumed_phase.upper()} "
                     f"({remaining:.0f} s restantes)", name=LOGGER_NAME)
                if resumed_phase == "on":
                    on_remaining = min(on_d, remaining)
                else:
                    # La phase ON du cycle interrompu est déjà passée : on
                    # termine l'attente OFF avant de reprendre le cycle normal.
                    _save_phase(store, state_section, "off", remaining)
                    await hb_sleep(remaining)
                    continue

            # ON → attente → OFF garanti (audit E5)
            box(f"[S][{phase}] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT, name=LOGGER_NAME)
            _save_phase(store, state_section, "on", on_remaining)
            with comp.energized():
                await hb_sleep(on_remaining)

            box(f"[S][{phase}] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF, name=LOGGER_NAME)
            _save_phase(store, state_section, "off", off_remaining)
            await hb_sleep(off_remaining)

        else:
            error(f"CyclicTimer #{tid} mode inconnu : « {mode} » → arrêt du timer", name=LOGGER_NAME)
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
