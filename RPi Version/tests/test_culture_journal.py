"""Lot H : journal transversal filtrable et observations d'espace, sans matériel.

Aucun test ici n'accède au GPIO, à `param.json` ni à un capteur : le carnet reste
déclaratif et son indisponibilité ne dégrade jamais la régulation.
"""

import csv
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_journal import (JOURNAL_TYPES, journal_filters, journal_window,
                                   space_event_payload, validate_space_events)
from tests.test_cultures import NOW, create, cultures, event  # noqa: F401 (fixtures pytest)
from tests.test_culture_cycles import photo_bytes
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401 (fixture pytest)
from utils.culture_backup import restore_bundle
from utils.culture_store import CultureStore


async def observation(store, space="space_2", note="Espace nettoyé", **extra):
    command = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": space,
               "kind": "observation", "effective_at": "2026-09-01", "note": note, **extra}
    return await store.call("space_event_mutate", command)


async def mother(store, name):
    return await store.call("mutate", create(name, "mother", stage="maintien", origins=[]))


def test_regles_pures_du_journal_sans_base():
    assert space_event_payload("incident", {"note": "  Fuite  "}) == {"note": "Fuite"}
    for kind, raw in (("plante", {"note": "x"}), ("observation", {"note": ""}),
                      ("observation", {"note": "x" * 4001}), ("observation", {"autre": "x"})):
        with pytest.raises(CultureError):
            space_event_payload(kind, raw)
    assert journal_filters({"type": "solution:water", "start": ""}) == {"type": "solution:water"}
    with pytest.raises(CultureError):
        journal_filters({"inconnu": "1"})
    with pytest.raises(CultureError):
        journal_filters({"type": "event:inexistant"})
    # Borne haute calendaire exclusive : le dernier jour du filtre reste entier.
    start, end = journal_window({"start": "2026-09-01", "end": "2026-09-01"}, "Europe/Paris")
    assert start == "2026-08-31T22:00:00+00:00" and end == "2026-09-01T22:00:00+00:00"
    with pytest.raises(CultureError):
        journal_window({"start": "2026-09-02", "end": "2026-09-01"}, "Europe/Paris")
    with pytest.raises(CultureError):
        journal_window({"start": "01/09/2026"}, "Europe/Paris")
    assert JOURNAL_TYPES["space_event:observation"] == "Espace · Observation"


def test_validation_des_observations_rejette_revisions_et_contenus_incoherents():
    base = {"id": "a", "revision": 1, "space": "space_1", "kind": "observation",
            "precision": "date", "cancelled": 0, "clock_reliable": 1,
            "payload": json.dumps({"note": "ok"})}
    validate_space_events([base, {**base, "revision": 2, "cancelled": 1}])
    # Une observation entièrement annulée reste légitime : sa trace ne disparaît pas.
    validate_space_events([{**base, "cancelled": 1}])
    for broken in ({**base, "revision": 2}, {**base, "space": "serre"}, {**base, "kind": "note"},
                   {**base, "payload": "{"}, {**base, "payload": json.dumps({"note": ""})},
                   {**base, "cancelled": 2}, {**base, "precision": "vague"}):
        with pytest.raises(CultureError):
            validate_space_events([broken])


async def test_observation_d_un_espace_vide_reste_consultable(cultures):
    saved = await observation(cultures, "space_2", "Bac vide désinfecté")
    journal = await cultures.call("journal", {"target": "space_2"})
    assert journal["total"] == 1
    entry = journal["items"][0]
    assert entry["source"] == "space_event" and entry["entry_id"] == saved["id"]
    assert entry["target_label"] == "Espace 2" and entry["note"] == "Bac vide désinfecté"
    assert entry["type_label"] == "Espace · Observation" and entry["editable"]
    # Aucune fausse plante n'a été créée pour porter la note.
    assert (await cultures.call("overview"))["total"] == 0
    assert (await cultures.call("journal", {"target": "space_1"}))["total"] == 0


