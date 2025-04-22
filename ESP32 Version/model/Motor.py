# Author: Progradius
# License: AGPL 3.0

from machine import Pin


class Motor:
    """
    Motor class used to represent a motor, obviously ^^
    """

    def __init__(self, pin1, pin2, pin3, pin4):
        self.pin1 = Pin(pin1, Pin.OUT)
        self.pin2 = Pin(pin2, Pin.OUT)
        self.pin3 = Pin(pin3, Pin.OUT)
        self.pin4 = Pin(pin4, Pin.OUT)

    # Setters
    def set_pin1_value(self, value):
        self.pin1.value(value)

    def set_pin2_value(self, value):
        self.pin2.value(value)

    def set_pin3_value(self, value):
        self.pin3.value(value)

    def set_pin4_value(self, value):
        self.pin4.value(value)

    def get_motor_speed(self):
        if self.pin1.value() == 1:
            return 1

        if self.pin2.value() == 2:
            return 2

        if self.pin3.value() == 3:
            return 3

        if self.pin4.value() == 4:
            return 4

