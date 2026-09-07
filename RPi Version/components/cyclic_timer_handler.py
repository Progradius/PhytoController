# components/cyclic_timer_handler.py
# Author  : Progradius
# License : AGPL-3.0

from datetime import datetime, timedelta, time
from time import monotonic, time as epoch_now

from utils.pretty_console import box, debug, info, error, warning
from utils.overrides import shared_overrides
from utils.state_store import shared_store
from utils.supervisor import beat, sleep as hb_sleep
from utils.operational_state import publish
from utils.schedule import is_day
from utils.time_reliability import time_reliability
from param.config_store import shared_config

LOGGER_NAME = "timer.cyclic"

aSYNC_DAY = 24 * 3600

aSYNC_COL_ACT  = "green"
aSYNC_COL_OFF  = "yellow"
aSYNC_COL_INFO = "cyan"
aSYNC_COL_WARN = "red"

aSYNC_SLEEP_TEMPLATE = "[J] #{tid} SLEEP {msg}"


def _next_journalier_trigger(now: datetime, period_days: int,
                             triggers_per_day: int, first_hour: int) -> datetime:
    """Retourne le prochain déclenchement strictement futur, sans rattrapage."""
    interval = aSYNC_DAY // triggers_per_day
    for offset in range(0, period_days + 2):
        candidate_day = now.date() + timedelta(days=offset)
        if candidate_day.toordinal() % period_days:
            continue
        first = datetime.combine(candidate_day, time(first_hour, 0))
        for index in range(triggers_per_day):
            candidate = first + timedelta(seconds=index * interval)
            if candidate > now:
                return candidate
    # La boucle couvre toujours au moins un jour admissible ; garde défensive.
    return datetime.combine(now.date() + timedelta(days=period_days), time(first_hour, 0))


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
    # Le magasin de configuration porte le repli : un `param.json`
    # momentanément illisible (POST /conf en cours, fichier tronqué…) rend la
    # dernière configuration valide au lieu de lever. Sans cela, la
    # JSONDecodeError tuait la tâche définitivement — plus rien ne repilotait la
    # sortie cyclique (audit C7, E7).
    config_store = shared_config()
    zero_cycle_reported = False
    equipment_id = f"cyclic_{tid}"

    while True:
        beat()
        # Aucune I/O tant que le fichier n'a pas bougé.
        cfg = config_store.refresh()

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
            publish(equipment_id, stale_after=10, requested="off", mode="désactivé",
                    reason="minuterie désactivée", since_mono=None,
                    next_transition={"type": "none"})
            await hb_sleep(5)
            continue

        if disabled_reported:
            info(f"Cyclic #{tid} réactivé", name=LOGGER_NAME)
            disabled_reported = False
        # ------------------------------

        # Forçage « arrêt » opérateur, lu en tête de boucle. Une création ou une
        # levée déclenche `supervisor.request_reload()` côté HTTP : sans cela un
        # cyclique en attente longue ignorerait l'ordre jusqu'à dix jours, et
        # `energized()` garantit la coupure si l'annulation tombe en pleine
        # impulsion.
        overrides = shared_overrides()
        if overrides.is_forced_off(equipment_id):
            record = overrides.active().get(equipment_id)
            comp.set_state(0)
            publish(equipment_id, stale_after=70, requested="off",
                    mode="forçage opérateur", reason="forçage opérateur : arrêt",
                    since_mono=None,
                    next_transition={
                        "type": "safety_deadline",
                        "in_seconds": round(
                            record.remaining_seconds(epoch_now(), monotonic()), 1
                        ) if record is not None else None,
                    })
            await hb_sleep(30)
            continue

        # si activé → on réinjecte la conf dans l'instance existante
        cyclic_timer._config = cfg
        cyclic_timer._load_from_config_block()

        mode = cyclic_timer.get_mode().lower()

        if mode == "journalier":
            period_days       = cyclic_timer.get_period_days()
            triggers_per_day  = cyclic_timer.get_triggers_per_day()
            first_hour        = cyclic_timer.get_first_trigger_hour()
            action_duration   = cyclic_timer.get_action_duration()
            reliability = time_reliability()
            if reliability.daily_suspended():
                comp.set_state(0)
                publish(equipment_id, stale_after=70, requested="suspended",
                        mode="journalier", reason="heure inconnue : impulsions suspendues",
                        since_mono=reliability.boot_mono,
                        next_transition={"type": "safety_deadline",
                                         "in_seconds": round(max(0, 900 - reliability.unknown_seconds), 1)})
                await hb_sleep(30)
                continue

            now = datetime.now()
            trigger = _next_journalier_trigger(now, period_days, triggers_per_day, first_hour)
            delay = (trigger - now).total_seconds()
            publish(equipment_id, stale_after=70, requested="off", mode="journalier",
                    reason="attente de la prochaine impulsion future", since_mono=None,
                    next_transition={"type": "clock", "at": trigger.isoformat(timespec="seconds")})
            # Tranches courtes : un hand-edit de param.json est pris en compte
            # sans attendre plusieurs jours. Le prochain tour recalcule tout.
            if delay > 30:
                await hb_sleep(30)
                continue
            await hb_sleep(delay)
            if datetime.now() < trigger:
                continue
            started = monotonic()
            box(f"[J] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT, name=LOGGER_NAME)
            try:
                with comp.energized():
                    # Publier après l'écriture permet à l'historique de relire
                    # le GPIO réellement activé, et non l'ancien état OFF.
                    publish(equipment_id, stale_after=max(70, 2 * action_duration), requested="on",
                            mode="journalier", reason="impulsion planifiée", since_mono=started,
                            next_transition={"type": "clock", "in_seconds": action_duration})
                    await hb_sleep(action_duration)
            finally:
                # `energized()` a déjà garanti et vérifié la coupure lorsque
                # cette publication déclenche la relecture matérielle.
                publish(equipment_id, stale_after=70, requested="off",
                        mode="journalier", reason="impulsion terminée ou interrompue",
                        since_mono=None, next_transition={"type": "none"})
                box(f"[J] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF, name=LOGGER_NAME)

        elif mode == "séquentiel":
            # Avant une preuve NTP, le séquentiel continue avec ses paramètres
            # nuit : jamais de suspension ni d'OFF illimité.
            if time_reliability().use_day_settings() and is_day(cfg):
                on_d  = cyclic_timer.get_on_time_day()
                off_d = cyclic_timer.get_off_time_day()
                phase = "Jour"
            else:
                on_d  = cyclic_timer.get_on_time_night()
                off_d = cyclic_timer.get_off_time_night()
                phase = "Nuit"

            # Un cycle de durée nulle enchaînerait deux `sleep(0)` : la boucle
            # tournerait à vide, plein CPU, sans jamais rien piloter. Le cas est
            # traité ici et non par un validateur : refuser la configuration
            # ferait un boot mort, et `Cyclic2_Settings` porte déjà 0/0 (sans
            # conséquence, il est en mode journalier).
            if on_d + off_d <= 0:
                if not zero_cycle_reported:
                    warning(f"Cyclic #{tid} [{phase}] : durées ON et OFF nulles → "
                            "rien à piloter, cycle en attente", name=LOGGER_NAME)
                    zero_cycle_reported = True
                comp.set_state(0)
                publish(equipment_id, stale_after=130, requested="off", mode="séquentiel",
                        reason=f"{phase.lower()} : cycle nul", since_mono=None,
                        next_transition={"type": "none"})
                await hb_sleep(60)
                continue
            zero_cycle_reported = False

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
                    publish(equipment_id, stale_after=max(70, 2 * remaining), requested="off",
                            mode="séquentiel", reason="reprise de la phase OFF",
                            since_mono=None, next_transition={"type": "clock", "in_seconds": round(remaining, 1)})
                    await hb_sleep(remaining)
                    continue

            # ON → attente → OFF garanti (audit E5)
            box(f"[S][{phase}] #{tid} ON  @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_ACT, name=LOGGER_NAME)
            _save_phase(store, state_section, "on", on_remaining)
            phase_completed = False
            try:
                with comp.energized():
                    publish(equipment_id, stale_after=max(70, 2 * on_remaining), requested="on",
                            mode="séquentiel", reason=f"phase ON ({phase.lower()})",
                            since_mono=monotonic(),
                            next_transition={"type": "clock", "in_seconds": round(on_remaining, 1)})
                    await hb_sleep(on_remaining)
                    phase_completed = True
            finally:
                publish(
                    equipment_id,
                    stale_after=max(70, 2 * off_remaining) if phase_completed else 70,
                    requested="off", mode="séquentiel",
                    reason=(f"phase OFF ({phase.lower()})" if phase_completed
                            else "phase ON interrompue : arrêt sécurisé"),
                    since_mono=monotonic() if phase_completed else None,
                    next_transition=(
                        {"type": "clock", "in_seconds": round(off_remaining, 1)}
                        if phase_completed else {"type": "none"}
                    ),
                )

            box(f"[S][{phase}] #{tid} OFF @ {datetime.now():%H:%M:%S}", color=aSYNC_COL_OFF, name=LOGGER_NAME)
            _save_phase(store, state_section, "off", off_remaining)
            await hb_sleep(off_remaining)

        else:
            error(f"CyclicTimer #{tid} mode inconnu : « {mode} » → arrêt du timer", name=LOGGER_NAME)
            return
