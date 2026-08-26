from __future__ import annotations

import asyncio
import importlib

import pytest

from tests.fakes.rpi_gpio import install


@pytest.fixture
def fake_gpio(monkeypatch):
    return install(monkeypatch)


def test_component_actif_bas_et_etat_terminal(fake_gpio):
    component_module = importlib.import_module("model.Component")
    component = component_module.Component(23)

    assert fake_gpio.pins[23] == {"direction": fake_gpio.OUT, "value": fake_gpio.HIGH}
    assert component.get_state() == 0

    component.set_state(1)
    assert fake_gpio.input(23) == fake_gpio.LOW
    assert component.get_state() == 1

    component.set_state(0)
    assert fake_gpio.input(23) == fake_gpio.HIGH
    assert component.get_state() == 0
    assert fake_gpio.cleanup_calls == 0


def test_energized_coupe_sur_sortie_normale_et_exception(fake_gpio):
    component = importlib.import_module("model.Component").Component(23)
    fake_gpio.clear_events()

    with component.energized():
        assert fake_gpio.input(23) == fake_gpio.LOW
    assert fake_gpio.input(23) == fake_gpio.HIGH

    with pytest.raises(RuntimeError):
        with component.energized():
            raise RuntimeError("panne injectée")
    assert fake_gpio.input(23) == fake_gpio.HIGH
    levels = [event[2] for event in fake_gpio.events if event[0] == "output"]
    assert levels == [fake_gpio.LOW, fake_gpio.HIGH, fake_gpio.LOW, fake_gpio.HIGH]


async def test_energized_coupe_sur_annulation(fake_gpio):
    component = importlib.import_module("model.Component").Component(23)
    entered = asyncio.Event()

    async def work():
        with component.energized():
            entered.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(work())
    await entered.wait()
    assert fake_gpio.input(23) == fake_gpio.LOW
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fake_gpio.input(23) == fake_gpio.HIGH


def test_moteur_actif_haut_break_before_make(fake_gpio, valid_config, monkeypatch):
    module = importlib.import_module("components.MotorHandler")
    monkeypatch.setattr(module, "sleep", lambda _delay: None)
    handler = module.MotorHandler(valid_config)
    pins = [16, 17, 18, 19]
    assert [fake_gpio.input(pin) for pin in pins] == [0, 0, 0, 0]

    fake_gpio.clear_events()
    assert handler.set_motor_speed(1) is True
    assert [fake_gpio.input(pin) for pin in pins] == [1, 0, 0, 0]
    assert handler.set_motor_speed(4) is True
    assert [fake_gpio.input(pin) for pin in pins] == [0, 0, 0, 1]

    output_events = [event for event in fake_gpio.events if event[0] == "output"]
    assert output_events
    for event in output_events:
        snapshot = event[3]
        assert sum(snapshot.get(pin, 0) == fake_gpio.HIGH for pin in pins) <= 1

    handler.all_off()
    assert [fake_gpio.input(pin) for pin in pins] == [0, 0, 0, 0]
    assert fake_gpio.cleanup_calls == 0


def test_moteur_detecte_conflit_et_all_off_le_recupere(
    fake_gpio, valid_config, monkeypatch
):
    module = importlib.import_module("components.MotorHandler")
    monkeypatch.setattr(module, "sleep", lambda _delay: None)
    handler = module.MotorHandler(valid_config)
    fake_gpio.output(16, fake_gpio.HIGH)
    fake_gpio.output(17, fake_gpio.HIGH)

    assert handler.motor.read_state() == {
        "status": "conflict", "speed": None, "active_speeds": [1, 2]
    }
    handler.all_off()
    assert handler.motor.get_motor_speed() == 0
