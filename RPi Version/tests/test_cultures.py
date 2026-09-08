"""Parcours complets du carnet sans matériel, avec disque et horloge isolés."""

import asyncio
import copy
import json
import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from model.culture import CultureConflict, CultureError, age, stamp
from utils.culture_backup import restore_copy
from utils.culture_store import CultureStore, CultureUnavailable

NOW = datetime(2026, 9, 7, 15, tzinfo=timezone.utc)


@pytest.fixture
async def cultures(tmp_path):
    store = CultureStore(tmp_path / "cultures.sqlite3", now=lambda: NOW)
    yield store
    await store.close()


def create(name="Semis", kind="lot", **overrides):
    return {"request_id": str(uuid.uuid4()), "operation": "create", "kind": kind,
            "name": name, "origin_at": "2026-08-01", "space_at": "2026-08-01",
            "stage_at": "2026-08-01", "stage": "maintien" if kind == "mother" else "germination",
            "origins": [] if kind == "mother" else [{"label": "Semences A", "count": 8}], **overrides}


async def event(store, result, kind, day, payload=None, **extra):
    command = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": result["subject_id"],
               "version": result["version"], "kind": kind, "effective_at": day,
               "payload": payload or {}, **extra}
    return await store.call("mutate", command)


async def backfill(store, result, steps, **extra):
    command = {"request_id": str(uuid.uuid4()), "operation": "backfill", "subject_id": result["subject_id"],
               "version": result["version"], "steps": steps, **extra}
    return await store.call("mutate", command)


async def test_reprise_en_floraison_completee_retrospectivement(cultures):
    mother = await cultures.call("mutate", create("Mère", "mother", origin_at="2026-05-01",
        space_at="2026-05-01", stage_at="2026-05-01"))
    lot = await cultures.call("mutate", create("Reprise", origin_type="cutting", stage="floraison",
        space="space_2", origin_at="2026-06-01", space_at="2026-08-01", stage_at="2026-08-01",
        origins=[{"mother_id": mother["subject_id"], "count": 6}]))
    detail = await cultures.call("detail", lot["subject_id"])
    assert detail["backfill"] == {"stages": ["enracinement", "vegetatif"],
                                  "spaces": ["space_1", "space_2"], "before": "2026-08-01"}
    assert detail["subject"]["age"]["days"] == 37
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "cuttings_1", "effective_at": "2026-06-01", "volume_l": 20})
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-06-01", "volume_l": 20})
    links = (await cultures.call("solution_data"))["links"]
    assert [link["subject_id"] for link in links] == [lot["subject_id"]]
    lot = await backfill(cultures, lot, [
        {"kind": "stage", "effective_at": "2026-06-05", "payload": {"stage": "enracinement"}},
        {"kind": "move", "effective_at": "2026-06-10", "payload": {"space": "space_1"}},
        {"kind": "stage", "effective_at": "2026-06-15", "payload": {"stage": "vegetatif"}}])
    subject = (await cultures.call("detail", lot["subject_id"]))["subject"]
    # Le stade courant et son compteur sont inchangés : seules les périodes passées apparaissent.
    assert subject["stage"] == "floraison" and subject["stage_at"] == "2026-08-01"
    assert subject["age"]["days"] == 37
    assert [(p["stage"], p["duration"]["days"]) for p in subject["periods"]] == [
        ("enracinement", 10), ("vegetatif", 47), ("floraison", 37)]
    assert [(o["space"], o["end"] is None) for o in subject["occupations"]] == [
        ("space_1", False), ("space_2", True)]
    # L'attribution des solutions suit les dates d'occupation corrigées.
    links = sorted((await cultures.call("solution_data"))["links"], key=lambda link: link["start_at"])
    # Clés UTC : minuit local du 10 juin et du 1er août, heure d'été.
    assert len(links) == 2 and links[0]["start_at"] == "2026-06-09T22:00:00+00:00"
    assert links[0]["end_at"] == "2026-07-31T22:00:00+00:00"
    assert links[1]["start_at"] == "2026-07-31T22:00:00+00:00" and links[1]["end_at"] is None
    assert (await cultures.call("detail", lot["subject_id"]))["backfill"]["stages"] == []


