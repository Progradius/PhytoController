from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from param.config import AppConfig
from param.config_store import ConfigStore


def test_save_cree_backup_et_preserve_identite(config_path):
    store = ConfigStore(config_path)
    shared = store.current
    old_content = config_path.read_text(encoding="utf-8")
    candidate = shared.model_copy(deep=True)
    candidate.life_period.stage = "floraison-test"

    result = store.save(candidate)

    assert result is shared
    assert store.current is shared
    assert shared.life_period.stage == "floraison-test"
    assert config_path.with_name("param.json.bak").read_text(encoding="utf-8") == old_content
    assert AppConfig.load(config_path).life_period.stage == "floraison-test"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["Heater_Settings"]["enabled"] == "enabled"
    assert raw["DailyTimer2_Settings"]["enabled"] == "disabled"


def test_refresh_corrompu_garde_la_configuration_et_ne_reparse_pas(
    config_path, monkeypatch
):
    store = ConfigStore(config_path)
    shared = store.current
    original_load = AppConfig.load
    calls = []

    def counted(path=None):
        calls.append(path)
        return original_load(path)

    monkeypatch.setattr(AppConfig, "load", counted)
    config_path.write_text("{cassé", encoding="utf-8")

    assert store.refresh() is shared
    assert shared.life_period.stage == "test"
    assert len(calls) == 1
    assert store.refresh() is shared
    assert len(calls) == 1


def test_refresh_valide_mute_instance_en_place(config_path, valid_config_payload):
    store = ConfigStore(config_path)
    shared = store.current
    modified = copy.deepcopy(valid_config_payload)
    modified["Life_Period"]["stage"] = "recharge"
    config_path.write_text(json.dumps(modified), encoding="utf-8")

    assert store.refresh() is shared
    assert store.current is shared
    assert shared.life_period.stage == "recharge"


def test_boot_restaure_un_backup_valide(tmp_path, valid_config_payload):
    path = tmp_path / "param.json"
    backup = tmp_path / "param.json.bak"
    path.write_text("pas du json", encoding="utf-8")
    backup.write_text(json.dumps(valid_config_payload), encoding="utf-8")

    store = ConfigStore(path)

    assert store.recovery_pending is True
    assert store.current.life_period.stage == "test"
    assert AppConfig.load(path).life_period.stage == "test"
    candidate = store.current.model_copy(deep=True)
    candidate.life_period.stage = "adoptee"
    store.save(candidate)
    assert store.recovery_pending is False


def test_boot_refuse_primaire_et_backup_invalides(tmp_path):
    path = tmp_path / "param.json"
    path.write_text("cassé", encoding="utf-8")
    (tmp_path / "param.json.bak").write_text("cassé aussi", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        ConfigStore(path)


def test_commit_refuse_restaure_memoire_et_disque(config_path):
    store = ConfigStore(config_path)
    shared = store.current
    disk_before = config_path.read_bytes()
    original_min = shared.motor.min_speed
    shared.motor.__dict__["min_speed"] = 4
    shared.motor.__dict__["max_speed"] = 1

    with pytest.raises(ValidationError):
        store.commit()

    assert store.current is shared
    assert shared.motor.min_speed == original_min
    assert shared.motor.max_speed == 4
    assert config_path.read_bytes() == disk_before


def test_echec_ecriture_n_adopte_pas_la_candidate(config_path, monkeypatch):
    store = ConfigStore(config_path)
    shared = store.current
    disk_before = config_path.read_bytes()
    candidate = shared.model_copy(deep=True)
    candidate.life_period.stage = "ne-doit-pas-passer"

    def fail_write(*_args, **_kwargs):
        raise OSError("disque plein simulé")

    monkeypatch.setattr("param.config_store.write_text_atomic", fail_write)
    with pytest.raises(OSError):
        store.save(candidate)

    assert store.current is shared
    assert shared.life_period.stage == "test"
    assert config_path.read_bytes() == disk_before
