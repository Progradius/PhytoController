"""Jalon 3 : photos bornées, restauration complète, rappels et données climatiques auxiliaires."""

import io
import json
import sqlite3
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from PIL import Image

from controllers.CultureService import CultureService
from model.culture import CultureConflict, CultureError, event_payload
from model.culture_cycle import MAX_PHOTO_BYTES
from tests.test_cultures import NOW, create, cultures, event
from tests.test_http_server import CSRF_TOKEN, CULTURE_NOW, web_context
from utils.culture_backup import restore_bundle, restore_copy
from utils.culture_cycle_store import CYCLE_TABLES
from utils.culture_media_store import image_bytes
from utils.culture_store import CultureStore, CultureUnavailable


def photo_bytes(size=(120, 80), exif=True):
    output = io.BytesIO()
    picture = Image.new("RGB", size, "green")
    metadata = Image.Exif()
    if exif:
        metadata[270] = "Métadonnées privées à supprimer"
    picture.save(output, "JPEG", exif=metadata)
    return output.getvalue()


def reminder(target, **extra):
    return {"operation": "reminder", "request_id": str(uuid.uuid4()), "target": target,
            "title": "Vérifier le relevé", "due_date": "2026-09-08", "interval_days": 2, **extra}


async def photo_command(store):
    lot = await store.call("mutate", create())
    detail = await store.call("detail", lot["subject_id"])
    entry = detail["events"][0]
    return {"request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"], "event_id": entry["id"],
            "event_revision": entry["revision"], "caption": "Observation après arrosage"}


async def seed_climate(store, rows):
    """Insère des agrégats horaires déjà constitués, sans passer par une acquisition."""
    def work():
        with store._db:
            store._db.executemany("INSERT OR REPLACE INTO climate_hours"
                " (sensor,hour,label,unit,minimum,maximum,total,valid_count,observed_count) VALUES (?,?,?,?,?,?,?,?,?)", rows)
        return len(rows)
    store._seed_climate = work
    return await store.call("seed_climate")


def hour_rows(sensor, first, count, *, minimum=5.0, maximum=5.0, total=300.0, valid=60, observed=60):
    return [(sensor, first + 3600 * n, "Température de l’air", "°C", minimum, maximum, total, valid, observed) for n in range(count)]


def test_photos_formats_bornes_et_suppression_metadonnees():
    jpeg, width, height = image_bytes(photo_bytes((2000, 1000)))
    assert (width, height) == (1600, 800)
    with Image.open(io.BytesIO(jpeg)) as picture:
        assert picture.format == "JPEG" and not picture.getexif()
    for raw in (b"<svg></svg>", b"", b"a"*(MAX_PHOTO_BYTES+1), photo_bytes()[:80]):
        with pytest.raises(CultureError):
            image_bytes(raw)
    output = io.BytesIO()
    Image.new("RGB", (8193, 1)).save(output, "PNG")
    with pytest.raises(CultureError):
        image_bytes(output.getvalue())
    output = io.BytesIO()
    Image.new("RGB", (4, 4)).save(output, "WEBP", save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")], duration=100)
    with pytest.raises(CultureError):
        image_bytes(output.getvalue())


async def test_photos_idempotence_limite_evenement_et_sauvegarde(cultures, tmp_path):
    command = await photo_command(cultures)
    raw = photo_bytes()
    saved = await cultures.call("media_add", command, raw)
    assert await cultures.call("media_add", command, raw) == saved
    assert (await cultures.call("media_storage"))["count"] == 1
    assert len((await cultures.call("detail", command["subject_id"]))["photos"]) == 1
    with pytest.raises(CultureConflict):
        await cultures.call("media_add", {**command, "caption": "Autre légende"}, raw)
    for _ in range(3):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    with pytest.raises(CultureError, match="Quatre"):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    bundle = Path(await cultures.call("bundle"))
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["files"]) == 5
    dest = tmp_path / "restore"
    restore_bundle(bundle, dest)
    # Exerce aussi l'outil opérateur réel sur une seconde copie entièrement isolée.
    cli_dest = tmp_path / "restore-cli"
    restored = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "restore-cultures.py"),
         "--bundle", str(bundle), str(cli_dest)],
        capture_output=True, text=True, timeout=30,
    )
    assert restored.returncode == 0, restored.stderr
    assert (cli_dest / "cultures.sqlite3").is_file()
    assert len(list((cli_dest / "culture_media").glob("*.jpg"))) == 4
    assert not (cli_dest / ".restauration-incomplete").exists()
    other = CultureStore(dest / "cultures.sqlite3", now=lambda: NOW)
    try:
        assert (await other.call("export"))["tables"] == (await cultures.call("export"))["tables"]
        assert await other.call("media_get", saved["id"]) == await cultures.call("media_get", saved["id"])
    finally:
        await other.close()
    with pytest.raises(CultureUnavailable):
        restore_bundle(bundle, dest)
    db_only = tmp_path / "database-only.sqlite3"
    db_only.write_bytes(await cultures.call("backup"))
    with pytest.raises(CultureUnavailable, match="photos"):
        restore_copy(db_only, tmp_path / "incomplete.sqlite3")
    bundle.unlink()


