"""Migration 3 → 4 du carnet : conservation des données, sauvegardes et refus explicites."""

import sqlite3
import uuid

import pytest

from tests.test_cultures import NOW, create
from utils.culture_backup import restore_copy
from utils.culture_cycle_store import CYCLE_SCHEMA
from utils.culture_schema_v4 import V4_TABLES, V4_VIEWS
from utils.culture_solution_store import SOLUTION_SCHEMA, SOLUTION_TABLES
from utils.culture_store import BASE_SCHEMA, CultureStore, CultureUnavailable

# Index du schéma 4 portés par des tables antérieures : ils survivraient à la seule
# suppression des tables neuves et feraient échouer une migration rejouée.
V4_SHARED_INDEXES = ("events_sort", "solution_entries_sort", "solution_targets_subject",
                     "solution_entries_kind", "climate_hours_hour", "culture_checklists_subject",
                     "culture_checklists_recorded", "culture_media_owner", "culture_media_space")


def strip_v4(db):
    """Retire les objets propres au schéma 4 pour simuler une base plus ancienne."""
    for view in V4_VIEWS:
        db.execute(f"DROP VIEW IF EXISTS {view}")
    for table in reversed(V4_TABLES):
        db.execute(f"DROP TABLE IF EXISTS {table}")
    for index in V4_SHARED_INDEXES:
        db.execute(f"DROP INDEX IF EXISTS {index}")
    if any(row[1] == "equipment_context" for row in db.execute("PRAGMA table_info(solution_entries)")):
        db.execute("ALTER TABLE solution_entries DROP COLUMN equipment_context")


def legacy_copy(source, destination, version):
    """Reconstruit une base de version 1, 2 ou 3 depuis les DDL historiques du dépôt.

    La copie est faite table par table avec des listes de colonnes explicites : une base
    ancienne n'est jamais une base actuelle amputée par un DROP, sinon la migration
    testée ne serait pas celle que subira une installation réelle.
    """
    script = BASE_SCHEMA + (SOLUTION_SCHEMA if version >= 2 else "") + (CYCLE_SCHEMA if version >= 3 else "")
    db = sqlite3.connect(destination)
    try:
        db.executescript(script)
        db.execute("ATTACH DATABASE ? AS moderne", (str(source),))
        tables = ["settings", "subjects", "origins", "events", "requests"]
        if version >= 2:
            tables += list(SOLUTION_TABLES)
        if version >= 3:
            tables += ["reminders", "climate_hours", "climate_minutes", "culture_checklists", "culture_media"]
        for table in tables:
            columns = ",".join(row[1] for row in db.execute(f"PRAGMA table_info({table})"))
            db.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM moderne.{table}")
        db.execute(f"PRAGMA user_version={version}")
        db.commit()
        db.execute("DETACH DATABASE moderne")
    finally:
        db.close()


async def populate(path):
    """Carnet complet en version 4, source des copies anciennes."""
    store = CultureStore(path, now=lambda: NOW)
    lot = await store.call("mutate", create(space="space_2"))
    await store.call("cycle_mutate", {"operation": "checklist", "request_id": str(uuid.uuid4()),
        "subject_id": lot["subject_id"], "version": lot["version"], "effective_at": "2026-09-07",
        "checks": {"lighting": True, "pump": False, "ventilation": True}})
    await store.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-08-05", "volume_l": 20})
    await store.close()
    return lot


def add_photo(path, event_id, subject_id, revision=1, name=None):
    """Photo enregistrée directement : la migration se juge sur la ligne, pas sur le fichier."""
    name = name or (str(uuid.uuid4()) + ".jpg")
    with sqlite3.connect(path) as db:
        columns = ",".join(row[1] for row in db.execute("PRAGMA table_info(culture_media)"))
        values = {"id": name[:-4], "subject_id": subject_id, "event_id": event_id, "event_revision": revision,
                  "name": name, "sha256": "0" * 64, "size": 12, "width": 4, "height": 3,
                  "caption": "Photo migrée", "recorded_at": NOW.isoformat()}
        ordered = [values.get(column) for column in columns.split(",")]
        db.execute(f"INSERT INTO culture_media ({columns}) VALUES ({','.join('?' for _ in ordered)})", ordered)
    return name[:-4]


