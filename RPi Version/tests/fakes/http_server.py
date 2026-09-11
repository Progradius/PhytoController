"""Doubles du serveur HTTP : capteurs, statut, superviseur et catalogue d'équipements.

Partagés par `tests/test_http_server.py` (suite pytest) et `tests/ui_server.py` (serveur des specs
navigateur). Ce module ne dépend **pas** de `pytest` : le serveur des specs l'importe à chaque
démarrage, et tirer `pytest` (≈ 0,7 s d'import) à travers le module de tests coûtait un cinquième
de chaque démarrage.
"""

from __future__ import annotations

from dataclasses import dataclass

from controllers.sensor_catalog import SENSOR_CATALOG


CSRF_TOKEN = "T" * 43


class FakeStats:
    KEYS = ("BME280T", "BME280H", "DS18B#3")

    def __init__(self):
        self.cleared = []
        self.data = {
            key: {"min": None, "min_date": None, "max": None, "max_date": None}
            for key in self.KEYS
        }

    def get_all(self):
        return {key: dict(value) for key, value in self.data.items()}

    def clear_key(self, key):
        self.cleared.append(key)

    def update(self, key, value):
        self.data[key].update({
            "min": value, "min_date": "2026-09-02T20:00:00",
            "max": value, "max_date": "2026-09-02T20:00:00",
        })


class FakeSensors:
    def __init__(self, config):
        self.config = config
        self.stats = FakeStats()
        self.reconfigured = 0
        self.quality_resets = []

    def snapshot(self):
        return {
            definition.key: {
                "key": definition.key,
                "label": definition.label,
                "unit": definition.unit,
                "decimals": definition.decimals,
                "enabled": bool(getattr(self.config.sensors, definition.enabled_field)),
                "family": definition.family,
                "hardware_id": None,
                "status": "normal",
                "acquisition_status": "ok",
                "reason_codes": [],
                "value": 21.5,
                "observed_value": 21.5,
                "raw_value": 21.5,
                "last_trusted_value": 21.5,
                "control_usable": True,
                "would_block_control": False,
                "control_disposition": "trusted",
                "enforcement_mode": self.config.sensor_quality.mode,
                "last_attempt_at": "2026-08-26T10:00:00Z",
                "last_success_at": "2026-08-26T10:00:00Z",
                "last_trusted_at": "2026-08-26T10:00:00Z",
                "attempt_age_s": 1.0,
                "age_s": 1.0,
                "unchanged_for_s": 0.0,
                "freshness_threshold_s": definition.freshness_seconds,
                "plausible_range": {
                    "min": definition.plausible_min,
                    "max": definition.plausible_max,
                },
                "freeze_epsilon": definition.freeze_epsilon,
                "freeze_after_seconds": definition.freeze_after_seconds,
                "freeze_min_samples": definition.freeze_min_samples,
                "calibration": {
                    "offset": 0.0, "calibrated_at": None,
                    "valid_days": None, "overdue": False,
                },
                "failures": {
                    "consecutive": 0, "since_calibration": 0,
                    "incoherences_since_calibration": 0, "last_at": None,
                },
                "redundancy": {
                    "group": None, "status": "not_configured", "delta": None,
                },
            }
            for definition in SENSOR_CATALOG
        }

    def cached_value(self, _key, max_age=30.0):
        return 21.5

    async def reconfigure(self, config):
        self.reconfigured += 1
        self.config = config

    def discovered_ds18_ids(self):
        return ["28-000000000001", "28-000000000002"]

    def reset_quality(self, key):
        self.quality_resets.append(key)


class FakeStatus:
    def get_component_state(self):
        return "off"

    def get_motor_speed(self):
        return 0

    def get_dailytimer_current_start_time(self):
        return "19:00"

    def get_dailytimer_current_stop_time(self):
        return "07:00"


class FakeSupervisor:
    def __init__(self):
        self.reloads = []

    def is_healthy(self):
        return True

    def control_healthy(self):
        return True

    def unhealthy_names(self):
        return []

    def snapshot(self):
        return {"http_server": {"alive": True, "healthy": True}}

    def health_domains(self):
        return {"http": {"healthy": True, "tasks": ["http_server"], "unhealthy": []}}

    def request_reload(self, name):
        self.reloads.append(name)
        return True


@dataclass
class FakeEquipmentStore:
    current: dict

    def payload(self):
        return {key: value.model_dump() for key, value in self.current.items()}

    def save(self, candidate):
        self.current = dict(candidate)
