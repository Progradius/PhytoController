from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from controllers.sensor_catalog import SENSORS_BY_KEY, effective_quality_profile
from controllers.sensor_quality import (
    ACQUISITION_OK,
    QualityDecision,
    QualityMemory,
    STATUS_ABSENT,
    STATUS_DEGRADED,
    STATUS_INCONSISTENT,
    STATUS_NORMAL,
    apply_enforcement_mode,
    apply_freshness,
    apply_redundancy,
    evaluate_sample,
)
from param.config import SensorRedundancyGroup
from sensor_handlers.DS18Handler import DS18Handler


NOW_ISO = "2026-08-27T10:00:00Z"


def evaluate(definition, profile, memory=QualityMemory(), *, raw=20.0, error=None,
             mono=0.0, mode="observe", today=date(2026, 8, 27)):
    return evaluate_sample(
        definition, profile, memory, raw_value=raw, error=error,
        now_mono=mono, now_iso=NOW_ISO, today=today, mode=mode,
    )


def test_offset_et_plage_s_appliquent_avant_publication(valid_config):
    definition = SENSORS_BY_KEY["BME280T"]
    profile = effective_quality_profile(valid_config, definition) | {"offset": 1.5}
    decision, memory = evaluate(definition, profile, raw=20.0)
    assert decision.status == STATUS_NORMAL
    assert decision.raw_value == 20.0
    assert decision.observed_value == 21.5
    assert decision.value == 21.5
    assert memory.last_trusted_value == 21.5

    rejected, _ = evaluate(definition, profile, raw=60.0, mono=10.0)
    assert rejected.status == STATUS_INCONSISTENT
    assert rejected.value is None
    assert rejected.control_usable is False
    assert "out_of_range" in rejected.reasons


def test_erreurs_transitoires_puis_absence_conservent_le_compteur(valid_config):
    definition = SENSORS_BY_KEY["BME280T"]
    profile = effective_quality_profile(valid_config, definition)
    _, memory = evaluate(definition, profile, raw=20.0, mono=0.0)
    for failure in range(1, 6):
        decision, memory = evaluate(
            definition, profile, memory, raw=None, error="lecture vide",
            mono=float(failure),
        )
        assert memory.consecutive_failures == failure
        assert memory.failures_since_calibration == failure
    assert decision.status == STATUS_ABSENT


def test_fraicheur_declasse_sans_modifier_la_memoire(valid_config):
    definition = SENSORS_BY_KEY["BME280T"]
    profile = effective_quality_profile(valid_config, definition)
    decision, memory = evaluate(definition, profile, raw=20.0, mono=10.0)
    stale = apply_freshness(decision, memory, now_mono=31.0, freshness_seconds=20.0)
    assert stale.status == STATUS_ABSENT
    assert stale.value is None
    assert memory.last_trusted_value == 20.0


def test_figement_exige_duree_et_echantillons_et_observe_avant_armement(valid_config):
    definition = SENSORS_BY_KEY["BME280T"]
    profile = effective_quality_profile(valid_config, definition) | {
        "freeze_after_seconds": 30.0,
        "freeze_min_samples": 4,
        "freeze_epsilon": 0.02,
        "freshness_seconds": 20.0,
    }
    memory = QualityMemory()
    for mono in (0.0, 10.0, 20.0, 30.0):
        observed, memory = evaluate(definition, profile, memory, raw=18.0, mono=mono)
    assert observed.status == STATUS_INCONSISTENT
    assert observed.reasons == ("frozen",)
    assert observed.control_usable is True
    assert observed.control_disposition == "shadow_accepted"

    armed, _ = evaluate(definition, profile, memory, raw=18.0, mono=40.0, mode="enforce")
    assert armed.status == STATUS_INCONSISTENT
    assert armed.control_usable is False
    assert armed.would_block_control is True

    cached_armed = apply_enforcement_mode(observed, "enforce")
    assert cached_armed.control_usable is False
    assert cached_armed.control_disposition == "blocked"


def test_changement_rearme_un_capteur_fige_apres_trois_reussites(valid_config):
    definition = SENSORS_BY_KEY["BME280T"]
    profile = effective_quality_profile(valid_config, definition) | {
        "freeze_after_seconds": 20.0, "freeze_min_samples": 3,
        "freshness_seconds": 20.0,
    }
    memory = QualityMemory()
    for mono in (0.0, 10.0, 20.0):
        decision, memory = evaluate(definition, profile, memory, raw=15.0, mono=mono)
    assert decision.status == STATUS_INCONSISTENT
    for index, raw in enumerate((15.2, 15.4, 15.6), start=3):
        decision, memory = evaluate(definition, profile, memory, raw=raw, mono=index * 10.0)
    assert decision.status == STATUS_NORMAL
    assert memory.frozen is False


