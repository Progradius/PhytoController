# controller/model/CyclicTimer.py
# Author : Progradius (adapted)
# License : AGPL‑3.0
# -------------------------------------------------------------
#  Minuteur cyclique : déclenche périodiquement un composant
# -------------------------------------------------------------

from controller.parameter_handler import read_parameters_from_json
from controller.ui.pretty_console import info, action, warning


class CyclicTimer:
    """
    • `period`           → temps entre deux déclenchements (minutes)  
    • `action_duration`  → durée pendant laquelle le composant reste activé (secondes)

    Les deux valeurs peuvent être modifiées à chaud via les *setters* ;
    la persistance est gérée ailleurs (API + parameter_handler).
    """

    # ───────────────────────────── init ───────────────────────
    def __init__(self, component, timer_id: str | int):
        param         = read_parameters_from_json()
        settings_key  = f"Cyclic{timer_id}_Settings"
        self.period          = int(param[settings_key]["period_minutes"])
        self.action_duration = int(param[settings_key]["action_duration_seconds"])

        self.component = component
        self.timer_id  = str(timer_id)

        info(f"CyclicTimer #{self.timer_id} → période {self.period} min  "
             f"| durée action {self.action_duration} s  "
             f"| GPIO {self.component.pin}")

    # ───────────────────────── getters ────────────────────────
    def get_period(self) -> int:
        """Période du cycle (minutes)."""
        return self.period

    def get_action_duration(self) -> int:
        """Durée d'activation (secondes)."""
        return self.action_duration

    # ───────────────────────── setters ────────────────────────
    def set_period_minutes(self, minutes: int) -> None:
        if minutes <= 0:
            warning(f"Période invalide : {minutes} – ignoré")
            return
        self.period = minutes
        action(f"CyclicTimer #{self.timer_id} nouvelle période : {minutes} min")

    def set_action_duration_seconds(self, seconds: int) -> None:
        if seconds <= 0:
            warning(f"Durée d'action invalide : {seconds} – ignoré")
            return
        self.action_duration = seconds
        action(f"CyclicTimer #{self.timer_id} nouvelle durée : {seconds} s")

    # ───────────────────────── debug repr ─────────────────────
    def __repr__(self) -> str:
        return (f"<CyclicTimer #{self.timer_id} "
                f"period={self.period} min "
                f"action={self.action_duration} s "
                f"GPIO={self.component.pin}>")
