
import RPi.GPIO as GPIO
from utils.pretty_console import debug, info, error
from utils.log_dedup import StateLogger

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

LOGGER_NAME = "motor"


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
        self._read_state_log = StateLogger("Lecture des relais moteur", name=LOGGER_NAME)

        # État SÉCURISÉ au démarrage : tout LOW
        for p in (self.pin1, self.pin2, self.pin3, self.pin4):
            GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)

        info(f"Moteur (active-HIGH) initialisé sur BCM {pin1}, {pin2}, {pin3}, {pin4}",
             name=LOGGER_NAME)

    # ───────────────────── helpers internes ──────────────────
    def _set_pin(self, pin: int, high: bool) -> None:
        """
        high=True  → GPIO.HIGH  → relais ON
        high=False → GPIO.LOW   → relais OFF
        """
        try:
            changed = (GPIO.input(pin) == GPIO.HIGH) != high
            GPIO.output(pin, GPIO.HIGH if high else GPIO.LOW)
        except (RuntimeError, ValueError, OSError) as e:
            error(f"GPIO {pin} non pilotable : {e}", name=LOGGER_NAME)
            return

        if changed:
            debug(f"GPIO {pin} ← {'HIGH' if high else 'LOW'}", name=LOGGER_NAME)

    # setters simples
    def set_pin1_value(self, high: bool): self._set_pin(self.pin1, high)
    def set_pin2_value(self, high: bool): self._set_pin(self.pin2, high)
    def set_pin3_value(self, high: bool): self._set_pin(self.pin3, high)
    def set_pin4_value(self, high: bool): self._set_pin(self.pin4, high)

    # ───────────────────────── getters ────────────────────────
    def read_state(self) -> dict:
        """Relit les quatre relais sans confondre arrêt, panne et conflit."""
        try:
            states = {
                1: GPIO.input(self.pin1) == GPIO.HIGH,
                2: GPIO.input(self.pin2) == GPIO.HIGH,
                3: GPIO.input(self.pin3) == GPIO.HIGH,
                4: GPIO.input(self.pin4) == GPIO.HIGH,
            }
        except (RuntimeError, ValueError, OSError) as exc:
            self._read_state_log.fail(exc.__class__.__name__)
            return {"status": "unreadable", "speed": None, "active_speeds": []}

        active = [speed for speed, enabled in states.items() if enabled]
        if not active:
            self._read_state_log.ok()
            return {"status": "ok", "speed": 0, "active_speeds": []}
        if len(active) == 1:
            self._read_state_log.ok()
            return {"status": "ok", "speed": active[0], "active_speeds": active}

        self._read_state_log.fail(f"plusieurs relais actifs : {active}")
        return {"status": "conflict", "speed": None, "active_speeds": active}

    def get_motor_speed(self) -> int:
        """
        Ici on lit l'état sans RIEN ÉCRIRE.
        Comme la carte est active-HIGH, une pin à HIGH = vitesse correspondante.
        S'il y en a plusieurs → on loggue, on renvoie 0.
        """
        state = self.read_state()
        return int(state["speed"]) if state["status"] == "ok" else 0

    # ───────────────────────── utilitaire ─────────────────────
    def all_off(self) -> None:
        """Force l'état sûr : tout LOW."""
        for p in (self.pin1, self.pin2, self.pin3, self.pin4):
            self._set_pin(p, False)