async def test_migration_v4_conserve_verifications_et_photos(tmp_path):
    lot = await populate(tmp_path / "source.sqlite3")
    ancienne = tmp_path / "cultures.sqlite3"
    legacy_copy(tmp_path / "source.sqlite3", ancienne, 3)
    with sqlite3.connect(ancienne) as db:
        event_id, revision = db.execute("SELECT id,revision FROM events LIMIT 1").fetchone()
        subject_id = db.execute("SELECT subject_id FROM events WHERE id=?", (event_id,)).fetchone()[0]
    photo_id = add_photo(ancienne, event_id, subject_id, revision)

    store = CultureStore(ancienne, now=lambda: NOW)
    detail = await store.call("detail", lot["subject_id"])
    assert detail["subject"]["id"] == lot["subject_id"]
    checklists = (await store.call("cycle_data", [lot["subject_id"]]))["summaries"][0]["checklists"]
    await store.close()

    with sqlite3.connect(ancienne) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        row = db.execute("SELECT * FROM culture_checklists").fetchone()
        columns = [description[0] for description in db.execute("SELECT * FROM culture_checklists").description]
        checklist = dict(zip(columns, row))
        assert checklist["revision"] == 1 and checklist["precision"] == "date" and checklist["cancelled"] == 0
        # Le contexte absent du schéma 3 reste inconnu : il n'est pas reconstitué.
        assert checklist["stage_at"] is None and checklist["stage_precision"] is None
        assert checklist["subject_version"] is None and checklist["clock_reliable"] is None
        assert checklist["equipment_context"] == "{}" and checklist["reason"] == ""
        photo = db.execute("SELECT owner_kind,subject_id,space,event_id,space_event_id FROM culture_media WHERE id=?",
                           (photo_id,)).fetchone()
        assert photo == ("event", subject_id, None, event_id, None)
        assert db.execute("SELECT equipment_context FROM solution_entries").fetchone()[0] == "{}"
        assert db.execute("SELECT COUNT(*) FROM culture_journal").fetchone()[0] >= 4
    assert len(checklists) == 1 and checklists[0]["lighting"] == 1 and checklists[0]["pump"] == 0

    sauvegarde = ancienne.with_name(ancienne.name + ".before-v4.sqlite3")
    with sqlite3.connect(sauvegarde) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert db.execute("SELECT COUNT(*) FROM culture_checklists").fetchone()[0] == 1

    # Une sauvegarde déjà présente bloque toute nouvelle tentative : arbitrage humain.
    for suffix in ("", "-wal", "-shm"):
        ancienne.with_name(ancienne.name + suffix).unlink(missing_ok=True)
    legacy_copy(tmp_path / "source.sqlite3", ancienne, 3)
    with pytest.raises(CultureUnavailable, match="Sauvegarde"):
        await CultureStore(ancienne, now=lambda: NOW).call("overview")

    futur = tmp_path / "futur.sqlite3"
    legacy_copy(tmp_path / "source.sqlite3", futur, 3)
    with sqlite3.connect(futur) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(CultureUnavailable, match="incompatible"):
        await CultureStore(futur, now=lambda: NOW).call("overview")


