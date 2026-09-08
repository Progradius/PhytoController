"""Lot I — clôture : migrations remplies, refus d'écriture, corruption, sauvegarde intégrale.

Ces scénarios ferment le rattrapage du carnet. Ils vérifient qu'une base ancienne remplie
traverse la migration sans perdre une ligne, qu'un disque refusant l'écriture, une base
corrompue ou un schéma futur laissent le fichier exactement tel qu'il est, qu'une
sauvegarde complète restaure toutes les familles des lots A à H sur une copie isolée, et
qu'aucune action du carnet ne touche `param.json`, un GPIO, un forçage, une alarme ou la
santé du contrôle.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from param.equipment_metadata import default_catalog
from tests.fakes.rpi_gpio import install
from tests.test_culture_cycles import photo_bytes
from tests.test_culture_schema_v4 import legacy_copy
from tests.test_cultures import NOW, create, event
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401 (fixture pytest)
from utils.culture_backup import restore_bundle
from utils.culture_solution_store import SOLUTION_TABLES
from utils.culture_store import CultureStore, CultureUnavailable

CATALOG = {key: value.model_dump() for key, value in default_catalog().items()}

# Tables réellement portées par une installation en version 3 : la migration se juge sur
# leur contenu, colonne par colonne, jamais sur les tables ajoutées par le schéma 4.
V3_TABLES = (("settings", "subjects", "origins", "events", "requests") + tuple(SOLUTION_TABLES)
             + ("reminders", "climate_hours", "climate_minutes", "culture_checklists", "culture_media"))

HEADERS = {"X-CSRF-Token": CSRF_TOKEN}

# Heure pleine du 6 septembre 2026 : les agrégats horaires sont indexés au multiple de 3600.
CLIMATE_ORIGIN = int(NOW.timestamp()) // 3600 * 3600 - 24 * 3600


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def columns_of(path, tables):
    with sqlite3.connect(path) as db:
        return {table: [row[1] for row in db.execute(f"PRAGMA table_info({table})")] for table in tables}


def read_tables(path, columns_by_table):
    """Contenu de chaque table, colonnes explicites et ordre stable indépendant du rowid."""
    data = {}
    with sqlite3.connect(path) as db:
        for table, columns in columns_by_table.items():
            rows = db.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall()
            data[table] = sorted(rows, key=lambda row: json.dumps(row, default=str))
    return data


def corrupt(path, offset=8192, length=2048):
    """Écrase des octets à l'intérieur d'une page : la base reste un fichier SQLite illisible."""
    raw = bytearray(Path(path).read_bytes())
    assert len(raw) > offset + length, "Base trop petite pour être corrompue de façon réaliste."
    raw[offset:offset + length] = b"\x00" * length
    Path(path).write_bytes(bytes(raw))


async def remplir_carnet_ancien(path):
    """Carnet dense tel qu'une installation de version 3 pouvait le contenir."""
    store = CultureStore(path, now=lambda: NOW)
    mere = await store.call("mutate", create("Mère A", "mother", origin_at="2026-05-01",
                                             space_at="2026-05-01", stage_at="2026-05-01"))
    lot = await store.call("mutate", create("Lot ancien", space="space_2", origin_type="cutting",
        stage="enracinement", origin_at="2026-06-01",
        origins=[{"mother_id": mere["subject_id"], "count": 6}]))
    lot = await event(store, lot, "note", "2026-08-02", {"note": "Observation ancienne"})
    await store.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-08-03", "volume_l": 20})
    recette = await store.call("solution_mutate", {"operation": "recipe", "request_id": str(uuid.uuid4()),
        "name": "Mélange A", "volume_l": 10,
        "ingredients": [{"product": "Produit A", "quantity": 2, "unit": "mL"}]})
    await store.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "water", "targets": [lot["subject_id"]], "effective_at": "2026-08-04", "volume_l": 5,
        "recipe_id": recette["id"], "recipe_revision": 1,
        "ingredients": [{"product": "Produit A", "quantity": 1, "unit": "mL"}]})
    await store.call("cycle_mutate", {"operation": "checklist", "request_id": str(uuid.uuid4()),
        "subject_id": lot["subject_id"], "version": lot["version"], "effective_at": "2026-09-06",
        "checks": {"lighting": True, "pump": False, "ventilation": True}})
    await store.call("cycle_mutate", {"operation": "reminder", "request_id": str(uuid.uuid4()),
        "target": "reservoir_2", "title": "Renouveler le bac", "due_date": "2026-09-08",
        "interval_days": 7})
    detail = await store.call("detail", lot["subject_id"])
    creation = next(item for item in detail["events"] if item["kind"] == "create")
    photo = await store.call("media_add", {"request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"],
        "event_id": creation["id"], "event_revision": creation["revision"],
        "caption": "Photo d’origine"}, photo_bytes())

    def climat():
        with store._db:
            store._db.executemany(
                "INSERT INTO climate_hours (sensor,hour,label,unit,minimum,maximum,total,valid_count,observed_count)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                [("BME280T", CLIMATE_ORIGIN + 3600 * index, "Température de l’air", "°C",
                  18.5, 24.5, 1290.0, 60, 60) for index in range(6)])
            store._db.executemany("INSERT INTO climate_minutes (sensor,minute) VALUES (?,?)",
                                  [("BME280T", CLIMATE_ORIGIN + 60 * index) for index in range(6)])
    store._seed_climat = climat
    await store.call("seed_climat")
    await store.close()
    return {"mother_id": mere["subject_id"], "subject_id": lot["subject_id"], "photo_id": photo["id"]}