async def test_photo_refus_disque_et_base_sans_succes_partiel(cultures, monkeypatch):
    command = await photo_command(cultures)
    import utils.culture_media_store as module
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 10**20)
    with pytest.raises(CultureError, match="disque"):
        await cultures.call("media_add", command, photo_bytes())
    assert (await cultures.call("media_storage"))["count"] == 0
    assert not list(cultures.media_path.glob("*.jpg"))
    monkeypatch.setattr(module, "MIN_FREE_BYTES", 0)
    def reject():
        cultures._db.execute("CREATE TRIGGER fail_photo BEFORE INSERT ON culture_media BEGIN SELECT RAISE(ABORT,'disque'); END")
    cultures._reject_photo = reject
    await cultures.call("reject_photo")
    with pytest.raises(CultureUnavailable):
        await cultures.call("media_add", command, photo_bytes())
    assert not list(cultures.media_path.glob("*.jpg"))
    assert (await cultures.call("media_storage"))["count"] == 0


async def test_bundle_altere_ou_chemin_malveillant_refuse(cultures, tmp_path):
    command = await photo_command(cultures)
    await cultures.call("media_add", command, photo_bytes())
    bundle = Path(await cultures.call("bundle"))
    with zipfile.ZipFile(bundle) as source:
        for kind in ("bytes", "path", "missing"):
            path = tmp_path / f"bad-{kind}.zip"
            with zipfile.ZipFile(path, "w") as target:
                for info in source.infolist():
                    raw = source.read(info)
                    if info.filename.endswith(".jpg"):
                        if kind == "missing":
                            continue
                        if kind == "bytes":
                            raw = b"invalid"
                    target.writestr(info.filename, raw)
                if kind == "path":
                    target.writestr("../outside", "interdit")
            with pytest.raises(CultureUnavailable):
                restore_bundle(path, tmp_path / f"destination-{kind}")
            assert not (tmp_path / f"destination-{kind}").exists()
    assert not (tmp_path / "outside").exists()
    bundle.unlink()


async def test_rappels_et_recurrence_pas_de_double_accomplissement(cultures):
    lot = await cultures.call("mutate", create())
    command = reminder(lot["subject_id"])
    saved = await cultures.call("cycle_mutate", command)
    assert await cultures.call("cycle_mutate", command) == saved
    action = {"operation": "reminder_action", "id": saved["id"], "version": 1, "request_id": str(uuid.uuid4()), "action": "postponed", "due_date": "2026-09-10", "note": "Report explicite"}
    updated = await cultures.call("cycle_mutate", action)
    data = await cultures.call("cycle_data", [lot["subject_id"]])
    assert data["reminders"][0]["state"] == "postponed"
    assert data["reminders"][0]["revisions"][0]["due_date"] == "2026-09-08"
    done = {**action, "version": updated["version"], "request_id": str(uuid.uuid4()), "action": "done"}
    result = await cultures.call("cycle_mutate", done)
    assert await cultures.call("cycle_mutate", done) == result
    rows = (await cultures.call("cycle_data"))["reminders"]
    assert len(rows) == 2
    following = next(r for r in rows if r["state"] == "planned")
    assert following["due_date"] == "2026-09-09" and following["parent_id"] == saved["id"]
    with pytest.raises(CultureConflict):
        await cultures.call("cycle_mutate", {**action, "request_id": str(uuid.uuid4())})
    await cultures.call("cycle_mutate", {"operation": "reminder_action", "request_id": str(uuid.uuid4()), "id": following["id"], "version": 1, "action": "cancelled"})
    assert len((await cultures.call("cycle_data"))["reminders"]) == 2
    await cultures.close()
    assert len((await cultures.call("cycle_data"))["reminders"]) == 2