@pytest.mark.parametrize("version,sauvegardes", [(1, (2, 3, 4)), (2, (3, 4))])
async def test_migration_enchainee_produit_une_sauvegarde_par_version(tmp_path, version, sauvegardes):
    lot = await populate(tmp_path / "source.sqlite3")
    ancienne = tmp_path / f"v{version}.sqlite3"
    legacy_copy(tmp_path / "source.sqlite3", ancienne, version)
    store = CultureStore(ancienne, now=lambda: NOW)
    assert (await store.call("detail", lot["subject_id"]))["subject"]["id"] == lot["subject_id"]
    await store.close()
    with sqlite3.connect(ancienne) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    for cible in sauvegardes:
        chemin = ancienne.with_name(ancienne.name + f".before-v{cible}.sqlite3")
        with sqlite3.connect(chemin) as db:
            assert db.execute("PRAGMA user_version").fetchone()[0] == cible - 1


async def test_migration_v4_interrompue_conserve_la_version_3(tmp_path, monkeypatch):
    import utils.culture_store as module
    await populate(tmp_path / "source.sqlite3")
    ancienne = tmp_path / "cultures.sqlite3"
    legacy_copy(tmp_path / "source.sqlite3", ancienne, 3)
    monkeypatch.setattr(module, "SCHEMA4_SQL", module.SCHEMA4_SQL + "\nCREATE TABLE interrompu (;\n")
    with pytest.raises(CultureUnavailable):
        await CultureStore(ancienne, now=lambda: NOW).call("overview")
    with sqlite3.connect(ancienne) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='culture_targets'").fetchone()
        assert db.execute("SELECT COUNT(*) FROM culture_checklists").fetchone()[0] == 1
    assert ancienne.with_name(ancienne.name + ".before-v4.sqlite3").exists()

    # Reprise après levée manuelle de la sauvegarde : la migration aboutit et les clés
    # étrangères sont bien réarmées sur la connexion vivante.
    ancienne.with_name(ancienne.name + ".before-v4.sqlite3").unlink()
    monkeypatch.undo()
    store = CultureStore(ancienne, now=lambda: NOW)
    # Lecture dans le thread SQLite du magasin : ces PRAGMA sont propres à sa connexion.
    store._pragmas = lambda: [store._db.execute(f"PRAGMA {name}").fetchone()[0]
                              for name in ("foreign_keys", "user_version")]
    assert await store.call("pragmas") == [1, 4]
    await store.close()


async def test_photo_a_deux_proprietaires_refusee(tmp_path):
    lot = await populate(tmp_path / "cultures.sqlite3")
    assert lot["saved"]
    with sqlite3.connect(tmp_path / "cultures.sqlite3") as db:
        event_id, revision = db.execute("SELECT id,revision FROM events LIMIT 1").fetchone()
        db.execute("""INSERT INTO space_events
            (id,revision,space,kind,effective_at,precision,sort_at,recorded_at,clock_reliable,payload)
            VALUES ('obs',1,'space_1','observation','2026-09-07','date',?,?,1,'{"note":"x"}')""",
            (NOW.isoformat(), NOW.isoformat()))
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("""INSERT INTO culture_media
                (id,owner_kind,subject_id,space,event_id,event_revision,space_event_id,space_event_revision,
                 name,sha256,size,width,height,caption,recorded_at)
                VALUES ('double','event',(SELECT subject_id FROM events LIMIT 1),'space_1',?,?, 'obs',1,
                 'double.jpg',?,1,1,1,'','')""", (event_id, revision, "0" * 64))


async def test_restauration_v4_exige_la_vue_du_journal(tmp_path):
    await populate(tmp_path / "cultures.sqlite3")
    store = CultureStore(tmp_path / "cultures.sqlite3", now=lambda: NOW)
    sauvegarde = tmp_path / "sauvegarde.sqlite3"
    sauvegarde.write_bytes(await store.call("backup"))
    await store.close()
    restore_copy(sauvegarde, tmp_path / "copie.sqlite3")
    with sqlite3.connect(sauvegarde) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
        db.execute("DROP VIEW culture_journal")
    with pytest.raises(CultureUnavailable, match="journal"):
        restore_copy(sauvegarde, tmp_path / "sans-vue.sqlite3")
