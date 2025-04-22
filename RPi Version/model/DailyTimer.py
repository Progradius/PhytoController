# Author: Progradius
# License: AGPL 3.0

from datetime import datetime
from function import convert_time_to_minutes
from controller.parameter_handler import read_parameters_from_json


class DailyTimer:
    """
    Représente un minuteur journalier, active un composant entre deux horaires donnés.
    """

    def __init__(self, component, timer_id):
        param = read_parameters_from_json()
        dailytimer_key = f"DailyTimer{timer_id}_Settings"

        self.component = component
        self.timer_id = timer_id

        self.start_hour = param[dailytimer_key]["start_hour"]
        self.start_minute = param[dailytimer_key]["start_minute"]
        self.stop_hour = param[dailytimer_key]["stop_hour"]
        self.stop_minute = param[dailytimer_key]["stop_minute"]

    def get_component_state(self):
        return self.component.get_state()

    def get_start_hour(self):
        return self.start_hour

    def get_start_minute(self):
        return self.start_minute

    def get_stop_hour(self):
        return self.stop_hour

    def get_stop_minute(self):
        return self.stop_minute

    # Setters
    def set_start_time(self, start_hour, start_minute):
        self.start_hour = start_hour
        self.start_minute = start_minute

    def set_stop_time(self, stop_hour, stop_minute):
        self.stop_hour = stop_hour
        self.stop_minute = stop_minute

    def toggle_state_daily(self):
        """
        Active ou désactive le composant en fonction de l’heure courante et des horaires configurés.
        """

        start_time = convert_time_to_minutes(self.start_hour, self.start_minute)
        end_time = convert_time_to_minutes(self.stop_hour, self.stop_minute)

        now = datetime.now()
        current_time_minute = convert_time_to_minutes(now.hour, now.minute)

        if start_time <= end_time:
            is_active = start_time <= current_time_minute <= end_time
        else:
            # Cas où le timer chevauche minuit (ex: 22h à 6h)
            is_active = current_time_minute >= start_time or current_time_minute <= end_time

        if is_active:
            print("On Period")
            print("Next off period in " + str(end_time - current_time_minute) + " minutes")
            if self.component.get_state() == 1:
                self.component.set_state(0)
                print(f"Enabling component at: {now.hour}:{now.minute}:{now.second}")
            else:
                print("Component already ON")
        else:
            print("Off Period")
            print("Next on period in " + str(start_time - current_time_minute) + " minutes")
            if self.component.get_state() == 0:
                self.component.set_state(1)
                print(f"Stopping component at: {now.hour}:{now.minute}:{now.second}")
            else:
                print("Component already OFF")
