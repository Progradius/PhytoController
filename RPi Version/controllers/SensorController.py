# controller/sensor/SensorController.py
# Author : Progradius
# License : AGPL-3.0
# --------------------------------------------------------------------
#  Gestion unifiée de tous les capteurs matériels pour Raspberry Pi
#  (refactoré pour utiliser AppConfig au lieu de Parameter)
# --------------------------------------------------------------------

import asyncio
import copy
import smbus2
import threading
from dataclasses import asdict, replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from typing import Dict, List

# Handlers spécialisés
from sensor_handlers.BME280Handler   import BME280Handler
from sensor_handlers.DS18Handler     import DS18Handler
from sensor_handlers.VEML6075Handler import VEMLHandler
from sensor_handlers.VL53L0XHandler  import VL53L0XHandler
from sensor_handlers.MLX90614Handler import MLX90614Handler
from sensor_handlers.TSL2591Handler  import TSL2591Handler
from sensor_handlers.HCSR04Handler   import HCSR04Handler

# Affichage « Pretty »
from utils.pretty_console import debug, info, warning, error
from utils.log_dedup import StateLogger

LOGGER_NAME = "sensors"

# Votre modèle de config
from param.config import AppConfig
from controllers.sensor_catalog import (
    SENSOR_CATALOG, SENSORS_BY_KEY, effective_quality_profile, enabled_definitions,
    serialized_quality_thresholds,
)
from controllers.sensor_quality import (
    RECOVERY_SAMPLES, QualityDecision, QualityMemory, STATUS_ABSENT,
    STATUS_INCONSISTENT, apply_enforcement_mode, apply_freshness,
    apply_redundancy, evaluate_sample,
)
from utils.state_store import shared_store
from utils.time_reliability import time_reliability


