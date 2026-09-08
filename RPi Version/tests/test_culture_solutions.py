"""Solutions : attribution temporelle, révisions, unité, durabilité et HTTP isolé."""

import json
import sqlite3
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_solution import ingredients, measurements, number
from tests.test_cultures import NOW, create, cultures, event
from tests.test_http_server import CSRF_TOKEN, web_context
from utils.culture_backup import restore_copy
from utils.culture_store import CultureStore, CultureUnavailable
from utils.culture_solution_store import SOLUTION_TABLES
from utils.culture_cycle_store import CYCLE_TABLES


def entry(kind="renewal", day="2026-08-01", **extra):
    return {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": kind,
            "reservoir_id": "reservoir_2", "effective_at": day,
            **({"volume_l": 20} if kind == "renewal" else {}), **extra}


def recipe(**extra):
    return {"operation": "recipe", "request_id": str(uuid.uuid4()), "name": "Mélange A",
            "volume_l": 10, "ingredients": [{"product": "Produit A", "quantity": 2, "unit": "mL"}], **extra}


def correction(saved, original, **extra):
    return {**original, "operation": "correct", "request_id": str(uuid.uuid4()),
            "id": saved["id"], "version": saved["version"], **extra}


@pytest.mark.parametrize("value", ["NaN", "inf", float("inf"), float("nan"), True, [], {}, "1,2,3", -1])
def test_nombres_invalides(value):
    with pytest.raises(CultureError):
        number(value, "Valeur")


def test_mesures_decimales_unites_et_absences():
    data = measurements({"ph": "0", "ec": "1234,5", "ec_unit": "µS/cm"})
    assert data["ph"] == 0 and data["ec"] == 1.2345
    assert data["temperature_c"] is None and data["volume_l"] is None
    with pytest.raises(CultureError):
        measurements({"ec": 300, "ec_unit": "ppm"})
    with pytest.raises(CultureError):
        ingredients([{"product": "X", "quantity": 1, "unit": "cuillère"}])


async def test_recette_figee_arrosage_partage_et_restauration(cultures, tmp_path):
    a = await cultures.call("mutate", create("A", "mother"))
    b = await cultures.call("mutate", create("B", "mother"))
    saved_recipe = await cultures.call("solution_mutate", recipe())
    command = entry("water", "2026-08-02", reservoir_id=None, targets=[a["subject_id"], b["subject_id"]],
                    volume_l=5, recipe_id=saved_recipe["id"], recipe_revision=1,
                    ingredients=[{"product": "Produit A", "quantity": 1, "unit": "mL"}])
    saved = await cultures.call("solution_mutate", command)
    assert await cultures.call("solution_mutate", command) == saved
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", {**command, "volume_l": 6})
    await cultures.call("solution_mutate", recipe(id=saved_recipe["id"], version=1,
        ingredients=[{"product": "Nouveau", "quantity": 99, "unit": "g"}]))
    for subject in (a, b):
        rows = (await cultures.call("solution_data", {"target": subject["subject_id"]}))["items"]
        assert len(rows) == 1 and rows[0]["volume_l"] == 5
        assert len(rows[0]["targets"]) == 2
        assert rows[0]["ingredients"][0] == {"product": "Produit A", "quantity": 1, "unit": "mL"}
    assert len((await cultures.call("export"))["tables"]["solution_entries"]) == 1
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", {**command, "request_id": str(uuid.uuid4()), "ingredients": []})
    backup = tmp_path / "backup.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    destination = tmp_path / "copy.sqlite3"
    restore_copy(backup, destination)
    other = CultureStore(destination, now=lambda: NOW)
    try:
        assert (await other.call("export"))["tables"] == (await cultures.call("export"))["tables"]
    finally:
        await other.close()


