"""État en mémoire des alarmes opérateur.

Le gestionnaire ne lit ni SQLite, ni GPIO, ni capteur. Il transforme des
conditions déjà observées en occurrences idempotentes. La persistance reste la
responsabilité de ``utils.operator_history``.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, replace


SEVERITIES = ("warning", "error", "critical")
SEVERITY_RANK = {name: index for index, name in enumerate(SEVERITIES)}
ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9 ._-]{0,32}$")


@dataclass(frozen=True)
class AlarmDefinition:
    code: str
    title: str
    severity: str
    category: str
    affects_control: bool
    consequence: str
    advice: str
    link: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError("gravité d'alarme inconnue")
        if not self.link.startswith("/") or self.link.startswith("//"):
            raise ValueError("le lien d'alarme doit être interne")


@dataclass(frozen=True)
class AlarmOccurrence:
    id: str
    alarm_key: str
    code: str
    title: str
    severity: str
    category: str
    affects_control: bool
    started_ts: float
    updated_ts: float
    resolved_ts: float | None
    consequence: str
    advice: str
    link: str
    detail: str
    acknowledged_ts: float | None = None
    acknowledged_by: str | None = None
    started_mono: float | None = None

    @property
    def active(self) -> bool:
        return self.resolved_ts is None

    def payload(self, now_ts: float | None = None, now_mono: float | None = None) -> dict:
        current_ts = time.time() if now_ts is None else now_ts
        if self.resolved_ts is not None:
            duration = max(0.0, self.resolved_ts - self.started_ts)
        elif self.started_mono is not None:
            current_mono = time.monotonic() if now_mono is None else now_mono
            duration = max(0.0, current_mono - self.started_mono)
        else:
            duration = max(0.0, current_ts - self.started_ts)
        result = asdict(self)
        result.pop("started_mono", None)
        result["status"] = "active" if self.active else "resolved"
        result["duration_seconds"] = round(duration, 1)
        return result


@dataclass(frozen=True)
class AlarmTransition:
    action: str
    occurrence: AlarmOccurrence


class AlarmManager:
    """Registre événement-loop des occurrences actives et récemment chargées."""

    def __init__(self, restored: list[dict] | None = None) -> None:
        self._occurrences: dict[str, AlarmOccurrence] = {}
        self._active_by_key: dict[str, str] = {}
        for raw in restored or []:
            occurrence = self._from_record(raw)
            self._occurrences[occurrence.id] = occurrence
            if occurrence.active:
                self._active_by_key[occurrence.alarm_key] = occurrence.id

    @staticmethod
    def _from_record(raw: dict) -> AlarmOccurrence:
        fields = {
            name: raw.get(name)
            for name in AlarmOccurrence.__dataclass_fields__
            if name != "started_mono"
        }
        fields["affects_control"] = bool(fields["affects_control"])
        fields["started_mono"] = None
        return AlarmOccurrence(**fields)

    def set_condition(
        self,
        alarm_key: str,
        definition: AlarmDefinition,
        active: bool,
        *,
        detail: str = "",
        severity: str | None = None,
        now_ts: float | None = None,
        now_mono: float | None = None,
    ) -> list[AlarmTransition]:
        """Ouvre, actualise ou résout une condition sans produire de doublon."""
        timestamp = time.time() if now_ts is None else now_ts
        monotonic_now = time.monotonic() if now_mono is None else now_mono
        wanted_severity = severity or definition.severity
        if wanted_severity not in SEVERITIES:
            raise ValueError("gravité d'alarme inconnue")
        safe_detail = str(detail)[:500]
        occurrence_id = self._active_by_key.get(alarm_key)
        occurrence = self._occurrences.get(occurrence_id) if occurrence_id else None

        if active and occurrence is None:
            opened = AlarmOccurrence(
                id=str(uuid.uuid4()),
                alarm_key=alarm_key,
                code=definition.code,
                title=definition.title,
                severity=wanted_severity,
                category=definition.category,
                affects_control=definition.affects_control,
                started_ts=timestamp,
                updated_ts=timestamp,
                resolved_ts=None,
                consequence=definition.consequence,
                advice=definition.advice,
                link=definition.link,
                detail=safe_detail,
                started_mono=monotonic_now,
            )
            self._occurrences[opened.id] = opened
            self._active_by_key[alarm_key] = opened.id
            return [AlarmTransition("opened", opened)]

        if active and occurrence is not None:
            escalated = SEVERITY_RANK[wanted_severity] > SEVERITY_RANK[occurrence.severity]
            changed = (
                occurrence.severity != wanted_severity
                or occurrence.detail != safe_detail
                or occurrence.code != definition.code
            )
            if not changed:
                return []
            updated = replace(
                occurrence,
                code=definition.code,
                title=definition.title,
                severity=wanted_severity,
                category=definition.category,
                affects_control=definition.affects_control,
                updated_ts=timestamp,
                consequence=definition.consequence,
                advice=definition.advice,
                link=definition.link,
                detail=safe_detail,
                acknowledged_ts=None if escalated else occurrence.acknowledged_ts,
                acknowledged_by=None if escalated else occurrence.acknowledged_by,
            )
            self._occurrences[updated.id] = updated
            return [AlarmTransition("updated", updated)]

        if not active and occurrence is not None:
            resolved = replace(occurrence, updated_ts=timestamp, resolved_ts=timestamp)
            self._occurrences[resolved.id] = resolved
            self._active_by_key.pop(alarm_key, None)
            return [AlarmTransition("resolved", resolved)]

        return []

    def get(self, occurrence_id: str) -> AlarmOccurrence | None:
        return self._occurrences.get(occurrence_id)

    def active_for_key(self, alarm_key: str) -> AlarmOccurrence | None:
        occurrence_id = self._active_by_key.get(alarm_key)
        return self._occurrences.get(occurrence_id) if occurrence_id else None

    def acknowledged_copy(
        self, occurrence_id: str, alias: str, *, now_ts: float | None = None
    ) -> AlarmOccurrence:
        if not ALIAS_PATTERN.fullmatch(alias):
            raise ValueError("alias opérateur invalide")
        occurrence = self._occurrences.get(occurrence_id)
        if occurrence is None:
            raise KeyError(occurrence_id)
        if occurrence.acknowledged_ts is not None and occurrence.acknowledged_by == (alias or None):
            return occurrence
        timestamp = time.time() if now_ts is None else now_ts
        return replace(
            occurrence,
            updated_ts=timestamp,
            acknowledged_ts=timestamp,
            acknowledged_by=alias or None,
        )

    def adopt(self, occurrence: AlarmOccurrence) -> None:
        self._occurrences[occurrence.id] = occurrence
        if occurrence.active:
            self._active_by_key[occurrence.alarm_key] = occurrence.id

    def active_payloads(self) -> list[dict]:
        active = [item for item in self._occurrences.values() if item.active]
        active.sort(key=lambda item: (-SEVERITY_RANK[item.severity], item.started_ts))
        return [item.payload() for item in active]

    def summary(self) -> dict:
        active = [item for item in self._occurrences.values() if item.active]
        highest = max(active, key=lambda item: SEVERITY_RANK[item.severity]).severity if active else None
        return {
            "active_count": len(active),
            "unacknowledged_count": sum(item.acknowledged_ts is None for item in active),
            "critical_count": sum(item.severity == "critical" for item in active),
            "control_count": sum(item.affects_control for item in active),
            "auxiliary_count": sum(not item.affects_control for item in active),
            "highest_severity": highest,
        }