# --- 1. Chemins de migration sur une base remplie -----------------------------------


async def test_migration_v3_remplie_conserve_chaque_ligne_et_sa_sauvegarde(tmp_path):
    identifiants = await remplir_carnet_ancien(tmp_path / "source.sqlite3")
    ancienne = tmp_path / "cultures.sqlite3"
    legacy_copy(tmp_path / "source.sqlite3", ancienne, 3)
    colonnes = columns_of(ancienne, V3_TABLES)
    avant = read_tables(ancienne, colonnes)
    # La migration ne prouve rien sur une base vide : chaque table de la version 3 porte
    # des lignes, hormis les liens relevé↔intervention nés avec le lot A.
    vides = [table for table in V3_TABLES if not avant[table] and table != "solution_links"]
    assert vides == [], f"Tables sans donnée avant migration : {vides}"

    store = CultureStore(ancienne, now=lambda: NOW)
    try:
        assert (await store.call("detail", identifiants["subject_id"]))["subject"]["name"] == "Lot ancien"
    finally:
        await store.close()

    with sqlite3.connect(ancienne) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 4
    # Chaque ligne antérieure est retrouvée à l'identique sur les colonnes de la version 3 :
    # une migration n'a le droit d'ajouter que des colonnes, jamais de réécrire une saisie.
    assert read_tables(ancienne, colonnes) == avant

    sauvegarde = ancienne.with_name(ancienne.name + ".before-v4.sqlite3")
    with sqlite3.connect(sauvegarde) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert not db.execute("SELECT name FROM sqlite_schema WHERE name='culture_targets'").fetchone()
    assert read_tables(sauvegarde, colonnes) == avant


# --- 2. Refus d'écriture ------------------------------------------------------------


@pytest.mark.skipif(os.getuid() == 0, reason="Le superutilisateur ignore les permissions du disque.")
async def test_disque_en_lecture_seule_refuse_sans_alterer_le_carnet(tmp_path):
    """Un stockage qui refuse l'écriture doit se déclarer indisponible, pas migrer à moitié."""
    dossier = tmp_path / "carnet"
    dossier.mkdir()
    await remplir_carnet_ancien(dossier / "source.sqlite3")
    ancienne = dossier / "cultures.sqlite3"
    legacy_copy(dossier / "source.sqlite3", ancienne, 3)
    empreinte = digest(ancienne)

    os.chmod(dossier, 0o500)
    store = CultureStore(ancienne, now=lambda: NOW)
    try:
        with pytest.raises(CultureUnavailable):
            await store.call("overview")
    finally:
        await store.close()
        os.chmod(dossier, 0o700)

    assert digest(ancienne) == empreinte
    with sqlite3.connect(ancienne) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 3
    assert not ancienne.with_name(ancienne.name + ".before-v4.sqlite3").exists()
    assert not list(dossier.glob(".culture-migrate-*"))

    # Fichier seul en lecture : la lecture reste possible, l'écriture est refusée en bloc.
    lecture = tmp_path / "lecture"
    lecture.mkdir()
    await remplir_carnet_ancien(lecture / "cultures.sqlite3")
    seule = lecture / "cultures.sqlite3"
    empreinte = digest(seule)
    os.chmod(seule, 0o400)
    store = CultureStore(seule, now=lambda: NOW)
    try:
        assert (await store.call("overview"))["total"] == 2
        with pytest.raises(CultureUnavailable):
            await store.call("mutate", create("Refusé"))
    finally:
        await store.close()
        os.chmod(seule, 0o600)
    assert digest(seule) == empreinte
    assert not list(lecture.glob(".culture-migrate-*"))


