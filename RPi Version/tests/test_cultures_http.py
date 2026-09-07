import json
import uuid

import pytest

from tests.test_http_server import web_context, CSRF_TOKEN
from tests.test_cultures import create


@pytest.mark.parametrize("value, expected", [
    (None, "—"),
    ("2026-09-07", "07/09/2026"),
    ("2026-10-25T00:30:00Z", "25/10/2026 à 02:30:00 (UTC+0200)"),
    ("2026-10-25T01:30:00Z", "25/10/2026 à 02:30:00 (UTC+0100)"),
    ("2026-09-06T22:30:00Z", "07/09/2026 à 00:30:00 (UTC+0200)"),
])
def test_dates_lisibles_sans_ambiguite_au_changement_heure(value, expected):
    from network.web.pages import env
    assert env.filters["culture_date"](value, "Europe/Paris") == expected


async def test_carnet_http_securite_et_absence_effet_controle(web_context, monkeypatch):
    client, server, config, sensors, supervisor = web_context
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_args: writes.append("save"))
    monkeypatch.setattr(config, "commit", lambda *_args: writes.append("commit"))
    response = await client.get("/cultures")
    assert response.status == 200
    assert "Carnet durable" in await response.text()
    assert response.headers["Cache-Control"] == "no-store"
    command = create(name='<script>alert("x")</script>')
    assert (await client.post("/api/v1/cultures", json=command)).status == 403
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    assert (await client.post("/api/v1/cultures", json=command, headers={**headers, "Origin": "http://evil.example"})).status == 403
    response = await client.post("/api/v1/cultures", json=command, headers=headers)
    assert response.status == 200, await response.text()
    result = await response.json()
    response = await client.get("/cultures/" + result["subject_id"])
    assert response.status == 200
    html = await response.text()
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    detail = await (await client.get("/api/v1/cultures/" + result["subject_id"])).json()
    assert detail["subject"]["count"] == 8
    assert (await client.get("/api/v1/cultures?offset=-1")).status == 400
    assert (await client.post("/api/v1/cultures", json=[1], headers=headers)).status == 400
    assert (await client.post("/api/v1/cultures", data="{", headers={**headers, "Content-Type": "application/json"})).status == 400
    assert (await client.post("/api/v1/cultures", json={"note": "x" * 70000}, headers=headers)).status == 413
    for format_name in ("json", "csv", "sqlite3"):
        response = await client.get("/api/v1/cultures/export?format=" + format_name)
        assert response.status == 200 and "attachment" in response.headers["Content-Disposition"]
    assert config.current.to_json() == original and writes == []
    assert sensors.reconfigured == 0
    assert (await client.get("/health/ready")).status == 200


async def test_panne_carnet_ne_degrade_pas_controle(web_context, monkeypatch):
    from utils.culture_store import CultureUnavailable
    client, server, *_ = web_context
    async def failed(*_args):
        raise CultureUnavailable("Carnet indisponible")
    monkeypatch.setattr(server.cultures.store, "call", failed)
    assert (await client.get("/cultures")).status == 503
    assert (await client.get("/api/v1/cultures")).status == 503
    assert (await client.get("/")).status == 200
    assert (await client.get("/health/ready")).status == 200
