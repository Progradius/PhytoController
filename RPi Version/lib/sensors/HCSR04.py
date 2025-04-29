# lib/sensors/HCSR04.py
# Adapté pour Python 3 sur Raspberry Pi
# Author: Progradius (adapté)
# License: AGPL 3.0

import RPi.GPIO as GPIO
import time

class HCSR04:
    """
    Driver HC-SR04 pour Raspberry Pi utilisant RPi.GPIO.
    Mesure la distance via un pulse trigger/echo.
    """

    def __init__(self, trigger_pin, echo_pin, echo_timeout_us=500*2*30):
        """
        trigger_pin      : GPIO BCM du trigger (output)
        echo_pin         : GPIO BCM de l'echo   (input)
        echo_timeout_us  : timeout en µs (microsecondes)
        """
        self.trigger_pin      = trigger_pin
        self.echo_pin         = echo_pin
        # Convertit le timeout en secondes
        self.timeout_s        = echo_timeout_us / 1_000_000.0

        # Initialisation RPi.GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trigger_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.echo_pin,    GPIO.IN)

        # Laisser le capteur se stabiliser
        time.sleep(0.05)

    def _send_pulse_and_wait(self):
        """
        Envoie l'impulsion et mesure la durée du signal echo en secondes.
        Lève OSError('Out of range') si timeout dépassé.
        """
        # --- Envoi de la pulse de 10µs sur trigger ---
        GPIO.output(self.trigger_pin, GPIO.HIGH)
        time.sleep(0.00001)  # 10 µs
        GPIO.output(self.trigger_pin, GPIO.LOW)

        # --- Attente front montant sur echo ---
        start = time.perf_counter()
        while GPIO.input(self.echo_pin) == 0:
            if (time.perf_counter() - start) > self.timeout_s:
                raise OSError('Out of range')
        pulse_start = time.perf_counter()

        # --- Attente front descendant sur echo ---
        while GPIO.input(self.echo_pin) == 1:
            if (time.perf_counter() - pulse_start) > self.timeout_s:
                raise OSError('Out of range')
        pulse_end = time.perf_counter()

        return pulse_end - pulse_start  # durée en secondes

    def distance_cm(self):
        """
        Calcule la distance en centimètres (float).
        vitesse du son ≈ 34300 cm/s.
        """
        pulse_time = self._send_pulse_and_wait()
        # distance = (vitesse * temps) / 2
        return (pulse_time * 34300) / 2

    def distance_mm(self):
        """
        Calcule la distance en millimètres (int).
        """
        return int(self.distance_cm() * 10)

    def cleanup(self):
        """
        Nettoyage des GPIO (à appeler en sortie de programme).
        """
        GPIO.cleanup((self.trigger_pin, self.echo_pin))