async def test_climat_qualite_couverture_et_aucune_acquisition(cultures):
    class Sensors:
        reads = 0
        snapshots = 0
        def snapshot(self):
            self.snapshots += 1
            return {"BME280T": {"value": 20, "status": "normal", "enabled": True}}
        def read(self):
            self.reads += 1
            raise AssertionError("Aucune acquisition supplémentaire")
    sensors = Sensors()
    service = CultureService(cultures, sensors)
    service.metadata = {"BME280T": ("Température de l’air", "°C")}
    await service.sample_once()
    await service.sample_once()
    assert sensors.reads == 0 and sensors.snapshots == 2
    lot = await cultures.call("mutate", create())
    data = await cultures.call("cycle_data", [lot["subject_id"]])
    summary = data["summaries"][0]
    hour = summary["climate_detail"]["rows"][0]
    assert hour["valid_count"] == 1 and hour["coverage"] == 1/60
    # La synthèse couvre tout le cycle : les journées sans agrégat restent des lacunes.
    assert summary["climate"]["granularity_label"] == "jour" and summary["climate"]["bucket_count"] == 39
    assert summary["climate"]["gap_count"] == 38 and summary["climate"]["gaps_shown"]
    assert summary["climate"]["points"][-1]["span_hours"] == 16
    cultures.now = lambda: NOW + timedelta(minutes=1)
    await cultures.call("climate_sample", {"BME280T": {"value": 0, "status": "normal"}}, service.metadata)
    cultures.now = lambda: NOW + timedelta(minutes=2)
    await cultures.call("climate_sample", {"BME280T": {"value": 99, "status": "degraded"}}, service.metadata)
    summary = (await cultures.call("cycle_data", [lot["subject_id"]]))["summaries"][0]
    point = summary["climate_detail"]["rows"][0]
    assert (point["minimum"], point["maximum"], point["mean"], point["observed_count"], point["valid_count"]) == (0, 20, 10, 3, 2)
    bucket = summary["climate"]["points"][-1]
    assert (bucket["minimum"], bucket["maximum"], bucket["mean"], bucket["observed_count"], bucket["valid_count"]) == (0, 20, 10, 3, 2)
    # Une marche arrière ne recompte pas les minutes déjà vues, même après redémarrage.
    await cultures.close()
    cultures.now = lambda: NOW
    await service.sample_once()
    assert (await cultures.call("cycle_data", [lot["subject_id"]]))["summaries"][0]["climate_detail"]["rows"][0]["observed_count"] == 3
    cultures.reliable = lambda: False
    assert (await service.sample_once())["saved"] is False


