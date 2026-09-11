"""Lot F : repères d'éclairage informatifs, écart aux horaires et état opérationnel.

Un repère ne commande rien. Ces tests vérifient les règles pures, le magasin versionné,
l'absence totale d'effet sur la configuration et les GPIO, et la restauration sur copie.
"""

import importlib
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_light import (LIGHT_PRESETS, compare_light, light_minutes, resolve_light,
                                 schedule_on_minutes, validate_light_windows)
from tests.fakes.rpi_gpio import install
from tests.test_cultures import NOW, create
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401 — fixture aiohttp
from utils.culture_backup import restore_copy
from utils.culture_store import CultureStore


@pytest.fixture
async def cultures(tmp_path):
    store = CultureStore(tmp_path / "cultures.sqlite3", now=lambda: NOW)
    yield store
    await store.close()


def target(**overrides):
    command = {"request_id": str(uuid.uuid4()), "operation": "light", "scope": "global",
               "label": "Végétatif 18/6", "on_minutes": 1080, "off_minutes": 360,
               "start_at": "2026-08-01"}
    command.update(overrides)
    return command


def window(identifier, revision=1, **overrides):
    row = {"id": identifier, "revision": revision, "scope": "global", "subject_id": None,
           "space": None, "stage": None, "label": "Repère", "on_minutes": 1080,
           "off_minutes": 360, "start_at": "2026-08-01", "start_precision": "date",
           "start_sort_at": "2026-08-01T00:00:00+00:00", "end_at": None, "end_precision": None,
           "end_sort_at": None, "note": "", "reason": "", "cancelled": 0,
           "recorded_at": "2026-08-01T00:00:00+00:00", "clock_reliable": 1}
    row.update(overrides)
    return row


def schedule(start_hour, start_minute, stop_hour, stop_minute):
    return {"start_hour": start_hour, "start_minute": start_minute,
            "stop_hour": stop_hour, "stop_minute": stop_minute}


def test_reperes_proposes_et_cycle_de_24_heures():
    assert LIGHT_PRESETS == {"vegetatif": (1080, 360), "floraison": (720, 720)}
    assert light_minutes(*LIGHT_PRESETS["vegetatif"]) == (1080, 360)
    assert light_minutes(*LIGHT_PRESETS["floraison"]) == (720, 720)
    for invalid in ((1080, 361), (1441, -1), (True, 1439), (1080.0, 360), ("1080", 360)):
        with pytest.raises(CultureError):
            light_minutes(*invalid)


def test_resolution_sujet_puis_espace_puis_global_et_stade():
    rows = [window("g"), window("e", scope="space", space="space_2", label="Espace 2"),
            window("s", scope="subject", subject_id="lot-1", label="Lot"),
            window("f", scope="space", space="space_2", stage="floraison",
                   on_minutes=720, off_minutes=720, label="Floraison espace 2")]
    at = "2026-09-01T00:00:00+00:00"
    assert resolve_light(at, "vegetatif", "lot-1", "space_2", rows)["id"] == "s"
    assert resolve_light(at, "vegetatif", "autre", "space_2", rows)["id"] == "e"
    # Un repère de stade est plus précis qu'un repère sans stade, à portée égale.
    assert resolve_light(at, "floraison", "autre", "space_2", rows)["id"] == "f"
    assert resolve_light(at, "vegetatif", "autre", "space_1", rows)["id"] == "g"
    # Aucun repère applicable : jamais de repère standard implicite.
    assert resolve_light("2026-07-01T00:00:00+00:00", "vegetatif", "lot-1", "space_1", rows) is None
    closed = [window("g", end_at="2026-08-15", end_sort_at="2026-08-15T00:00:00+00:00")]
    assert resolve_light(at, "vegetatif", "lot-1", "space_1", closed) is None
    assert resolve_light(at, "vegetatif", "lot-1", "space_1", [window("g", cancelled=1)]) is None