# --- 3 et 4. Corruption et schéma futur ---------------------------------------------


@pytest.mark.parametrize("degat", ["octets", "troncature"])
async def test_base_corrompue_reste_intacte_sur_le_disque(tmp_path, degat):
    await remplir_carnet_ancien(tmp_path / "cultures.sqlite3")
    chemin = tmp_path / "cultures.sqlite3"
    if degat == "octets":
        corrupt(chemin)
    else:
        raw = chemin.read_bytes()
        chemin.write_bytes(raw[:len(raw) // 2])
    empreinte = digest(chemin)
    store = CultureStore(chemin, now=lambda: NOW)
    try:
        # Une corruption détectée par `quick_check` est nommée ; une base illisible dès
        # l'ouverture reste une indisponibilité, jamais une réparation silencieuse.
        with pytest.raises(CultureUnavailable,
                           match="corrompu" if degat == "octets" else "indisponible"):
            await store.call("overview")
    finally:
        await store.close()
    assert digest(chemin) == empreinte
    assert not list(tmp_path.glob("*.before-v*.sqlite3"))


async def test_schema_futur_immediat_refuse_toute_ecriture(tmp_path):
    """La version 5 est le cas réel d'un retour en arrière après mise à jour."""
    await remplir_carnet_ancien(tmp_path / "cultures.sqlite3")
    chemin = tmp_path / "cultures.sqlite3"
    with sqlite3.connect(chemin) as db:
        db.execute("PRAGMA user_version=5")
    empreinte = digest(chemin)
    store = CultureStore(chemin, now=lambda: NOW)
    try:
        with pytest.raises(CultureUnavailable, match="incompatible"):
            await store.call("overview")
        with pytest.raises(CultureUnavailable, match="incompatible"):
            await store.call("mutate", create("Refusé"))
    finally:
        await store.close()
    assert digest(chemin) == empreinte
    assert not list(tmp_path.glob("*.before-v*.sqlite3"))


# --- 5. Sauvegarde et restauration complètes ----------------------------------------


async def test_sauvegarde_complete_restaure_donnees_anciennes_et_nouvelles(tmp_path):
    dossier = tmp_path / "carnet"
    dossier.mkdir()
    identifiants = await remplir_carnet_ancien(dossier / "source.sqlite3")
    ancienne = dossier / "cultures.sqlite3"
    legacy_copy(dossier / "source.sqlite3", ancienne, 3)
    subject_id = identifiants["subject_id"]

    store = CultureStore(ancienne, now=lambda: NOW)
    try:
        # Familles apparues après la migration : elles cohabitent avec l'ancien contenu.
        detail = await store.call("detail", subject_id)
        lot = {"subject_id": subject_id, "version": detail["subject"]["version"]}
        lot = await store.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "backfill",
            "subject_id": subject_id, "version": lot["version"],
            "steps": [{"kind": "move", "effective_at": "2026-07-15", "precision": "date",
                       "payload": {"space": "space_1"}}]})
        note = next(item for item in (await store.call("detail", subject_id))["events"] if item["kind"] == "note")
        lot = await store.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
            "subject_id": subject_id, "version": lot["version"], "event_id": note["id"],
            "effective_at": "2026-08-02", "payload": {"note": "Observation corrigée"}})
        releve = next(item for item in (await store.call("solution_data", {}))["items"]
                      if item["kind"] == "renewal")
        await store.call("solution_mutate", {"operation": "correct", "request_id": str(uuid.uuid4()),
            "id": releve["id"], "version": releve["revision"], "kind": releve["kind"],
            "reservoir_id": releve["reservoir_id"], "effective_at": "2026-08-03",
            "volume_l": 20, "ph": "6,1", "reason": "Relevé pH ajouté après coup"}, CATALOG)
        verification = (await store.call("cycle_data", [subject_id]))["summaries"][0]["checklists"][0]
        await store.call("cycle_mutate", {"operation": "checklist_correct", "request_id": str(uuid.uuid4()),
            "id": verification["id"], "version": verification["revision"],
            "checks": {"lighting": True, "pump": True, "ventilation": True},
            "note": "Pompe vérifiée", "reason": "Case oubliée"})
        annulable = await store.call("cycle_mutate", {"operation": "checklist", "request_id": str(uuid.uuid4()),
            "subject_id": subject_id, "version": lot["version"], "effective_at": "2026-09-05",
            "checks": {"lighting": False, "pump": False, "ventilation": False}})
        await store.call("cycle_mutate", {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()),
            "id": annulable["id"], "version": annulable["revision"], "reason": "Attribuée au mauvais lot"})
        plage = await store.call("target_mutate", {"operation": "target", "request_id": str(uuid.uuid4()),
            "target": "reservoir_2", "start_at": "2026-08-01", "ph_min": "5,8", "ph_max": "6,4"})
        await store.call("target_mutate", {"operation": "target_action", "request_id": str(uuid.uuid4()),
            "id": plage["id"], "version": plage["version"], "action": "end", "end_at": "2026-08-20"})
        annulee = await store.call("target_mutate", {"operation": "target", "request_id": str(uuid.uuid4()),
            "target": "reservoir_2", "start_at": "2026-08-21", "ec_min": "1,2", "ec_max": "1,8"})
        await store.call("target_mutate", {"operation": "target_action", "request_id": str(uuid.uuid4()),
            "id": annulee["id"], "version": annulee["version"], "action": "cancel", "reason": "Saisie erronée"})
        await store.call("light_mutate", {"operation": "light", "request_id": str(uuid.uuid4()),
            "scope": "global", "label": "Végétatif 18/6", "on_minutes": 1080, "off_minutes": 360,
            "start_at": "2026-08-01"})
        await store.call("equipment_mutate", {"operation": "link", "request_id": str(uuid.uuid4()),
            "equipment_id": "cyclic_2", "usage": "irrigation espace 2", "scope": "space",
            "space": "space_2", "start_at": "2026-06-01"}, CATALOG)
        observation = await store.call("space_event_mutate", {"operation": "space_event",
            "request_id": str(uuid.uuid4()), "space": "space_2", "kind": "observation",
            "effective_at": "2026-09-01", "note": "Bac nettoyé"})
        await store.call("media_add", {"request_id": str(uuid.uuid4()), "space_event_id": observation["id"],
            "space_event_revision": 1, "caption": "Coin nord"}, photo_bytes((100, 60)))
        bundle = Path(await store.call("bundle"))
        reference = await store.call("export")
    finally:
        await store.close()

    destination, cli = tmp_path / "restauration", tmp_path / "restauration-cli"
    try:
        restore_bundle(bundle, destination)
        # Outil opérateur réel, vers un second dossier entièrement isolé.
        termine = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "restore-cultures.py"),
             "--bundle", str(bundle), str(cli)], capture_output=True, text=True, timeout=120)
        assert termine.returncode == 0, termine.stderr
        assert (cli / "cultures.sqlite3").is_file() and not (cli / ".restauration-incomplete").exists()
    finally:
        bundle.unlink(missing_ok=True)

    photos_source = {path.name: digest(path) for path in (dossier / "culture_media").glob("*.jpg")}
    assert len(photos_source) == 2
    for copie in (destination, cli):
        assert {path.name: digest(path) for path in (copie / "culture_media").glob("*.jpg")} == photos_source

    copie = CultureStore(destination / "cultures.sqlite3", now=lambda: NOW)
    copie._parcours = lambda: copie._cycle_validate()
    try:
        assert (await copie.call("export"))["tables"] == reference["tables"]
        assert await copie.call("parcours") is None
        restaure = await copie.call("detail", subject_id)
        assert restaure["subject"]["name"] == "Lot ancien"
        assert [space["space"] for space in restaure["subject"]["occupations"]] == ["space_1", "space_2"]
        corrige = next(item for item in restaure["events"] if item["kind"] == "note")
        assert corrige["payload"]["note"] == "Observation corrigée" and corrige["revisions"]
        assert len(restaure["photos"]) == 1
        releves = (await copie.call("solution_data", {}))["items"]
        assert [item["kind"] for item in releves] == ["water", "renewal"]
        assert releves[1]["ph"] == 6.1 and releves[1]["revision"] == 2
        verifications = (await copie.call("cycle_data", [subject_id]))["summaries"][0]["checklists"]
        assert sorted(item["cancelled"] for item in verifications) == [0, 1]
        assert (await copie.call("cycle_data"))["reminders"][0]["title"] == "Renouveler le bac"
        plages = (await copie.call("targets"))["items"]
        assert len(plages) == 2 and [item["cancelled"] for item in plages].count(1) == 1
        assert (await copie.call("light_data", {}))["targets"][0]["label"] == "Végétatif 18/6"
        liens = await copie.call("equipment_links", {"at": "2026-06-15"}, CATALOG)
        assert [item["usage"] for item in liens["resolved"]["items"]] == ["irrigation espace 2"]
        journal = await copie.call("journal", {"target": "space_2"})
        assert journal["items"][0]["note"] == "Bac nettoyé" and len(journal["items"][0]["photos"]) == 1
    finally:
        await copie.close()


