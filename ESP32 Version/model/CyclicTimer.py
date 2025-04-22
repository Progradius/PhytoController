# Author: Progradius
# License: AGPL 3.0

from controller.parameter_handler import read_parameters_from_json


class CyclicTimer:
    """
    Represent a cyclic timer, takes a component as parameter to drive it in cycle mode
    """
    def __init__(self, component, timer_id):
        param = read_parameters_from_json()
        cyclictimer_key = "Cyclic" + str(timer_id) + "_Settings"
        self.period = param[cyclictimer_key]["period_minutes"]
        self.action_duration = param[cyclictimer_key]["action_duration_seconds"]
        self.component = component
        self.timer_id = timer_id

    def get_period(self):
        return self.period

    def get_action_duration(self):
        return self.action_duration

