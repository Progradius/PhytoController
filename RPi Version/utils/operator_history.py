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


SCHEMA_VERSION = 3
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
        else:
            if version == 1:
                self._migrate_v1_to_v2(connection)
                version = 2
            if version == 2:
                self._migrate_v2_to_v3(connection)
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
                monotonic_ts REAL,
                session_id TEXT,
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
            CREATE INDEX idx_samples_session_ts ON samples(session_id, ts);

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
            PRAGMA user_version=3;
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

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        """Associe les relectures au démarrage et à son horloge monotone."""
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("ALTER TABLE samples ADD COLUMN session_id TEXT")
            connection.execute("ALTER TABLE samples ADD COLUMN monotonic_ts REAL")
            connection.execute(
                "CREATE INDEX idx_samples_session_ts ON samples(session_id, ts)"
            )
            connection.execute("PRAGMA user_version=3")
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
                    ts,monotonic_ts,session_id,time_state,is_day,climate_state,temp_min,temp_max,
                    heater_off_threshold,vent_threshold,humidity_threshold
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    sample["ts"], sample.get("monotonic_ts"), sample.get("session_id"),
                    sample["time_state"], sample.get("is_day"),
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
               FROM events WHERE ts>=? AND ts<=? AND kind IN ('alarm','config','operator_note')
               ORDER BY ts""",
            (start_ts, end_ts),
        )
        events = []
        for row in self._dict_rows(event_cursor):
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
            events.append(row)

        actuator_history = self._actuator_history(
            connection, start_ts, end_ts, equipment_metadata,
        )

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
            "actuator_history": actuator_history,
        }

    def _actuator_history(
        self, connection: sqlite3.Connection, start_ts: float, end_ts: float,
        equipment_metadata: dict[str, dict],
    ) -> dict[str, dict]:
        """
        Reconstruit les plages à partir des transitions dont le GPIO a été
        relu. Les bornes d'une session sont confirmées par ses échantillons :
        un redémarrage ou un arrêt ne prolonge donc jamais artificiellement le
        dernier état connu jusqu'à la session suivante.
        """
        bounds_cursor = connection.execute(
            """SELECT s.session_id,v.equipment_id,MIN(s.ts) AS first_ts,
                      MAX(s.ts) AS last_ts,MIN(s.monotonic_ts) AS first_mono,
                      MAX(s.monotonic_ts) AS last_mono
               FROM samples s JOIN actuator_values v ON v.sample_id=s.id
               WHERE s.session_id IS NOT NULL AND s.monotonic_ts IS NOT NULL
                     AND s.ts<=?
               GROUP BY s.session_id,v.equipment_id
               HAVING MAX(s.ts)>=?""",
            (end_ts, start_ts),
        )
        bounds = {
            (row["session_id"], row["equipment_id"]):
            (
                float(row["first_ts"]), float(row["last_ts"]),
                float(row["first_mono"]), float(row["last_mono"]),
            )
            for row in self._dict_rows(bounds_cursor)
        }
        if not bounds:
            return {}

        event_cursor = connection.execute(
            """SELECT ts,subject,payload_json FROM events
               WHERE kind='output' AND ts<=? AND ts>=?
               ORDER BY ts,id""",
            (end_ts, start_ts - RETENTION_SECONDS),
        )
        points: dict[tuple[str, str], list[dict]] = {}
        for row in self._dict_rows(event_cursor):
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            session_id = payload.get("session_id")
            monotonic_ts = payload.get("monotonic_ts")
            status = payload.get("actual_status")
            if (
                not isinstance(session_id, str)
                or isinstance(monotonic_ts, bool)
                or not isinstance(monotonic_ts, (int, float))
                or "actual" not in payload
            ):
                continue
            actual = payload.get("actual")
            if status == "ok":
                if isinstance(actual, bool) or not isinstance(actual, (int, float)):
                    status = "unreadable"
                    actual = None
                else:
                    actual = float(actual)
            else:
                actual = None
            key = (session_id, row["subject"])
            if key not in bounds:
                continue
            points.setdefault(key, []).append({
                "ts": float(row["ts"]),
                "monotonic_ts": float(monotonic_ts),
                "actual": actual,
                "status": str(status or "unknown"),
                "source": str(payload.get("source") or "transition"),
            })

        result: dict[str, dict] = {}
        range_seconds = max(1.0, end_ts - start_ts)
        for key, session_points in points.items():
            _session_id, equipment_id = key
            first_sample, last_sample, _first_sample_mono, last_sample_mono = bounds[key]
            session_points.sort(key=lambda item: item["ts"])
            window_start = max(start_ts, min(first_sample, session_points[0]["ts"]))
            window_end = min(
                end_ts, max(last_sample, session_points[-1]["ts"]),
            )
            if window_end <= window_start:
                continue
            prior = [point for point in session_points if point["ts"] <= window_start]
            selected = ([prior[-1]] if prior else []) + [
                point for point in session_points if window_start < point["ts"] <= window_end
            ]
            if not selected:
                continue
            equipment = result.setdefault(equipment_id, {
                "intervals": [], "covered_seconds": 0.0,
                "monitored_seconds": 0.0, "on_seconds": 0.0,
                "transition_count": 0, "observed_boundary_count": 0,
                "speed_seconds": {},
            })
            previous_valid = None
            for index, point in enumerate(selected):
                interval_start = max(window_start, point["ts"])
                interval_end = min(
                    window_end,
                    selected[index + 1]["ts"] if index + 1 < len(selected) else window_end,
                )
                if interval_end <= interval_start:
                    continue
                next_point = selected[index + 1] if index + 1 < len(selected) else None
                end_mono = (
                    next_point["monotonic_ts"] if next_point is not None
                    else last_sample_mono
                )
                # Les extrémités coupées par la fenêtre utilisent seulement
                # l'heure civile pour la portion coupée. Entre deux relectures,
                # la durée reste monotone et résiste aux corrections NTP.
                start_mono = point["monotonic_ts"] + max(
                    0.0, interval_start - point["ts"],
                )
                if next_point is not None and interval_end < next_point["ts"]:
                    end_mono = point["monotonic_ts"] + max(
                        0.0, interval_end - point["ts"],
                    )
                elif next_point is None and interval_end < last_sample:
                    end_mono = point["monotonic_ts"] + max(
                        0.0, interval_end - point["ts"],
                    )
                duration = max(0.0, end_mono - start_mono)
                interval = {
                    "start_ts": interval_start, "end_ts": interval_end,
                    "duration_seconds": round(duration, 3),
                    "actual": point["actual"], "status": point["status"],
                    "source": point["source"],
                    "boundary_precision": (
                        "observed" if point["source"] == "periodic_observation"
                        else "transition"
                    ),
                }
                equipment["intervals"].append(interval)
                equipment["monitored_seconds"] += duration
                if point["source"] == "periodic_observation":
                    equipment["observed_boundary_count"] += 1
                if point["status"] != "ok" or point["actual"] is None:
                    previous_valid = None
                    continue
                equipment["covered_seconds"] += duration
                if point["actual"] > 0:
                    equipment["on_seconds"] += duration
                speed_key = str(int(point["actual"])) if equipment_id == "motor" else None
                if speed_key is not None:
                    equipment["speed_seconds"][speed_key] = (
                        equipment["speed_seconds"].get(speed_key, 0.0) + duration
                    )
                if previous_valid is not None and previous_valid != point["actual"]:
                    equipment["transition_count"] += 1
                previous_valid = point["actual"]

        for equipment_id, equipment in result.items():
            equipment["intervals"].sort(key=lambda item: item["start_ts"])
            for key in ("covered_seconds", "monitored_seconds", "on_seconds"):
                equipment[key] = round(equipment[key], 3)
            equipment["speed_seconds"] = {
                key: round(value, 3)
                for key, value in sorted(equipment["speed_seconds"].items())
            }
            equipment["coverage_ratio"] = round(
                min(1.0, equipment["covered_seconds"] / range_seconds), 6,
            )
            equipment["duration_precision"] = (
                "observed" if equipment["observed_boundary_count"] else "transition"
            )
            equipment["display_name"] = equipment_metadata.get(
                equipment_id, {},
            ).get("display_name", equipment_id)
        return result

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
