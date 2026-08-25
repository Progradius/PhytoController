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
from param.config       import AppConfig
from param.config_store import shared_config
from utils.pretty_console import debug, info, warning

LOGGER_NAME = "timer.cyclic"

class CyclicTimer:
    """
    • mode                    → "journalier" ou "séquentiel"
    • period_days             → espacement en jours (journalier)
    • triggers_per_day        → nombre d'actions par journée (journalier)
    • first_trigger_hour      → heure du 1er déclenchement (journalier)
    • action_duration_seconds → durée ON (journalier)
    • on/off_*                → durées ON/OFF jour & nuit (séquentiel)

    Toute modification met à jour AppConfig et sauve automatiquement.
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
        self._load_from_config_block()
        info(f"CyclicTimer #{self.timer_id} chargé → {self}", name=LOGGER_NAME)

    def _config_block(self):
        if self.timer_id == "1":
            return self._config.cyclic1
        elif self.timer_id == "2":
            return self._config.cyclic2
        else:
            raise ValueError(f"timer_id invalide : {self.timer_id!r}")

    def _load_from_config_block(self):
        s = self._config_block()
        # commun
        self.mode               = s.mode
        # journalier
        self.period_days        = s.period_days
        self.triggers_per_day   = s.triggers_per_day
        self.first_trigger_hour = s.first_trigger_hour
        self.action_duration    = s.action_duration_seconds
        # séquentiel
        self.on_time_day        = s.on_time_day
        self.off_time_day       = s.off_time_day
        self.on_time_night      = s.on_time_night
        self.off_time_night     = s.off_time_night

    def refresh_from_config(self):
        """
        Recharge les paramètres depuis le magasin partagé.

        `self._config` reste **la même instance** que celle distribuée au boot :
        `refresh()` la mute en place. L'ancienne version remplaçait la
        référence, et le minuteur cessait alors de partager la configuration du
        reste du processus (audit M4).
        """
        self._config = shared_config().refresh()
        self._load_from_config_block()
        debug(f"CyclicTimer #{self.timer_id} rafraîchi depuis AppConfig", name=LOGGER_NAME)

    # ───────────────────────── getters ───────────────────────
    def get_mode(self):               return self.mode
    def get_period_days(self):        return self.period_days
    def get_triggers_per_day(self):   return self.triggers_per_day
    def get_first_trigger_hour(self): return self.first_trigger_hour
    def get_action_duration(self):    return self.action_duration
    def get_on_time_day(self):        return self.on_time_day
    def get_off_time_day(self):       return self.off_time_day
    def get_on_time_night(self):      return self.on_time_night
    def get_off_time_night(self):     return self.off_time_night

    # ───────────────────────── setters ───────────────────────
    def _set_and_save(self, attr: str, value):
        blk = self._config_block()
        setattr(self, attr, value)
        # mapping interne → nom de champ JSON
        json_field = "action_duration_seconds" if attr == "action_duration" else attr
        setattr(blk, json_field, value)
        # Le magasin revalide le modèle complet — les validateurs croisés ne
        # sont pas rejoués par une simple affectation de champ (audit C5).
        shared_config().commit()

    def set_mode(self, mode: str):
        if mode not in ("journalier", "séquentiel"):
            warning(f"Mode invalide : {mode}", name=LOGGER_NAME); return
        self._set_and_save("mode", mode)
        info(f"CyclicTimer #{self.timer_id} mode → {mode}", name=LOGGER_NAME)

    def set_period_days(self, days: int):
        if days <= 0:
            warning(f"period_days invalide : {days}", name=LOGGER_NAME); return
        self._set_and_save("period_days", days)
        info(f"CyclicTimer #{self.timer_id} period_days → {days}", name=LOGGER_NAME)

    def set_triggers_per_day(self, n: int):
        if n <= 0:
            warning(f"triggers_per_day invalide : {n}", name=LOGGER_NAME); return
        self._set_and_save("triggers_per_day", n)
        info(f"CyclicTimer #{self.timer_id} triggers_per_day → {n}", name=LOGGER_NAME)

    def set_first_trigger_hour(self, h: int):
        if not 0 <= h < 24:
            warning(f"first_trigger_hour invalide : {h}", name=LOGGER_NAME); return
        self._set_and_save("first_trigger_hour", h)
        info(f"CyclicTimer #{self.timer_id} first_trigger_hour → {h}h", name=LOGGER_NAME)

    def set_action_duration_seconds(self, sec: int):
        if sec <= 0:
            warning(f"action_duration invalide : {sec}", name=LOGGER_NAME); return
        self._set_and_save("action_duration", sec)
        info(f"CyclicTimer #{self.timer_id} action_duration → {sec}s", name=LOGGER_NAME)

    def set_on_time_day(self, sec: int):
        if sec < 0:
            warning(f"on_time_day invalide : {sec}", name=LOGGER_NAME); return
        self._set_and_save("on_time_day", sec)
        info(f"CyclicTimer #{self.timer_id} on_time_day → {sec}s", name=LOGGER_NAME)

    def set_off_time_day(self, sec: int):
        if sec < 0:
            warning(f"off_time_day invalide : {sec}", name=LOGGER_NAME); return
        self._set_and_save("off_time_day", sec)
        info(f"CyclicTimer #{self.timer_id} off_time_day → {sec}s", name=LOGGER_NAME)

    def set_on_time_night(self, sec: int):
        if sec < 0:
            warning(f"on_time_night invalide : {sec}", name=LOGGER_NAME); return
        self._set_and_save("on_time_night", sec)
        info(f"CyclicTimer #{self.timer_id} on_time_night → {sec}s", name=LOGGER_NAME)

    def set_off_time_night(self, sec: int):
        if sec < 0:
            warning(f"off_time_night invalide : {sec}", name=LOGGER_NAME); return
        self._set_and_save("off_time_night", sec)
        info(f"CyclicTimer #{self.timer_id} off_time_night → {sec}s", name=LOGGER_NAME)

    # ───────────────────────── debug repr ─────────────────────
    def __repr__(self):
        return (
            f"<CyclicTimer #{self.timer_id} mode={self.mode} "
            f"period={self.period_days}j trg/day={self.triggers_per_day} "
            f"first={self.first_trigger_hour}h action={self.action_duration}s "
            f"day {self.on_time_day}/{self.off_time_day}s "
            f"night {self.on_time_night}/{self.off_time_night}s "
            f"GPIO={self.component.pin}>"
        )
