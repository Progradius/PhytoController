from __future__ import annotations

import sqlite3
import time

import pytest

from utils.operator_history import OperatorHistory


def _create_v1_database(path):
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY, ts REAL NOT NULL, time_state TEXT NOT NULL,
            is_day INTEGER, climate_state TEXT, temp_min REAL, temp_max REAL,
            heater_off_threshold REAL, vent_threshold REAL,
            humidity_threshold REAL
        );
        CREATE TABLE sensor_values (
            sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
            sensor_key TEXT NOT NULL, value REAL, status TEXT NOT NULL,
            PRIMARY KEY (sample_id, sensor_key)
        ) WITHOUT ROWID;
        CREATE TABLE actuator_values (
            sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
            equipment_id TEXT NOT NULL, requested REAL, actual REAL,
            status TEXT NOT NULL, PRIMARY KEY (sample_id, equipment_id)
        ) WITHOUT ROWID;
        CREATE TABLE events (
            id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL,
            subject TEXT NOT NULL, severity TEXT, alarm_id TEXT,
            payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE alarm_occurrences (
            id TEXT PRIMARY KEY, alarm_key TEXT NOT NULL, code TEXT NOT NULL,
            title TEXT NOT NULL, severity TEXT NOT NULL, category TEXT NOT NULL,
            affects_control INTEGER NOT NULL, started_ts REAL NOT NULL,
            updated_ts REAL NOT NULL, resolved_ts REAL, consequence TEXT NOT NULL,
            advice TEXT NOT NULL, link TEXT NOT NULL, detail TEXT NOT NULL,
            acknowledged_ts REAL, acknowledged_by TEXT
        );
        PRAGMA user_version=1;
        """
    )
    connection.commit()
    connection.close()


@pytest.mark.asyncio
async def test_historique_enregistre_et_agrege_les_statuts_qualite(tmp_path):
    path = tmp_path / "operator.sqlite3"
    history = OperatorHistory(path)
    assert history.available is True

    await history.record_sample({
        "ts": time.time(),
        "time_state": "synchronized",
        "is_day": True,
        "climate_state": "NEUTRE",
        "sensors": [{
            "key": "BME280T", "value": None, "raw_value": 20.0,
            "status": "inconsistent", "acquisition_status": "ok",
            "reason_codes": ["frozen"],
        }],
        "actuators": [],
    })
    payload = await history.query_history(
        24,
        {"BME280T": {"key": "BME280T", "label": "Température", "unit": "°C"}},
        {"cyclic_1": {"display_name": "Brumisation"}},
    )

    bucket = payload["buckets"][-1]
    assert bucket["sensors"]["BME280T"]["valid_count"] == 0
    assert bucket["sensor_quality"]["BME280T"] == {"inconsistent": 1}
    assert payload["equipment"]["cyclic_1"]["display_name"] == "Brumisation"
    await history.close()


@pytest.mark.asyncio
async def test_historique_reconstruit_les_durees_depuis_les_gpio_relus(tmp_path):
    history = OperatorHistory(tmp_path / "operator.sqlite3")
    started = time.time() - 600
    session_id = "session-a"

    for timestamp, monotonic_ts in ((started, 1000), (started + 300, 1300)):
        await history.record_sample({
            "ts": timestamp, "monotonic_ts": monotonic_ts,
            "session_id": session_id,
            "time_state": "synchronized", "is_day": True,
            "climate_state": "NEUTRE", "sensors": [],
            "actuators": [{
                "equipment_id": "cyclic_1", "requested": 0,
                "actual": 0, "status": "ok",
            }],
        })
    await history.record_events([
        {"ts": started, "kind": "output", "subject": "cyclic_1", "payload": {
            "actual": 0, "actual_status": "ok", "source": "baseline",
            "session_id": session_id, "monotonic_ts": 1000,
        }},
        {"ts": started + 100, "kind": "output", "subject": "cyclic_1", "payload": {
            "actual": 1, "actual_status": "ok", "source": "transition",
            "session_id": session_id, "monotonic_ts": 1100,
        }},
        # L'heure civile a pris 30 s, l'horloge monotone conserve 120 s de ON.
        {"ts": started + 250, "kind": "output", "subject": "cyclic_1", "payload": {
            "actual": 0, "actual_status": "ok", "source": "transition",
            "session_id": session_id, "monotonic_ts": 1220,
        }},
    ])

    payload = await history.query_history(24, {}, {})
    actuator = payload["actuator_history"]["cyclic_1"]

    assert actuator["covered_seconds"] == pytest.approx(300)
    assert actuator["on_seconds"] == pytest.approx(120)
    assert actuator["transition_count"] == 2
    assert actuator["duration_precision"] == "transition"
    assert [interval["actual"] for interval in actuator["intervals"]] == [0, 1, 0]
    assert all(
        interval["boundary_precision"] == "transition"
        for interval in actuator["intervals"]
    )
    await history.close()


@pytest.mark.asyncio
async def test_historique_ne_prolonge_pas_un_etat_entre_deux_demarrages(tmp_path):
    history = OperatorHistory(tmp_path / "operator.sqlite3")
    now = time.time()
    sessions = (("ancienne", now - 600, 1), ("courante", now - 100, 0))
    events = []
    for session_id, started, actual in sessions:
        for offset in (0, 100):
            await history.record_sample({
                "ts": started + offset, "monotonic_ts": 1000 + offset,
                "session_id": session_id,
                "time_state": "synchronized", "is_day": True,
                "climate_state": "NEUTRE", "sensors": [],
                "actuators": [{
                    "equipment_id": "heater", "requested": actual,
                    "actual": actual, "status": "ok",
                }],
            })
        events.append({
            "ts": started, "kind": "output", "subject": "heater",
            "payload": {
                "actual": actual, "actual_status": "ok", "source": "baseline",
                "session_id": session_id, "monotonic_ts": 1000,
            },
        })
    await history.record_events(events)

    actuator = (await history.query_history(24, {}, {}))["actuator_history"]["heater"]

    assert actuator["covered_seconds"] == pytest.approx(200)
    assert actuator["on_seconds"] == pytest.approx(100)
    assert len(actuator["intervals"]) == 2
    await history.close()


def test_migration_v1_conserve_une_sauvegarde_et_ajoute_la_qualite(tmp_path):
    path = tmp_path / "operator.sqlite3"
    _create_v1_database(path)

    history = OperatorHistory(path)

    assert history.available is True
    backup = path.with_name(path.name + ".pre-v2.bak")
    assert backup.exists()
    assert backup.stat().st_mode & 0o777 == 0o600
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sensor_values)")
        }
        sample_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(samples)")
        }
    finally:
        connection.close()
    assert {"raw_value", "acquisition_status", "reason_json"} <= columns
    assert "session_id" in sample_columns
    assert "monotonic_ts" in sample_columns
