from __future__ import annotations

import sys
from types import ModuleType


class FakeGPIO(ModuleType):
    BCM = "BCM"
    OUT = "OUT"
    IN = "IN"
    HIGH = 1
    LOW = 0

    def __init__(self) -> None:
        super().__init__("RPi.GPIO")
        self.mode = None
        self.warnings = True
        self.pins: dict[int, dict[str, object]] = {}
        self.events: list[tuple] = []
        self.cleanup_calls = 0

    def setwarnings(self, enabled) -> None:
        self.warnings = bool(enabled)

    def setmode(self, mode) -> None:
        self.mode = mode

    def setup(self, pin, direction, initial=None, **_kwargs) -> None:
        previous = self.pins.get(pin, {})
        value = previous.get("value", self.LOW) if initial is None else initial
        self.pins[pin] = {"direction": direction, "value": value}
        self.events.append(("setup", pin, direction, value, self.snapshot()))

    def output(self, pin, value) -> None:
        if pin not in self.pins:
            raise RuntimeError(f"GPIO {pin} non configuré")
        self.pins[pin]["value"] = value
        self.events.append(("output", pin, value, self.snapshot()))

    def input(self, pin):
        if pin not in self.pins:
            raise RuntimeError(f"GPIO {pin} non configuré")
        return self.pins[pin]["value"]

    def cleanup(self, *_args, **_kwargs) -> None:
        self.cleanup_calls += 1
        raise AssertionError("GPIO.cleanup() est interdit par le modèle de sûreté")

    def snapshot(self) -> dict[int, int]:
        return {pin: int(state["value"]) for pin, state in self.pins.items()}

    def clear_events(self) -> None:
        self.events.clear()


def install(monkeypatch) -> FakeGPIO:
    """Installe RPi.GPIO avant l'import du code matériel à exercer."""
    gpio = FakeGPIO()
    package = ModuleType("RPi")
    package.GPIO = gpio
    monkeypatch.setitem(sys.modules, "RPi", package)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    for name in ("model.Component", "model.Motor", "components.MotorHandler"):
        sys.modules.pop(name, None)
    return gpio
