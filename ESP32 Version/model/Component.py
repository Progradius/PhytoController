# Author: Progradius
# License: AGPL 3.0

from machine import Pin


class Component:
    """
    Represent a component, takes a pin value as parameter to set the GPIO
    """
    def __init__(self, pin):
        self.pin = Pin(pin, Pin.OUT)
        self.pin.value(1)

    # Setters
    def set_state(self, value):
        self.pin.value(value)

    # Getters
    def get_pin(self):
        return self.pin

    def get_state(self):
        return self.pin.value()
