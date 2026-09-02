from __future__ import annotations

import asyncio
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from components import cyclic_timer_handler


class _EndCycle(RuntimeError):
    pass


class _Component:
    def __init__(self):
        self.state = 0

    def set_state(self, state):
        self.state = int(bool(state))

    @contextmanager
    def energized(self):
        self.state = 1
        try:
            yield
        finally:
            self.state = 0


class _Timer:
    timer_id = "1"

    def __init__(self):
        self.component = _Component()

    def _load_from_config_block(self):
        pass

    def get_mode(self):
        return "séquentiel"

    def get_on_time_night(self):
        return 2

    def get_off_time_night(self):
        return 3


class _Store:
    def load(self, _section):
        return {}

    def save(self, _section, _payload):
        pass


def _configure(monkeypatch, timer, sleep):
    config = SimpleNamespace(
        cyclic1=SimpleNamespace(enabled=True),
        gpio=SimpleNamespace(cyclic1_pin=22),
    )
    monkeypatch.setattr(
        cyclic_timer_handler, "shared_config",
        lambda: SimpleNamespace(refresh=lambda: config),
    )
    monkeypatch.setattr(cyclic_timer_handler, "shared_store", lambda: _Store())
    monkeypatch.setattr(
        cyclic_timer_handler, "shared_overrides",
        lambda: SimpleNamespace(is_forced_off=lambda _target: False),
    )
    monkeypatch.setattr(
        cyclic_timer_handler, "time_reliability",
        lambda: SimpleNamespace(use_day_settings=lambda: False),
    )
    monkeypatch.setattr(cyclic_timer_handler, "hb_sleep", sleep)
    monkeypatch.setattr(cyclic_timer_handler, "beat", lambda: None)
    monkeypatch.setattr(cyclic_timer_handler, "box", lambda *args, **kwargs: None)


@pytest.mark.asyncio
async def test_sequentiel_publie_apres_activation_et_apres_coupure(monkeypatch):
    timer = _Timer()
    publications = []

    async def sleep(duration):
        if duration == 3:
            raise _EndCycle

    _configure(monkeypatch, timer, sleep)
    monkeypatch.setattr(
        cyclic_timer_handler, "publish",
        lambda _equipment_id, **values: publications.append(
            (values["requested"], timer.component.state)
        ),
    )

    with pytest.raises(_EndCycle):
        await cyclic_timer_handler.timer_cyclic(timer)

    assert publications == [("on", 1), ("off", 0)]


@pytest.mark.asyncio
async def test_sequentiel_publie_la_coupure_apres_annulation(monkeypatch):
    timer = _Timer()
    publications = []

    async def cancelled(_duration):
        raise asyncio.CancelledError

    _configure(monkeypatch, timer, cancelled)
    monkeypatch.setattr(
        cyclic_timer_handler, "publish",
        lambda _equipment_id, **values: publications.append(
            (values["requested"], timer.component.state)
        ),
    )

    with pytest.raises(asyncio.CancelledError):
        await cyclic_timer_handler.timer_cyclic(timer)

    assert publications == [("on", 1), ("off", 0)]