def test_ecart_informatif_avec_horaire_traversant_minuit():
    reference = {"on_minutes": 1080, "off_minutes": 360}
    crossing = compare_light(reference, schedule(19, 0, 7, 0))
    assert crossing["configured_on_minutes"] == 720 and crossing["crosses_midnight"]
    assert crossing["difference_minutes"] == -360 and not crossing["matches"]
    assert "d’éclairage configuré" in crossing["gap_label"]
    exact = compare_light(reference, schedule(6, 0, 0, 0))
    assert exact["configured_on_minutes"] == 1080 and exact["matches"]
    # Bornes égales : plage vide par convention, jamais 24 h d'éclairage.
    empty = compare_light(reference, schedule(8, 0, 8, 0))
    assert empty["configured_on_minutes"] == 0 and empty["empty"]
    assert schedule_on_minutes(schedule(23, 30, 0, 30)) == 60
    # Sans repère résolu, aucun écart n'est calculé.
    assert compare_light(None, schedule(19, 0, 7, 0)) is None


def test_validation_revisions_et_fenetres_non_chevauchantes():
    validate_light_windows([window("a"), window("a", revision=2, cancelled=1),
                            window("b", scope="space", space="space_1")])
    with pytest.raises(CultureError):
        validate_light_windows([window("a"), window("a", revision=3)])
    with pytest.raises(CultureError):
        validate_light_windows([window("a"), window("b")])
    # Deux stades distincts pour la même cible ne se chevauchent pas au sens du repère.
    validate_light_windows([window("a", stage="vegetatif"), window("b", stage="floraison")])
    validate_light_windows([window("a", end_at="2026-08-15", end_sort_at="2026-08-15T00:00:00+00:00"),
                            window("b", start_sort_at="2026-08-15T00:00:00+00:00", start_at="2026-08-15")])
    with pytest.raises(CultureError):
        validate_light_windows([window("a", on_minutes=1000)])
    with pytest.raises(CultureError):
        validate_light_windows([window("a", end_at="2026-07-01", end_sort_at="2026-07-01T00:00:00+00:00")])


async def test_saisie_correction_cloture_et_annulation_versionnees(cultures):
    lot = await cultures.call("mutate", create())
    saved = await cultures.call("light_mutate", target(scope="subject", subject_id=lot["subject_id"]))
    assert saved["version"] == 1
    with pytest.raises(CultureConflict):
        await cultures.call("light_mutate", target(scope="subject", subject_id=lot["subject_id"],
                                                   id=saved["id"], version=7, reason="Correction"))
    corrected = await cultures.call("light_mutate", target(
        scope="subject", subject_id=lot["subject_id"], id=saved["id"], version=1,
        on_minutes=720, off_minutes=720, label="Floraison 12/12", reason="Passage en floraison"))
    assert corrected["version"] == 2
    closed = await cultures.call("light_mutate", {"request_id": str(uuid.uuid4()), "operation": "light_close",
        "id": saved["id"], "version": 2, "end_at": "2026-09-01", "reason": "Fin du repère"})
    assert closed["version"] == 3
    cancelled = await cultures.call("light_mutate", {"request_id": str(uuid.uuid4()), "operation": "light_cancel",
        "id": saved["id"], "version": 3, "reason": "Saisie erronée"})
    assert cancelled["version"] == 4
    with pytest.raises(CultureError):
        await cultures.call("light_mutate", {"request_id": str(uuid.uuid4()), "operation": "light_cancel",
            "id": saved["id"], "version": 4, "reason": "Deux fois"})
    targets = await cultures.call("light_targets", {})
    assert len(targets) == 1 and targets[0]["cancelled"] == 1
    assert [old["revision"] for old in targets[0]["revisions"]] == [1, 2, 3]
    # Un repère annulé ne résout plus rien.
    data = await cultures.call("light_data", {})
    assert [occupant["reference"] for occupant in data["occupants"]] == [None]


