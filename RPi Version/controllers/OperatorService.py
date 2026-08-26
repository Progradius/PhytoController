"""Surveillance opérateur auxiliaire : alarmes, réseau et historique local."""

from __future__ import annotations

import asyncio
import copy
import shutil
import time
import uuid
from collections import deque

from components.climate_control import (
    get_climate_alarm_status,
    get_climate_snapshot,
)
from components.climate_policy import (
    ALARM_CONTINUOUS_LIMIT,
    ALARM_SENSOR_FALLBACK,
    settings_from_config,
)
from controllers.sensor_catalog import SENSOR_CATALOG
from network.web import influx_handler
from utils.alarm_manager import (
    AlarmDefinition,
    AlarmManager,
    AlarmTransition,
    SEVERITY_RANK,
)
from utils.operational_state import set_transition_sink
from utils.operational_state import snapshot as operational_snapshot
from utils.pretty_console import debug, info, warning
from utils.schedule import is_day as scheduled_day
from utils.supervisor import beat, sleep as hb_sleep
from utils.time_reliability import UNKNOWN_SUSPENSION_SECONDS, time_reliability


LOGGER_NAME = "operator"
EVENT_QUEUE_LIMIT = 1000


DEFINITIONS = {
    "sensor_fallback": AlarmDefinition(
        code="sensor_fallback", title="Repli de la régulation sur perte du capteur",
        severity="critical", category="control", affects_control=True,
        consequence="Chauffage coupé et ventilation placée à la vitesse de repli.",
        advice="Contrôler le BME280, son câblage et la température avec un instrument indépendant.",
        link="/#surveillance",
    ),
    "heater_continuous_limit": AlarmDefinition(
        code="heater_continuous_limit", title="Durée maximale de chauffe atteinte",
        severity="critical", category="control", affects_control=True,
        consequence="Le chauffage est forcé au repos pendant le cooldown de sécurité.",
        advice="Vérifier le capteur, la puissance de chauffe et les pertes thermiques.",
        link="/#surveillance",
    ),
    "influx": AlarmDefinition(
        code="influx_unavailable", title="Export InfluxDB indisponible",
        severity="warning", category="telemetry", affects_control=False,
        consequence="Les mesures locales continuent, mais la référence analytique n'est plus alimentée.",
        advice="Vérifier l'hôte InfluxDB et sa disponibilité réseau.", link="/console",
    ),
    "time": AlarmDefinition(
        code="time_unreliable", title="Heure non synchronisée",
        severity="warning", category="time", affects_control=False,
        consequence="Les décisions horaires sont suspendues ou utilisent la reprise bornée.",
        advice="Vérifier systemd-timesyncd, le réseau et l'heure du Raspberry Pi.", link="/console",
    ),
    "network": AlarmDefinition(
        code="network_degraded", title="Accès réseau local dégradé",
        severity="warning", category="network", affects_control=False,
        consequence="L'interface locale ou les services distants peuvent être injoignables.",
        advice="Vérifier l'interface, l'adresse IPv4 et la passerelle NetworkManager.", link="/console",
    ),
    "disk": AlarmDefinition(
        code="disk_space", title="Espace disque faible",
        severity="warning", category="storage", affects_control=False,
        consequence="Les logs, la configuration et l'historique peuvent ne plus s'écrire.",
        advice="Libérer de l'espace sur la partition racine avant saturation.", link="/console",
    ),
    "config_backup": AlarmDefinition(
        code="config_backup_restored", title="Configuration restaurée depuis la sauvegarde",
        severity="warning", category="configuration", affects_control=False,
        consequence="Les paramètres actifs datent de la dernière écriture valide connue.",
        advice="Relire puis enregistrer une configuration complète validée.", link="/conf",
    ),
    "history": AlarmDefinition(
        code="history_unavailable", title="Historique local indisponible",
        severity="error", category="storage", affects_control=False,
        consequence="Les tendances locales peuvent présenter une lacune; le contrôle continue.",
        advice="Vérifier l'espace disque et l'intégrité de la base SQLite.", link="/alarms",
    ),
}