def test_recuperation_redondante_reste_sans_effet_en_observation():
    decision = QualityDecision(
        status=STATUS_INCONSISTENT,
        acquisition_status=ACQUISITION_OK,
        reasons=("redundancy_recovery",),
        raw_value=20.0,
        observed_value=20.0,
        value=None,
        last_trusted_value=20.0,
        control_usable=False,
        would_block_control=True,
        control_disposition="blocked",
        calibration_overdue=False,
    )
    observed = apply_enforcement_mode(decision, "observe")
    assert observed.control_usable is True
    assert observed.control_disposition == "shadow_accepted"


def test_calibration_expiree_degrade_sans_bloquer(valid_config):
    definition = SENSORS_BY_KEY["BME280H"]
    profile = effective_quality_profile(valid_config, definition) | {
        "calibrated_at": "2026-01-01", "calibration_valid_days": 30,
    }
    decision, _ = evaluate(definition, profile, raw=50.0)
    assert decision.status == STATUS_DEGRADED
    assert decision.value == 50.0
    assert decision.control_usable is True
    assert decision.calibration_overdue is True


@pytest.mark.parametrize(
    "profile",
    [
        {"calibrated_at": "2026-02-31"},
        {"plausible_min": -30.0, "plausible_max": 40.0},
        {"plausible_min": 50.0, "plausible_max": 70.0},
    ],
)
def test_configuration_refuse_un_profil_impossible(valid_config, profile):
    payload = valid_config.model_dump(by_alias=True, mode="json")
    payload["Sensor_Quality"] = {"profiles": {"BME280T": profile}}
    with pytest.raises(ValidationError):
        valid_config.__class__.model_validate(payload)


def test_configuration_refuse_une_identite_ds18_invalide(valid_config):
    payload = valid_config.model_dump(by_alias=True, mode="json")
    payload["Sensor_Quality"] = {
        "ds18b20_bindings": {"DS18B#1": "28-pas-un-identifiant"}
    }
    with pytest.raises(ValidationError):
        valid_config.__class__.model_validate(payload)


def test_configuration_refuse_une_tolerance_redondante_infinie(valid_config):
    payload = valid_config.model_dump(by_alias=True, mode="json")
    payload["Sensor_Quality"] = {
        "redundancy_groups": {
            "air": {
                "members": ["BME280T", "MLX-AMB"],
                "tolerance": float("inf"),
                "minimum_agreeing": 2,
            }
        }
    }
    with pytest.raises(ValidationError):
        valid_config.__class__.model_validate(payload)


def test_ds18_est_lu_par_identite_stable_et_non_par_ordre(tmp_path):
    first = tmp_path / "28-000000000001"
    second = tmp_path / "28-000000000002"
    first.mkdir()
    second.mkdir()
    (first / "w1_slave").write_text("aa YES\naa t=12500\n", encoding="utf-8")
    (second / "w1_slave").write_text("bb YES\nbb t=23750\n", encoding="utf-8")
    handler = DS18Handler.__new__(DS18Handler)
    handler._sensors = [second, first]
    handler._missing_reported = set()

    assert handler.get_ds18_temp_by_id("28-000000000001") == 12.5
    assert handler.get_ds18_temp_by_id("28-000000000002") == 23.8


def test_redondance_a_deux_ne_choisit_pas_de_gagnant(valid_config):
    bme = SENSORS_BY_KEY["BME280T"]
    mlx = SENSORS_BY_KEY["MLX-AMB"]
    bme_decision, _ = evaluate(bme, effective_quality_profile(valid_config, bme), raw=20.0)
    mlx_decision, _ = evaluate(mlx, effective_quality_profile(valid_config, mlx), raw=24.0)
    group = SensorRedundancyGroup(
        members=["BME280T", "MLX-AMB"], tolerance=1.0, minimum_agreeing=2,
    )
    result = apply_redundancy(
        {"BME280T": bme_decision, "MLX-AMB": mlx_decision},
        {"air": group}, mode="enforce",
    )
    assert result["BME280T"].status == STATUS_INCONSISTENT
    assert result["MLX-AMB"].status == STATUS_INCONSISTENT


def test_redondance_a_trois_isole_l_outlier(valid_config):
    keys_values = {"BME280T": 20.0, "MLX-AMB": 20.4, "DS18B#1": 25.0}
    decisions = {}
    for key, value in keys_values.items():
        definition = SENSORS_BY_KEY[key]
        decisions[key], _ = evaluate(
            definition, effective_quality_profile(valid_config, definition), raw=value,
        )
    group = SensorRedundancyGroup(
        members=list(keys_values), tolerance=1.0, minimum_agreeing=2,
    )
    result = apply_redundancy(decisions, {"air": group}, mode="enforce")
    assert result["BME280T"].redundancy_status == "coherent"
    assert result["MLX-AMB"].redundancy_status == "coherent"
    assert result["DS18B#1"].status == STATUS_INCONSISTENT