async def test_idempotence_et_refus_de_chevauchement(cultures):
    command = target()
    first = await cultures.call("light_mutate", command)
    assert await cultures.call("light_mutate", command) == first
    with pytest.raises(CultureError):
        await cultures.call("light_mutate", target(label="Second repère global"))
    # Le refus ne laisse aucune trace : le repère refusé n'existe pas.
    assert len(await cultures.call("light_targets", {})) == 1
    space = await cultures.call("light_mutate", target(scope="space", space="space_2", label="Espace 2"))
    assert space["version"] == 1
    with pytest.raises(CultureError):
        await cultures.call("light_mutate", target(scope="space", space="inconnu"))
    with pytest.raises(CultureError):
        await cultures.call("light_mutate", target(scope="subject", subject_id="inexistant"))
    with pytest.raises(CultureError):
        await cultures.call("light_mutate", target(stage="inconnu", label="Stade inconnu"))


async def test_repere_applicable_a_une_culture_en_place(cultures):
    lot = await cultures.call("mutate", create())
    await cultures.call("light_mutate", target(label="Global 18/6"))
    await cultures.call("light_mutate", target(scope="space", space="space_1",
                                               label="Espace 1 en 12/12", on_minutes=720, off_minutes=720))
    data = await cultures.call("light_data", {})
    occupant = data["occupants"][0]
    assert occupant["id"] == lot["subject_id"] and occupant["space"] == "space_1"
    assert occupant["reference"]["label"] == "Espace 1 en 12/12"
    assert occupant["reference"]["window_label"] == "12 h / 12 h"
    assert data["presets"]["vegetatif"]["label"] == "18 h / 6 h"
    filtered = await cultures.call("light_targets", {"scope": "space"})
    assert [row["label"] for row in filtered] == ["Espace 1 en 12/12"]
    with pytest.raises(CultureError):
        await cultures.call("light_targets", {"scope": "inconnue"})


async def test_export_et_restauration_conservent_les_reperes(cultures, tmp_path):
    await cultures.call("mutate", create())
    saved = await cultures.call("light_mutate", target())
    await cultures.call("light_mutate", target(id=saved["id"], version=1, on_minutes=720,
                                               off_minutes=720, reason="Correction"))
    exported = await cultures.call("export")
    assert len(exported["tables"]["culture_light_targets"]) == 2
    backup = tmp_path / "download.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    restored = tmp_path / "restored.sqlite3"
    restore_copy(backup, restored)
    copy_store = CultureStore(restored, now=lambda: NOW)
    try:
        targets = await copy_store.call("light_targets", {})
        assert targets[0]["on_minutes"] == 720 and [old["revision"] for old in targets[0]["revisions"]] == [1]
    finally:
        await copy_store.close()


async def test_restauration_refuse_un_chevauchement_de_reperes(cultures, tmp_path):
    await cultures.call("mutate", create())
    await cultures.call("light_mutate", target())

    def corrupt():
        with cultures._db:
            cultures._db.execute(
                "INSERT INTO culture_light_targets (id,revision,scope,label,on_minutes,off_minutes,"
                "start_at,start_precision,start_sort_at,recorded_at) VALUES"
                " ('double',1,'global','Doublon',1080,360,'2026-08-02','date','2026-08-02T00:00:00+00:00','2026-08-02T00:00:00+00:00')")
        return True
    cultures._corrupt = corrupt
    await cultures.call("corrupt")
    backup = tmp_path / "double.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    # Le validateur du lot est rejoué à la restauration : la copie est refusée.
    with pytest.raises(CultureError):
        restore_copy(backup, tmp_path / "refuse.sqlite3")


