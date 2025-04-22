# controller/ControllerStatus.py
# Author : Progradius (adapted)
# License: AGPL‑3.0
"""
Fournit une vue « statut système » centralisée :
  • état des composants (ON / OFF)
  • vitesse moteur courante
  • valeurs de paramètres (timers, etc.)
"""

from __future__ import annotations

from controller.ui.pretty_console import info, warning


class ControllerStatus:
    """
    Instanciée une seule fois dans l'application et passée partout
    (PuppetMaster, pages web, API…) pour exposer _en lecture seulement_
    l'état courant du système.
    """

    def __init__(self, parameters, component, motor=None):
        self._p    = parameters     # raccourci
        self._comp = component
        self._motor = motor

        info("ControllerStatus initialisé")

    # ──────────────────────────────────────────────────────────
    #  Lectures simples
    # ──────────────────────────────────────────────────────────
    # Composant « maître » (DailyTimer #1)
    # ----------------------------------------------------------
    def get_component_state(self) -> str:
        return "Enabled" if self._comp.get_state() else "Disabled"

    # Moteur – gère le cas « pas de moteur »
    # ----------------------------------------------------------
    def get_motor_speed(self):
        if self._motor is None:
            warning("get_motor_speed : aucun moteur déclaré")
            return None
        return self._motor.get_motor_speed()

    # Timers
    # ----------------------------------------------------------
    def get_dailytimer_current_start_time(self) -> str:
        return self._p.get_dailytimer1_start_time_formated()

    def get_dailytimer_current_stop_time(self) -> str:
        return self._p.get_dailytimer1_stop_time_formated()

    def get_cyclic_duration(self) -> int:
        return self._p.get_cyclic1_action_duration_seconds()

    def get_cyclic_period(self) -> int:
        return self._p.get_cyclic1_period_minutes()