async def test_backfill_refuse_atomiquement_chronologie_et_occupation(cultures):
    other = await cultures.call("mutate", create("Occupant", space="space_2", space_at="2026-07-01",
        origin_at="2026-07-01", stage_at="2026-07-01"))
    lot = await cultures.call("mutate", create("Reprise", stage="floraison", origin_at="2026-06-01",
        space="space_1", space_at="2026-06-01", stage_at="2026-08-01"))
    events = len((await cultures.call("detail", lot["subject_id"]))["events"])
    key = str(uuid.uuid4())
    with pytest.raises(CultureError, match="précéder"):
        await backfill(cultures, lot, [{"kind": "stage", "effective_at": "2026-08-01",
                                        "payload": {"stage": "vegetatif"}}], request_id=key)
    with pytest.raises(CultureError, match="antérieure manquante"):
        await backfill(cultures, lot, [{"kind": "stage", "effective_at": "2026-07-01",
                                        "payload": {"stage": "sechage"}}])
    with pytest.raises(CultureError, match="occupé"):
        await backfill(cultures, lot, [
            {"kind": "stage", "effective_at": "2026-06-20", "payload": {"stage": "vegetatif"}},
            {"kind": "move", "effective_at": "2026-07-02", "payload": {"space": "space_2"}}])
    detail = await cultures.call("detail", lot["subject_id"])
    assert len(detail["events"]) == events and detail["subject"]["stage"] == "floraison"
    assert (await cultures.call("detail", other["subject_id"]))["subject"]["space"] == "space_2"
    # Aucune trace de l'échec : la clé reste libre pour une autre saisie.
    saved = await backfill(cultures, lot, [{"kind": "stage", "effective_at": "2026-06-20",
                                            "payload": {"stage": "vegetatif"}}], request_id=key)
    assert saved["saved"]


async def test_backfill_precisions_dst_revisions_et_onglet_perime(cultures, tmp_path):
    cultures.reliable = lambda: False
    spring = await cultures.call("mutate", {**create("Printemps", stage="floraison", origin_at="2026-03-20",
        space_at="2026-03-20", stage_at="2026-04-05"), "confirm_date": True})
    with pytest.raises(CultureError, match="Horloge"):
        await backfill(cultures, spring, [{"kind": "stage", "effective_at": "2026-03-28",
                                           "payload": {"stage": "germination"}}])
    spring = await backfill(cultures, spring, [
        {"kind": "stage", "effective_at": "2026-03-28T23:30:00+01:00", "precision": "instant",
         "payload": {"stage": "germination"}},
        {"kind": "stage", "effective_at": "2026-03-29T03:30:00+02:00", "precision": "instant",
         "payload": {"stage": "vegetatif"}}], confirm_date=True)
    subject = (await cultures.call("detail", spring["subject_id"]))["subject"]
    # Une heure « sautée » au passage à l'heure d'été ne crée ni ne perd un jour calendaire.
    assert [p["duration"]["days"] for p in subject["periods"]] == [1, 7, 155]
    assert [p["precision"] for p in subject["periods"]] == ["instant", "instant", "date"]
    events = (await cultures.call("detail", spring["subject_id"]))["events"]
    germination = next(e for e in events if e["payload"].get("stage") == "germination")
    corrected = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "subject_id": spring["subject_id"], "version": spring["version"], "event_id": germination["id"],
        "effective_at": "2026-03-27", "precision": "approximative", "confirm_date": True,
        "payload": {"stage": "germination"}, "reason": "Date retrouvée"})
    row = next(e for e in (await cultures.call("detail", spring["subject_id"]))["events"] if e["id"] == germination["id"])
    assert row["precision"] == "approximative" and row["revisions"][0]["precision"] == "instant"
    with pytest.raises(CultureConflict):
        await backfill(cultures, spring, [{"kind": "move", "effective_at": "2026-03-25",
                                           "payload": {"space": "space_2"}}], confirm_date=True)
    assert (await cultures.call("detail", spring["subject_id"]))["subject"]["periods"][0]["duration"]["days"] == 2
    autumn_store = CultureStore(tmp_path / "autumn.sqlite3", now=lambda: datetime(2026, 11, 10, tzinfo=timezone.utc))
    try:
        autumn = await autumn_store.call("mutate", create("Automne", stage="floraison",
            origin_at="2026-10-20", space_at="2026-10-20", stage_at="2026-11-01"))
        autumn = await backfill(autumn_store, autumn, [
            {"kind": "stage", "effective_at": "2026-10-25T02:30:00+02:00", "precision": "instant",
             "payload": {"stage": "germination"}},
            {"kind": "stage", "effective_at": "2026-10-25T02:30:00+01:00", "precision": "instant",
             "payload": {"stage": "vegetatif"}}])
        subject = (await autumn_store.call("detail", autumn["subject_id"]))["subject"]
        # Heure locale ambiguë : deux instants distincts, une seule date locale, donc zéro jour.
        assert [p["duration"]["days"] for p in subject["periods"]] == [0, 7, 9]
        assert corrected["saved"]
    finally:
        await autumn_store.close()


