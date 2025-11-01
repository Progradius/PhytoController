
import RPi.GPIO as GPIO
from utils.pretty_console import info, warning, error

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)


class Motor:
    """
    Carte relais active HAUT.

    Tableau attendu :

        Vitesse   pin1   pin2   pin3   pin4
        -----------------------------------
          0        LOW    LOW    LOW    LOW
          1        HIGH   LOW    LOW    LOW
          2        LOW    HIGH   LOW    LOW
          3        LOW    LOW    HIGH   LOW
          4        LOW    LOW    LOW    HIGH
    """

    def __init__(self, pin1: int, pin2: int, pin3: int, pin4: int):
        self.pin1, self.pin2, self.pin3, self.pin4 = pin1, pin2, pin3, pin4

        # État SÉCURISÉ au démarrage : tout LOW
        for p in (self.pin1, self.pin2, self.pin3, self.pin4):
            GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)

        info(f"Moteur (active-HIGH) initialisé sur BCM {pin1}, {pin2}, {pin3}, {pin4}")

    # ───────────────────── helpers internes ──────────────────
    def _set_pin(self, pin: int, high: bool) -> None:
        """
        high=True  → GPIO.HIGH  → relais ON
        high=False → GPIO.LOW   → relais OFF
        """
        try:
            GPIO.output(pin, GPIO.HIGH if high else GPIO.LOW)
        except RuntimeError as e:
            warning(f"[MOTOR] GPIO {pin} non prêt : {e}")

    # setters simples
    def set_pin1_value(self, high: bool): self._set_pin(self.pin1, high)
    def set_pin2_value(self, high: bool): self._set_pin(self.pin2, high)
    def set_pin3_value(self, high: bool): self._set_pin(self.pin3, high)
    def set_pin4_value(self, high: bool): self._set_pin(self.pin4, high)

    # ───────────────────────── getters ────────────────────────
    def get_motor_speed(self) -> int:
        """
        Ici on lit l’état sans RIEN ÉCRIRE.
        Comme la carte est active-HIGH, une pin à HIGH = vitesse correspondante.
        S’il y en a plusieurs → on loggue, on renvoie 0.
        """
        try:
            states = {
                1: GPIO.input(self.pin1) == GPIO.HIGH,
                2: GPIO.input(self.pin2) == GPIO.HIGH,
                3: GPIO.input(self.pin3) == GPIO.HIGH,
                4: GPIO.input(self.pin4) == GPIO.HIGH,
            }
        except RuntimeError as e:
            warning(f"[MOTOR] Lecture vitesse impossible (GPIO nettoyés ?) : {e}")
            return 0

        active = [spd for spd, on in states.items() if on]

        if len(active) == 0:
            return 0
        if len(active) == 1:
            return active[0]

        # plusieurs pins à HIGH → c’est dangereux, mais ON NE TOUCHE PAS
        error(f"[MOTOR] État dangereux : plusieurs relais moteur actifs : {active}")
        return 0

    # ───────────────────────── utilitaire ─────────────────────
    def all_off(self) -> None:
        """Force l’état sûr : tout LOW."""
        for p in (self.pin1, self.pin2, self.pin3, self.pin4):
            self._set_pin(p, False)