async def test_cycle_long_synthese_bornee_moyennes_ponderees_et_detail_pagine(cultures):
    lot = await cultures.call("mutate", create(origin_at="2026-03-08", space_at="2026-03-08", stage_at="2026-03-08"))
    day = int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp())
    dst = int(datetime(2026, 3, 29, tzinfo=timezone.utc).timestamp())
    # Couvertures inégales, zéro réel, heure observée sans valeur fiable puis interruption.
    rows = [("BME280T", day, "Température de l’air", "°C", 20.0, 20.0, 1200.0, 60, 60),
            ("BME280T", day + 3600, "Température de l’air", "°C", 0.0, 0.0, 0.0, 1, 30),
            ("BME280T", day + 7200, "Température de l’air", "°C", None, None, 0.0, 0, 45)]
    # Le passage à l'heure d'été du 29 mars ne déplace aucun seau : la clé reste un epoch UTC.
    rows += hour_rows("BME280T", dst, 70)
    assert await seed_climate(cultures, rows) == 73
    summary = (await cultures.call("cycle_data", [lot["subject_id"]]))["summaries"][0]
    climate = summary["climate"]
    assert (climate["granularity_label"], climate["bucket_count"], climate["sensor_count"]) == ("jour", 185, 1)
    assert len(climate["points"]) == 185 and climate["gap_count"] == 181 and climate["gaps_shown"] and not climate["truncated"]
    points = {point["hour"]: point for point in climate["points"]}
    bucket = points[day]
    # Moyenne pondérée par les effectifs : une moyenne des moyennes horaires donnerait 10.
    assert bucket["mean"] == pytest.approx(1200 / 61) and bucket["mean"] != 10
    assert (bucket["minimum"], bucket["maximum"], bucket["valid_count"], bucket["observed_count"]) == (0.0, 20.0, 61, 135)
    assert (bucket["hours"], bucket["span_hours"]) == (3, 24)
    assert bucket["coverage"] == pytest.approx(61 / 1440) and bucket["hour_coverage"] == pytest.approx(3 / 24)
    absent = points[day + 86400]
    assert absent["missing"] and absent["mean"] is None and absent["minimum"] is None and absent["valid_count"] == 0
    assert points[dst]["span_hours"] == 24 and points[dst]["mean"] == 5.0 and points[dst]["valid_count"] == 1440
    assert points[dst + 86400]["hour"] - points[dst]["hour"] == 86400 and points[dst + 86400]["span_hours"] == 24
    ordered = sorted(points)
    assert points[ordered[0]]["span_hours"] == 1 and points[ordered[-1]]["span_hours"] == 16
    detail = summary["climate_detail"]
    assert (detail["total"], detail["offset"], detail["previous"], detail["next"]) == (73, 0, None, 60)
    assert [row["hour"] for row in detail["rows"]] == sorted(row[1] for row in rows)[:60]
    empty = next(row for row in (await cultures.call("cycle_data", [lot["subject_id"]], 0, None, 60))["summaries"][0]["climate_detail"]["rows"] if row["hour"] == day + 7200)
    assert empty["mean"] is None and empty["coverage"] == 0 and empty["observed_count"] == 45
    later = (await cultures.call("cycle_data", [lot["subject_id"]], 0, None, 60))["summaries"][0]["climate_detail"]
    assert (later["offset"], len(later["rows"]), later["previous"], later["next"]) == (60, 13, 0, None)
    jump = (await cultures.call("cycle_data", [lot["subject_id"]], 0, None, 0, day))["summaries"][0]["climate_detail"]
    assert jump["offset"] == 60 and jump["rows"][0]["hour"] == dst + 3600 * 60
    # Un décalage hors bornes retombe sur la dernière page ; aucun agrégat n'est perdu en base.
    edge = (await cultures.call("cycle_data", [lot["subject_id"]], 0, None, 10 ** 6))["summaries"][0]["climate_detail"]
    assert edge["offset"] == 60 and edge["total"] == 73


async def test_comparaison_de_quatre_cycles_bornee_et_granularite_explicite(cultures):
    lots = [await cultures.call("mutate", create(f"Lot {index}", origin_at="2026-03-08", space_at="2026-03-08", stage_at="2026-03-08")) for index in range(4)]
    await seed_climate(cultures, hour_rows("BME280T", int(datetime(2026, 4, 1, tzinfo=timezone.utc).timestamp()), 500))
    data = await cultures.call("cycle_data", [lot["subject_id"] for lot in lots])
    assert len(data["summaries"]) == 4
    for summary in data["summaries"]:
        climate = summary["climate"]
        assert climate["granularity_label"] == "jour" and climate["bucket_count"] <= 200
        assert len(climate["points"]) == climate["bucket_count"] and summary["climate_detail"] is None
    with pytest.raises(CultureError):
        await cultures.call("cycle_data", [lot["subject_id"] for lot in lots] + [lots[0]["subject_id"]])


