# Author: Progradius
# License: AGPL 3.0

import RPi.GPIO as GPIO

# Configuration globale (doit être appelée une seule fois dans ton app, si ce n’est pas déjà fait ailleurs)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

class Motor:
    """
    Classe représentant un moteur contrôlé par 4 broches GPIO.
    Utilise la bibliothèque RPi.GPIO.
    """

    def __init__(self, pin1, pin2, pin3, pin4):
        self.pin1 = pin1
        self.pin2 = pin2
        self.pin3 = pin3
        self.pin4 = pin4

        for pin in [self.pin1, self.pin2, self.pin3, self.pin4]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    # Setters
    def set_pin1_value(self, value):
        GPIO.output(self.pin1, GPIO.HIGH if value else GPIO.LOW)

    def set_pin2_value(self, value):
        GPIO.output(self.pin2, GPIO.HIGH if value else GPIO.LOW)

    def set_pin3_value(self, value):
        GPIO.output(self.pin3, GPIO.HIGH if value else GPIO.LOW)

    def set_pin4_value(self, value):
        GPIO.output(self.pin4, GPIO.HIGH if value else GPIO.LOW)

    # Getter vitesse moteur simulée (à adapter selon ton vrai usage moteur)
    def get_motor_speed(self):
        if GPIO.input(self.pin1):
            return 1
        if GPIO.input(self.pin2):