async def test_arrosage_partage_reste_une_operation_unique_dans_le_journal(cultures):
    first = await mother(cultures, "Mère A")
    second = await mother(cultures, "Mère B")
    third = await mother(cultures, "Mère C")
    targets = [first["subject_id"], second["subject_id"], third["subject_id"]]
    await cultures.call("solution_mutate", {"request_id": str(uuid.uuid4()), "operation": "entry",
        "kind": "water", "targets": targets, "effective_at": "2026-09-02", "volume_l": 5})
    watering = await cultures.call("journal", {"type": "solution:water"})
    assert watering["total"] == 1 and len(watering["items"]) == 1
    assert len(watering["items"][0]["targets"]) == 3
    # Chaque mère retrouve l'arrosage, sans que la ligne soit dupliquée pour autant.
    for subject_id in targets:
        page = await cultures.call("journal", {"target": subject_id, "type": "solution:water"})
        assert page["total"] == 1


async def test_journal_retrouve_les_evenements_d_un_lot_archive_sur_une_periode(cultures):
    lot = await cultures.call("mutate", create("Lot archivé", stage="vegetatif", space="space_2"))
    lot = await event(cultures, lot, "harvest", "2026-08-20")
    lot = await event(cultures, lot, "finish", "2026-08-25", {"release": True, "weight_g": 12.0})
    subject_id = lot["subject_id"]
    assert (await cultures.call("overview", True))["total"] == 1
    period = await cultures.call("journal", {"target": subject_id, "start": "2026-08-20", "end": "2026-08-25"})
    assert [item["kind"] for item in period["items"]] == ["finish", "harvest"]
    assert (await cultures.call("journal", {"target": subject_id, "start": "2026-08-26"}))["total"] == 0
    assert (await cultures.call("journal", {"target": subject_id, "end": "2026-08-19"}))["total"] == 3


async def test_pagination_stable_et_lien_focus_a_travers_les_pages(cultures):
    ordered = []
    for day in range(1, 46):
        saved = await observation(cultures, "space_1", f"Passage {day:02d}",
                                  effective_at=f"2026-07-{day:02d}" if day <= 31 else f"2026-08-{day - 31:02d}")
        ordered.append(saved["id"])
    first = await cultures.call("journal", {"target": "space_1"})
    second = await cultures.call("journal", {"target": "space_1"}, 40)
    assert first["total"] == 45 and len(first["items"]) == 40 and len(second["items"]) == 5
    # Aucune opération n'est perdue ni comptée deux fois entre deux pages.
    identifiers = [item["entry_id"] for item in first["items"] + second["items"]]
    assert len(set(identifiers)) == 45 and set(identifiers) == set(ordered)
    # Le repère ramène directement sur la page qui contient l'opération visée.
    focused = await cultures.call("journal", {"target": "space_1"}, 0, ordered[0])
    assert focused["offset"] == 40 and any(item["entry_id"] == ordered[0] for item in focused["items"])
    assert (await cultures.call("journal", {"target": "space_1"}, 0, str(uuid.uuid4())))["offset"] == 0


async def test_correction_et_annulation_d_observation_sont_tracables(cultures):
    saved = await observation(cultures, "space_1", "Ventilateur bruyant")
    correction = {"request_id": str(uuid.uuid4()), "operation": "correct", "id": saved["id"],
                  "version": 1, "note": "Ventilateur remplacé", "effective_at": "2026-09-01",
                  "reason": "Précision apportée"}
    corrected = await cultures.call("space_event_mutate", correction)
    assert corrected["version"] == 2
    # Idempotence : rejouer la même clé ne crée pas une seconde révision.
    assert await cultures.call("space_event_mutate", correction) == corrected
    with pytest.raises(CultureConflict):
        await cultures.call("space_event_mutate", {**correction, "request_id": str(uuid.uuid4())})
    entry = (await cultures.call("journal", {"target": "space_1"}))["items"][0]
    assert entry["note"] == "Ventilateur remplacé" and entry["revision"] == 2
    assert [old["note"] for old in entry["revisions"]] == ["Ventilateur bruyant"]
    assert entry["reason"] == "Précision apportée"
    cancelled = await cultures.call("space_event_mutate", {
        "request_id": str(uuid.uuid4()), "operation": "correct", "id": saved["id"], "version": 2,
        "note": "Ventilateur remplacé", "effective_at": "2026-09-01",
        "reason": "Saisie erronée", "cancelled": True})
    assert cancelled["version"] == 3
    entry = (await cultures.call("journal", {"target": "space_1"}))["items"][0]
    assert entry["cancelled"] and not entry["editable"] and len(entry["revisions"]) == 2
    # L'espace et le genre ne se corrigent pas : la trace ne change pas de cible.
    with pytest.raises(CultureError, match="ne se corrigent pas"):
        await cultures.call("space_event_mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
            "id": saved["id"], "version": 3, "space": "space_2", "note": "x", "reason": "y",
            "effective_at": "2026-09-01"})
    await cultures.call("cycle_validate")