async def test_formulaire_de_comparaison_reconduit_sa_page_et_sort_le_filtre(web_context):
    """Deux défauts du sélecteur, visibles dans le seul balisage (R1.2 b et c).

    (b) Le formulaire reconduisait `q` mais pas `selection_offset` : valider une coche depuis
    la page 2 des choix renvoyait page 1. (c) Le champ « Filtrer les choix affichés » n'a pas
    de `name` — il ne fait que masquer des cases dans le navigateur — mais il était **dans**
    le formulaire, donc la touche Entrée y déclenchait « Afficher les cycles ».
    """
    client, server, *_ = web_context
    store = server.cultures.store
    for index in range(44):
        await store.call("mutate", create(f"Mère {index:02}", "mother"))

    response = await client.get("/cultures/cycles?selection_offset=10000000")
    assert response.status == 200
    html = await response.text()

    form = html.index('<form method="get" data-offline-filter class="culture-form">')
    end = html.index("</form>", form)
    # Le décalage normalisé par le magasin, pas celui de la requête, est reconduit.
    assert '<input type="hidden" name="selection_offset" value="40">' in html[form:end]
    # Le champ de filtre est hors du formulaire, mais dans la zone lue par le script.
    assert "data-comparison-filter" in html and html.index("data-comparison-filter") < form
    assert "data-comparison-filter" not in html[form:end]
    zone = html.index("data-comparison-selection")
    assert zone < html.index("data-comparison-filter")
    # Les bornes viennent de la réponse : plus de 4 ni de 40 recopiés dans le gabarit.
    assert 'data-comparison-max="4"' in html
    assert "40 résultats au plus par page de choix" in html
    choices = html.index('<fieldset class="culture-comparison-choices">')
    fieldset = html[choices:html.index("</fieldset>", choices)]
    # Dernière page réelle des 44 cultures : les quatre restantes, pas une page vide.
    assert "Mère 43" in fieldset and "Mère 39" not in fieldset


async def test_taille_des_reponses_de_cycle_sous_le_plafond_du_cache_pwa(web_context):
    client, server, *_ = web_context
    store = server.cultures.store
    # Le magasin du serveur de test a une horloge **figée** (`CULTURE_NOW`) : c'est elle qui
    # borne la fin du cycle. Semer à partir de l'heure réelle faisait donc dépendre du moment
    # d'exécution le nombre d'agrégats compris entre le début du cycle et cette fin — les
    # heures postérieures à `CULTURE_NOW` tombaient hors bornes et le total variait
    # (11 862 au lieu de 12 000). Le semis part de la même horloge que le carnet.
    now = CULTURE_NOW.replace(minute=0, second=0, microsecond=0)
    origin = (now - timedelta(hours=4000)).date().isoformat()
    lot = await store.call("mutate", create(origin_at=origin, space_at=origin, stage_at=origin))
    base = int(now.timestamp()) // 3600 * 3600 - 3600 * 3999
    rows = [row for sensor in ("BME280T", "BME280H", "DS18B20") for row in hour_rows(sensor, base, 4000)]
    assert await seed_climate(store, rows) == 12000
    page = await client.get("/cultures/cycles?subject=" + lot["subject_id"])
    body = await page.read()
    assert page.status == 200 and len(body) < 1048576
    api = await client.get("/api/v1/cultures/cycles?subject=" + lot["subject_id"])
    payload = await api.read()
    assert api.status == 200 and len(payload) < 1048576
    summary = json.loads(payload)["summaries"][0]
    assert summary["climate"]["granularity_label"] == "jour" and summary["climate"]["sensor_count"] == 3
    assert summary["climate"]["bucket_count"] <= 200 and len(summary["climate"]["points"]) <= 600
    assert summary["climate_detail"]["total"] == 12000 and len(summary["climate_detail"]["rows"]) == 60
    detail = await client.get(f"/cultures/cycles?subject={lot['subject_id']}&climate_offset=11940")
    assert detail.status == 200 and len(await detail.read()) < 1048576
    assert (await client.get(f"/cultures/cycles?subject={lot['subject_id']}&climate_offset=-1")).status == 400