async def test_cycle_multi_meres_recolte_et_archive(cultures):
    a = await cultures.call("mutate", create("Mère A", "mother"))
    b = await cultures.call("mutate", create("Mère B", "mother"))
    lot = await cultures.call("mutate", create("Boutures", origin_type="cutting", stage="enracinement",
        origin_at="2026-08-02", space_at="2026-08-02", stage_at="2026-08-02",
        origins=[{"mother_id": a["subject_id"], "count": 3}, {"mother_id": b["subject_id"], "count": 5}]))
    detail = await cultures.call("detail", lot["subject_id"])
    origin_id = detail["subject"]["origins"][0]["id"]
    lot = await event(cultures, lot, "loss", "2026-08-03", {"count": 1, "origin_id": origin_id})
    lot = await event(cultures, lot, "stage", "2026-08-05", {"stage": "vegetatif"})
    lot = await event(cultures, lot, "move", "2026-08-10", {"space": "space_2"})
    detail = await cultures.call("detail", lot["subject_id"])
    assert detail["subject"]["stage_at"] == "2026-08-05"
    lot = await event(cultures, lot, "stage", "2026-08-15", {"stage": "floraison"})
    detail = await cultures.call("detail", lot["subject_id"])
    assert detail["subject"]["age"] == {"days": 23, "weeks": 3, "remaining_days": 2, "week": 4}
    assert detail["subject"]["count"] == 7
    assert detail["subject"]["initial_count"] == 8
    lot = await event(cultures, lot, "harvest", "2026-09-01")
    lot = await event(cultures, lot, "finish", "2026-09-06", {"weight_g": 102.5, "note": "Bilan"})
    detail = await cultures.call("detail", lot["subject_id"])
    assert detail["subject"]["archived"] and detail["subject"]["space"] == "space_2"
    assert detail["subject"]["age"]["days"] == 5
    lot = await event(cultures, lot, "release", "2026-09-07")
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["space"] is None
    assert len((await cultures.call("detail", a["subject_id"]))["descendants"]) == 1
    await event(cultures, a, "archive", "2026-09-07")
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["origins"][0]["mother_id"] == a["subject_id"]


