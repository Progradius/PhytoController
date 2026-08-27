"""Politique pure de calibration et de qualité des mesures capteurs."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date
from typing import Mapping

from controllers.sensor_catalog import SensorDefinition


STATUS_NORMAL = "normal"
STATUS_DEGRADED = "degraded"
STATUS_ABSENT = "absent"
STATUS_INCONSISTENT = "inconsistent"

ACQUISITION_OK = "ok"
ACQUISITION_ERROR = "error"

RECOVERY_SAMPLES = 3
MISSING_AFTER_FAILURES = 5


@dataclass(frozen=True)
class QualityMemory:
    last_raw_value: float | None = None
    last_sample_mono: float | None = None
    last_change_mono: float | None = None
    unchanged_seconds: float = 0.0
    unchanged_samples: int = 0
    frozen: bool = False
    recovery_samples: int = 0
    redundancy_inconsistent: bool = False
    redundancy_recovery_samples: int = 0
    consecutive_failures: int = 0
    failures_since_calibration: int = 0
    incoherences_since_calibration: int = 0
    last_failure_at: str | None = None
    last_trusted_value: float | None = None
    last_trusted_mono: float | None = None
    last_trusted_at: str | None = None
    previous_status: str = STATUS_ABSENT


@dataclass(frozen=True)
class QualityDecision:
    status: str
    acquisition_status: str
    reasons: tuple[str, ...]
    raw_value: float | None
    observed_value: float | None
    value: float | None
    last_trusted_value: float | None
    control_usable: bool
    would_block_control: bool
    control_disposition: str
    calibration_overdue: bool | None
    redundancy_group: str | None = None
    redundancy_status: str = "not_configured"
    redundancy_delta: float | None = None


def _calibration_overdue(profile: Mapping, today: date | None) -> bool | None:
    calibrated_at = profile.get("calibrated_at")
    valid_days = profile.get("calibration_valid_days")
    if not calibrated_at or not valid_days:
        return False
    if today is None:
        return None
    try:
        calibrated = date.fromisoformat(str(calibrated_at))
    except ValueError:
        return None
    return (today - calibrated).days > int(valid_days)


def _inside_plausible(definition: SensorDefinition, value: float, profile: Mapping) -> bool:
    minimum = max(float(profile["plausible_min"]), float(definition.plausible_min))
    maximum = min(float(profile["plausible_max"]), float(definition.plausible_max))
    if definition.control_role == "climate_temperature":
        return minimum < value < maximum
    return minimum <= value <= maximum


def evaluate_sample(
    definition: SensorDefinition,
    profile: Mapping,
    memory: QualityMemory,
    *,
    raw_value,
    error: str | None,
    now_mono: float,
    now_iso: str,
    today: date | None,
    mode: str,
) -> tuple[QualityDecision, QualityMemory]:
    """Évalue une tentative sans I/O ni horloge implicite."""
    freshness = float(profile["freshness_seconds"])
    overdue = _calibration_overdue(profile, today)
    numeric = (
        error is None
        and isinstance(raw_value, (int, float))
        and not isinstance(raw_value, bool)
        and math.isfinite(float(raw_value))
    )

    if not numeric:
        failures = memory.consecutive_failures + 1
        age = (
            now_mono - memory.last_trusted_mono
            if memory.last_trusted_mono is not None else math.inf
        )
        status = (
            STATUS_DEGRADED
            if age <= freshness and failures < MISSING_AFTER_FAILURES
            else STATUS_ABSENT
        )
        reasons = ("read_error" if error else "non_numeric",)
        new_memory = replace(
            memory,
            consecutive_failures=failures,
            failures_since_calibration=memory.failures_since_calibration + 1,
            last_failure_at=now_iso,
            previous_status=status,
        )
        return QualityDecision(
            status=status,
            acquisition_status=ACQUISITION_ERROR,
            reasons=reasons,
            raw_value=None,
            observed_value=None,
            value=None,
            last_trusted_value=memory.last_trusted_value,
            control_usable=False,
            would_block_control=True,
            control_disposition="blocked",
            calibration_overdue=overdue,
        ), new_memory

    raw = float(raw_value)
    observed = raw + float(profile.get("offset", 0.0))
    plausible = _inside_plausible(definition, observed, profile)
    reasons: list[str] = []
    frozen = memory.frozen
    recovery = memory.recovery_samples
    unchanged_seconds = memory.unchanged_seconds
    unchanged_samples = memory.unchanged_samples
    last_change = memory.last_change_mono

    if plausible:
        epsilon = float(profile.get("freeze_epsilon", 0.0))
        changed = memory.last_raw_value is None or abs(raw - memory.last_raw_value) > epsilon
        if changed:
            last_change = now_mono
            unchanged_seconds = 0.0
            unchanged_samples = 1
            recovery = recovery + 1 if frozen else 0
        else:
            interval = 0.0 if memory.last_sample_mono is None else max(
                0.0, min(now_mono - memory.last_sample_mono, freshness)
            )
            unchanged_seconds += interval
            unchanged_samples += 1
            # Une seule variation suivie de valeurs à nouveau identiques ne
            # prouve pas que le capteur s'est réellement débloqué.
            recovery = 0 if frozen else recovery

        freeze_after = profile.get("freeze_after_seconds")
        if freeze_after is not None and not frozen:
            frozen = (
                unchanged_seconds >= float(freeze_after)
                and unchanged_samples >= int(profile.get("freeze_min_samples", 2))
            )
        if frozen and recovery >= RECOVERY_SAMPLES:
            frozen = False
            recovery = 0
        if frozen:
            reasons.append("frozen")
    else:
        reasons.append("out_of_range")

    if overdue is True:
        reasons.append("calibration_overdue")
    elif overdue is None:
        reasons.append("calibration_age_unknown")

    inconsistent = not plausible or frozen
    status = STATUS_INCONSISTENT if inconsistent else (
        STATUS_DEGRADED if reasons else STATUS_NORMAL
    )
    shadowable = inconsistent and plausible and frozen
    control_usable = not inconsistent or (mode == "observe" and shadowable)
    trusted = None if inconsistent else observed
    entered_inconsistent = (
        status == STATUS_INCONSISTENT and memory.previous_status != STATUS_INCONSISTENT
    )
    new_memory = replace(
        memory,
        last_raw_value=raw,
        last_sample_mono=now_mono,
        last_change_mono=last_change,
        unchanged_seconds=unchanged_seconds,
        unchanged_samples=unchanged_samples,
        frozen=frozen,
        recovery_samples=recovery,
        consecutive_failures=0,
        incoherences_since_calibration=(
            memory.incoherences_since_calibration + int(entered_inconsistent)
        ),
        last_trusted_value=trusted if trusted is not None else memory.last_trusted_value,
        last_trusted_mono=now_mono if trusted is not None else memory.last_trusted_mono,
        last_trusted_at=now_iso if trusted is not None else memory.last_trusted_at,
        previous_status=status,
    )
    return QualityDecision(
        status=status,
        acquisition_status=ACQUISITION_OK,
        reasons=tuple(reasons),
        raw_value=raw,
        observed_value=observed,
        value=trusted,
        last_trusted_value=new_memory.last_trusted_value,
        control_usable=control_usable,
        would_block_control=inconsistent,
        control_disposition=(
            "shadow_accepted" if inconsistent and control_usable
            else "blocked" if inconsistent else "trusted"
        ),
        calibration_overdue=overdue,
    ), new_memory


def apply_enforcement_mode(decision: QualityDecision, mode: str) -> QualityDecision:
    """Réapplique le mode courant à un diagnostic déjà calculé.

    Le passage d'Observation à Armé doit prendre effet sur le snapshot en
    mémoire, sans attendre la prochaine lecture matérielle.
    """
    if not decision.would_block_control:
        return decision
    shadowable = (
        decision.acquisition_status == ACQUISITION_OK
        and decision.observed_value is not None
        and any(
            reason in {"frozen", "redundancy_mismatch", "redundancy_recovery"}
            for reason in decision.reasons
        )
        and "out_of_range" not in decision.reasons
    )
    usable = mode == "observe" and shadowable
    return replace(
        decision,
        control_usable=usable,
        control_disposition="shadow_accepted" if usable else "blocked",
    )


def apply_freshness(
    decision: QualityDecision,
    memory: QualityMemory,
    *,
    now_mono: float,
    freshness_seconds: float,
) -> QualityDecision:
    """Déclasse une ancienne valeur sans modifier la mémoire persistée."""
    if memory.last_sample_mono is None:
        return replace(decision, status=STATUS_ABSENT, reasons=("never",), value=None,
                       control_usable=False, would_block_control=True,
                       control_disposition="blocked")
    if now_mono - memory.last_sample_mono <= freshness_seconds:
        return decision
    reasons = tuple(dict.fromkeys((*decision.reasons, "stale")))
    return replace(decision, status=STATUS_ABSENT, reasons=reasons, value=None,
                   control_usable=False, would_block_control=True,
                   control_disposition="blocked")


def apply_redundancy(
    decisions: Mapping[str, QualityDecision],
    groups: Mapping,
    *,
    mode: str,
) -> dict[str, QualityDecision]:
    """Applique des comparaisons déterministes sans choisir arbitrairement."""
    result = dict(decisions)
    for group_name, group in groups.items():
        members = list(group.members)
        available = {
            key: result[key].observed_value
            for key in members
            if key in result
            and result[key].status in {STATUS_NORMAL, STATUS_DEGRADED}
            and result[key].observed_value is not None
        }
        if len(available) < group.minimum_agreeing:
            for key in members:
                if key not in result:
                    continue
                decision = result[key]
                status = STATUS_DEGRADED if decision.status == STATUS_NORMAL else decision.status
                reasons = tuple(dict.fromkeys((*decision.reasons, "redundancy_unavailable")))
                result[key] = replace(decision, status=status, reasons=reasons,
                                      redundancy_group=group_name,
                                      redundancy_status="unavailable")
            continue

        tolerance = float(group.tolerance)
        keys = sorted(available)
        clusters = []
        for anchor in keys:
            cluster = {
                key for key in keys
                if abs(float(available[key]) - float(available[anchor])) <= tolerance
            }
            if max(float(available[key]) for key in cluster) - min(
                float(available[key]) for key in cluster
            ) <= tolerance:
                clusters.append(cluster)
        max_size = max(len(cluster) for cluster in clusters)
        winners = {frozenset(cluster) for cluster in clusters if len(cluster) == max_size}
        coherent = set(next(iter(winners))) if len(winners) == 1 and max_size >= group.minimum_agreeing else set()
        all_inconsistent = not coherent
        for key in members:
            if key not in result:
                continue
            decision = result[key]
            delta = None
            if key in available and coherent:
                centre = sum(float(available[item]) for item in coherent) / len(coherent)
                delta = abs(float(available[key]) - centre)
            mismatch = key in available and (all_inconsistent or key not in coherent)
            if mismatch:
                reasons = tuple(dict.fromkeys((*decision.reasons, "redundancy_mismatch")))
                control_usable = mode == "observe" and decision.control_usable
                result[key] = replace(
                    decision,
                    status=STATUS_INCONSISTENT,
                    reasons=reasons,
                    value=None,
                    control_usable=control_usable,
                    would_block_control=True,
                    control_disposition="shadow_accepted" if control_usable else "blocked",
                    redundancy_group=group_name,
                    redundancy_status="mismatch",
                    redundancy_delta=delta,
                )
            else:
                result[key] = replace(decision, redundancy_group=group_name,
                                      redundancy_status="coherent",
                                      redundancy_delta=delta)
    return result
