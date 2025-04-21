# Author: Progradius
# License: AGPL 3.0

from controller.parameter_handler import read_parameters_from_json


class CyclicTimer:
    """
    Représente un minuteur cyclique qui active un composant de manière périodique.
    """

    def __init__(self, component, timer_id):
        param = read_parameters_from_json()
        settings_key = f"Cyclic{timer_id}_Settings"
        self.period = param[settings_key]["period_minutes"]
        self.action_duration = param[settings_key]["action_duration_seconds"]
        self.component = component
        self.timer_id = timer_id

    def get_period(self):
        """
        Retourne la période du cycle (en minutes)
        """
        return self.period

    def get_action_duration(self):
        """
        Retourne la durée d’activation du composant dans un cycle (en secondes)
        """
        return self.action_duration