class OperatorService:
    def __init__(
        self, *, history, alarm_manager: AlarmManager, supervisor, config_store,
        sensor_handler, components: dict, motor, equipment_store,
    ) -> None:
        self.history = history
        self.alarms = alarm_manager
        self.supervisor = supervisor
        self.config_store = config_store
        self.sensor_handler = sensor_handler
        self.components = components
        self.motor = motor
        self.equipment_store = equipment_store
        self._events: deque[dict] = deque()
        self._alarm_transitions: deque[AlarmTransition] = deque()
        self._queue_overflow = False
        self._history_recovery_pending = bool(history.recovered_corrupt_path)
        self._network = {
            "status": "unknown", "interface": None, "connection": None,
            "ipv4": None, "gateway": None, "degraded_seconds": 0.0,
        }
        self._network_degraded_since: float | None = None
        self._disk_free_percent: float | None = None
        self._disk_level: str | None = None
        self._previous_config = copy.deepcopy(config_store.current.model_dump(by_alias=True))
        self._previous_equipment = copy.deepcopy(equipment_store.payload())
        self._dynamic_alarm_keys: set[str] = {
            item["alarm_key"] for item in alarm_manager.active_payloads()
            if item["alarm_key"].startswith(("gpio:", "control:", "restart:"))
        }
        set_transition_sink(self._on_output_transition)

    # ── snapshots synchrones, sans I/O bloquante autre que GPIO ─────────
    def actuator_snapshot(self) -> dict[str, dict]:
        entries = operational_snapshot()
        metadata = self.equipment_store.payload()
        for equipment_id in metadata:
            item = entries.setdefault(equipment_id, {
                "requested": "unknown", "reason": "en attente de publication métier",
                "mode": "unknown", "stale": True, "age_seconds": None,
                "stale_after_seconds": 0.0,
            })
            if equipment_id == "motor":
                diagnostic = self.motor.read_state()
                item["actual_status"] = diagnostic["status"]
                item["actual"] = diagnostic["speed"] if diagnostic["status"] == "ok" else "unknown"
                if diagnostic["status"] == "conflict":
                    item["active_speeds"] = diagnostic["active_speeds"]
            else:
                try:
                    item["actual"] = "on" if self.components[equipment_id].get_state() else "off"
                    item["actual_status"] = "ok"
                except Exception:
                    item["actual"] = "unknown"
                    item["actual_status"] = "unreadable"
            item["metadata"] = metadata[equipment_id]
            if item.get("stale"):
                item["requested"] = "unknown"
                item["reason"] = "publication métier périmée"
            requested = item.get("applied", item.get("requested"))
            actual = item.get("actual")
            normalized_requested = self._numeric_state(requested)
            normalized_actual = self._numeric_state(actual)
            if item["actual_status"] != "ok" or item.get("stale"):
                tracking = "unknown"
            elif normalized_requested != normalized_actual and metadata[equipment_id].get("out_of_service"):
                tracking = "known_hardware_fault"
            elif normalized_requested != normalized_actual:
                tracking = "mismatch"
            else:
                tracking = "ok"
            item["tracking"] = tracking
        return entries

    @staticmethod
    def _numeric_state(value):
        if value == "on":
            return 1
        if value == "off":
            return 0
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
        return None

    def snapshot(self) -> dict:
        return {
            "alarms": self.alarms.summary(),
            "history": self.history.snapshot(),
            "network": dict(self._network),
        }

    # ── événements non bloquants ───────────────────────────────
    def _enqueue_event(self, event: dict) -> None:
        if len(self._events) >= EVENT_QUEUE_LIMIT:
            self._queue_overflow = True
            return
        self._events.append(event)

    def _on_output_transition(self, equipment_id: str, values: dict) -> None:
        self._enqueue_event({
            "ts": time.time(), "kind": "output", "subject": equipment_id,
            "payload": {
                "requested": values.get("requested"),
                "applied": values.get("applied"),
                "mode": str(values.get("mode", ""))[:64],
            },
        })

    def enqueue_system_action(self, action: str) -> None:
        if action in {"reboot", "poweroff"}:
            self._enqueue_event({
                "ts": time.time(), "kind": "system", "subject": action, "payload": {},
            })

    async def record_system_action(self, action: str) -> None:
        """Tente de vider l'événement avant que l'action coupe le processus."""
        self.enqueue_system_action(action)
        await self._flush_pending()

    # ── boucle auxiliaire ──────────────────────────────────────
    async def run(self) -> None:
        info("Service opérateur auxiliaire démarré", name=LOGGER_NAME)
        now = time.monotonic()
        # Laisser les boucles métier publier leur premier état avant de
        # réévaluer les occurrences restaurées, sinon un boot résoudrait puis
        # rouvrirait artificiellement une condition toujours présente.
        next_alarm = now + 10.0
        next_network = next_disk = next_sample = now
        while True:
            beat()
            now = time.monotonic()
            if now >= next_network:
                await self._probe_network()
                next_network = now + 30.0
            if now >= next_disk:
                await self._probe_disk()
                next_disk = now + 60.0
            if now >= next_alarm:
                self._detect_configuration_changes()
                self._evaluate_alarms()
                next_alarm = now + 10.0
            if now >= next_sample:
                await self._sample_once()
                next_sample = now + 60.0
            await self._flush_pending()
            await hb_sleep(1.0)

    @staticmethod
    async def _nmcli(*arguments: str) -> tuple[int, bytes]:
        process = await asyncio.create_subprocess_exec(
            "nmcli", *arguments, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=4.0)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise
        return int(process.returncode or 0), stdout

    async def _probe_network(self) -> None:
        started = time.monotonic()
        try:
            returncode, stdout = await self._nmcli(
                "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status",
            )
            if returncode != 0:
                raise RuntimeError("nmcli status")
            candidates = []
            for line in stdout.decode("utf-8", "replace").splitlines():
                parts = line.split(":", 3)
                if len(parts) == 4 and parts[0] != "lo" and parts[2] == "connected":
                    candidates.append((parts[0], parts[3]))
            if not candidates:
                self._set_network("offline", None, None, None, None)
                return
            interface, connection_name = candidates[0]
            detail_returncode, detail_out = await self._nmcli(
                "-g", "IP4.ADDRESS,IP4.GATEWAY", "device", "show", interface,
            )
            if detail_returncode != 0:
                raise RuntimeError("nmcli device show")
            lines = [line.strip() for line in detail_out.decode("utf-8", "replace").splitlines()]
            ipv4 = lines[0].split("/", 1)[0] if lines and lines[0] else None
            gateway = lines[1] if len(lines) > 1 and lines[1] else None
            status = "online" if ipv4 and gateway and connection_name != "phyto-rescue" else "degraded" if ipv4 else "offline"
            self._set_network(status, interface, connection_name, ipv4, gateway)
        except (OSError, RuntimeError, asyncio.TimeoutError):
            self._set_network("unknown", None, None, None, None)
        finally:
            debug(f"Sonde réseau terminée en {time.monotonic() - started:.2f} s", name=LOGGER_NAME)

    def _set_network(self, status, interface, connection_name, ipv4, gateway) -> None:
        now = time.monotonic()
        if status == "online":
            self._network_degraded_since = None
        elif self._network_degraded_since is None:
            self._network_degraded_since = now
        self._network = {
            "status": status,
            "interface": interface,
            "connection": connection_name,
            "ipv4": ipv4,
            "gateway": gateway,
            "degraded_seconds": round(
                max(0.0, now - self._network_degraded_since), 1
            ) if self._network_degraded_since is not None else 0.0,
        }

    async def _probe_disk(self) -> None:
        loop = asyncio.get_running_loop()
        usage = await loop.run_in_executor(None, shutil.disk_usage, "/")
        self._disk_free_percent = usage.free / usage.total * 100 if usage.total else 0.0
        free = self._disk_free_percent
        if self._disk_level == "critical":
            self._disk_level = "warning" if free >= 7.0 else "critical"
        if self._disk_level == "warning":
            if free >= 12.0:
                self._disk_level = None
            elif free < 5.0:
                self._disk_level = "critical"
        elif self._disk_level is None:
            self._disk_level = "critical" if free < 5.0 else "warning" if free < 10.0 else None

    async def _sample_once(self) -> None:
        if time_reliability().state == "unknown":
            debug("Historique suspendu : heure réellement inconnue", name=LOGGER_NAME)
            return
        sample = self._build_sample()
        try:
            await self.history.record_sample(sample)
        except Exception as exc:
            warning(f"Échantillon historique refusé ({exc.__class__.__name__})", name=LOGGER_NAME)
            return
        self._history_recovery_pending = False

    def _build_sample(self) -> dict:
        config = self.config_store.current
        reliability = time_reliability()
        is_day = reliability.use_day_settings() and scheduled_day(config)
        settings = settings_from_config(config, is_day)
        climate = get_climate_snapshot()
        sensors = self.sensor_handler.snapshot()
        actuators = self.actuator_snapshot()
        return {
            "ts": time.time(), "time_state": reliability.state,
            "is_day": int(is_day), "climate_state": climate.get("state"),
            "temp_min": climate.get("temp_min", settings.temp_min),
            "temp_max": climate.get("temp_max", settings.temp_max),
            "heater_off_threshold": climate.get("heater_off_threshold", settings.heater_off_threshold),
            "vent_threshold": climate.get("vent_threshold", settings.vent_threshold),
            "humidity_threshold": settings.winter_humidity_threshold,
            "sensors": [
                {
                    "key": definition.key,
                    "status": sensors[definition.key]["status"],
                    "value": sensors[definition.key]["value"]
                    if sensors[definition.key]["status"] == "ok" else None,
                }
                for definition in SENSOR_CATALOG if sensors[definition.key]["enabled"]
            ],
            "actuators": [
                {
                    "equipment_id": equipment_id,
                    "requested": self._numeric_state(item.get("applied", item.get("requested"))),
                    "actual": self._numeric_state(item.get("actual"))
                    if item.get("actual_status") == "ok" else None,
                    "status": item.get("actual_status", "unknown"),
                }
                for equipment_id, item in actuators.items()
            ],
        }

    def _detect_configuration_changes(self) -> None:
        current = copy.deepcopy(self.config_store.current.model_dump(by_alias=True))
        changed = self._changed_paths(self._previous_config, current)
        if changed:
            self._enqueue_event({
                "ts": time.time(), "kind": "config", "subject": "param.json",
                "payload": {"fields": changed[:100]},
            })
            self._previous_config = current
        equipment = copy.deepcopy(self.equipment_store.payload())
        equipment_changed = self._changed_paths(self._previous_equipment, equipment)
        if equipment_changed:
            self._enqueue_event({
                "ts": time.time(), "kind": "config", "subject": "equipment_metadata",
                "payload": {"fields": equipment_changed[:100]},
            })
            self._previous_equipment = equipment

    @classmethod
    def _changed_paths(cls, before, after, prefix="") -> list[str]:
        if isinstance(before, dict) and isinstance(after, dict):
            result = []
            for key in sorted(set(before) | set(after)):
                path = f"{prefix}.{key}" if prefix else str(key)
                result.extend(cls._changed_paths(before.get(key), after.get(key), path))
            return result
        return [prefix] if before != after else []

    # ── conditions d'alarmes ──────────────────────────────────
    def _condition(self, key, definition, active, *, detail="", severity=None) -> None:
        transitions = self.alarms.set_condition(
            key, definition, active, detail=detail, severity=severity,
        )
        for transition in transitions:
            occurrence = transition.occurrence
            if transition.action == "opened":
                warning(
                    f"Alarme {occurrence.severity} ouverte : {occurrence.title}",
                    name=LOGGER_NAME,
                )
            elif transition.action == "resolved":
                info(f"Alarme résolue : {occurrence.title}", name=LOGGER_NAME)
        self._alarm_transitions.extend(transitions)

    def _evaluate_alarms(self) -> None:
        current_dynamic: set[str] = set()
        climate = get_climate_alarm_status()
        for code in (ALARM_SENSOR_FALLBACK, ALARM_CONTINUOUS_LIMIT):
            key = f"climate:{code}"
            self._condition(key, DEFINITIONS[code], climate.get("code") == code,
                            detail=climate.get("message") or "")

        actuators = self.actuator_snapshot()
        for equipment_id, item in actuators.items():
            key = f"gpio:{equipment_id}"
            current_dynamic.add(key)
            status = item.get("actual_status")
            active = status in {"unreadable", "conflict"} or item.get("tracking") == "mismatch"
            definition = AlarmDefinition(
                code="gpio_tracking", title=f"Sortie {equipment_id} non suivie",
                severity="critical", category="hardware", affects_control=True,
                consequence="La relecture matérielle ne confirme pas la consigne.",
                advice="Contrôler le GPIO, le relais et le câblage avant toute remise en service.",
                link="/#surveillance",
            )
            detail = f"statut={status}, suivi={item.get('tracking')}"
            self._condition(key, definition, active, detail=detail)

        tasks = self.supervisor.snapshot()
        for name, task in tasks.items():
            control_key = f"control:{name}"
            restart_key = f"restart:{name}"
            current_dynamic.update((control_key, restart_key))
            control_definition = AlarmDefinition(
                code="control_unhealthy", title=f"Contrôle malsain : {name}",
                severity="critical", category="control", affects_control=True,
                consequence="Une boucle qui pilote la serre ne progresse plus normalement.",
                advice="Consulter la tâche et les logs; vérifier l'état physique des sorties.",
                link="/console",
            )
            self._condition(
                control_key, control_definition,
                bool(task.get("gates_watchdog") and not task.get("healthy")),
                detail=str(task.get("last_error") or "tâche non saine")[:500],
            )
            restart_definition = AlarmDefinition(
                code="restart_storm", title=f"Relances répétées : {name}",
                severity="critical" if task.get("gates_watchdog") else "error",
                category="control" if task.get("gates_watchdog") else "system",
                affects_control=bool(task.get("gates_watchdog")),
                consequence="La tâche est instable malgré les relances du superviseur.",
                advice="Identifier la première exception au lieu de laisser le back-off la masquer.",
                link="/console",
            )
            self._condition(
                restart_key, restart_definition, int(task.get("restarts_10m", 0)) >= 2,
                detail=f"{task.get('restarts_10m', 0)} relance(s) sur 10 min",
            )

        for stale_key in self._dynamic_alarm_keys - current_dynamic:
            occurrence = self.alarms.active_for_key(stale_key)
            if occurrence:
                definition = AlarmDefinition(
                    code=occurrence.code, title=occurrence.title,
                    severity=occurrence.severity, category=occurrence.category,
                    affects_control=occurrence.affects_control,
                    consequence=occurrence.consequence, advice=occurrence.advice,
                    link=occurrence.link,
                )
                self._condition(stale_key, definition, False)
        self._dynamic_alarm_keys = current_dynamic

        influx = influx_handler.get_health()
        self._condition(
            "influx", DEFINITIONS["influx"],
            bool(influx.get("enabled") and influx.get("state") == "error"),
            detail=str(influx.get("last_error") or "")[:200],
        )
        reliability = time_reliability()
        time_severity = (
            "error" if reliability.state == "unknown"
            and reliability.unknown_seconds >= UNKNOWN_SUSPENSION_SECONDS else "warning"
        )
        self._condition(
            "time", DEFINITIONS["time"], reliability.state != "synchronized",
            severity=time_severity, detail=f"état={reliability.state}",
        )
        network_status = self._network["status"]
        self._condition(
            "network", DEFINITIONS["network"], network_status != "online",
            severity="error" if network_status == "offline" else "warning",
            detail=f"état={network_status}",
        )
        self._condition(
            "disk", DEFINITIONS["disk"], self._disk_level is not None,
            severity=self._disk_level or "warning",
            detail=f"{self._disk_free_percent:.1f} % libres" if self._disk_free_percent is not None else "",
        )
        self._condition(
            "config_backup", DEFINITIONS["config_backup"],
            self.config_store.recovery_pending,
        )
        history_active = (
            not self.history.available or self._history_recovery_pending or self._queue_overflow
        )
        history_detail = self.history.last_error_class or (
            "base recréée après corruption" if self._history_recovery_pending
            else "file d'événements saturée" if self._queue_overflow else ""
        )
        self._condition(
            "history", DEFINITIONS["history"], history_active,
            detail=history_detail,
        )

    async def _flush_pending(self) -> None:
        while self._alarm_transitions:
            transition = self._alarm_transitions[0]
            try:
                await self.history.persist_alarm(transition)
            except Exception:
                return
            self._alarm_transitions.popleft()
        if self._events:
            batch = list(self._events)[:100]
            try:
                await self.history.record_events(batch)
            except Exception:
                return
            for _ in batch:
                self._events.popleft()
        if not self._events:
            self._queue_overflow = False

    # ── API appelée par HTTP ───────────────────────────────────
    async def acknowledge(self, occurrence_id: str, alias: str) -> dict:
        uuid.UUID(occurrence_id)
        updated = self.alarms.acknowledged_copy(occurrence_id, alias)
        transition = AlarmTransition("acknowledged", updated)
        await self.history.persist_alarm(transition)
        self.alarms.adopt(updated)
        return updated.payload()

    async def list_alarm_payloads(self, filters: dict) -> list[dict]:
        records = []
        if self.history.available:
            try:
                records = await self.history.list_alarms(filters)
            except Exception:
                records = []
        by_id = {record["id"]: record for record in records}
        for payload in self.alarms.active_payloads():
            by_id[payload["id"]] = payload
        payloads = []
        now = time.time()
        for record in by_id.values():
            record = dict(record)
            record["affects_control"] = bool(record.get("affects_control"))
            if "status" not in record:
                record["status"] = "active" if record.get("resolved_ts") is None else "resolved"
                end = record.get("resolved_ts") or now
                record["duration_seconds"] = round(max(0.0, end - record["started_ts"]), 1)
            if self._matches_filters(record, filters):
                payloads.append(record)
        payloads.sort(
            key=lambda item: (
                item.get("status") != "active",
                -SEVERITY_RANK.get(item.get("severity"), 0),
                -float(item.get("started_ts", 0)),
            )
        )
        return payloads[:max(1, min(int(filters.get("limit", 500)), 2000))]

    @staticmethod
    def _matches_filters(item: dict, filters: dict) -> bool:
        status = filters.get("status", "active")
        if status != "all" and item.get("status") != status:
            return False
        if filters.get("severity") and item.get("severity") != filters["severity"]:
            return False
        if filters.get("category") and item.get("category") != filters["category"]:
            return False
        acknowledged = filters.get("acknowledged")
        if acknowledged == "yes" and item.get("acknowledged_ts") is None:
            return False
        if acknowledged == "no" and item.get("acknowledged_ts") is not None:
            return False
        return True

    async def query_history(self, hours: int) -> dict:
        metadata = {
            definition.key: {
                "key": definition.key, "label": definition.label,
                "unit": definition.unit, "decimals": definition.decimals,
                "family": definition.family,
            }
            for definition in SENSOR_CATALOG
        }
        return await self.history.query_history(hours, metadata)