async def test_corrections_atomiques_et_idempotence(cultures):
    command = create()
    first, second = await asyncio.gather(cultures.call("mutate", command), cultures.call("mutate", command))
    assert first == second
    with pytest.raises(CultureConflict):
        await cultures.call("mutate", {**command, "name": "Autre"})
    note = await event(cultures, first, "note", "2026-08-02", {"note": "Ancienne"})
    with pytest.raises(CultureConflict):
        await event(cultures, first, "note", "2026-08-03", {"note": "Onglet périmé"})
    old = next(e for e in (await cultures.call("detail", first["subject_id"]))["events"] if e["kind"] == "note")
    correction = {"operation": "correct", "request_id": str(uuid.uuid4()), "subject_id": first["subject_id"],
                  "version": note["version"], "event_id": old["id"], "effective_at": "2026-08-03",
                  "payload": {"note": "Corrigée"}, "reason": "Erreur de carnet"}
    updated = await cultures.call("mutate", correction)
    detail = await cultures.call("detail", first["subject_id"])
    row = next(e for e in detail["events"] if e["kind"] == "note")
    assert row["payload"]["note"] == "Corrigée" and row["revisions"][0]["payload"]["note"] == "Ancienne"
    create_event = next(e for e in detail["events"] if e["kind"] == "create")
    # Même date : une révision de l'origine doit garder son ordre initial.
    await cultures.call("mutate", {**correction, "request_id": str(uuid.uuid4()), "version": updated["version"],
                                  "event_id": create_event["id"], "effective_at": "2026-08-01", "payload": {}})
    with pytest.raises(CultureError):
        await cultures.call("mutate", {**correction, "request_id": str(uuid.uuid4()), "version": updated["version"] + 1,
            "event_id": create_event["id"], "effective_at": "2026-09-01", "payload": {}})
    assert len((await cultures.call("detail", first["subject_id"]))["events"]) == 4


async def test_occupation_historique_et_rollback(cultures):
    first = await cultures.call("mutate", create(space="space_2"))
    with pytest.raises(CultureError, match="occupé"):
        await cultures.call("mutate", create("Concurrent", space="space_2"))
    assert (await cultures.call("overview"))["total"] == 1
    with pytest.raises(CultureError, match="effectif"):
        await event(cultures, first, "loss", "2026-08-03", {"count": 9})
    assert (await cultures.call("detail", first["subject_id"]))["subject"]["count"] == 8
    first = await event(cultures, first, "harvest", "2026-08-10")
    first = await event(cultures, first, "finish", "2026-08-15", {"release": True})
    second = await cultures.call("mutate", create("Suivant", space="space_2", space_at="2026-08-15"))
    finish = next(e for e in (await cultures.call("detail", first["subject_id"]))["events"] if e["kind"] == "finish")
    with pytest.raises(CultureError, match="occupé"):
        await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct", "subject_id": first["subject_id"],
            "version": first["version"], "event_id": finish["id"], "effective_at": "2026-08-16", "payload": {"release": True}})
    assert second["saved"]


async def test_export_restauration_et_redemarrage(cultures, tmp_path):
    lot = await cultures.call("mutate", create())
    await event(cultures, lot, "note", "2026-08-02", {"note": "=HYPERLINK(\"x\")\nTexte, français"})
    exported = await cultures.call("export")
    assert exported["schema_version"] == 3
    assert "Texte, français" in await cultures.call("csv")
    backup = tmp_path / "download.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    restored = tmp_path / "restored.sqlite3"
    restore_copy(backup, restored)
    with pytest.raises(CultureUnavailable):
        restore_copy(backup, restored)
    copy_store = CultureStore(restored, now=lambda: NOW)
    try:
        assert (await copy_store.call("detail", lot["subject_id"]))["subject"]["initial_count"] == 8
        assert (await copy_store.call("export"))["tables"] == exported["tables"]
    finally:
        await copy_store.close()
    await cultures.close()
    assert (await cultures.call("overview"))["total"] == 1