async def test_renouvellement_avant_apres_recolte_et_changement_lot(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    old = await cultures.call("solution_mutate", entry())
    new_command = entry(day="2026-08-10", ph="5,8", context="after")
    new = await cultures.call("solution_mutate", new_command)
    before = await cultures.call("solution_mutate", entry("reading", "2026-08-10", ph=6.5,
                  intervention_id=new["id"], context="before"))
    after = await cultures.call("solution_mutate", entry("reading", "2026-08-10", ec="1200", ec_unit="µS/cm",
                  intervention_id=new["id"], context="after"))
    rows = {e["id"]: e for e in (await cultures.call("solution_data"))["items"]}
    assert rows[before["id"]]["period_id"] == old["id"]
    assert rows[after["id"]]["period_id"] == new["id"] and rows[after["id"]]["ec"] == 1.2
    await cultures.call("solution_mutate", entry("reading", "2026-08-12", ph=6))
    await cultures.call("solution_mutate", entry("reading", "2026-08-16", ph=7))
    await event(cultures, lot, "harvest", "2026-08-11")
    assert len((await cultures.call("solution_data", {"target": lot["subject_id"]}))["items"]) == 4
    current = (await cultures.call("detail", lot["subject_id"]))["subject"]
    await event(cultures, {"subject_id": lot["subject_id"], "version": current["version"]}, "finish", "2026-08-15", {"release": True})
    second = await cultures.call("mutate", create("Suivant", space="space_2", space_at="2026-08-15"))
    data = await cultures.call("solution_data", {"target": second["subject_id"]})
    assert [e["ph"] for e in data["items"]] == [7]
    assert data["items"][0]["period_id"] == new["id"]
    # Une correction qui casserait le lien avant/après est atomiquement refusée.
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", correction(new, new_command, effective_at="2026-08-11"))
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", correction(new, new_command, cancelled=True))
    assert len((await cultures.call("solution_data"))["periods"]) == 2


async def test_correction_retroactive_rejoue_attribution_et_conflits(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    await cultures.call("solution_mutate", entry())
    renewal_command = entry(day="2026-08-10")
    renewal = await cultures.call("solution_mutate", renewal_command)
    reading_command = entry("reading", "2026-08-11", ph=6)
    reading = await cultures.call("solution_mutate", reading_command)
    await cultures.call("solution_mutate", correction(renewal, renewal_command, effective_at="2026-08-12"))
    row = next(e for e in (await cultures.call("solution_data"))["items"] if e["id"] == reading["id"])
    assert row["period_id"] != renewal["id"]
    await cultures.call("solution_mutate", correction(reading, reading_command, ph=0, note="Corrigé"))
    row = next(e for e in (await cultures.call("solution_data"))["items"] if e["id"] == reading["id"])
    assert row["ph"] == 0 and row["revisions"][0]["ph"] == 6
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", correction(reading, reading_command, ph=7))
    await event(cultures, lot, "harvest", "2026-08-10")
    assert all(e["kind"] != "reading" for e in (await cultures.call("solution_data", {"target": lot["subject_id"]}))["items"])


async def test_erreurs_atomicite_horloge_et_csv(cultures):
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", entry("reading", ph=6))
    await cultures.call("solution_mutate", entry())
    before = await cultures.call("export")
    for command in [entry(), entry("reading"), entry("reading", ph=15), entry("topup", volume_l=0),
                    entry("ph"), entry("reading", ph=6, context="before"), entry("water"),
                    entry("reading", ph=6, reservoir_id="absent"), entry("reading", ph=6, targets=[{}])]:
        with pytest.raises(CultureError):
            await cultures.call("solution_mutate", command)
    assert before == await cultures.call("export")
    cultures.reliable = lambda: False
    command = entry("reading", ph=6, note="=HYPERLINK(\"x\")\nNote,français")
    with pytest.raises(CultureError, match="Horloge"):
        await cultures.call("solution_mutate", command)
    await cultures.call("solution_mutate", {**command, "confirm_date": True})
    exported = await cultures.call("solution_csv")
    assert "EC_mS_cm" in exported and "'=HYPERLINK" in exported
    assert (await cultures.call("solution_data"))["items"][0]["clock_reliable"] == 0


async def test_migration_v1_sauvegarde_et_schema_futur(cultures, tmp_path):
    lot = await cultures.call("mutate", create())
    source = cultures.path
    await cultures.close()
    with sqlite3.connect(source) as db:
        for table in reversed(SOLUTION_TABLES + CYCLE_TABLES):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=1")
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["initial_count"] == 8
    backup = source.with_name(source.name + ".before-v2.sqlite3")
    with sqlite3.connect(backup) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 1
    restore_copy(backup, tmp_path / "old-restored.sqlite3")
    await cultures.close()
    assert (await cultures.call("solution_data"))["items"] == []


async def test_stockage_refuse_et_reprise(cultures):
    await cultures.call("overview")
    cultures._read_only = lambda: cultures._db.execute("PRAGMA query_only=ON").fetchall()
    cultures._writable = lambda: cultures._db.execute("PRAGMA query_only=OFF").fetchall()
    await cultures.call("read_only")
    command = entry()
    with pytest.raises(CultureUnavailable):
        await cultures.call("solution_mutate", command)
    await cultures.call("writable")
    assert (await cultures.call("solution_data"))["periods"] == []
    assert (await cultures.call("solution_mutate", command))["saved"]


async def test_solutions_http_securite_et_rendu(web_context, monkeypatch):
    client, server, config, sensors, supervisor = web_context
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_: writes.append("save"))
    command = entry(note='<script>alert("x")</script>')
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    assert (await client.post("/api/v1/cultures/solutions", json=command)).status == 403
    assert (await client.post("/api/v1/cultures/solutions", json=command, headers={**headers, "Origin": "http://evil.example"})).status == 403
    response = await client.post("/api/v1/cultures/solutions", json=command, headers=headers)
    assert response.status == 200, await response.text()
    response = await client.get("/cultures/solutions")
    assert response.status == 200, await response.text()
    html = await response.text()
    assert '&lt;script&gt;' in html and '<script>alert' not in html
    assert response.headers["Cache-Control"] == "no-store"
    assert (await client.get("/static/js/culture_solutions.js")).status == 200
    assert (await client.get("/api/v1/cultures/solutions?target=absent")).status == 400
    assert (await client.get("/api/v1/cultures/solutions/export")).status == 200
    lookup = await client.get("/api/v1/cultures/solutions?interventions=renouvellement")
    assert lookup.status == 200 and "items" not in await lookup.json()
    assert (await client.get("/api/v1/cultures/solutions?interventions=x&interventions_offset=-1")).status == 400
    assert (await client.get("/api/v1/cultures/solutions?interventions=" + "x" * 200)).status == 400
    assert (await client.post("/api/v1/cultures/solutions", json=[], headers=headers)).status == 400
    assert (await client.post("/api/v1/cultures/solutions", json={"note": "x"*70000}, headers=headers)).status == 413
    assert config.current.to_json() == original and not writes and not sensors.reconfigured
    assert (await client.get("/health/ready")).status == 200


async def test_courbes_longues_pagination_et_preparation_sans_rupture(cultures):
    first = await cultures.call("solution_mutate", entry())
    second = await cultures.call("solution_mutate", entry(day="2026-08-02"))
    # Charge représentative insérée dans le thread propriétaire : deux solutions,
    # même journée civile, pour vérifier que l'agrégation ne mélange pas leurs valeurs.
    def populate():
        with cultures._db:
            columns = [r[1] for r in cultures._db.execute("PRAGMA table_info(solution_entries)") if r[1] != "sequence"]
            template = dict(cultures._db.execute("SELECT * FROM solution_entries LIMIT 1").fetchone())
            for i in range(1002):
                row = {**template, "id": str(uuid.uuid4()), "kind": "reading", "ph": 5 if i < 501 else 7,
                       "volume_l": None, "effective_at": "2026-08-01" if i < 501 else "2026-08-02",
                       "sort_at": "2026-07-31T22:00:00+00:00" if i < 501 else "2026-08-01T22:00:00+00:00"}
                cultures._db.execute(f"INSERT INTO solution_entries ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])
    cultures._populate = populate
    await cultures.call("populate")
    data = await cultures.call("solution_data", {"target": "reservoir_2"}, 40)
    assert data["total"] == 1004 and len(data["items"]) == 40
    assert data["chart_aggregated"] and len(data["chart"]) == 2
    assert [(p["ph"], p["ph_count"], p["ph_min"], p["ph_max"]) for p in data["chart"]] == [(5, 501, 5, 5), (7, 501, 7, 7)]
    assert data["chart"][0]["period"] == first["id"] and data["chart"][1]["period"] == second["id"]
    focused = await cultures.call("solution_data", {}, 0, False, first["id"])
    assert any(e["id"] == first["id"] for e in focused["items"])
    assert len((await cultures.call("solution_data", {"start": "2026-08-02", "end": "2026-08-02"}, 0, True))) == 502


async def test_intervention_ancienne_reste_liee_et_retrouvable(cultures):
    """Lot A : une correction de pH ou de note conserve un lien devenu ancien."""
    lot = await cultures.call("mutate", create(space="space_2"))
    renewal = await cultures.call("solution_mutate", entry(day="2026-08-01"))
    await cultures.call("solution_mutate", entry(day="2026-08-01", reservoir_id="cuttings_1"))
    reading_command = entry("reading", "2026-08-01", ph=6, intervention_id=renewal["id"], context="after")
    reading = await cultures.call("solution_mutate", reading_command)
    # Plus de 200 interventions ultérieures, sur deux cibles, repoussent le renouvellement hors fenêtre.
    for index in range(201):
        day = f"2026-08-{index % 28 + 1:02d}"
        target = "reservoir_2" if index % 2 else "cuttings_1"
        await cultures.call("solution_mutate", entry("topup", day, reservoir_id=target, volume_l=1))
    data = await cultures.call("solution_data", {}, 0, False, reading["id"])
    proposed = {item["id"] for item in data["interventions"]}
    assert data["interventions_total"] == 203 and len(data["interventions"]) == 201
    assert renewal["id"] in proposed and any(item["linked"] for item in data["interventions"])
    # Correction « pH seul » : l'association n'est ni mentionnée, ni perdue, ni changée.
    partial = {"operation": "correct", "request_id": str(uuid.uuid4()), "id": reading["id"], "version": 1,
               "kind": "reading", "reservoir_id": "reservoir_2", "effective_at": "2026-08-01", "ph": 6.5}
    saved = await cultures.call("solution_mutate", partial)
    row = next(e for e in (await cultures.call("solution_data", {}, 0, False, reading["id"]))["items"] if e["id"] == reading["id"])
    assert row["ph"] == 6.5 and row["intervention_id"] == renewal["id"] and row["context"] == "after"
    # Correction « note seule », depuis la version issue de la précédente.
    await cultures.call("solution_mutate", {**partial, "request_id": str(uuid.uuid4()), "version": saved["version"],
                                            "ph": 6.5, "note": "Relevé revérifié"})
    row = next(e for e in (await cultures.call("solution_data", {}, 0, False, reading["id"]))["items"] if e["id"] == reading["id"])
    assert row["note"] == "Relevé revérifié" and row["intervention_id"] == renewal["id"] and row["revision"] == 3
    # Recherche bornée : l'intervention ancienne reste sélectionnable pour une saisie rétrospective.
    found = await cultures.call("solution_data", None, 0, False, None, renewal["id"][:8])
    assert [item["id"] for item in found["interventions"]] == [renewal["id"]] and "items" not in found
    assert found["interventions"][0]["target_label"] == "Réservoir de l’espace 2"
    page = await cultures.call("solution_data", None, 0, False, None, "", 200)
    assert page["interventions_offset"] == 200 and len(page["interventions"]) == 3
    assert (await cultures.call("solution_data", None, 0, False, None, "appoint"))["interventions_total"] == 201
    # Association incohérente : refus atomique, sans doublon à la nouvelle tentative identique.
    before = await cultures.call("export")
    broken = {**reading_command, "request_id": str(uuid.uuid4()), "operation": "correct", "id": reading["id"],
              "version": 3, "targets": [lot["subject_id"]], "reservoir_id": None}
    for _ in range(2):
        with pytest.raises(CultureError):
            await cultures.call("solution_mutate", broken)
    assert before == await cultures.call("export")


async def test_migration_interrompue_ne_publie_pas_un_schema_partiel(cultures):
    await cultures.call("mutate", create())
    path = cultures.path
    await cultures.close()
    with sqlite3.connect(path) as db:
        for table in reversed(SOLUTION_TABLES + CYCLE_TABLES):
            db.execute(f"DROP TABLE {table}")
        db.execute("CREATE TABLE recipes (incompatible TEXT)")
        db.execute("PRAGMA user_version=1")
    with pytest.raises(CultureUnavailable):
        await cultures.call("overview")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='reservoirs'").fetchone()
        assert db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 1
    assert path.with_name(path.name + ".before-v2.sqlite3").exists()
    with pytest.raises(CultureUnavailable, match="Sauvegarde"):
        await cultures.call("overview")
