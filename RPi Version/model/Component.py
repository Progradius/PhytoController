# Author: Progradius
# License: AGPL 3.0

import RPi.GPIO as GPIO

# Configuration globale du mode BCM (une seule fois dans l’app)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

class Component:
    """
    Représente un composant connecté à un GPIO du Raspberry Pi.
    Utilise RPi.GPIO pour contrôler une sortie.
    """

    def __init__(self, pin):
        self.pin_number = pin
        GPIO.setup(self.pin_number, GPIO.OUT)
        # Par défaut on l'active (équivalent à .value(1))
        GPIO.output(self.pin_number, GPIO.HIGH)

    # Setters
    def set_state(self, value):
        """
        Définit l’état du GPIO : 1 = HIGH, 0 = LOW
        """
        GPIO.output(self.pin_number, GPIO.HIGH if value else GPIO.LOW)

    # Getters
    def get_pin(self):
        """
        Retourne le numéro de pin GPIO (BCM)
        """
        return self.pin_number

    def get_state(self):
        """
        Retourne l'état actuel de la broche GPIO (0 ou 1)
        """
        return GPIO.input(self.pin_number)
