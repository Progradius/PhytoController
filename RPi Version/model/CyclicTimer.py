# controller/model/CyclicTimer.py
# Author  : Progradius 
# License : AGPL-3.0
# -------------------------------------------------------------
#  Minuteur cyclique : déclenche périodiquement un composant
# -------------------------------------------------------------

from typing import Union
from param.config import AppConfig
from ui.pretty_console import info, action, warning

class CyclicTimer:
    """
    • `period_minutes`           → temps entre deux déclenchements (minutes)  
    • `action_duration_seconds`  → durée pendant laquelle le composant reste activé (secondes)

    Les deux valeurs sont lues depuis AppConfig.cyclic{1,2} et
    toute modification est automatiquement sauvé dans le JSON.
    """

    def __init__(
        self,
        component,
        timer_id: Union[int, str],
        config: AppConfig
    ):
        self.component = component
        self.timer_id  = str(timer_id)
        self._config   = config

        # On récupère le bon bloc de config
        if self.timer_id == "1":
            settings = config.cyclic1
        elif self.timer_id == "2":
            settings = config.cyclic2
        else:
            raise ValueError(f"timer_id invalide: {timer_id!r} (doit être 1 ou 2)")

        # Initialise à partir de la config
        self.period          = settings.period_minutes
        self.action_duration = settings.action_duration_seconds

        info(
            f"CyclicTimer #{self.timer_id} chargé → "
            f"période {self.period} min | durée {self.action_duration} s | "
            f"GPIO {self.component.pin}"
        )


    # ───────────────────────── getters ────────────────────────

    def get_period(self) -> int:
        """Retourne la période du cycle (minutes)."""
        return self.period

    def get_action_duration(self) -> int:
        """Retourne la durée d’activation (secondes)."""
        return self.action_duration


    # ───────────────────────── setters ────────────────────────

    def set_period_minutes(self, minutes: int) -> None:
        """
        Met à jour la période et sauve la config.
        """
        if minutes <= 0:
            warning(f"Période invalide : {minutes} – ignoré")
            return

        self.period = minutes
        # Met à jour la config pydantic puis enregistre
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.period_minutes = minutes
        self._config.save()

        action(f"CyclicTimer #{self.timer_id} nouvelle période : {minutes} min")


    def set_action_duration_seconds(self, seconds: int) -> None:
        """
        Met à jour la durée d’action et sauve la config.
        """
        if seconds <= 0:
            warning(f"Durée d'action invalide : {seconds} – ignoré")
            return

        self.action_duration = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.action_duration_seconds = seconds
        self._config.save()

        action(f"CyclicTimer #{self.timer_id} nouvelle durée : {seconds} s")


    # ───────────────────────── debug repr ─────────────────────

    def __repr__(self) -> str:
        return (
            f"<CyclicTimer #{self.timer_id} "
            f"period={self.period} min "
            f"action={self.action_duration} s "
            f"GPIO={self.component.pin}>"
        )