async def test_checklist_declarative_bilan_et_origines(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    original = (await cultures.call("detail", lot["subject_id"]))["subject"]
    await cultures.call("cycle_mutate", {"operation": "checklist", "request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"], "version": lot["version"], "effective_at": "2026-09-07", "checks": {"lighting": True, "pump": False, "ventilation": True}})
    assert (await cultures.call("detail", lot["subject_id"]))["subject"] == original
    lot = await event(cultures, lot, "harvest", "2026-09-01")
    await event(cultures, lot, "finish", "2026-09-06", {"weight_g": 10, "lessons": "Observation pour le prochain cycle", "origin_weights": [{"origin_id": original["origins"][0]["id"], "weight_g": 8}]})
    summary = (await cultures.call("cycle_data", [lot["subject_id"]]))["summaries"][0]
    assert summary["subject"]["balance"]["lessons"].startswith("Observation")
    with pytest.raises(CultureError):
        event_payload("finish", {"weight_g": 5, "origin_weights": [{"origin_id": "a", "weight_g": 8}]})


async def test_routes_photo_rappel_limites_et_pas_effet_controle(web_context):
    client, server, config, sensors, supervisor = web_context
    before = config.current.to_json()
    command = await photo_command(server.cultures.store)
    metadata = quote(json.dumps(command))
    headers = {"X-CSRF-Token": CSRF_TOKEN, "Content-Type": "application/octet-stream", "X-Culture-Metadata": metadata}
    assert (await client.post("/api/v1/cultures/photos", data=photo_bytes(), headers={**headers, "X-CSRF-Token": "bad"})).status == 403
    assert (await client.post("/api/v1/cultures/photos", data=photo_bytes(), headers={**headers, "Origin": "http://evil.example"})).status == 403
    response = await client.post("/api/v1/cultures/photos", data=photo_bytes(), headers=headers)
    assert response.status == 200, await response.text()
    saved = await response.json()
    photo = await client.get("/cultures/photos/" + saved["id"])
    assert photo.status == 200 and photo.content_type == "image/jpeg" and photo.headers["Cache-Control"] == "no-store"
    assert (await client.post("/api/v1/cultures/photos", data=b"a"*(MAX_PHOTO_BYTES+1), headers=headers)).status == 413
    assert (await client.post("/api/v1/cultures/cycles", json={"note": "x"*70000}, headers={"X-CSRF-Token": CSRF_TOKEN})).status == 413
    response = await client.get("/cultures/cycles?subject=" + command["subject_id"])
    assert response.status == 200, await response.text()
    response = await client.get("/cultures/" + command["subject_id"])
    assert response.status == 200 and 'data-photo-form' in await response.text()
    response = await client.get("/api/v1/cultures/bundle")
    assert response.status == 200 and response.headers["Cache-Control"] == "no-store"
    with zipfile.ZipFile(io.BytesIO(await response.read())) as archive:
        assert "manifest.json" in archive.namelist()
    assert config.current.to_json() == before and sensors.reconfigured == 0
    assert (await client.get("/health/ready")).status == 200


async def test_migration_v2_conserve_releves_et_sauvegarde(cultures):
    from tests.test_culture_schema_v4 import strip_v4
    from tests.test_culture_solutions import entry
    saved = await cultures.call("solution_mutate", entry())
    path = cultures.path
    await cultures.close()
    with sqlite3.connect(path) as db:
        strip_v4(db)
        for table in reversed(CYCLE_TABLES):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=2")
    assert (await cultures.call("solution_data"))["items"][0]["id"] == saved["id"]
    with sqlite3.connect(path.with_name(path.name + ".before-v3.sqlite3")) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert (await cultures.call("cycle_data"))["reminders"] == []


async def test_panne_synthese_n_interrompt_pas_le_controle(cultures, monkeypatch):
    import asyncio
    import controllers.CultureService as module
    from tests.helpers import wait_until
    from tests.test_supervisor import stop_supervisor
    from utils.supervisor import TaskSupervisor, beat
    class Sensors:
        def snapshot(self):
            return {}
    async def broken(*_args):
        raise CultureUnavailable("stockage indisponible")
    monkeypatch.setattr(cultures, "call", broken)
    service = CultureService(cultures, Sensors())
    async def control():
        beat()
        await asyncio.Event().wait()
    supervisor = TaskSupervisor()
    supervisor.register("control", control, max_silence=None, gates_watchdog=True)
    auxiliary = supervisor.register("cultures", service.run, max_silence=300, gates_watchdog=False)
    supervisor.start()
    try:
        await wait_until(lambda: service.logger.failing)
        assert supervisor.control_healthy()
        assert auxiliary.restarts == 0
    finally:
        await stop_supervisor(supervisor)