async def test_commandes_d_observation_refusees_sans_effet(cultures):
    for command in (
        {"request_id": "k1", "operation": "inconnue", "space": "space_1", "note": "x", "effective_at": "2026-09-01"},
        {"request_id": "k2", "operation": "space_event", "space": "serre", "note": "x", "effective_at": "2026-09-01"},
        {"request_id": "k3", "operation": "space_event", "space": "space_1", "note": "", "effective_at": "2026-09-01"},
        {"request_id": "k4", "operation": "space_event", "space": "space_1", "note": "x", "effective_at": "2099-01-01"},
        {"request_id": "k5", "operation": "space_event", "space": "space_1", "note": "x",
         "effective_at": "2026-09-01", "id": "imposé"},
        {"request_id": "k6", "operation": "correct", "id": "absent", "version": 1, "note": "x",
         "effective_at": "2026-09-01", "reason": "y"},
        {"request_id": "k7", "operation": "space_event", "space": "space_1", "note": "x",
         "effective_at": "2026-09-01", "champ": "inconnu"},
    ):
        with pytest.raises(CultureError):
            await cultures.call("space_event_mutate", command)
    assert (await cultures.call("journal", {}))["total"] == 0
    with pytest.raises(CultureError, match="Cible de filtre"):
        await cultures.call("journal", {"target": "inconnue"})
    with pytest.raises(CultureError, match="Filtre de journal"):
        await cultures.call("journal", {"inconnu": "1"})


async def test_export_csv_du_filtre_neutralise_les_textes(cultures):
    await observation(cultures, "space_1", "=cmd|' /c calc'!A1")
    await observation(cultures, "space_2", "Note ordinaire")
    export = await cultures.call("journal_csv", {"target": "space_1"})
    lines = export.strip().splitlines()
    assert lines[0].startswith("source,operation_id,revision,type")
    assert len(lines) == 2 and "'=cmd" in lines[1] and "Note ordinaire" not in export
    assert '"[{""kind"": ""space"", ""id"": ""space_1""' in lines[1]
    # Une opération multi-cibles reste une ligne unique, cibles sérialisées en JSON.
    first, second = await mother(cultures, "Mère X"), await mother(cultures, "Mère Y")
    await cultures.call("solution_mutate", {"request_id": str(uuid.uuid4()), "operation": "entry",
        "kind": "water", "targets": [first["subject_id"], second["subject_id"]],
        "effective_at": "2026-09-02", "volume_l": 4})
    rows = list(csv.DictReader(io.StringIO(await cultures.call("journal_csv", {"type": "solution:water"}))))
    assert len(rows) == 1 and len(json.loads(rows[0]["cibles"])) == 2