async def test_corruption_schema_futur_et_horloge(cultures, tmp_path):
    cultures.reliable = lambda: False
    command = create()
    with pytest.raises(CultureError, match="Horloge"):
        await cultures.call("mutate", command)
    await cultures.call("mutate", {**command, "confirm_date": True})
    assert (await cultures.call("overview"))["clock_reliable"] is False
    path = tmp_path / "broken.sqlite3"
    path.write_bytes(b"donnees corrompues conservees")
    broken = CultureStore(path)
    try:
        with pytest.raises(CultureUnavailable):
            await broken.call("overview")
        assert path.read_bytes() == b"donnees corrompues conservees"
    finally:
        await broken.close()
    future = tmp_path / "future.sqlite3"
    with sqlite3.connect(future) as db:
        db.execute("PRAGMA user_version=99")
    future_store = CultureStore(future)
    try:
        with pytest.raises(CultureUnavailable, match="Schéma"):
            await future_store.call("overview")
    finally:
        await future_store.close()


def test_compteurs_dates_dst_et_precision():
    assert age("2026-03-28", None, datetime(2026, 3, 29, 22, tzinfo=timezone.utc), "Europe/Paris")["days"] == 2
    assert age("2026-10-24", "2026-10-26", NOW, "Europe/Paris")["days"] == 2
    assert age("2026-09-07", None, NOW, "Europe/Paris")["days"] == 0
    assert age("2026-08-31", None, NOW, "Europe/Paris")["week"] == 2
    assert stamp("2026-09-07", "approximative", "Europe/Paris", NOW)[1] == "2026-09-07"
    with pytest.raises(CultureError):
        stamp("2026-09-08", "date", "Europe/Paris", NOW)
    with pytest.raises(CultureError):
        stamp("2026-09-07T08:00:00", "instant", "Europe/Paris", NOW)


@pytest.mark.parametrize("overrides", [
    {"origins": [{"label": "x", "count": -1}]},
    {"origins": [{"label": "x", "count": True}]},
    {"origin_type": "cutting"}, {"stage": "maintien"},
    {"origin_at": "2027-01-01"}, {"origins": "invalid"},
])
async def test_saisies_invalides_sans_creation_partielle(cultures, overrides):
    with pytest.raises(CultureError):
        await cultures.call("mutate", create(**overrides))
    assert (await cultures.call("overview"))["total"] == 0


async def test_origine_corrigee_et_sechage_distinct(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    detail = await cultures.call("detail", lot["subject_id"])
    creation = next(e for e in detail["events"] if e["kind"] == "create")
    origin = detail["subject"]["origins"][0]
    lot = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "subject_id": lot["subject_id"], "version": lot["version"], "event_id": creation["id"],
        "effective_at": "2026-08-01", "payload": {"origins": [{**origin, "count": 9}]}})
    detail = await cultures.call("detail", lot["subject_id"])
    assert detail["subject"]["initial_count"] == 9
    creation = next(e for e in detail["events"] if e["kind"] == "create")
    assert creation["revisions"][0]["payload"]["origins"][0]["count"] == 8
    lot = await event(cultures, lot, "loss", "2026-08-02", {"count": 1})
    lot = await event(cultures, lot, "harvest", "2026-09-01", {"drying_at": "2026-09-02"})
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["age"]["days"] == 5
    with pytest.raises(CultureError, match="précède"):
        await event(cultures, lot, "finish", "2026-09-01")
    lot = await event(cultures, lot, "finish", "2026-09-06", {"release": True})
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["age"]["days"] == 4


async def test_erreur_ecriture_sql_et_retry_sans_perte(cultures):
    await cultures.call("overview")
    # Simule un stockage refusant toute écriture, sur le même thread propriétaire.
    cultures._read_only = lambda: cultures._db.execute("PRAGMA query_only=ON").fetchall()
    cultures._writable = lambda: cultures._db.execute("PRAGMA query_only=OFF").fetchall()
    await cultures.call("read_only")
    command = create()
    with pytest.raises(CultureUnavailable):
        await cultures.call("mutate", command)
    assert (await cultures.call("overview"))["total"] == 0
    await cultures.call("writable")
    assert (await cultures.call("mutate", command))["saved"]