# --- 6. Aucune action du carnet ne touche la configuration ni les GPIO ---------------


async def test_toutes_les_mutations_laissent_configuration_gpio_et_forcages_intacts(
        web_context, config_path, tmp_path, monkeypatch):
    from network.web import pages as pages_module
    from network.web import server as server_module
    from utils.overrides import OverrideStore
    from utils.state_store import StateStore

    client, server, config, sensors, supervisor = web_context
    gpio = install(monkeypatch)
    forcages = OverrideStore(StateStore(tmp_path / "runtime_state.json"))
    monkeypatch.setattr(server_module, "shared_overrides", lambda: forcages)
    monkeypatch.setattr(pages_module, "shared_overrides", lambda: forcages)
    ecritures = []
    monkeypatch.setattr(config, "save", lambda *_args: ecritures.append("save"))
    monkeypatch.setattr(config, "commit", lambda *_args: ecritures.append("commit"))
    avant = config_path.read_bytes()
    etat = await (await client.get("/api/v1/state")).json()

    async def poster(route, body):
        response = await client.post(route, json=body, headers=HEADERS)
        assert response.status == 200, (route, await response.text())
        return await response.json()

    lot = await poster("/api/v1/cultures", create("Clôture", space="space_2", origin_at="2026-06-01"))
    lot = await poster("/api/v1/cultures", {"request_id": str(uuid.uuid4()), "operation": "event",
        "subject_id": lot["subject_id"], "version": lot["version"], "kind": "note",
        "effective_at": "2026-08-02", "payload": {"note": "Observation"}})
    lot = await poster("/api/v1/cultures", {"request_id": str(uuid.uuid4()), "operation": "backfill",
        "subject_id": lot["subject_id"], "version": lot["version"],
        "steps": [{"kind": "move", "effective_at": "2026-07-20", "precision": "date",
                   "payload": {"space": "space_1"}}]})
    detail = await (await client.get("/api/v1/cultures/" + lot["subject_id"])).json()
    note = next(item for item in detail["events"] if item["kind"] == "note")
    lot = await poster("/api/v1/cultures", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "subject_id": lot["subject_id"], "version": lot["version"], "event_id": note["id"],
        "effective_at": "2026-08-02", "payload": {"note": "Observation corrigée"}})
    await poster("/api/v1/cultures/solutions", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-08-03", "volume_l": 20})
    await poster("/api/v1/cultures/cycles", {"operation": "reminder", "request_id": str(uuid.uuid4()),
        "target": "reservoir_2", "title": "Renouveler le bac", "due_date": "2026-09-30",
        "interval_days": 7})
    verification = await poster("/api/v1/cultures/cycles", {"operation": "checklist",
        "request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"], "version": lot["version"],
        "effective_at": "2026-09-06", "checks": {"lighting": True, "pump": False, "ventilation": True}})
    await poster("/api/v1/cultures/cycles", {"operation": "checklist_correct",
        "request_id": str(uuid.uuid4()), "id": verification["id"], "version": verification["revision"],
        "checks": {"lighting": True, "pump": True, "ventilation": True},
        "note": "Pompe vérifiée", "reason": "Case oubliée"})
    await poster("/api/v1/cultures/targets", {"operation": "target", "request_id": str(uuid.uuid4()),
        "target": "reservoir_2", "start_at": "2026-08-01", "ph_min": "5,8", "ph_max": "6,4"})
    await poster("/api/v1/cultures/light", {"operation": "light", "request_id": str(uuid.uuid4()),
        "scope": "global", "label": "Végétatif 18/6", "on_minutes": 1080, "off_minutes": 360,
        "start_at": "2026-08-01"})
    await poster("/api/v1/cultures/equipment", {"operation": "link", "request_id": str(uuid.uuid4()),
        "equipment_id": "cyclic_2", "usage": "irrigation espace 2", "scope": "space",
        "space": "space_2", "start_at": "2026-06-01"})
    await poster("/api/v1/cultures/journal", {"operation": "space_event", "request_id": str(uuid.uuid4()),
        "space": "space_2", "kind": "observation", "effective_at": "2026-09-01", "note": "Bac nettoyé"})

    assert config_path.read_bytes() == avant
    assert ecritures == [] and sensors.reconfigured == 0 and supervisor.reloads == []
    # Le carnet est déclaratif : pas une seule commande de sortie, pas un seul forçage.
    assert [item for item in gpio.events if item[0] == "output"] == []
    assert forcages.payload()["items"] == [] and forcages.payload()["active_count"] == 0
    apres = await (await client.get("/api/v1/state")).json()
    assert apres["alarms"] == etat["alarms"]
    assert apres["health"]["control_healthy"] is True
    assert (await client.get("/health/ready")).status == 200


