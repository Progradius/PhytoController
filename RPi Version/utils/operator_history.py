"""Historique opérateur SQLite, entièrement déporté hors de l'event loop."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from utils.alarm_manager import AlarmOccurrence, AlarmTransition


SCHEMA_VERSION = 2
RETENTION_SECONDS = 72 * 3600
ALARM_RETENTION_SECONDS = 30 * 24 * 3600
MAX_ALARM_OCCURRENCES = 2000


class HistoryUnavailable(RuntimeError):
    pass


class OperatorHistory:
    FILE = Path(__file__).parent.parent / "param" / "operator_history.sqlite3"

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else self.FILE
        startup_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phyto-history-boot")
        self._executor: ThreadPoolExecutor | None = None
        self._connection: sqlite3.Connection | None = None
        self._owner_thread_id: int | None = None
        self._closed = False
        self.available = False
        self.last_error_class: str | None = None
        self.last_sample_ts: float | None = None
        self.recovered_corrupt_path: str | None = None
        self._startup_alarms: list[dict] = []
        try:
            self._startup_alarms = startup_executor.submit(self._initialize).result()
        except Exception as exc:
            self.available = False
            self.last_error_class = exc.__class__.__name__
        finally:
            if self._connection is not None:
                try:
                    startup_executor.submit(self._close_connection).result()
                except Exception:
                    pass
            startup_executor.shutdown(wait=True, cancel_futures=True)
            self._owner_thread_id = None
            self._connection = None

    @property
    def startup_alarms(self) -> list[dict]:
        return [dict(item) for item in self._startup_alarms]

    def snapshot(self) -> dict:
        return {
            "available": self.available,
            "last_sample_ts": self.last_sample_ts,
            "last_error_class": self.last_error_class,
            "retention_hours": 72,
            "recovered_corrupt_path": self.recovered_corrupt_path,
        }

    def _initialize(self) -> list[dict]:
        self._owner_thread_id = threading.get_ident()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(str(self.path), timeout=3.0)
            if existed:
                result = connection.execute("PRAGMA quick_check").fetchall()
                if result != [("ok",)]:
                    raise sqlite3.DatabaseError("quick_check en échec")
        except Exception:
            try:
                if connection is not None:
                    connection.close()
            except Exception:
                pass
            if existed:
                self._preserve_corrupt_files()
            connection = sqlite3.connect(str(self.path), timeout=3.0)

        self._connection = connection
        connection.execute("PRAGMA auto_vacuum=NONE")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=3000")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            raise HistoryUnavailable(f"schéma SQLite futur : {version}")
        if version == 0:
            self._create_schema(connection)
        elif version == 1:
            self._migrate_v1_to_v2(connection)
        self._assert_owner()
        self.last_sample_ts = connection.execute("SELECT MAX(ts) FROM samples").fetchone()[0]
        os.chmod(self.path, 0o600)
        self.available = True
        self.last_error_class = None
        return self._load_active_alarms()

    def _preserve_corrupt_files(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.path.with_name(f"{self.path.name}.corrupt.{stamp}")
        for suffix in ("", "-wal", "-shm"):
            source = Path(str(self.path) + suffix)
            if source.exists():
                os.replace(source, Path(str(target) + suffix))
        self.recovered_corrupt_path = str(target)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE samples (
                id INTEGER PRIMARY KEY,
                ts REAL NOT NULL,
                time_state TEXT NOT NULL,
                is_day INTEGER,
                climate_state TEXT,
                temp_min REAL,
                temp_max REAL,
                heater_off_threshold REAL,
                vent_threshold REAL,
                humidity_threshold REAL
            );
            CREATE INDEX idx_samples_ts ON samples(ts);

            CREATE TABLE sensor_values (
                sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
                sensor_key TEXT NOT NULL,
                value REAL,
                status TEXT NOT NULL,
                raw_value REAL,
                acquisition_status TEXT,
                reason_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (sample_id, sensor_key)
            ) WITHOUT ROWID;
            CREATE INDEX idx_sensor_key ON sensor_values(sensor_key, sample_id);

            CREATE TABLE actuator_values (
                sample_id INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
                equipment_id TEXT NOT NULL,
                requested REAL,
                actual REAL,
                status TEXT NOT NULL,
                PRIMARY KEY (sample_id, equipment_id)
            ) WITHOUT ROWID;
            CREATE INDEX idx_actuator_equipment ON actuator_values(equipment_id, sample_id);

            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                subject TEXT NOT NULL,
                severity TEXT,
                alarm_id TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX idx_events_ts ON events(ts);

            CREATE TABLE alarm_occurrences (
                id TEXT PRIMARY KEY,
                alarm_key TEXT NOT NULL,
                code TEXT NOT NULL,
                title TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT NOT NULL,
                affects_control INTEGER NOT NULL,
                started_ts REAL NOT NULL,
                updated_ts REAL NOT NULL,
                resolved_ts REAL,
                consequence TEXT NOT NULL,
                advice TEXT NOT NULL,
                link TEXT NOT NULL,
                detail TEXT NOT NULL,
                acknowledged_ts REAL,
                acknowledged_by TEXT
            );
            CREATE UNIQUE INDEX idx_alarm_active_key
                ON alarm_occurrences(alarm_key) WHERE resolved_ts IS NULL;
            CREATE INDEX idx_alarm_started ON alarm_occurrences(started_ts DESC);
            PRAGMA user_version=2;
            """
        )
        connection.commit()

    def _migrate_v1_to_v2(self, connection: sqlite3.Connection) -> None:
        """Migration additive ; la copie v1 permet un rollback de l'auxiliaire."""
        backup = self.path.with_name(self.path.name + ".pre-v2.bak")
        if not backup.exists():
            target = sqlite3.connect(str(backup))
            try:
                connection.backup(target)
            finally:
                target.close()
            os.chmod(backup, 0o600)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ALTER TABLE sensor_values ADD COLUMN raw_value REAL")
            connection.execute(
                "ALTER TABLE sensor_values ADD COLUMN acquisition_status TEXT"
            )
            connection.execute(
                "ALTER TABLE sensor_values ADD COLUMN reason_json "
                "TEXT NOT NULL DEFAULT '[]'"
            )
            connection.execute("PRAGMA user_version=2")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _assert_owner(self) -> None:
        if self._owner_thread_id != threading.get_ident():
            raise RuntimeError("SQLite appelé hors du thread propriétaire")

    def _conn(self) -> sqlite3.Connection:
        self._assert_owner()
        if self._connection is None:
            raise HistoryUnavailable("connexion SQLite indisponible")
        return self._connection

    async def _call(self, function: Callable, *args):
        if self._closed:
            raise HistoryUnavailable("historique fermé")
        if self._executor is None:
            # L'executor reste dédié à SQLite. Sur CPython/WSL, le callback
            # de réveil de ``run_in_executor`` peut se perdre après
            # l'initialisation synchrone pré-loop ; on attend donc le Future
            # concurrent de manière coopérative, sans jamais bloquer le loop.
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="phyto-history"
            )
        try:
            future = self._executor.submit(self._guarded_call, function, args)
            while not future.done():
                await asyncio.sleep(0.01)
            result = future.result()
        except Exception as exc:
            self.available = False
            self.last_error_class = exc.__class__.__name__
            raise
        self.available = True
        self.last_error_class = None
        return result

    def _guarded_call(self, function: Callable, args: tuple):
        if self._connection is None:
            self._initialize()
        return function(*args)

    async def probe(self) -> None:
        await self._call(self._probe)

    def _probe(self) -> None:
        if self._connection is None:
            self._initialize()
        self._conn().execute("SELECT 1").fetchone()

    async def record_sample(self, sample: dict) -> None:
        await self._call(self._record_sample, sample)
        self.last_sample_ts = float(sample["ts"])

    def _record_sample(self, sample: dict) -> None:
        connection = self._conn()
        try:
            cursor = connection.execute(
                """INSERT INTO samples(
                    ts,time_state,is_day,climate_state,temp_min,temp_max,
                    heater_off_threshold,vent_threshold,humidity_threshold
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    sample["ts"], sample["time_state"], sample.get("is_day"),
                    sample.get("climate_state"), sample.get("temp_min"),
                    sample.get("temp_max"), sample.get("heater_off_threshold"),
                    sample.get("vent_threshold"), sample.get("humidity_threshold"),
                ),
            )
            sample_id = cursor.lastrowid
            connection.executemany(
                """INSERT INTO sensor_values(
                       sample_id,sensor_key,value,status,raw_value,acquisition_status,reason_json
                   ) VALUES(?,?,?,?,?,?,?)""",
                [
                    (
                        sample_id, item["key"], item.get("value"), item["status"],
                        item.get("raw_value"), item.get("acquisition_status"),
                        json.dumps(item.get("reason_codes", []), separators=(",", ":")),
                    )
                    for item in sample.get("sensors", [])
                ],
            )
            connection.executemany(
                """INSERT INTO actuator_values(
                    sample_id,equipment_id,requested,actual,status
                ) VALUES(?,?,?,?,?)""",
                [
                    (
                        sample_id, item["equipment_id"], item.get("requested"),
                        item.get("actual"), item["status"],
                    )
                    for item in sample.get("actuators", [])
                ],
            )
            self._purge(connection, float(sample["ts"]))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    async def record_events(self, events: list[dict]) -> None:
        if events:
            await self._call(self._record_events, events)

    def _record_events(self, events: list[dict]) -> None:
        connection = self._conn()
        try:
            connection.executemany(
                """INSERT INTO events(ts,kind,subject,severity,alarm_id,payload_json)
                   VALUES(?,?,?,?,?,?)""",
                [
                    (
                        event["ts"], event["kind"], event["subject"],
                        event.get("severity"), event.get("alarm_id"),
                        json.dumps(event.get("payload", {}), ensure_ascii=False, separators=(",", ":")),
                    )
                    for event in events
                ],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    async def persist_alarm(self, transition: AlarmTransition) -> None:
        await self._call(self._persist_alarm, transition)

    def _persist_alarm(self, transition: AlarmTransition) -> None:
        occurrence = transition.occurrence
        connection = self._conn()
        try:
            connection.execute(
                """INSERT INTO alarm_occurrences(
                    id,alarm_key,code,title,severity,category,affects_control,
                    started_ts,updated_ts,resolved_ts,consequence,advice,link,
                    detail,acknowledged_ts,acknowledged_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    code=excluded.code,title=excluded.title,severity=excluded.severity,
                    category=excluded.category,affects_control=excluded.affects_control,
                    updated_ts=excluded.updated_ts,resolved_ts=excluded.resolved_ts,
                    consequence=excluded.consequence,advice=excluded.advice,
                    link=excluded.link,detail=excluded.detail,
                    acknowledged_ts=excluded.acknowledged_ts,
                    acknowledged_by=excluded.acknowledged_by""",
                (
                    occurrence.id, occurrence.alarm_key, occurrence.code,
                    occurrence.title, occurrence.severity, occurrence.category,
                    int(occurrence.affects_control), occurrence.started_ts,
                    occurrence.updated_ts, occurrence.resolved_ts,
                    occurrence.consequence, occurrence.advice, occurrence.link,
                    occurrence.detail, occurrence.acknowledged_ts,
                    occurrence.acknowledged_by,
                ),
            )
            connection.execute(
                """INSERT INTO events(ts,kind,subject,severity,alarm_id,payload_json)
                   VALUES(?,?,?,?,?,?)""",
                (
                    occurrence.updated_ts, "alarm", transition.action,
                    occurrence.severity, occurrence.id,
                    json.dumps({"code": occurrence.code}, separators=(",", ":")),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def _load_active_alarms(self) -> list[dict]:
        connection = self._conn()
        cursor = connection.execute(
            "SELECT * FROM alarm_occurrences WHERE resolved_ts IS NULL ORDER BY started_ts"
        )
        return [dict(row) for row in self._dict_rows(cursor)]

    async def list_alarms(self, filters: dict) -> list[dict]:
        return await self._call(self._list_alarms, filters)

    def _list_alarms(self, filters: dict) -> list[dict]:
        clauses = []
        values: list[object] = []
        status = filters.get("status", "active")
        if status == "active":
            clauses.append("resolved_ts IS NULL")
        elif status == "resolved":
            clauses.append("resolved_ts IS NOT NULL")
        severity = filters.get("severity")
        if severity:
            clauses.append("severity=?")
            values.append(severity)
        category = filters.get("category")
        if category:
            clauses.append("category=?")
            values.append(category)
        acknowledged = filters.get("acknowledged")
        if acknowledged == "yes":
            clauses.append("acknowledged_ts IS NOT NULL")
        elif acknowledged == "no":
            clauses.append("acknowledged_ts IS NULL")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        limit = max(1, min(int(filters.get("limit", 500)), MAX_ALARM_OCCURRENCES))
        cursor = self._conn().execute(
            "SELECT * FROM alarm_occurrences" + where + " ORDER BY started_ts DESC LIMIT ?",
            (*values, limit),
        )
        return [dict(row) for row in self._dict_rows(cursor)]

    async def query_history(
        self, hours: int, series_metadata: dict[str, dict],
        equipment_metadata: dict[str, dict] | None = None,
    ) -> dict:
        return await self._call(
            self._query_history, hours, series_metadata, equipment_metadata or {},
        )

    def _query_history(
        self, hours: int, series_metadata: dict[str, dict],
        equipment_metadata: dict[str, dict],
    ) -> dict:
        connection = self._conn()
        end_ts = datetime.now(timezone.utc).timestamp()
        start_ts = end_ts - hours * 3600
        bucket_seconds = {24: 120, 48: 240, 72: 360}[hours]
        buckets: dict[float, dict] = {}

        sensor_rows = connection.execute(
            """SELECT CAST(s.ts / ? AS INTEGER) * ? AS bucket_start_ts,
                      v.sensor_key, MIN(v.value) AS min_value,
                      AVG(v.value) AS avg_value, MAX(v.value) AS max_value,
                      COUNT(v.value) AS valid_count
               FROM samples s JOIN sensor_values v ON v.sample_id=s.id
               WHERE s.ts>=? AND s.ts<=?
               GROUP BY bucket_start_ts,v.sensor_key
               ORDER BY bucket_start_ts,v.sensor_key""",
            (bucket_seconds, bucket_seconds, start_ts, end_ts),
        )
        seen_series = set()
        for row in self._dict_rows(sensor_rows):
            ts = float(row["bucket_start_ts"])
            bucket = buckets.setdefault(ts, {"bucket_start_ts": ts, "sensors": {}, "sensor_quality": {}, "setpoints": {}, "actuators": {}})
            bucket["sensors"][row["sensor_key"]] = {
                "min": row["min_value"], "avg": row["avg_value"],
                "max": row["max_value"], "valid_count": row["valid_count"],
            }
            seen_series.add(row["sensor_key"])

        status_rows = connection.execute(
            """SELECT CAST(s.ts / ? AS INTEGER) * ? AS bucket_start_ts,
                      v.sensor_key,v.status,COUNT(*) AS status_count
               FROM samples s JOIN sensor_values v ON v.sample_id=s.id
               WHERE s.ts>=? AND s.ts<=?
               GROUP BY bucket_start_ts,v.sensor_key,v.status
               ORDER BY bucket_start_ts,v.sensor_key""",
            (bucket_seconds, bucket_seconds, start_ts, end_ts),
        )
        for row in self._dict_rows(status_rows):
            ts = float(row["bucket_start_ts"])
            bucket = buckets.setdefault(ts, {"bucket_start_ts": ts, "sensors": {}, "sensor_quality": {}, "setpoints": {}, "actuators": {}})
            counts = bucket["sensor_quality"].setdefault(row["sensor_key"], {})
            counts[row["status"]] = int(row["status_count"])

        setpoint_rows = connection.execute(
            """SELECT CAST(ts / ? AS INTEGER) * ? AS bucket_start_ts,
                      AVG(temp_min) AS temp_min, AVG(temp_max) AS temp_max,
                      AVG(heater_off_threshold) AS heater_off_threshold,
                      AVG(vent_threshold) AS vent_threshold,
                      AVG(humidity_threshold) AS humidity_threshold
               FROM samples WHERE ts>=? AND ts<=?
               GROUP BY bucket_start_ts ORDER BY bucket_start_ts""",
            (bucket_seconds, bucket_seconds, start_ts, end_ts),
        )
        for row in self._dict_rows(setpoint_rows):
            ts = float(row.pop("bucket_start_ts"))
            bucket = buckets.setdefault(ts, {"bucket_start_ts": ts, "sensors": {}, "sensor_quality": {}, "setpoints": {}, "actuators": {}})
            bucket["setpoints"] = row

        actuator_rows = connection.execute(
            """SELECT CAST(s.ts / ? AS INTEGER) * ? AS bucket_start_ts,
                      v.equipment_id,
                      AVG(CASE WHEN v.status='ok' AND v.actual>0 THEN 1.0
                               WHEN v.status='ok' THEN 0.0 END) AS on_rate,
                      MIN(CASE WHEN v.status='ok' THEN v.actual END) AS min_value,
                      AVG(CASE WHEN v.status='ok' THEN v.actual END) AS avg_value,
                      MAX(CASE WHEN v.status='ok' THEN v.actual END) AS max_value,
                      SUM(CASE WHEN v.status='ok' THEN 1 ELSE 0 END) AS valid_count
               FROM samples s JOIN actuator_values v ON v.sample_id=s.id
               WHERE s.ts>=? AND s.ts<=?
               GROUP BY bucket_start_ts,v.equipment_id
               ORDER BY bucket_start_ts,v.equipment_id""",
            (bucket_seconds, bucket_seconds, start_ts, end_ts),
        )
        for row in self._dict_rows(actuator_rows):
            ts = float(row.pop("bucket_start_ts"))
            equipment_id = row.pop("equipment_id")
            bucket = buckets.setdefault(ts, {"bucket_start_ts": ts, "sensors": {}, "sensor_quality": {}, "setpoints": {}, "actuators": {}})
            bucket["actuators"][equipment_id] = row

        event_cursor = connection.execute(
            """SELECT ts,kind,subject,severity,alarm_id,payload_json
               FROM events WHERE ts>=? AND ts<=? AND kind IN ('alarm','config')
               ORDER BY ts""",
            (start_ts, end_ts),
        )
        events = []
        for row in self._dict_rows(event_cursor):
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
            events.append(row)

        ordered_bucket_keys = sorted(buckets)[-720:]
        return {
            "hours": hours,
            "bucket_seconds": bucket_seconds,
            "max_buckets": 720,
            "range_start_ts": start_ts,
            "range_end_ts": end_ts,
            "series": [series_metadata[key] for key in sorted(seen_series) if key in series_metadata],
            "equipment": equipment_metadata,
            "buckets": [buckets[key] for key in ordered_bucket_keys],
            "events": events,
        }

    @staticmethod
    def _dict_rows(cursor) -> list[dict]:
        columns = [item[0] for item in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    @staticmethod
    def _purge(connection: sqlite3.Connection, now_ts: float) -> None:
        connection.execute("DELETE FROM samples WHERE ts<?", (now_ts - RETENTION_SECONDS,))
        connection.execute("DELETE FROM events WHERE ts<?", (now_ts - RETENTION_SECONDS,))
        connection.execute(
            "DELETE FROM alarm_occurrences WHERE resolved_ts IS NOT NULL AND resolved_ts<?",
            (now_ts - ALARM_RETENTION_SECONDS,),
        )
        active_count = int(connection.execute(
            "SELECT COUNT(*) FROM alarm_occurrences WHERE resolved_ts IS NULL"
        ).fetchone()[0])
        resolved_limit = max(0, MAX_ALARM_OCCURRENCES - active_count)
        connection.execute(
            """DELETE FROM alarm_occurrences WHERE id IN (
                   SELECT id FROM alarm_occurrences WHERE resolved_ts IS NOT NULL
                   ORDER BY resolved_ts DESC LIMIT -1 OFFSET ?
               )""",
            (resolved_limit,),
        )

    async def close(self) -> None:
        if self._closed:
            return
        if self._executor is None:
            self._closed = True
            return
        try:
            await self._call(self._close_connection)
        finally:
            self._closed = True
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def _close_connection(self) -> None:
        if self._connection is not None:
            self._assert_owner()
            self._connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
            self._connection.close()
            self._connection = None