async def test_saisies_jalon3_et_horloge_rejetees_atomiquement(cultures):
    for command in (reminder("absent"), reminder("reservoir_2", interval_days=-1), reminder("reservoir_2", due_date="pas-une-date"), {"operation": "inconnue", "request_id": str(uuid.uuid4())}):
        with pytest.raises(CultureError):
            await cultures.call("cycle_mutate", command)
    assert (await cultures.call("cycle_data"))["reminders"] == []
    cultures.reliable = lambda: False
    with pytest.raises(CultureError, match="Horloge"):
        await cultures.call("cycle_mutate", reminder("reservoir_2"))
    assert (await cultures.call("cycle_mutate", reminder("reservoir_2", confirm_date=True)))["saved"]


async def test_date_retrospective_photo_ancienne_reste_consultable(cultures):
    command = await photo_command(cultures)
    saved = await cultures.call("media_add", command, photo_bytes())
    lot = (await cultures.call("detail", command["subject_id"]))["subject"]
    result = {"subject_id": lot["id"], "version": lot["version"]}
    for i in range(41):
        result = await event(cultures, result, "note", "2026-08-02", {"note": f"Observation {i}"})
    recent = await cultures.call("detail", lot["id"], 0)
    older = await cultures.call("detail", lot["id"], 40)
    assert not recent["photos"] and older["photos"][0]["id"] == saved["id"]


