# controller/model/CyclicTimer.py
# Author  : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Minuteur cyclique : déclenche périodiquement un composant
#  Deux modes :
#    • journalier   : déclenchement tous les N jours
#    • séquentiel   : cycles ON/OFF jour & nuit avec durées distinctes
# -------------------------------------------------------------

from typing import Union
from param.config import AppConfig
from ui.pretty_console import info, action, warning

class CyclicTimer:
    """
    • mode                     → "journalier" ou "séquentiel"
    • period_days              → pour mode journalier, nombre de jours entre chaque cycle
    • action_duration_seconds  → durée d'activation dans le mode journalier
    • on_time_day, off_time_day,
      on_time_night, off_time_night → pour mode séquentiel, durées ON/OFF (secondes)
    Toute modification met à jour AppConfig et sauvegarde automatiquement.
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

        # sélection du bloc config adéquat
        if self.timer_id == "1":
            settings = config.cyclic1
        elif self.timer_id == "2":
            settings = config.cyclic2
        else:
            raise ValueError(f"timer_id invalide: {timer_id!r} (doit être '1' ou '2')")

        # lecture initiale
        self.mode                 = settings.mode
        self.period_days          = settings.period_days
        self.action_duration      = settings.action_duration_seconds
        self.on_time_day          = settings.on_time_day
        self.off_time_day         = settings.off_time_day
        self.on_time_night        = settings.on_time_night
        self.off_time_night       = settings.off_time_night

        info(
            f"CyclicTimer #{self.timer_id} chargé → "
            f"mode={self.mode} | "
            f"period_days={self.period_days} j | "
            f"action_duration={self.action_duration}s | "
            f"on/off day={self.on_time_day}/{self.off_time_day}s | "
            f"on/off night={self.on_time_night}/{self.off_time_night}s | "
            f"GPIO {self.component.pin}"
        )

    # ───────────────────────── getters ────────────────────────

    def get_mode(self) -> str:
        return self.mode

    def get_period_days(self) -> int:
        return self.period_days

    def get_action_duration(self) -> int:
        return self.action_duration

    def get_on_time_day(self) -> int:
        return self.on_time_day

    def get_off_time_day(self) -> int:
        return self.off_time_day

    def get_on_time_night(self) -> int:
        return self.on_time_night

    def get_off_time_night(self) -> int:
        return self.off_time_night

    # ───────────────────────── setters ────────────────────────

    def set_mode(self, mode: str) -> None:
        if mode not in ("journalier", "séquentiel"):
            warning(f"Mode invalide : {mode} - ignoré")
            return
        self.mode = mode
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.mode = mode
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} mode défini → {mode}")

    def set_period_days(self, days: int) -> None:
        if days <= 0:
            warning(f"Période invalide : {days} j - ignoré")
            return
        self.period_days = days
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.period_days = days
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} period_days mis à jour → {days} j")

    def set_action_duration_seconds(self, seconds: int) -> None:
        if seconds <= 0:
            warning(f"Durée action invalide : {seconds}s - ignoré")
            return
        self.action_duration = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.action_duration_seconds = seconds
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} action_duration mis à jour → {seconds}s")

    def set_on_time_day(self, seconds: int) -> None:
        if seconds < 0:
            warning(f"ON day invalide : {seconds}s - ignoré")
            return
        self.on_time_day = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.on_time_day = seconds
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} on_time_day → {seconds}s")

    def set_off_time_day(self, seconds: int) -> None:
        if seconds < 0:
            warning(f"OFF day invalide : {seconds}s - ignoré")
            return
        self.off_time_day = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.off_time_day = seconds
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} off_time_day → {seconds}s")

    def set_on_time_night(self, seconds: int) -> None:
        if seconds < 0:
            warning(f"ON night invalide : {seconds}s - ignoré")
            return
        self.on_time_night = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.on_time_night = seconds
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} on_time_night → {seconds}s")

    def set_off_time_night(self, seconds: int) -> None:
        if seconds < 0:
            warning(f"OFF night invalide : {seconds}s - ignoré")
            return
        self.off_time_night = seconds
        blk = self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2
        blk.off_time_night = seconds
        self._config.save()
        action(f"CyclicTimer #{self.timer_id} off_time_night → {seconds}s")

    # ───────────────────────── debug repr ─────────────────────

    def __repr__(self) -> str:
        return (
            f"<CyclicTimer #{self.timer_id} "
            f"mode={self.mode} "
            f"period_days={self.period_days}j "
            f"action={self.action_duration}s "
            f"on/off day={self.on_time_day}/{self.off_time_day}s "
            f"on/off night={self.on_time_night}/{self.off_time_night}s "
            f"GPIO={self.component.pin}>"
        )