async def test_photos_d_observation_partagent_limites_sauvegarde_et_restauration(cultures, tmp_path):
    saved = await observation(cultures, "space_2", "Traces d’humidité")
    command = {"request_id": str(uuid.uuid4()), "space_event_id": saved["id"],
               "space_event_revision": 1, "caption": "Coin nord"}
    raw = photo_bytes()
    photo = await cultures.call("media_add", command, raw)
    assert photo["space"] == "space_2"
    assert await cultures.call("media_add", command, raw) == photo
    with pytest.raises(CultureConflict):
        await cultures.call("media_add", {**command, "caption": "Autre"}, raw)
    for _ in range(3):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    with pytest.raises(CultureError, match="Quatre"):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    # Exclusivité du propriétaire : jamais une photo à la fois de culture et d'espace.
    with pytest.raises(CultureError, match="jamais aux deux"):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4()),
                                          "event_id": "x", "subject_id": "y"}, raw)
    entry = (await cultures.call("journal", {"target": "space_2"}))["items"][0]
    assert len(entry["photos"]) == 4 and entry["photos"][0]["owner_kind"] == "space_event"
    # La galerie des cycles ne mélange pas les propriétaires : son lien de fiche resterait vide.
    assert (await cultures.call("media_list")) == []
    assert (await cultures.call("media_storage"))["count"] == 4
    bundle = Path(await cultures.call("bundle"))
    try:
        with zipfile.ZipFile(bundle) as archive:
            assert len(json.loads(archive.read("manifest.json"))["files"]) == 5
        destination = tmp_path / "restauration"
        restore_bundle(bundle, destination)
        assert len(list((destination / "culture_media").glob("*.jpg"))) == 4
        other = CultureStore(destination / "cultures.sqlite3", now=lambda: NOW)
        try:
            restored = await other.call("journal", {"target": "space_2"})
            assert restored["total"] == 1 and len(restored["items"][0]["photos"]) == 4
            assert await other.call("media_get", photo["id"]) == await cultures.call("media_get", photo["id"])
        finally:
            await other.close()
    finally:
        bundle.unlink()


async def test_photo_refusee_sur_observation_annulee(cultures):
    saved = await observation(cultures, "space_1", "À supprimer")
    await cultures.call("space_event_mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "id": saved["id"], "version": 1, "note": "À supprimer", "effective_at": "2026-09-01",
        "reason": "Doublon", "cancelled": True})
    with pytest.raises(CultureError, match="annulée"):
        await cultures.call("media_add", {"request_id": str(uuid.uuid4()), "space_event_id": saved["id"],
                                          "space_event_revision": 2, "caption": ""}, photo_bytes())


async def test_journal_http_expose_page_donnees_mutation_et_export(web_context):
    client, server, config, *_ = web_context
    original = config.current.to_json()
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": "space_2",
            "kind": "incident", "effective_at": "2026-09-01", "note": "<script>alert(1)</script>"}
    assert (await client.post("/api/v1/cultures/journal", json=body)).status == 403
    response = await client.post("/api/v1/cultures/journal", json=body, headers=headers)
    assert response.status == 200, await response.text()
    saved = await response.json()
    assert (await client.post("/api/v1/cultures/journal", json={**body, "request_id": str(uuid.uuid4()),
                                                                "note": ""}, headers=headers)).status == 400
    page = await client.get("/cultures/journal?target=space_2&type=space_event:incident")
    assert page.status == 200
    html = await page.text()
    assert "Journal du carnet" in html and "<script>alert" not in html and "&lt;script&gt;" in html
    assert 'value="space_2" selected' in html
    data = await (await client.get("/api/v1/cultures/journal?target=space_2")).json()
    assert data["total"] == 1 and data["items"][0]["entry_id"] == saved["id"]
    # Un filtre refusé conserve les champs saisis au lieu de vider le formulaire.
    refused = await client.get("/cultures/journal?start=2026-09-05&end=2026-09-01")
    assert refused.status == 400 and 'value="2026-09-05"' in await refused.text()
    assert (await client.get("/api/v1/cultures/journal?start=2026-09-05&end=2026-09-01")).status == 400
    assert (await client.get("/api/v1/cultures/journal?offset=-1")).status == 400
    export = await client.get("/api/v1/cultures/journal/export?target=space_2")
    assert export.status == 200 and "attachment" in export.headers["Content-Disposition"]
    assert "space_event:incident" in await export.text()
    assert (await client.get("/api/v1/cultures/journal/export?format=json")).status == 400
    # Le carnet reste déclaratif : aucune écriture de configuration, aucune commande.
    assert config.current.to_json() == original
    assert (await client.get("/health/ready")).status == 200