class SensorController:
    """
    Regroupe tous les capteurs sous des measurements « métier » :
      • air          : BME280 + MLX90614 ambiant
      • surface_temp : MLX90614 objet
      • water        : DS18B#3 (température d'eau)
      • distance     : VL53L0X + HC-SR04
      • lux          : TSL2591
    """

    def __init__(self, config: AppConfig, stats=None):
        self.config = config
        self.stats = stats
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phyto-sensors")
        self._snapshot_lock = threading.Lock()
        self._snapshot: dict[str, dict] = {}
        self._quality_memory: dict[str, QualityMemory] = {}
        self._quality_decisions: dict[str, QualityDecision] = {}
        self._quality_signatures: dict[str, dict] = {}
        self._quality_store = shared_store()
        self._quality_state_raw = self._quality_store.load("sensor_quality")
        self._closed = False

        # Échecs de lecture : une ligne à l'entrée en panne, une au rétablissement
        self._read_states: Dict[str, StateLogger] = {}
        self._stats_state = StateLogger("Mise à jour des min/max capteurs",
                                        name=LOGGER_NAME, level="warning")
        self.i2c = None
        self.bme = self.ds18 = self.veml = self.vl53 = None
        self.mlx = self.tsl = self.hcsr = None
        self.__init_handlers()

    def __init_handlers(self) -> None:
        """Construit les handlers activés sur l'unique propriétaire matériel."""
        # ── Bus I2C (/dev/i2c-1) ───────────────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)
            info("Bus I²C /dev/i2c-1 ouvert", name=LOGGER_NAME)
        except (FileNotFoundError, PermissionError, OSError) as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 → {e.__class__.__name__} : {e}",
                  name=LOGGER_NAME)
            self.i2c = None

        # ── Activation selon AppConfig.sensors ─────────────────────────
        s = self.config.sensors
        self.bme_enabled  = s.bme280_state
        self.ds18_enabled = s.ds18b20_state
        self.veml_enabled = s.veml6075_state
        self.vl53_enabled = s.vl53L0x_state
        self.mlx_enabled  = s.mlx90614_state
        self.tsl_enabled  = s.tsl2591_state
        self.hcsr_enabled = s.hcsr04_state

        # Instanciation conditionnelle
        i2c_users = (self.bme_enabled or self.veml_enabled
                     or self.mlx_enabled or self.tsl_enabled)
        if self.i2c is None and i2c_users:
            warning("Bus I²C indisponible → capteurs I²C en mode dégradé (lectures None)",
                    name=LOGGER_NAME)

        self.bme  = BME280Handler(i2c=self.i2c)   if self.bme_enabled else None
        self.ds18 = DS18Handler()                 if self.ds18_enabled else None
        self.veml = VEMLHandler(i2c=self.i2c)     if self.veml_enabled else None
        self.vl53 = VL53L0XHandler(self.config)   if self.vl53_enabled else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if self.mlx_enabled else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if self.tsl_enabled else None
        self.hcsr = HCSR04Handler(
            trigger_pin=self.config.gpio.hcsr_trigger_pin,
            echo_pin=self.config.gpio.hcsr_echo_pin
        ) if self.hcsr_enabled else None

        # ── Dictionnaire de mesures pour Influx / Web ─────────────────
        self.sensor_dict = self._build_sensor_dict()

        # État des capteurs journalisé UNE fois, à l'init (et non en boucle)
        etats = {
            "BME280": self.bme_enabled, "DS18B20": self.ds18_enabled,
            "VEML6075": self.veml_enabled, "VL53L0X": self.vl53_enabled,
            "MLX90614": self.mlx_enabled, "TSL2591": self.tsl_enabled,
            "HC-SR04": self.hcsr_enabled,
        }
        actifs   = [n for n, on in etats.items() if on] or ["aucun"]
        inactifs = [n for n, on in etats.items() if not on] or ["aucun"]
        info(f"Capteurs actifs : {', '.join(actifs)}", name=LOGGER_NAME)
        info(f"Capteurs désactivés : {', '.join(inactifs)}", name=LOGGER_NAME)
        debug(f"Mesures exportées : {self.sensor_dict}", name=LOGGER_NAME)

    def _close_devices(self) -> None:
        """Ferme les bus sans jamais libérer les GPIO vers un état flottant."""
        if self.vl53 and hasattr(self.vl53, "close"):
            self.vl53.close()
        if self.hcsr and getattr(self.hcsr, "sensor", None):
            try:
                import RPi.GPIO as GPIO
                GPIO.output(self.hcsr.sensor.trigger_pin, GPIO.LOW)
            except Exception as exc:
                warning(
                    f"HC-SR04 : maintien du trigger LOW impossible ({exc.__class__.__name__})",
                    name=LOGGER_NAME,
                )
        if self.i2c is not None:
            try:
                self.i2c.close()
            except Exception as exc:
                debug(f"Fermeture I²C ignorée : {exc.__class__.__name__}", name=LOGGER_NAME)
        self.i2c = None
        self.bme = self.ds18 = self.veml = self.vl53 = None
        self.mlx = self.tsl = self.hcsr = None

    def _is_sensor_enabled(self, sensor_name: str) -> bool:
        definition = SENSORS_BY_KEY.get(sensor_name)
        return bool(
            definition
            and getattr(self.config.sensors, definition.enabled_field, False)
        )

    def _build_sensor_dict(self) -> Dict[str, List[str]]:
        """
        Construit le dictionnaire des capteurs activés, utilisé pour l'export.
        """
        sensor_dict: Dict[str, List[str]] = {}
        for definition in enabled_definitions(self.config):
            sensor_dict.setdefault(definition.measurement, []).append(definition.key)

        return sensor_dict

    def get_sensor_value(self, sensor_key: str):
        """
        Retourne la mesure demandée (float ou int) ou None si désactivé/erreur.
        """
        try:
            result = None

            if sensor_key.startswith("DS18B#") and self.ds18:
                hardware_id = self.config.sensor_quality.ds18b20_bindings.get(sensor_key)
                if not hardware_id:
                    self._state_for(sensor_key).fail("identité 1-Wire non liée")
                    self._record_snapshot(sensor_key, None, error="hardware_identity_unbound")
                    return None
                result = self.ds18.get_ds18_temp_by_id(hardware_id)

            elif sensor_key.startswith("BME280") and self.bme:
                result = {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }[sensor_key]()

            elif sensor_key.startswith("TSL-") and self.tsl:
                result = {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR": self.tsl.get_ir
                }[sensor_key]()

            elif sensor_key.startswith("VEML-") and self.veml:
                result = {
                    "VEML-UVA": self.veml.get_veml_uva,
                    "VEML-UVB": self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_veml_uv_index
                }[sensor_key]()

            elif sensor_key in ("MLX-AMB", "MLX-OBJ") and self.mlx:
                result = {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }[sensor_key]()

            elif sensor_key == "VL53L0X" and self.vl53:
                result = self.vl53.get_vl53_reading()

            elif sensor_key == "HCSR04" and self.hcsr:
                result = self.hcsr.get_distance_cm()

        except Exception as e:
            self._state_for(sensor_key).fail(f"{e.__class__.__name__} : {e}")
            self._record_snapshot(sensor_key, None, error=f"{e.__class__.__name__}")
            return None

        if result is None:
            if not self._is_sensor_enabled(sensor_key):
                # Capteur volontairement désactivé : ce n'est pas une anomalie
                debug(f"{sensor_key} désactivé", name=LOGGER_NAME)
            else:
                self._state_for(sensor_key).fail("lecture vide")
            self._record_snapshot(sensor_key, None, error="lecture vide")
            return None

        self._state_for(sensor_key).ok()
        decision = self._record_snapshot(sensor_key, result)

        stats = getattr(self, "stats", None)
        if stats and sensor_key in stats.KEYS and decision.value is not None:
            try:
                stats.update(sensor_key, float(decision.value))
                self._stats_state.ok()
            except Exception as e:
                self._stats_state.fail(f"{sensor_key} → {e.__class__.__name__} : {e}")

        return result

    async def read(self, sensor_key: str):
        """Lit une mesure dans l'unique exécuteur matériel sérialisé."""
        if self._closed:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.get_sensor_value, sensor_key)

    async def refresh_active(self) -> None:
        """Rafraîchit toutes les mesures actives, sans bloquer l'event loop."""
        for definition in enabled_definitions(self.config):
            await self.read(definition.key)
        self._apply_redundancy_snapshot()

    def cached_value(self, sensor_key: str, max_age: float = 20.0):
        """Compatibilité : ne rend qu'une valeur actuellement autorisée."""
        reading = self.cached_reading(sensor_key, max_age=max_age)
        if not reading or not reading["control_usable"]:
            return None
        return reading["observed_value"]

    def cached_reading(self, sensor_key: str, max_age: float | None = None) -> dict | None:
        definition = SENSORS_BY_KEY.get(sensor_key)
        if definition is None:
            return None
        profile = effective_quality_profile(self.config, definition)
        freshness = float(profile["freshness_seconds"])
        if max_age is not None:
            freshness = min(freshness, float(max_age))
        now = monotonic()
        with self._snapshot_lock:
            record = self._snapshot.get(sensor_key)
            decision = self._quality_decisions.get(sensor_key)
            memory = self._quality_memory.get(sensor_key)
            if not record or decision is None or memory is None:
                return None
            decision = apply_freshness(
                decision, memory, now_mono=now, freshness_seconds=freshness,
            )
            return self._serialize_reading(definition, profile, record, decision, memory, now)

    async def fresh_value(self, sensor_key: str, max_age: float = 20.0):
        reading = await self.fresh_reading(sensor_key, max_age=max_age)
        if not reading or not reading["control_usable"]:
            return None
        return reading["observed_value"]

    async def fresh_reading(self, sensor_key: str, max_age: float | None = None) -> dict | None:
        reading = self.cached_reading(sensor_key, max_age=max_age)
        if reading is not None and reading["attempt_age_s"] <= reading["freshness_threshold_s"]:
            return reading
        await self.read(sensor_key)
        self._apply_redundancy_snapshot()
        return self.cached_reading(sensor_key, max_age=max_age)

    def snapshot(self) -> dict[str, dict]:
        """Copie sérialisable du dernier état connu, sans aucune lecture."""
        now = monotonic()
        result: dict[str, dict] = {}
        with self._snapshot_lock:
            records = copy.deepcopy(self._snapshot)
            decisions = dict(self._quality_decisions)
            memories = dict(self._quality_memory)
        for definition in SENSOR_CATALOG:
            record = records.get(definition.key)
            enabled = self._is_sensor_enabled(definition.key)
            profile = effective_quality_profile(self.config, definition)
            if not enabled:
                result[definition.key] = self._empty_reading(definition, profile, "disabled", enabled=False)
                continue
            decision = decisions.get(definition.key)
            memory = memories.get(definition.key)
            if record is None or decision is None or memory is None:
                result[definition.key] = self._empty_reading(definition, profile, STATUS_ABSENT, enabled=True)
                continue
            fresh = apply_freshness(
                decision, memory, now_mono=now,
                freshness_seconds=float(profile["freshness_seconds"]),
            )
            result[definition.key] = self._serialize_reading(
                definition, profile, record, fresh, memory, now,
            )
        return result

    async def reconfigure(self, config: AppConfig) -> None:
        """Reconstruit les handlers sur le même propriétaire, de façon sérialisée."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._reconfigure_sync, config)

    def discovered_ds18_ids(self) -> list[str]:
        return self.ds18.get_address_list() if self.ds18 else []

    def reset_quality(self, sensor_key: str) -> None:
        """Réarme les diagnostics d'une mesure sans toucher au matériel."""
        if sensor_key not in SENSORS_BY_KEY:
            raise ValueError("mesure capteur inconnue")
        with self._snapshot_lock:
            self._quality_memory.pop(sensor_key, None)
            self._quality_decisions.pop(sensor_key, None)
            self._quality_signatures.pop(sensor_key, None)
            self._snapshot.pop(sensor_key, None)
            self._persist_quality_state_locked()
        self._quality_store.flush()

    def _reconfigure_sync(self, config: AppConfig) -> None:
        self._close_devices()
        self.config = config
        self.__init_handlers()
        self.sensor_dict = self._build_sensor_dict()
        with self._snapshot_lock:
            for key in list(self._snapshot):
                if not self._is_sensor_enabled(key):
                    self._snapshot.pop(key, None)
                    self._quality_decisions.pop(key, None)
        info("Pile capteurs reconfigurée sans nouvelle instance", name=LOGGER_NAME)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._close_devices)
        self._quality_store.flush()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _record_snapshot(self, sensor_key: str, value, error: str | None = None) -> QualityDecision:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        now_mono = monotonic()
        definition = SENSORS_BY_KEY[sensor_key]
        profile = effective_quality_profile(self.config, definition)
        reliable_date = (
            datetime.now(timezone.utc).date()
            if time_reliability().state != "unknown" else None
        )
        with self._snapshot_lock:
            previous = self._snapshot.get(sensor_key, {})
            signature = self._profile_signature(sensor_key, profile)
            memory = self._quality_memory.get(sensor_key)
            if memory is None or self._quality_signatures.get(sensor_key) != signature:
                memory = self._restore_quality_memory(sensor_key, profile)
                self._quality_signatures[sensor_key] = signature
            decision, memory = evaluate_sample(
                definition, profile, memory, raw_value=value, error=error,
                now_mono=now_mono, now_iso=now_iso, today=reliable_date,
                mode=self.config.sensor_quality.mode,
            )
            record = {
                "last_attempt_at": now_iso,
                "attempt_monotonic": now_mono,
                "last_success_at": previous.get("last_success_at"),
                "success_monotonic": previous.get("success_monotonic"),
                "error": error,
            }
            if error is None:
                record["last_success_at"] = now_iso
                record["success_monotonic"] = now_mono
            self._snapshot[sensor_key] = record
            self._quality_memory[sensor_key] = memory
            self._quality_decisions[sensor_key] = decision
            self._persist_quality_state_locked()
            return decision

    def _profile_signature(self, sensor_key: str, profile: dict) -> dict:
        redundancy = None
        for name, group in self.config.sensor_quality.redundancy_groups.items():
            if sensor_key in group.members:
                redundancy = {
                    "name": name,
                    **group.model_dump(mode="json"),
                }
                break
        return {
            "profile": dict(profile),
            "hardware_id": self.config.sensor_quality.ds18b20_bindings.get(sensor_key),
            "redundancy": redundancy,
        }

    def _restore_quality_memory(self, sensor_key: str, profile: dict) -> QualityMemory:
        saved = self._quality_state_raw.get(sensor_key, {})
        if saved.get("signature") != self._profile_signature(sensor_key, profile):
            return QualityMemory()
        raw = saved.get("memory", {})
        allowed = set(QualityMemory.__dataclass_fields__)
        try:
            restored = QualityMemory(**{key: value for key, value in raw.items() if key in allowed})
        except (TypeError, ValueError):
            return QualityMemory()
        return replace(restored, last_sample_mono=None, last_change_mono=None,
                       last_trusted_mono=None, previous_status=STATUS_ABSENT)

    def _persist_quality_state_locked(self) -> None:
        payload = {}
        for key, memory in self._quality_memory.items():
            definition = SENSORS_BY_KEY[key]
            profile = effective_quality_profile(self.config, definition)
            serialized = asdict(memory)
            serialized["last_sample_mono"] = None
            serialized["last_change_mono"] = None
            serialized["last_trusted_mono"] = None
            payload[key] = {
                "signature": self._profile_signature(key, profile),
                "memory": serialized,
            }
        # `reset_quality()` peut être suivi d'une lecture avant l'écriture
        # physique différée du StateStore. La source de restauration en mémoire
        # doit donc refléter immédiatement le nouvel état, sinon l'ancien
        # diagnostic serait ressuscité.
        self._quality_state_raw = copy.deepcopy(payload)
        self._quality_store.save("sensor_quality", payload)

    def _apply_redundancy_snapshot(self) -> None:
        with self._snapshot_lock:
            decisions = apply_redundancy(
                self._quality_decisions,
                self.config.sensor_quality.redundancy_groups,
                mode=self.config.sensor_quality.mode,
            )
            for key, decision in list(decisions.items()):
                memory = self._quality_memory.get(key)
                if memory is None or decision.redundancy_group is None:
                    continue
                if decision.redundancy_status == "mismatch":
                    entered = not memory.redundancy_inconsistent
                    self._quality_memory[key] = replace(
                        memory,
                        redundancy_inconsistent=True,
                        redundancy_recovery_samples=0,
                        incoherences_since_calibration=(
                            memory.incoherences_since_calibration + int(entered)
                        ),
                    )
                    continue
                if (decision.redundancy_status == "coherent"
                        and memory.redundancy_inconsistent):
                    recovery = memory.redundancy_recovery_samples + 1
                    if recovery < RECOVERY_SAMPLES:
                        reasons = tuple(dict.fromkeys(
                            (*decision.reasons, "redundancy_recovery")
                        ))
                        held = replace(
                            decision,
                            status=STATUS_INCONSISTENT,
                            reasons=reasons,
                            value=None,
                            would_block_control=True,
                            redundancy_status="recovery",
                        )
                        decisions[key] = apply_enforcement_mode(
                            held, self.config.sensor_quality.mode
                        )
                        self._quality_memory[key] = replace(
                            memory, redundancy_recovery_samples=recovery
                        )
                    else:
                        self._quality_memory[key] = replace(
                            memory,
                            redundancy_inconsistent=False,
                            redundancy_recovery_samples=0,
                        )
            self._quality_decisions = decisions
            self._persist_quality_state_locked()

    def _hardware_id(self, definition) -> str | None:
        if definition.family == "DS18B20":
            return self.config.sensor_quality.ds18b20_bindings.get(definition.key)
        return None

    def _serialize_reading(self, definition, profile, record, decision, memory, now) -> dict:
        decision = apply_enforcement_mode(decision, self.config.sensor_quality.mode)
        attempt_age = round(max(0.0, now - record["attempt_monotonic"]), 1)
        trusted_age = (
            round(max(0.0, now - memory.last_trusted_mono), 1)
            if memory.last_trusted_mono is not None else None
        )
        return {
            "key": definition.key, "slug": definition.slug,
            "family": definition.family,
            "hardware_id": self._hardware_id(definition),
            "label": definition.label, "unit": definition.unit,
            "decimals": definition.decimals, "enabled": True,
            "status": decision.status,
            "acquisition_status": decision.acquisition_status,
            "reason_codes": list(decision.reasons),
            "value": decision.value,
            "observed_value": decision.observed_value,
            "raw_value": decision.raw_value,
            "last_trusted_value": decision.last_trusted_value,
            "control_usable": decision.control_usable,
            "would_block_control": decision.would_block_control,
            "control_disposition": decision.control_disposition,
            "enforcement_mode": self.config.sensor_quality.mode,
            "last_attempt_at": record.get("last_attempt_at"),
            "last_success_at": record.get("last_success_at"),
            "last_trusted_at": memory.last_trusted_at,
            "attempt_age_s": attempt_age,
            "age_s": trusted_age,
            "unchanged_for_s": round(memory.unchanged_seconds, 1),
            "freshness_threshold_s": float(profile["freshness_seconds"]),
            "plausible_range": {"min": profile["plausible_min"], "max": profile["plausible_max"]},
            **serialized_quality_thresholds(profile),
            "calibration": {
                "offset": profile.get("offset", 0.0),
                "calibrated_at": profile.get("calibrated_at"),
                "valid_days": profile.get("calibration_valid_days"),
                "overdue": decision.calibration_overdue,
            },
            "failures": {
                "consecutive": memory.consecutive_failures,
                "since_calibration": memory.failures_since_calibration,
                "incoherences_since_calibration": memory.incoherences_since_calibration,
                "last_at": memory.last_failure_at,
            },
            "redundancy": {
                "group": decision.redundancy_group,
                "status": decision.redundancy_status,
                "delta": decision.redundancy_delta,
            },
        }

    def _empty_reading(self, definition, profile, status, *, enabled) -> dict:
        return {
            "key": definition.key, "slug": definition.slug,
            "family": definition.family,
            "hardware_id": self._hardware_id(definition), "label": definition.label,
            "unit": definition.unit, "decimals": definition.decimals,
            "enabled": enabled, "status": status,
            "acquisition_status": "never", "reason_codes": [status],
            "value": None, "observed_value": None, "raw_value": None,
            "last_trusted_value": None, "control_usable": False,
            "would_block_control": enabled, "control_disposition": "blocked",
            "enforcement_mode": self.config.sensor_quality.mode,
            "last_attempt_at": None, "last_success_at": None, "last_trusted_at": None,
            "attempt_age_s": None, "age_s": None, "unchanged_for_s": 0.0,
            "freshness_threshold_s": float(profile["freshness_seconds"]),
            "plausible_range": {"min": profile["plausible_min"], "max": profile["plausible_max"]},
            **serialized_quality_thresholds(profile),
            "calibration": {"offset": profile.get("offset", 0.0),
                            "calibrated_at": profile.get("calibrated_at"),
                            "valid_days": profile.get("calibration_valid_days"),
                            "overdue": False},
            "failures": {"consecutive": 0, "since_calibration": 0,
                         "incoherences_since_calibration": 0, "last_at": None},
            "redundancy": {"group": None, "status": "not_configured", "delta": None},
        }

    def _state_for(self, sensor_key: str) -> StateLogger:
        """StateLogger dédié à un capteur (créé à la volée)."""
        state = self._read_states.get(sensor_key)
        if state is None:
            state = StateLogger(f"Lecture {sensor_key}", name=LOGGER_NAME, level="warning")
            self._read_states[sensor_key] = state
        return state