async def test_verification_le_jour_du_changement_horodate(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    lot = await event(cultures, lot, "stage", "2026-09-06T14:00:00+00:00", {"stage": "floraison"}, precision="instant")
    command = {"operation": "checklist", "request_id": str(uuid.uuid4()),
               "subject_id": lot["subject_id"], "version": lot["version"],
               "effective_at": "2026-09-06", "checks": {"lighting": True, "pump": True, "ventilation": True}}
    assert (await cultures.call("cycle_mutate", command))["saved"]
    with pytest.raises(CultureError, match="précède"):
        await cultures.call("cycle_mutate", {**command, "request_id": str(uuid.uuid4()), "effective_at": "2026-09-05"})


async def test_galerie_comparaison_exclut_les_cultures_non_selectionnees(cultures):
    identifiers = []
    photos = []
    for name in ("Mère A", "Mère B", "Mère hors comparaison"):
        result = await cultures.call("mutate", create(name, "mother"))
        identifier = result["subject_id"]
        identifiers.append(identifier)
        detail = await cultures.call("detail", identifier)
        source = detail["events"][0]
        photos.append(await cultures.call("media_add", {"request_id": str(uuid.uuid4()),
            "subject_id": identifier, "event_id": source["id"], "event_revision": source["revision"],
            "caption": name}, photo_bytes()))
    data = await cultures.call("cycle_data", identifiers[:2])
    assert {photo["subject_id"] for photo in data["media"]} == set(identifiers[:2])
    assert len((await cultures.call("cycle_data"))["media"]) == 3


async def test_rappels_du_jour_separes_du_reste_et_nommes_rappel_du_carnet(web_context):
    """R2.6 : « Rappels du jour » ne montre que les échéances atteintes.

    Le titre annonçait le jour et la section listait la page entière des rappels, toutes
    échéances confondues. Le partage réutilise la règle pure `reminder_buckets` — celle du
    bloc « Aujourd'hui » de `/cultures` — sans lecture ni projection nouvelle. Le carnet
    n'émet pas d'alarme : chaque carte le dit, et ces deux sections n'écrivent jamais ce mot.
    """
    client, server, *_ = web_context
    store = server.cultures.store
    lot = await store.call("mutate", create("Lot des rappels"))
    today = (await store.call("cycle_data"))["today"]
    for titre, echeance in (("Rappel en retard", "2026-09-01"), ("Rappel du jour", today),
                            ("Rappel à venir", "2026-09-30")):
        await store.call("cycle_mutate", {**reminder(lot["subject_id"], due_date=echeance,
                                                     interval_days=0), "title": titre})
    html = await (await client.get("/cultures/cycles")).text()

    debut = html.index('id="rappels"')
    milieu = html.index('id="rappels-suivants"')
    fin = html.index('id="cycle-view-comparer"')
    du_jour, autres = html[debut:milieu], html[milieu:fin]
    assert "Rappel en retard" in du_jour and "Rappel du jour" in du_jour
    assert "Rappel à venir" not in du_jour
    assert "Rappel à venir" in autres
    assert "Rappel en retard" not in autres and "Rappel du jour" not in autres
    # Un libellé par carte, et jamais le mot « alarme » dans ces deux sections.
    assert du_jour.count("Rappel du carnet ·") == 2 and autres.count("Rappel du carnet ·") == 1
    assert "alarme" not in (du_jour + autres).lower()
    # R5.1/R5.3 : « Fait » et « Reporter » sont les gestes les plus fréquents de la page ;
    # leur cible tactile fait 44 px dans les deux dimensions, et l'échéance est tabulaire.
    assert du_jour.count('class="button action-link" type="submit" name="action" value="done"') == 2
    assert du_jour.count('class="button button-secondary action-link" type="submit" name="action" value="postponed"') == 2
    assert du_jour.count('· échéance <span class="num">') == 2
    # La pagination reste sur la liste du dessous ; le total porte sur tous les rappels.
    assert "Pagination des rappels" in autres and "Pagination des rappels" not in du_jour
    assert '<span class="num">40</span> par page sur <span class="num">3</span> au total' in autres


async def test_vue_des_cycles_bornee_et_onglets_rendus_en_liens(web_context):
    """R2.6 : `view` validé côté serveur, et un balisage honnête pour des liens qui rechargent.

    Un `role="tablist"` sur le `<nav>` écrasait le repère de navigation et promettait un
    panneau échangé sur place ; ce sont des liens qui rechargent la page, donc une liste de
    liens et `aria-current="page"`. L'index des copies hors ligne et la sauvegarde passent
    après les rappels : à 390 × 844 c'est la prochaine action qui doit tenir dans l'écran.
    """
    client, *_ = web_context
    faire = await (await client.get("/cultures/cycles")).text()
    assert 'role="tab"' not in faire and 'role="tablist"' not in faire
    assert 'role="tabpanel"' not in faire and "aria-selected" not in faire
    assert '<a class="action-link" href="?view=faire" aria-current="page">À faire</a>' in faire
    assert '<a class="action-link" href="?view=comparer">Comparer</a>' in faire
    assert '<section id="cycle-view-faire" aria-label="À faire">' in faire
    assert '<section id="cycle-view-comparer" aria-label="Comparer" hidden>' in faire

    comparer = await (await client.get("/cultures/cycles?view=comparer")).text()
    assert '<section id="cycle-view-faire" aria-label="À faire" hidden>' in comparer
    assert '<section id="cycle-view-comparer" aria-label="Comparer">' in comparer
    assert '<a class="action-link" href="?view=comparer" aria-current="page">Comparer</a>' in comparer

    # Une vue inconnue retombe sur « À faire » plutôt que de masquer les deux panneaux.
    inconnue = await (await client.get("/cultures/cycles?view=inexistante")).text()
    assert '<section id="cycle-view-faire" aria-label="À faire">' in inconnue
    assert '<section id="cycle-view-comparer" aria-label="Comparer" hidden>' in inconnue

    # Ordre de la page et nav locale alignée sur le libellé et l'ancre de `/app`.
    assert faire.index('id="rappels"') < faire.index('id="copies"') < faire.index('id="sauvegarde"')
    assert '<a href="#sauvegarde">Sauvegarde et carnet de cultures</a>' in faire
    # R5.1/R5.3 : les actions autonomes fréquentes portent `.action-link` (44 px dans les
    # deux dimensions) et les chiffres `.num`.
    assert '<a class="button action-link" href="/api/v1/cultures/bundle">' in faire
    assert '<span class="num">' in faire
    assert "<h2>Sauvegarde et carnet de cultures</h2>" in faire
