# controller/model/CyclicTimer.py
# Author  : Progradius
# License : AGPL-3.0
# -------------------------------------------------------------
#  Minuteur cyclique : déclenche périodiquement un composant
#  Deux modes :
#    • journalier   : period_days, triggers_per_day, first_trigger_hour
#    • séquentiel   : cycles ON/OFF jour & nuit
# -------------------------------------------------------------

from typing import Union
from param.config import AppConfig
from ui.pretty_console import info, action, warning

class CyclicTimer:
    """
    • mode                      → "journalier" ou "séquentiel"
    • period_days               → espacement de jours (journalier)
    • triggers_per_day          → combien d'actions par journée (journalier)
    • first_trigger_hour        → heure du 1ᵉʳ déclenchement (journalier)
    • action_duration_seconds   → durée ON (journalier)
    • on/off_*                  → durées ON/OFF jour-nuit (séquentiel)

    Toute modification met à jour AppConfig et sauvegarde automatiquement.
    """

    # ───────────────────────── init ──────────────────────────
    def __init__(
        self,
        component,
        timer_id: Union[int, str],
        config: AppConfig
    ):
        self.component = component
        self.timer_id  = str(timer_id)
        self._config   = config

        # bloc de config selon l’ID
        settings = (
            config.cyclic1 if self.timer_id == "1"
            else config.cyclic2 if self.timer_id == "2"
            else None
        )
        if settings is None:
            raise ValueError(f"timer_id invalide : {timer_id!r}")

        # lecture initiale
        self.mode                 = settings.mode
        self.period_days          = settings.period_days
        self.triggers_per_day     = settings.triggers_per_day
        self.first_trigger_hour   = settings.first_trigger_hour
        self.action_duration      = settings.action_duration_seconds
        self.on_time_day          = settings.on_time_day
        self.off_time_day         = settings.off_time_day
        self.on_time_night        = settings.on_time_night
        self.off_time_night       = settings.off_time_night

        info(
            f"CyclicTimer #{self.timer_id} chargé → "
            f"mode={self.mode} | "
            f"period={self.period_days} j | "
            f"triggers/j={self.triggers_per_day} | "
            f"first={self.first_trigger_hour}h | "
            f"action={self.action_duration}s | "
            f"on/off day={self.on_time_day}/{self.off_time_day}s | "
            f"on/off night={self.on_time_night}/{self.off_time_night}s | "
            f"GPIO {self.component.pin}"
        )

    # ───────────────────────── getters ───────────────────────
    def get_mode(self) -> str:                 return self.mode
    def get_period_days(self) -> int:          return self.period_days
    def get_triggers_per_day(self) -> int:     return self.triggers_per_day
    def get_first_trigger_hour(self) -> int:   return self.first_trigger_hour
    def get_action_duration(self) -> int:      return self.action_duration
    def get_on_time_day(self) -> int:          return self.on_time_day
    def get_off_time_day(self) -> int:         return self.off_time_day
    def get_on_time_night(self) -> int:        return self.on_time_night
    def get_off_time_night(self) -> int:       return self.off_time_night

    # ───────────────────────── setters (résumé) ──────────────
    # Les setters ci-dessous mettent aussi à jour AppConfig puis enregistrent.
    # Seuls les champs vraiment nécessaires ont été ajoutés.

    def _blk(self):
        return self._config.cyclic1 if self.timer_id == "1" else self._config.cyclic2

    def set_mode(self, mode: str):
        if mode not in ("journalier", "séquentiel"):
            warning(f"Mode invalide : {mode}")
            return
        self.mode = mode; self._blk().mode = mode; self._config.save()
        action(f"Cyclic #{self.timer_id} mode → {mode}")

    def set_period_days(self, days: int):
        if days <= 0: warning("period_days doit être >0"); return
        self.period_days = days; self._blk().period_days = days; self._config.save()
        action(f"Cyclic #{self.timer_id} period_days → {days}")

    def set_triggers_per_day(self, n: int):
        if n <= 0: warning("triggers_per_day doit être >0"); return
        self.triggers_per_day = n; self._blk().triggers_per_day = n; self._config.save()
        action(f"Cyclic #{self.timer_id} triggers_per_day → {n}")

    def set_first_trigger_hour(self, h: int):
        if not 0 <= h < 24: warning("first_trigger_hour 0-23"); return
        self.first_trigger_hour = h; self._blk().first_trigger_hour = h; self._config.save()
        action(f"Cyclic #{self.timer_id} first_trigger_hour → {h}h")

    def set_action_duration_seconds(self, s: int):
        if s <= 0: warning("Durée invalide"); return
        self.action_duration = s; self._blk().action_duration_seconds = s; self._config.save()
        action(f"Cyclic #{self.timer_id} action_duration → {s}s")

    # les setters on/off_* inchangés …

    # ───────────────────────── debug repr ─────────────────────
    def __repr__(self) -> str:
        return (
            f"<CyclicTimer #{self.timer_id} "
            f"mode={self.mode} "
            f"period={self.period_days}j "
            f"trig/j={self.triggers_per_day} "
            f"first={self.first_trigger_hour}h "
            f"action={self.action_duration}s "
            f"on/off day={self.on_time_day}/{self.off_time_day}s "
            f"on/off night={self.on_time_night}/{self.off_time_night}s "
            f"GPIO={self.component.pin}>"
        )