# --- 7. Panne du carnet sans dégradation du contrôle --------------------------------


async def test_carnet_corrompu_rend_les_pages_lisibles_sans_toucher_au_controle(
        web_context, tmp_path, monkeypatch):
    client, server, _config, _sensors, supervisor = web_context
    gpio = install(monkeypatch)
    corrompu = tmp_path / "corrompu.sqlite3"
    await remplir_carnet_ancien(corrompu)
    corrupt(corrompu)
    empreinte = digest(corrompu)
    # Toutes les vues partagent le magasin agrégé par `CultureViews` : une seule bascule.
    server.cultures.store.path = corrompu

    for route in ("/cultures", "/cultures/journal", "/cultures/targets", "/cultures/light",
                  "/cultures/equipment", "/cultures/cycles", "/cultures/solutions"):
        response = await client.get(route)
        assert response.status == 503, route
        page = await response.text()
        assert "Carnet corrompu" in page, route
    for route in ("/api/v1/cultures", "/api/v1/cultures/journal", "/api/v1/cultures/targets",
                  "/api/v1/cultures/light", "/api/v1/cultures/equipment",
                  "/api/v1/cultures/cycles", "/api/v1/cultures/solutions"):
        assert (await client.get(route)).status == 503, route

    assert digest(corrompu) == empreinte
    assert [item for item in gpio.events if item[0] == "output"] == []
    assert (await client.get("/health/ready")).status == 200
    assert (await client.get("/")).status == 200
    state = await (await client.get("/api/v1/state")).json()
    assert state["health"]["control_healthy"] is True
    assert supervisor.is_healthy() and supervisor.control_healthy()


