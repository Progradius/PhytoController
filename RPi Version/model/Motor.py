# model/Motor.py
# Author: Progradius
# License: AGPL 3.0

import RPi.GPIO as GPIO

# Configuration globale (appelée une seule fois, p. ex. dans main.py)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

class Motor:
    """
    Classe représentant un moteur piloté par 4 broches GPIO.
    """

    def __init__(self, pin1, pin2, pin3, pin4):
        self.pin1 = pin1
        self.pin2 = pin2
        self.pin3 = pin3
        self.pin4 = pin4

        for pin in (self.pin1, self.pin2, self.pin3, self.pin4):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    # Setters
    def set_pin1_value(self, value):
        GPIO.output(self.pin1, GPIO.HIGH if value else GPIO.LOW)

    def set_pin2_value(self, value):
        GPIO.output(self.pin2, GPIO.HIGH if value else GPIO.LOW)

    def set_pin3_value(self, value):
        GPIO.output(self.pin3, GPIO.HIGH if value else GPIO.LOW)

    def set_pin4_value(self, value):
        GPIO.output(self.pin4, GPIO.HIGH if value else GPIO.LOW)

    # Getter simulant la vitesse du moteur en fonction de la broche activée
    def get_motor_speed(self):
        """
        Retourne un int de 0 à 4 correspondant à la broche active :
         - 1 si pin1 active
         - 2 si pin2 active
         - 3 si pin3 active
         - 4 si pin4 active
         - 0 si aucune pin ou plusieurs pins actives
        """
        # On vérifie chacune des broches en priorité
        if GPIO.input(self.pin1):
            return 1
        elif GPIO.input(self.pin2):
            return 2
        elif GPIO.input(self.pin3):
            return 3
        elif GPIO.input(self.pin4):
            return 4
        else:
            return 0
