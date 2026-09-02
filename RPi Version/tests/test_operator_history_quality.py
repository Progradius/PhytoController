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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sensor_values)")
        }
    finally:
        connection.close()
    assert {"raw_value", "acquisition_status", "reason_json"} <= columns
