"""Magasin de forçages « arrêt » — bornes, double horloge et reprise au boot."""

from __future__ import annotations

import json

import pytest

from utils import overrides as overrides_module
from utils.overrides import (
    InvalidDuration,
    OverrideStore,
    TimeUnreliable,
    UnknownTarget,
    max_seconds,
)
from utils.state_store import StateStore


class FakeReliability:
    def __init__(self, state: str = "synchronized") -> None:
        self.state = state


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    return OverrideStore(StateStore(tmp_path / "runtime_state.json"))


def test_plafonds_distincts_par_cible():
    # Le chauffage et le moteur sont des outils d'intervention physique : 4 h.
    assert max_seconds("heater") == 4 * 3600
    assert max_seconds("motor") == 4 * 3600
    assert max_seconds("daily_1") == 24 * 3600


def test_duree_hors_bornes_refusee(store):
    with pytest.raises(InvalidDuration):
        store.create("heater", 4 * 3600 + 1, "")
    with pytest.raises(InvalidDuration):
        store.create("heater", 0, "")
    with pytest.raises(InvalidDuration):
        store.create("daily_1", "trop long", "")
    assert store.active() == {}


def test_cible_hors_liste_blanche_refusee(store):
    with pytest.raises(UnknownTarget):
        store.create("gpio_17", 60, "")
    with pytest.raises(UnknownTarget):
        store.cancel("all")


def test_heure_inconnue_interdit_la_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("unknown"))
    magasin = OverrideStore(StateStore(tmp_path / "runtime_state.json"))
    with pytest.raises(TimeUnreliable):
        magasin.create("motor", 600, "")


def test_expiration_au_premier_des_deux_horloges(store):
    store.create("motor", 600, "", now_epoch=1_000.0, now_mono=500.0)

    assert store.is_forced_off("motor", 1_100.0, 600.0) is True
    # Saut NTP avant : l'échéance epoch tombe la première.
    assert store.is_forced_off("motor", 9_999.0, 600.0) is False

    store.create("motor", 600, "", now_epoch=1_000.0, now_mono=500.0)
    # Saut NTP arrière : le monotonic borne quand même.
    assert store.is_forced_off("motor", 0.0, 2_000.0) is False


def test_un_saut_arriere_ne_prolonge_pas(store):
    store.create("heater", 600, "", now_epoch=1_000.0, now_mono=500.0)
    # L'horloge murale recule d'une heure : le forçage ne gagne pas une heure.
    assert store.is_forced_off("heater", -2_600.0, 1_101.0) is False


def test_raison_bornee_et_nettoyee(store):
    record = store.create("daily_1", 60, "  arrosage\x00 manuel  " + "x" * 400)
    assert "\x00" not in record.reason
    assert len(record.reason) <= 200


def test_persistance_et_reprise_apres_redemarrage(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    chemin = tmp_path / "runtime_state.json"
    premier = OverrideStore(StateStore(chemin))
    premier.create("cyclic_1", 3_600, "maintenance", now_epoch=1_000.0, now_mono=10.0)

    persisté = json.loads(chemin.read_text(encoding="utf-8"))
    assert persisté["overrides"]["cyclic_1"]["expires_epoch"] == 4_600.0
    # `deadline_mono` n'a aucun sens après un redémarrage : elle n'est pas écrite.
    assert "deadline_mono" not in persisté["overrides"]["cyclic_1"]

    second = OverrideStore(StateStore(chemin))
    assert second.restore(now_epoch=2_000.0, now_mono=0.0) == 1
    record = second.active(2_000.0, 0.0)["cyclic_1"]
    assert record.confirmed is True
    assert record.remaining_seconds(2_000.0, 0.0) == pytest.approx(2_600.0)


def test_reprise_echue_ignoree(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    chemin = tmp_path / "runtime_state.json"
    premier = OverrideStore(StateStore(chemin))
    premier.create("daily_2", 60, "", now_epoch=1_000.0, now_mono=0.0)

    second = OverrideStore(StateStore(chemin))
    assert second.restore(now_epoch=99_999.0, now_mono=0.0) == 0
    assert second.active() == {}


def test_reprise_avant_heure_fiable_est_rebornee_et_a_confirmer(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    chemin = tmp_path / "runtime_state.json"
    premier = OverrideStore(StateStore(chemin))
    premier.create("heater", 4 * 3600, "", now_epoch=1_000.0, now_mono=0.0)

    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("unknown"))
    second = OverrideStore(StateStore(chemin))
    assert second.restore(now_epoch=0.0, now_mono=0.0) == 1
    record = second.active(0.0, 0.0)["heater"]
    # Un forçage chauffage repris indéfiniment, c'est une serre non chauffée.
    assert record.confirmed is False
    assert record.remaining_seconds(0.0, 0.0) == pytest.approx(4 * 3600)


def test_enregistrement_illisible_ignore_sans_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    chemin = tmp_path / "runtime_state.json"
    chemin.write_text(json.dumps({"overrides": {
        "heater": {"expires_epoch": "demain"},
        "inconnu": {"expires_epoch": 9e9},
        "daily_1": "pas un dictionnaire",
    }}), encoding="utf-8")

    magasin = OverrideStore(StateStore(chemin))
    assert magasin.restore(now_epoch=0.0, now_mono=0.0) == 0


def test_creation_refusee_si_ecriture_impossible(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    magasin = OverrideStore(StateStore(tmp_path / "runtime_state.json"))
    magasin.create("daily_1", 600, "avant", now_epoch=0.0, now_mono=0.0)

    def _echec(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr(overrides_module, "write_text_atomic", _echec, raising=False)
    monkeypatch.setattr("utils.state_store.write_text_atomic", _echec)

    with pytest.raises(OSError):
        magasin.create("daily_2", 600, "", now_epoch=0.0, now_mono=0.0)
    # L'état en mémoire ne garde pas un forçage que le disque ignore.
    assert "daily_2" not in magasin.active(0.0, 0.0)
    assert "daily_1" in magasin.active(0.0, 0.0)


def test_annulation_appliquee_meme_si_la_trace_echoue(tmp_path, monkeypatch):
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: FakeReliability("synchronized"))
    magasin = OverrideStore(StateStore(tmp_path / "runtime_state.json"))
    magasin.create("motor", 600, "", now_epoch=0.0, now_mono=0.0)

    def _echec(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr("utils.state_store.write_text_atomic", _echec)
    # On ne rétablit jamais une coupure que l'opérateur vient de lever.
    assert magasin.cancel("motor") is True
    assert magasin.is_forced_off("motor", 0.0, 0.0) is False


def test_expiration_purge_et_persiste(store):
    store.create("daily_1", 60, "", now_epoch=0.0, now_mono=0.0)
    assert store.payload(0.0, 0.0)["active_count"] == 1
    payload = store.payload(1_000.0, 1_000.0)
    assert payload["active_count"] == 0
    assert payload["items"] == []


def test_payload_publie_les_plafonds(store):
    payload = store.payload(0.0, 0.0)
    assert payload["limits_minutes"]["heater"] == 240
    assert payload["limits_minutes"]["daily_1"] == 1440
    assert payload["default_minutes"] == 60


def test_state_store_strict_remonte_l_erreur(tmp_path, monkeypatch):
    magasin = StateStore(tmp_path / "runtime_state.json")

    def _echec(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr("utils.state_store.write_text_atomic", _echec)
    # Défaut inchangé : les budgets d'hiver ne peuvent pas tuer la régulation.
    magasin.save("climate", {"renew_minutes_used": 1.0})
    with pytest.raises(OSError):
        magasin.save("overrides", {"heater": {}}, strict=True)
