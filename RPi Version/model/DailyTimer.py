# controller/components/DailyTimer.py
# Author  : Progradius (refactorisé)
# License : AGPL-3.0
# -------------------------------------------------------------
#  Minuteur journalier : active un composant entre deux horaires
# -------------------------------------------------------------

from datetime import datetime
from function import convert_time_to_minutes
from param.config import AppConfig
from ui.pretty_console import info, warning, clock, action

class DailyTimer:
    """
    Active/désactive *component* entre deux horaires (HH:MM) stockés
    dans AppConfig.daily_timer{N}.  
    • `timer_id` ∈ {1,2} → lit config.daily_timer1 ou daily_timer2
    """

    def __init__(self, component, timer_id: int, config: AppConfig):
        self.component = component
        self.timer_id  = int(timer_id)
        self._config   = config

        # Sélectionne le bon bloc dans la config
        if self.timer_id == 1:
            settings = self._config.daily_timer1
        elif self.timer_id == 2:
            settings = self._config.daily_timer2
        else:
            raise ValueError(f"timer_id invalide : {self.timer_id!r}")

        # Initialise les heures
        self.start_hour   = settings.start_hour
        self.start_minute = settings.start_minute
        self.stop_hour    = settings.stop_hour
        self.stop_minute  = settings.stop_minute

        info(
            f"DailyTimer #{self.timer_id} chargé : "
            f"{self.start_hour:02d}:{self.start_minute:02d} → "
            f"{self.stop_hour:02d}:{self.stop_minute:02d}"
        )

    # ────────────────────────── getters & setters ─────────────

    def get_component_state(self) -> bool:
        return self.component.get_state()

    def set_start_time(self, h: int, m: int):
        """
        Modifie l'heure de début dans l'objet et sauve la config.
        """
        self.start_hour, self.start_minute = h, m
        # Met à jour la config pydantic puis réécrit le JSON
        block = self._config.daily_timer1 if self.timer_id == 1 else self._config.daily_timer2
        block.start_hour   = h
        block.start_minute = m
        self._config.save()
        info(f"DailyTimer #{self.timer_id} start mis à jour → {h:02d}:{m:02d}")

    def set_stop_time(self, h: int, m: int):
        """
        Modifie l'heure de fin dans l'objet et sauve la config.
        """
        self.stop_hour, self.stop_minute = h, m
        block = self._config.daily_timer1 if self.timer_id == 1 else self._config.daily_timer2
        block.stop_hour   = h
        block.stop_minute = m
        self._config.save()
        info(f"DailyTimer #{self.timer_id} stop mis à jour → {h:02d}:{m:02d}")

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

        # la période passe-t-elle sur minuit ?
        active = (
            start <= now_m <= stop if start <= stop
            else now_m >= start or now_m <= stop
        )

        if active:
            mins_left = (stop - now_m) % 1440
            clock(f"DailyTimer #{self.timer_id} : ON — arrêt dans {mins_left} min")
            if not self.component.get_state():
                action(f"Activation du composant (GPIO {self.component.pin})")
                self.component.set_state(1)
        else:
            mins_left = (start - now_m) % 1440
            clock(f"DailyTimer #{self.timer_id} : OFF — mise en marche dans {mins_left} min")
            if self.component.get_state():
                action(f"Désactivation du composant (GPIO {self.component.pin})")
                self.component.set_state(0)
            else:
                warning("Composant déjà à l'état OFF")