async def test_page_rapproche_repere_horaires_et_etat_sans_effet(web_context, monkeypatch):
    client, server, config, _sensors, _supervisor = web_context
    from network.web import culture_light as light_module
    gpio = install(monkeypatch)
    component = importlib.import_module("model.Component").Component(23)
    assert component.get_state() == 0
    pins, events = gpio.snapshot(), len(gpio.events)
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_args: writes.append("save"))
    monkeypatch.setattr(config, "commit", lambda *_args: writes.append("commit"))
    # État opérationnel déterministe : la publication métier reste la seule source.
    monkeypatch.setattr(light_module, "operational_snapshot", lambda: {
        "daily_1": {"requested": "on", "applied": "on", "actual": "off", "tracking": "mismatch",
                    "stale": False, "reason": "plage active", "mode": "auto"}})
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    lot = await (await client.post("/api/v1/cultures", json=create(), headers=headers)).json()
    body = {**target(scope="subject", subject_id=lot["subject_id"], label="Repère du lot")}
    response = await client.post("/api/v1/cultures/light", json=body, headers=headers)
    assert response.status == 200, await response.text()
    assert (await client.post("/api/v1/cultures/light", json={**body, "request_id": str(uuid.uuid4()),
                                                              "id": (await response.json())["id"],
                                                              "version": 9, "reason": "x"}, headers=headers)).status == 409
    page = await (await client.get("/cultures/light")).text()
    assert "Repère du lot" in page and "18 h / 6 h" in page
    # DailyTimer1 des tests : 19:00 → 07:00, soit 12 h d'éclairage traversant minuit.
    assert "19:00 → 07:00" in page and "plage traversant minuit" in page
    assert "−6 h d’éclairage configuré" in page
    assert "écart entre la consigne et l’état relu" in page
    assert "ne prouve pas le fonctionnement physique" in page
    assert "/conf#daily-timer-1" in page
    # L'équipement de l'espace 2 est désactivé dans cette configuration de test.
    assert "Minuterie quotidienne 2 désactivée" in page
    assert "État opérationnel indisponible" in page
    data = await (await client.get("/api/v1/cultures/light")).json()
    assert data["occupants"][0]["comparison"]["difference_minutes"] == -360
    assert data["operational"]["ventilation"]["available"] is False
    assert config.current.to_json() == original and writes == []
    assert gpio.snapshot() == pins and len(gpio.events) == events


async def test_page_eclairage_selecteur_puis_declare_puis_applique(web_context):  # noqa: F811
    """R2.7 : sélecteur espace/culture et date, puis les deux blocs aux libellés imposés."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    lot = await (await client.post("/api/v1/cultures", json=create(), headers=headers)).json()
    saved = await client.post("/api/v1/cultures/light",
                              json=target(scope="subject", subject_id=lot["subject_id"],
                                          label="Repère consulté", start_at="2026-06-01"),
                              headers=headers)
    assert saved.status == 200, await saved.text()

    body = await (await client.get("/cultures/light")).text()
    # Les libellés imposés sont vérifiés sur les titres, pas sur les liens de la page.
    assert body.index('id="selection"') < body.index("<h2>Déclaré dans le carnet</h2>")
    assert body.index("<h2>Déclaré dans le carnet</h2>") < body.index("<h2>Appliqué maintenant</h2>")
    assert "Comment cette valeur est choisie" in body
    # Le repère résolu est déclaré, avec l'indication de la portée qui l'a emporté.
    assert f'data-light-declared="{lot["subject_id"]}"' in body
    assert "Repère consulté" in body and "Une culture" in body
    # Horaires et état relu restent dans « Appliqué maintenant », après le déclaré.
    assert body.index("<h2>Appliqué maintenant</h2>") < body.index('data-light-applied="space_1"')
    # R2.5 : les deux formulaires GET de la page sont des filtres serveur **déclarés**.
    assert body.count('<form method="get"') == 2
    assert body.count('<form method="get"') == body.count("data-offline-filter")
    # Un repère sans fin déclarée ne propose pas « None » comme date de fin à corriger.
    assert 'value="None"' not in body

    # Aucune rétroactivité : avant son début, le repère ne s'applique pas.
    avant = await (await client.get("/cultures/light?at=2026-05-01")).text()
    assert "Aucun repère enregistré pour cette culture à cette date" in avant
    # Un espace consulté : seul cet espace est rapproché.
    espace = await (await client.get("/cultures/light?focus=space_2")).text()
    assert 'data-light-applied="space_2"' in espace
    assert 'data-light-applied="space_1"' not in espace
    # Une cible ou une date impossibles sont refusées, jamais ignorées.
    assert (await client.get("/cultures/light?focus=inconnu")).status == 400
    assert (await client.get("/cultures/light?at=2027-01-01")).status == 400
