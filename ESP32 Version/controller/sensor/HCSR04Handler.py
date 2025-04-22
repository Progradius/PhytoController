# Author: Progradius
# License: AGPL 3.0

from lib.sensors.HCSR04 import HCSR04


class HCSR04Handler:
    """
    Class used for abstraction of library
    """
    def __init__(self, trigger_pin, echo_pin, echo_timeout_us=1000000):
        self.hcsr = HCSR04(trigger_pin, echo_pin, echo_timeout_us)

    def get_distance_cm(self):
        try:
            return self.hcsr.distance_cm()
        except OSError as e:
            print("Error, check sensor connection/integrity: ", e)
