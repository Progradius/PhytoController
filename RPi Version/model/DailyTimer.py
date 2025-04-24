# controller/model/DailyTimer.py
# Author  : Progradius 
# License : AGPL-3.0
# -------------------------------------------------------------
#  Minuteur journalier : active un composant entre deux horaires
# -------------------------------------------------------------

from datetime          import datetime
from function          import convert_time_to_minutes
from param.config      import AppConfig
from ui.pretty_console import info, warning, clock, action, success

class DailyTimer:
    """
    Active/désactive *component* entre deux horaires stockés
    dans AppConfig.daily_timer{N}.  
    • `timer_id` ∈ {1,2} → lit daily_timer1 ou daily_timer2.
    """

    def __init__(self, component, timer_id: int, config: AppConfig):
        self.component = component
        self.timer_id  = int(timer_id)
        self._config   = config

        # choix du bloc config
        if self.timer_id == 1:
            settings = config.daily_timer1
        elif self.timer_id == 2:
            settings = config.daily_timer2
        else:
            raise ValueError(f"timer_id invalide : {self.timer_id!r}")

        self.start_hour   = settings.start_hour
        self.start_minute = settings.start_minute
        self.stop_hour    = settings.stop_hour
        self.stop_minute  = settings.stop_minute

        info(
            f"DailyTimer #{self.timer_id} chargé : "
            f"{self.start_hour:02d}:{self.start_minute:02d} → "
            f"{self.stop_hour:02d}:{self.stop_minute:02d}"
        )

        # 🔄 Synchronisation immédiate de la broche au bon état
        changed = self.toggle_state_daily()
        if changed:
            state = "ON" if self.component.get_state() else "OFF"
            success(f"DailyTimer #{self.timer_id} initialisé → {state}")

    def refresh_from_config(self):
        """
        Recharge les horaires depuis le JSON en cours.
        À appeler à chaque boucle pour prise en compte à chaud.
        """
        self._config = AppConfig.load()
        blk = self._config.daily_timer1 if self.timer_id == 1 else self._config.daily_timer2
        self.start_hour   = blk.start_hour
        self.start_minute = blk.start_minute
        self.stop_hour    = blk.stop_hour
        self.stop_minute  = blk.stop_minute
        success(f"DailyTimer #{self.timer_id} rafraîchi depuis AppConfig: "
                f"{self.start_hour:02d}:{self.start_minute:02d} → "
                f"{self.stop_hour:02d}:{self.stop_minute:02d}")

    def get_component_state(self) -> bool:
        return self.component.get_state()

    def set_start_time(self, h: int, m: int):
        self.start_hour, self.start_minute = h, m
        blk = self._config.daily_timer1 if self.timer_id == 1 else self._config.daily_timer2
        blk.start_hour   = h
        blk.start_minute = m
        self._config.save()
        info(f"DailyTimer #{self.timer_id} start → {h:02d}:{m:02d}")

    def set_stop_time(self, h: int, m: int):
        self.stop_hour, self.stop_minute = h, m
        blk = self._config.daily_timer1 if self.timer_id == 1 else self._config.daily_timer2
        blk.stop_hour    = h
        blk.stop_minute  = m
        self._config.save()
        info(f"DailyTimer #{self.timer_id} stop → {h:02d}:{m:02d}")

    def toggle_state_daily(self) -> bool:
        """
        À appeler périodiquement : active/désactive selon l'heure.
        Retourne True si l’état GPIO a été changé.
        """
        start = convert_time_to_minutes(self.start_hour, self.start_minute)
        stop  = convert_time_to_minutes(self.stop_hour,  self.stop_minute)
        now   = datetime.now()
        now_m = convert_time_to_minutes(now.hour, now.minute)

        active = (
            (start <= now_m <= stop) if start <= stop
            else (now_m >= start or now_m <= stop)
        )
        current = bool(self.component.get_state())
        changed = False

        if active and not current:
            clock(f"DailyTimer #{self.timer_id} → ON")
            action(f"Activation GPIO {self.component.pin}")
            self.component.set_state(1)
            changed = True

        if not active and current:
            clock(f"DailyTimer #{self.timer_id} → OFF")
            action(f"Désactivation GPIO {self.component.pin}")
            self.component.set_state(0)
            changed = True

        return changed
