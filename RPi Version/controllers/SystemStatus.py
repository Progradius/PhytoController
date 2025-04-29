# controller/SystemStatus.py
# Author : Progradius
# License: AGPL-3.0
"""
Fournit une vue « statut système » centralisée :
  • état des composants (ON / OFF)
  • vitesse moteur courante
  • valeurs de paramètres (timers, etc.)
"""

from __future__             import annotations

from ui.pretty_console      import info, warning
from param.config           import AppConfig


class SystemStatus:
    """
    Instanciée une seule fois dans l'application et passée partout
    (PuppetMaster, pages web, API…) pour exposer _en lecture seulement_
    l'état courant du système.
    """

    def __init__(
        self,
        config: AppConfig,
        component,
        motor = None
    ):
        self._config   = config
        self._comp     = component
        self._motor    = motor

        info("SystemStatus initialisé")

    # ──────────────────────────────────────────────────────────
    #  Lectures simples
    # ──────────────────────────────────────────────────────────

    def get_component_state(self) -> str:
        """État ON/OFF du composant principal."""
        return "Enabled" if self._comp.get_state() else "Disabled"

    def get_motor_speed(self) -> int | None:
        """Vitesse actuelle du moteur (0–4), ou None si aucun moteur."""
        if self._motor is None:
            warning("get_motor_speed : aucun moteur déclaré")
            return None
        return self._motor.get_motor_speed()

    # ──────────────────────────────────────────────────────────
    #  Timers (DailyTimer #1)
    # ──────────────────────────────────────────────────────────

    def get_dailytimer_current_start_time(self) -> str:
        """HH:MM formaté pour DailyTimer #1."""
        dt = self._config.daily_timer1
        return f"{dt.start_hour:02d}:{dt.start_minute:02d}"

    def get_dailytimer_current_stop_time(self) -> str:
        """HH:MM formaté pour DailyTimer #1."""
        dt = self._config.daily_timer1
        return f"{dt.stop_hour:02d}:{dt.stop_minute:02d}"

    # ──────────────────────────────────────────────────────────
    #  Timers (CyclicTimer #1)
    # ──────────────────────────────────────────────────────────

    def get_cyclic_period(self) -> int:
        """Période en minutes du CyclicTimer #1."""
        return self._config.cyclic1.period_minutes

    def get_cyclic_duration(self) -> int:
        """Durée d’action en secondes du CyclicTimer #1."""
        return self._config.cyclic1.action_duration_seconds
