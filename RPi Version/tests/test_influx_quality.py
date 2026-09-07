from __future__ import annotations

import pytest

from network.web import influx_handler


class _Response:
    status = 204

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def read(self):
        return b""


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, *, params, data):
        self.calls.append((url, params, data))
        return _Response()


@pytest.mark.asyncio
async def test_point_influx_qualite_separe_valeur_suspecte_et_diagnostic(monkeypatch):
    monkeypatch.setattr(influx_handler, "_write_url", "http://influx.invalid/write")
    monkeypatch.setattr(influx_handler, "_write_params", {"db": "phyto"})
    session = _Session()
    outcome, detail = await influx_handler._send_quality_point(session, {
        "key": "BME280T",
        "status": "inconsistent",
        "control_usable": False,
        "raw_value": 18.0,
        "observed_value": 18.4,
        "unchanged_for_s": 1900.0,
        "failures": {"consecutive": 0},
    })

    assert (outcome, detail) == (True, None)
    line = session.calls[0][2]
    assert line.startswith("sensor_quality,sensor=BME280T ")
    assert 'status="inconsistent"' in line
    assert "control_usable=false" in line
    assert "raw_value=18.0" in line
    assert "observed_value=18.4" in line
