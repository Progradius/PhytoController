# Author: Progradius
# License: AGPL 3.0

class ControllerStatus:
    """ Class used to retrieve the current system state """

    def __init__(self, parameters, component, motor=None):
        self.component = component
        self.motor = motor
        self.parameters = parameters

    def get_component_state(self):
        """ Get component state,currently one, refactor this for more """
        if self.component.get_state() == 1:
            return "Enabled"
        else:
            return "Disabled"

    def get_motor_speed(self):
        """ Retrieve current motor speed """
        return self.motor.get_motor_speed()

    def get_dailytimer_current_start_time(self):
        """ Get Dailytimer1 start settings """
        return self.parameters.get_dailytimer1_start_time_formated()

    def get_dailytimer_current_stop_time(self):
        """ Get Dailytimer1 stop settings """
        return self.parameters.get_dailytimer1_stop_time_formated()

    def get_cyclic_duration(self):
        """ Get Cyclic1 duration settings """
        return self.parameters.get_cyclic1_action_duration_seconds()

    def get_cyclic_period(self):
        """ Get Cyclic1 period settings """
        return self.parameters.get_cyclic1_period_minutes()
