# Author: Progradius
# License: AGPL 3.0

from machine import RTC
from function import convert_time_to_minutes
from controller.parameter_handler import read_parameters_from_json


class DailyTimer:
    """
    Represent a daily timer, takes a start and stop time to toggle a component
    """
    def __init__(self, component, timer_id):
        param = read_parameters_from_json()
        self.component = component
        dailytimer_key = "DailyTimer" + str(timer_id) + "_Settings"
        self.start_hour = param[dailytimer_key]["start_hour"]
        self.start_minute = param[dailytimer_key]["start_minute"]
        self.stop_hour = param[dailytimer_key]["stop_hour"]
        self.stop_minute = param[dailytimer_key]["stop_minute"]
        self.timer_id = timer_id

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
        """ Toggle GPIO state depending on current time """

        # Converting time into minutes and comparing them against current time in minute
        # Selected start time
        start_time = convert_time_to_minutes(hour=self.start_hour, minute=self.start_minute)
        # Selected stop time
        end_time = convert_time_to_minutes(hour=self.stop_hour, minute=self.stop_minute)
        # Current time from NTP server
        current_time = RTC().datetime()
        # Current time in minutes
        current_time_minute = convert_time_to_minutes(hour=current_time[4], minute=current_time[5])
        # Check if the current time is in the On time range
        if current_time_minute >= start_time or current_time_minute <= end_time:
            print("On Period")
            print("Next off period in " + str(end_time - current_time_minute) + " minutes")
            # Turn the component ON
            if self.component.get_state() == 1:
                self.component.set_state(0)
                print("Enabling component at: " +
                      str(current_time[4]) + ':' +
                      str(current_time[5]) + ':' +
                      str(current_time[6]))
            else:
                print("Component already ON")

        else:
            print("Off Period")
            print("Next on period in " + str(start_time - current_time_minute) + " minutes")
            # Turn the component OFF
            if self.component.get_state() == 0:
                self.component.set_state(1)
                print("Stopping component at: " +
                      str(current_time[4]) + ':' +
                      str(current_time[5]) + ':' +
                      str(current_time[6]))
            else:
                print("Component already OFF")