# --- 8. Idempotence et double clic --------------------------------------------------


@pytest.mark.parametrize("route,commande,different", [
    ("/api/v1/cultures", {"operation": "create", "kind": "lot", "name": "Double clic",
                          "origin_at": "2026-08-01", "space_at": "2026-08-01", "stage_at": "2026-08-01",
                          "stage": "germination", "origins": [{"label": "Semences A", "count": 8}]},
     {"name": "Autre saisie"}),
    ("/api/v1/cultures/targets", {"operation": "target", "target": "reservoir_2",
                                  "start_at": "2026-08-01", "ph_min": "5,8", "ph_max": "6,4"},
     {"ph_max": "6,6"}),
    ("/api/v1/cultures/journal", {"operation": "space_event", "space": "space_2",
                                  "kind": "observation", "effective_at": "2026-09-01",
                                  "note": "Bac nettoyé"},
     {"note": "Autre note"}),
])
async def test_double_clic_ne_cree_qu_une_ligne_et_refuse_une_cle_reutilisee(
        web_context, route, commande, different):
    client, *_ = web_context
    body = {**commande, "request_id": str(uuid.uuid4())}
    premier = await client.post(route, json=body, headers=HEADERS)
    assert premier.status == 200, await premier.text()
    saved = await premier.json()
    second = await client.post(route, json=body, headers=HEADERS)
    assert second.status == 200 and await second.json() == saved
    conflit = await client.post(route, json={**body, **different}, headers=HEADERS)
    assert conflit.status == 409

    # Le double envoi n'a créé qu'une ligne, et la clé refusée n'en a créé aucune.
    listing = await (await client.get(route)).json()
    assert listing["total"] == 1
