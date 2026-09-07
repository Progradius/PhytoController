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
    assert exported["schema_version"] == 1
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
