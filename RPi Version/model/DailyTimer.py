# controller/components/DailyTimer.py
# Author : Progradius (adapted)
# License : AGPL‑3.0
# -------------------------------------------------------------
#  Minuteur journalier : active un composant entre deux horaires
# -------------------------------------------------------------

from datetime import datetime
from function                       import convert_time_to_minutes
from controller.parameter_handler   import read_parameters_from_json
from controller.ui.pretty_console   import info, warning, clock, action


class DailyTimer:
    """
    Active/désactive *component* entre deux horaires (HH:MM) stockés
    dans ``param.json``.  
    • `timer_id` ∈ {1,2,…} → lit la section *DailyTimer{N}_Settings*.
    """

    def __init__(self, component, timer_id: int):
        self.component = component
        self.timer_id  = int(timer_id)

        param           = read_parameters_from_json()
        key             = f"DailyTimer{self.timer_id}_Settings"

        self.start_hour   = param[key]["start_hour"]
        self.start_minute = param[key]["start_minute"]
        self.stop_hour    = param[key]["stop_hour"]
        self.stop_minute  = param[key]["stop_minute"]

        info(f"DailyTimer #{self.timer_id} chargé :"
             f" {self.start_hour:02d}:{self.start_minute:02d}"
             f" → {self.stop_hour:02d}:{self.stop_minute:02d}")

    # ────────────────────────── getters & setters ─────────────
    def get_component_state(self): return self.component.get_state()

    def set_start_time(self, h: int, m: int):
        self.start_hour, self.start_minute = h, m

    def set_stop_time(self, h: int, m: int):
        self.stop_hour, self.stop_minute = h, m

    # ────────────────────────── logique principale ────────────
    def toggle_state_daily(self) -> None:
        """
        À appeler périodiquement : met le GPIO ON ou OFF selon l'heure.
        Gère le cas d'une plage « à cheval » sur minuit (ex 22 h → 06 h).
        """
        start = convert_time_to_minutes(self.start_hour, self.start_minute)
        stop  = convert_time_to_minutes(self.stop_hour,  self.stop_minute)

        now   = datetime.now()
        now_m = convert_time_to_minutes(now.hour, now.minute)

        # --- la période chevauche‑t‑elle minuit ? -------------
        active = (
            start <= now_m <= stop   if start <= stop
            else  now_m >= start or now_m <= stop
        )

        # --- calcul temps restant -----------------------------
        if active:
            mins_left = (stop - now_m) % 1440
            clock(f"DailyTimer #{self.timer_id} : ON — arrêt dans {mins_left} min")
            if self.component.get_state():        # déjà OFF → activer
                action(f"Activation du composant (GPIO {self.component.pin})")
                self.component.set_state(0)
        else:
            mins_left = (start - now_m) % 1440
            clock(f"DailyTimer #{self.timer_id} : OFF — mise en marche dans {mins_left} min")
            if not self.component.get_state():    # déjà ON → désactiver
                action(f"Désactivation du composant (GPIO {self.component.pin})")
                self.component.set_state(1)
            else:
                warning("Composant déjà à l'état OFF")
