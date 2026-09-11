"""Plages cibles pH/EC (lot E) : bornes, fenêtres, résolution du contexte et durabilité."""

import re
import sqlite3
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_targets import bounds, resolve_targets, target_bands, target_text, validate_target_windows
from tests.test_cultures import create, cultures, event
from tests.test_http_server import CSRF_TOKEN, web_context
from utils.culture_backup import restore_copy


def target(**extra):
    return {"operation": "target", "request_id": str(uuid.uuid4()), "target": "reservoir_2",
            "start_at": "2026-08-01", "ph_min": "5,8", "ph_max": "6,4", **extra}


def texte(html):
    """Texte visible d'une page rendue.

    Le filtre `nombre` enveloppe chaque valeur dans un `<span class="num">` : un `in` sur
    le HTML brut ne verrait donc pas « pH 5,80 à 6,40 », alors que c'est bien ce que
    l'opérateur lit. Les tests portent sur ce texte-là.
    """
    return re.sub(r"<[^>]+>", "", html)


def action(saved, kind, **extra):
    return {"operation": "target_action", "request_id": str(uuid.uuid4()), "id": saved["id"],
            "version": saved["version"], "action": kind, **extra}


def window(identifier, start, end=None, **extra):
    return {"id": identifier, "revision": 1, "scope": "reservoir", "subject_id": None,
            "reservoir_id": "reservoir_2", "ph_min": 5.8, "ph_max": 6.4, "ec_min": None, "ec_max": None,
            "start_sort_at": start, "end_sort_at": end, "cancelled": 0, **extra}


# --- Règles pures ----------------------------------------------------------


@pytest.mark.parametrize("raw", [
    {},
    {"ph_min": "NaN"},
    {"ec_min": float("inf")},
    {"ph_min": 6.5, "ph_max": 6.0},
    {"ec_min": 2, "ec_max": 1},
    {"ph_min": 6.0, "ec_unit": "ppm"},
    {"ph_min": 15},
])
def test_bornes_refusees(raw):
    with pytest.raises(CultureError):
        bounds(raw)


def test_bornes_decimales_unites_et_absences():
    values = bounds({"ph_min": "5,8", "ec_max": "1234,5", "ec_unit": "µS/cm"})
    assert values == {"ph_min": 5.8, "ph_max": None, "ec_min": None, "ec_max": 1.2345}
    # Une plage EC seule reste une plage EC seule : rien n'est complété côté pH.
    assert bounds({"ec_min": 1.2})["ph_min"] is None
    assert target_text({"ph_min": 5.8, "ph_max": None}, "ph") == "≥ 5.8"
    assert target_text({"ph_min": None, "ph_max": 6.4}, "ph") == "≤ 6.4"
    assert target_text(None, "ph") == "" and target_text({"ec_min": None, "ec_max": None}, "ec") == ""


def test_fenetres_chevauchantes_refusees_et_annulees_ignorees():
    validate_target_windows([window("a", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"),
                             window("b", "2026-02-01T00:00:00+00:00")])
    with pytest.raises(CultureError, match="chevauchent"):
        validate_target_windows([window("a", "2026-01-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00"),
                                 window("b", "2026-02-01T00:00:00+00:00")])
    # Une plage annulée ne bloque plus la fenêtre qu'elle occupait.
    validate_target_windows([window("a", "2026-01-01T00:00:00+00:00", "2026-03-01T00:00:00+00:00", cancelled=1),
                             window("b", "2026-02-01T00:00:00+00:00")])
    with pytest.raises(CultureError, match="suivre son début"):
        validate_target_windows([window("a", "2026-03-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00")])
    with pytest.raises(CultureError, match="aucune borne"):
        validate_target_windows([{**window("a", "2026-01-01T00:00:00+00:00"), "ph_min": None, "ph_max": None}])


def test_resolution_priorite_stricte_et_absence_de_retroactivite():
    direct = window("direct", "2026-02-01T00:00:00+00:00", scope="subject", subject_id="lot", reservoir_id=None, ph_min=6.0, ph_max=6.1)
    fed = window("fed", "2026-01-01T00:00:00+00:00", scope="subject", subject_id="autre", reservoir_id=None, ph_min=5.0, ph_max=5.1)
    reservoir = window("res", "2026-01-01T00:00:00+00:00", ec_min=1.0, ec_max=2.0)
    targets = [direct, fed, reservoir]
    entry = {"sort_at": "2026-03-01T00:00:00+00:00", "targets": ["lot"], "fed_subjects": ["autre"],
             "reservoir_id": "reservoir_2"}
    resolved = resolve_targets(entry, targets)
    # Priorité stricte : la cible directe gagne entièrement, aucune EC empruntée au réservoir.
    assert resolved["source"] == "subject" and resolved["ph_min"] == 6.0 and resolved["ec_min"] is None
    fed_only = resolve_targets({**entry, "targets": []}, targets)
    assert fed_only["source"] == "fed_subject" and fed_only["ph_min"] == 5.0
    reservoir_only = resolve_targets({**entry, "targets": [], "fed_subjects": []}, targets)
    assert reservoir_only["source"] == "reservoir" and reservoir_only["ec_max"] == 2.0
    # Aucune rétroactivité : une mesure antérieure à toute plage n'a pas de cible.
    assert resolve_targets({**entry, "sort_at": "2025-12-01T00:00:00+00:00"}, targets) is None
    # Une plage close ne s'applique plus après sa fin.
    closed = [window("res", "2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00")]
    assert resolve_targets({**entry, "targets": [], "fed_subjects": []}, closed) is None


def test_bandes_ne_franchissent_pas_une_periode_sans_cible():
    plage = {"id": "a", "ph_min": 5.8, "ph_max": 6.4, "ec_min": None, "ec_max": None,
             "source": "reservoir", "label": ""}
    bands = target_bands([{"at": "1", "target": plage}, {"at": "2", "target": None},
                          {"at": "3", "target": plage}])
    assert [(b["start"], b["end"]) for b in bands] == [("1", "1"), ("3", "3")]


# --- Magasin ---------------------------------------------------------------


async def test_saisie_correction_cloture_annulation_et_historique(cultures):
    saved = await cultures.call("target_mutate", target(label="Végétatif", note="Repère"))
    assert saved == {"saved": True, "id": saved["id"], "version": 1}
    rows = (await cultures.call("targets"))["items"]
    assert len(rows) == 1 and rows[0]["ph_min"] == 5.8 and rows[0]["ec_min"] is None
    assert rows[0]["scope"] == "reservoir" and rows[0]["subject_id"] is None and rows[0]["cancelled"] == 0
    corrected = await cultures.call("target_mutate", target(id=saved["id"], version=1, ph_max="6,2", reason="Erreur de saisie"))
    assert corrected["version"] == 2
    with pytest.raises(CultureConflict):
        await cultures.call("target_mutate", target(id=saved["id"], version=1, ph_max="6,3"))
    closed = await cultures.call("target_mutate", action(corrected, "end", end_at="2026-08-20", reason="Fin de stade"))
    rows = (await cultures.call("targets"))["items"]
    assert rows[0]["end_at"] == "2026-08-20" and rows[0]["ph_max"] == 6.2 and len(rows[0]["revisions"]) == 2
    cancelled = await cultures.call("target_mutate", action(closed, "cancel", reason="Doublon"))
    rows = (await cultures.call("targets"))["items"]
    assert rows[0]["cancelled"] == 1 and rows[0]["reason"] == "Doublon" and cancelled["version"] == 4
    with pytest.raises(CultureError, match="conserve son historique"):
        await cultures.call("target_mutate", target(id=saved["id"], version=4))


async def test_fenetres_refusees_et_idempotence(cultures):
    first = await cultures.call("target_mutate", target())
    command = target()
    with pytest.raises(CultureError, match="chevauchent"):
        await cultures.call("target_mutate", command)
    # La transaction refusée n'a rien écrit : la clé reste réutilisable après correction.
    assert len((await cultures.call("targets"))["items"]) == 1
    await cultures.call("target_mutate", action(first, "end", end_at="2026-08-10"))
    saved = await cultures.call("target_mutate", {**command, "start_at": "2026-08-10"})
    assert await cultures.call("target_mutate", {**command, "start_at": "2026-08-10"}) == saved
    with pytest.raises(CultureError, match="suivre le début"):
        await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), target="cuttings_1",
                                                    start_at="2026-08-10", end_at="2026-08-01"))
    with pytest.raises(CultureError, match="Cible"):
        await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), target="inconnu"))
    with pytest.raises(CultureError, match="au moins une borne"):
        await cultures.call("target_mutate", {"operation": "target", "request_id": str(uuid.uuid4()),
                                              "target": "cuttings_1", "start_at": "2026-08-01"})


async def test_deux_periodes_successives_gardent_leurs_cibles(cultures):
    first = await cultures.call("target_mutate", target(ph_min=5.5, ph_max=5.9))
    await cultures.call("target_mutate", action(first, "end", end_at="2026-08-10"))
    second = await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), start_at="2026-08-10",
                                                         ph_min=6.0, ph_max=6.4))
    for day in ("2026-08-05", "2026-08-15"):
        await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
            "kind": "renewal" if day == "2026-08-05" else "reading", "reservoir_id": "reservoir_2",
            "effective_at": day, "ph": 6.1, **({"volume_l": 20} if day == "2026-08-05" else {})})
    data = await cultures.call("solution_data")
    resolved = {entry["effective_at"]: entry["target"] for entry in data["items"]}
    assert resolved["2026-08-05"]["ph_max"] == 5.9 and resolved["2026-08-15"]["ph_max"] == 6.4
    # Corriger la seconde plage ne déplace pas la cible de la première période.
    await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), id=second["id"], version=1,
                                                start_at="2026-08-10", ph_min=6.1, ph_max=6.6))
    data = await cultures.call("solution_data")
    resolved = {entry["effective_at"]: entry["target"] for entry in data["items"]}
    assert resolved["2026-08-05"]["ph_max"] == 5.9 and resolved["2026-08-15"]["ph_max"] == 6.6
    assert data["chart_targets"] and all(band["start"] <= band["end"] for band in data["chart_targets"])
    assert {band["id"] for band in data["chart_targets"]} == {first["id"], second["id"]}


async def test_periode_sans_cible_reste_sans_cible_et_csv_vide(cultures):
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-08-01", "volume_l": 20, "ph": 6.0})
    data = await cultures.call("solution_data")
    assert data["items"][0]["target"] is None and data["chart_targets"] == []
    lines = (await cultures.call("solution_csv")).splitlines()
    header = lines[0].split(",")
    assert "ph_cible" in header and "ec_cible" in header
    assert lines[1].split(",")[header.index("ph_cible")] == ""
    await cultures.call("target_mutate", target(start_at="2026-08-01", ec_min="1,2", ec_max="1,8",
                                                ph_min=None, ph_max=None))
    lines = (await cultures.call("solution_csv")).splitlines()
    row = lines[1].split(",")
    # Une cible EC seule ne fabrique pas de cible pH.
    assert row[header.index("ec_cible")] == "1.2 à 1.8" and row[header.index("ph_cible")] == ""


async def test_changement_d_espace_ne_melange_pas_les_contextes(cultures):
    mother = await cultures.call("mutate", create("Mère", "mother", origin_at="2026-05-01",
        space_at="2026-05-01", stage_at="2026-05-01"))
    lot = await cultures.call("mutate", create("Lot", origin_type="cutting", space="space_1",
        stage="enracinement", origin_at="2026-06-01", space_at="2026-06-01", stage_at="2026-06-01",
        origins=[{"mother_id": mother["subject_id"], "count": 6}]))
    for reservoir in ("cuttings_1", "reservoir_2"):
        await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
            "kind": "renewal", "reservoir_id": reservoir, "effective_at": "2026-06-01", "volume_l": 20})
    await cultures.call("target_mutate", target(target="cuttings_1", start_at="2026-06-01", ph_min=5.5, ph_max=5.9))
    await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), target="reservoir_2",
                                                start_at="2026-06-01", ph_min=6.0, ph_max=6.4))
    lot = await event(cultures, lot, "move", "2026-08-01", {"space": "space_2"})
    for day, reservoir in (("2026-07-01", "cuttings_1"), ("2026-08-15", "reservoir_2")):
        await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
            "kind": "reading", "reservoir_id": reservoir, "effective_at": day, "ph": 6.0})
    data = await cultures.call("solution_data", {"target": lot["subject_id"]})
    resolved = {entry["effective_at"]: entry["target"] for entry in data["items"] if entry["kind"] == "reading"}
    # Le lot ne reçoit la plage du réservoir 2 qu'à partir de son occupation réelle.
    assert resolved["2026-07-01"]["ph_max"] == 5.9 and resolved["2026-07-01"]["source"] == "reservoir"
    assert resolved["2026-08-15"]["ph_max"] == 6.4 and resolved["2026-08-15"]["source"] == "reservoir"
    # Une plage propre au lot prime sur celle du réservoir qui l'alimente, à partir de sa fenêtre.
    await cultures.call("target_mutate", target(request_id=str(uuid.uuid4()), target=lot["subject_id"],
                                                start_at="2026-08-10", ph_min=6.5, ph_max=6.9))
    data = await cultures.call("solution_data", {"target": lot["subject_id"]})
    resolved = {entry["effective_at"]: entry["target"] for entry in data["items"] if entry["kind"] == "reading"}
    assert resolved["2026-08-15"]["source"] == "fed_subject" and resolved["2026-08-15"]["ph_max"] == 6.9
    assert resolved["2026-07-01"]["ph_max"] == 5.9
    # Un renouvellement ne change pas la plage : elle est indépendante des périodes de solution.
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-08-20", "volume_l": 20, "ph": 6.2})
    data = await cultures.call("solution_data", {"target": lot["subject_id"]})
    assert next(e for e in data["items"] if e["effective_at"] == "2026-08-20")["target"]["ph_max"] == 6.9


async def test_export_restauration_et_validateur(cultures, tmp_path):
    saved = await cultures.call("target_mutate", target(label="Repère"))
    await cultures.call("target_mutate", target(id=saved["id"], version=1, ph_max="6,2", reason="Correction"))
    exported = await cultures.call("export")
    assert len(exported["tables"]["culture_targets"]) == 2 and exported["schema_version"] == 4
    backup = tmp_path / "sauvegarde.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    restore_copy(backup, tmp_path / "copie.sqlite3")
    # Une révision manquante rend la sauvegarde irrecevable plutôt que restaurée en silence.
    broken = sqlite3.connect(backup)
    broken.execute("DELETE FROM culture_targets WHERE revision=1")
    broken.commit()
    broken.close()
    with pytest.raises(Exception, match="Révisions de plage cible"):
        restore_copy(backup, tmp_path / "refusee.sqlite3")


async def test_page_et_api_des_plages_cibles(web_context):
    client, *_ = web_context
    response = await client.get("/cultures/targets")
    body = await response.text()
    assert response.status == 200 and "Plages cibles pH et EC" in body
    assert "Aucune plage cible pour ce filtre" in body
    command = {**target(), "confirm_date": False}
    response = await client.post("/api/v1/cultures/targets", json=command,
                                 headers={"X-CSRF-Token": CSRF_TOKEN})
    assert response.status == 200
    saved = await response.json()
    conflict = await client.post("/api/v1/cultures/targets",
                                 json={**target(id=saved["id"], version=99)},
                                 headers={"X-CSRF-Token": CSRF_TOKEN})
    assert conflict.status == 409
    refused = await client.post("/api/v1/cultures/targets", json={**target(target="inconnu")},
                                headers={"X-CSRF-Token": CSRF_TOKEN})
    assert refused.status == 400
    data = await (await client.get("/api/v1/cultures/targets?scope=reservoir")).json()
    assert data["total"] == 1 and data["items"][0]["label"] == ""
    assert (await client.get("/api/v1/cultures/targets?scope=inconnue")).status == 400
    export = await client.get("/api/v1/cultures/targets/export?format=csv")
    text = await export.text()
    assert export.status == 200 and "ec_min_mS_cm" in text and saved["id"] in text
    assert (await client.get("/api/v1/cultures/targets/export?format=json")).status == 400


async def test_page_des_plages_met_la_plage_applicable_et_sa_source_en_tete(web_context):
    """R2.7 : sélecteur d'abord, plage applicable en tête, indication de source à côté."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = await (await client.get("/cultures/targets")).text()
    # Ordre imposé : sélecteur, « Appliqué maintenant », puis « Déclaré dans le carnet ».
    # Les libellés sont vérifiés sur les titres eux-mêmes, pas sur les liens de la page.
    assert body.index('id="selection"') < body.index("<h2>Appliqué maintenant</h2>")
    assert body.index("<h2>Appliqué maintenant</h2>") < body.index("<h2>Déclaré dans le carnet</h2>")
    assert "Comment cette valeur est choisie" in body
    # Sans cible consultée, aucune plage n'est supposée.
    assert "Aucune cible consultée" in body and "data-target-source" not in body
    # Sans cible, aucun fait d'alimentation n'est énoncé : pas de phrase par défaut.
    assert "data-target-feeding" not in body

    saved = await client.post("/api/v1/cultures/targets", json=target(start_at="2026-06-01"),
                              headers=headers)
    assert saved.status == 200, await saved.text()
    applique = await (await client.get("/cultures/targets?target=reservoir_2")).text()
    assert 'data-target-source="reservoir"' in applique and ">réservoir<" in applique
    assert "pH 5,80 à 6,40" in texte(applique)
    assert "Du 01/06/2026" in applique and "toujours en vigueur" in applique
    # La plage applicable est bien avant la liste des plages déclarées.
    assert applique.index("data-target-applied") < applique.index("<h2>Déclaré dans le carnet</h2>")
    # Écart E8 : entre le sélecteur de tête (cible, date) et la plage appliquée, plus rien ne
    # la repousse. La portée, qui ne filtre que la liste, et la présentation des plages vivent
    # avec la liste ; la portée est reconduite par le sélecteur en champ caché, et le filtre de
    # portée reconduit à son tour la cible et la date. La source suit la valeur.
    selection = applique[applique.index('id="selection"'):]
    selection = selection[:selection.index("</form>")]
    assert '<select name="scope"' not in selection and 'type="hidden" name="scope"' in selection
    liste = applique[applique.index("<h2>Déclaré dans le carnet</h2>"):]
    portee = liste[:liste.index("</form>")]
    assert "servent à lire les relevés" in portee and '<select name="scope"' in portee
    assert 'name="target" value="reservoir_2"' in portee and "data-offline-filter" in portee
    assert applique.count("servent à lire les relevés") == 1
    assert '<p><span class="culture-source" data-target-source="reservoir">' in applique

    # Aucune rétroactivité : avant son début, la plage ne s'applique pas.
    avant = await (await client.get("/cultures/targets?target=reservoir_2&at=2026-05-01")).text()
    assert "Aucune plage applicable à cette date" in avant and "data-target-source" not in avant
    # Une date de consultation future est refusée explicitement, jamais ignorée.
    assert (await client.get("/cultures/targets?target=reservoir_2&at=2027-01-01")).status == 400

    # Une plage portée par une culture se lit « cible directe » : la source, pas la portée.
    lot = await (await client.post("/api/v1/cultures", json=create(), headers=headers)).json()
    direct = await client.post("/api/v1/cultures/targets",
                               json=target(target=lot["subject_id"], start_at="2026-06-01"),
                               headers=headers)
    assert direct.status == 200, await direct.text()
    page = await (await client.get(f"/cultures/targets?target={lot['subject_id']}")).text()
    assert 'data-target-source="subject"' in page and ">cible directe<" in page


async def test_resolution_du_magasin_suit_la_cascade_et_les_associations_datees(cultures):
    """`target_resolution` : lecture seule, cascade stricte, aucune rétroactivité."""
    lot = await cultures.call("mutate", create("Lot alimenté", space="space_2",
        origin_at="2026-06-01", space_at="2026-06-01", stage_at="2026-06-01"))
    await cultures.call("solution_mutate", {
        "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "renewal",
        "reservoir_id": "reservoir_2", "effective_at": "2026-06-05", "volume_l": 20})
    await cultures.call("target_mutate", target(target="reservoir_2", start_at="2026-06-01"))
    await cultures.call("target_mutate", target(target=lot["subject_id"], start_at="2026-06-01",
                                                ph_min="6,0", ph_max="6,6"))

    # Association déclarée à cette date : le sujet alimenté passe avant le réservoir, et
    # c'est **sa** plage qui est rendue, sans fusion avec celle du réservoir.
    apres = await cultures.call("target_resolution", "reservoir_2", "2026-06-10")
    assert apres["range"]["source"] == "fed_subject"
    assert apres["range"]["subject_id"] == lot["subject_id"]
    assert (apres["range"]["ph_min"], apres["range"]["ph_max"]) == (6.0, 6.6)
    assert apres["fed_subjects"] == [lot["subject_id"]]
    # Avant l'association, la cascade retombe sur le réservoir : rien n'est rétroactif.
    avant = await cultures.call("target_resolution", "reservoir_2", "2026-06-02")
    assert avant["range"]["source"] == "reservoir" and avant["fed_subjects"] == []
    assert (avant["range"]["ph_min"], avant["range"]["ph_max"]) == (5.8, 6.4)
    # La culture consultée reste sa propre cible directe ; son réservoir est un fait daté.
    fiche = await cultures.call("target_resolution", lot["subject_id"], "2026-06-10")
    assert fiche["range"]["source"] == "subject" and fiche["reservoirs"] == ["reservoir_2"]
    assert (await cultures.call("target_resolution", lot["subject_id"], "2026-06-02"))["reservoirs"] == []
    # Cible inconnue et date impossible sont refusées, jamais ignorées.
    with pytest.raises(CultureError):
        await cultures.call("target_resolution", "inconnu", "2026-06-10")
    with pytest.raises(CultureError):
        await cultures.call("target_resolution", "reservoir_2", "pas-une-date")


async def test_ce_qu_annonce_la_page_est_ce_qu_un_releve_recevrait(cultures):
    """Équivalence page ↔ relevé réel : la page ne promet aucune plage inatteignable.

    Un relevé vise une culture **ou** un réservoir, jamais les deux (`_solution_mutate`).
    Une culture sans plage propre ne reçoit donc rien, même alimentée par un réservoir qui
    en a une : la page doit dire exactement cela, et le réservoir alimentant n'est qu'un
    fait affiché à côté.
    """
    lot = await cultures.call("mutate", create("Lot sans plage", space="space_2",
        origin_at="2026-06-01", space_at="2026-06-01", stage_at="2026-06-01"))
    await cultures.call("solution_mutate", {
        "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "renewal",
        "reservoir_id": "reservoir_2", "effective_at": "2026-06-05", "volume_l": 20})
    await cultures.call("target_mutate", target(target="reservoir_2", start_at="2026-06-01"))

    # Le carnet refuse un relevé qui viserait à la fois la culture et le réservoir : c'est
    # ce refus qui rend une résolution « réservoir » inatteignable pour une culture.
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", {
            "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "reading",
            "reservoir_id": "reservoir_2", "targets": [lot["subject_id"]],
            "effective_at": "2026-06-10", "ph": "6,1"})

    # Relevé réel visant la culture : aucune plage, et la page annonce la même chose.
    await cultures.call("solution_mutate", {
        "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "water",
        "targets": [lot["subject_id"]], "effective_at": "2026-06-10", "volume_l": 2})
    entries = (await cultures.call("solution_data", {}))["items"]
    arrosage = next(entry for entry in entries if entry["kind"] == "water")
    assert arrosage["target"] is None
    vue = await cultures.call("target_resolution", lot["subject_id"], "2026-06-10")
    assert vue["range"] is None
    # Le réservoir alimentant reste connu — comme information, pas comme résolution.
    assert vue["reservoirs"] == ["reservoir_2"]

    # Relevé réel sur le réservoir : la plage du réservoir s'applique, et la page l'annonce
    # avec la même source. Les deux consultations restent distinctes, sans fusion.
    await cultures.call("solution_mutate", {
        "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "reading",
        "reservoir_id": "reservoir_2", "effective_at": "2026-06-11", "ph": "6,1"})
    entries = (await cultures.call("solution_data", {}))["items"]
    releve = next(entry for entry in entries if entry["kind"] == "reading")
    cote_reservoir = await cultures.call("target_resolution", "reservoir_2", "2026-06-11")
    assert releve["target"]["source"] == cote_reservoir["range"]["source"] == "reservoir"
    assert releve["target"]["id"] == cote_reservoir["range"]["id"]


async def test_page_des_plages_resout_le_sujet_alimente_a_la_date_de_l_association(web_context):
    """R2.7 : la cascade complète est rendue, l'étape « sujet alimenté » comprise."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    lot = await (await client.post("/api/v1/cultures", json=create(
        "Lot alimenté", space="space_2", origin_at="2026-06-01", space_at="2026-06-01",
        stage_at="2026-06-01"), headers=headers)).json()
    assert "subject_id" in lot, lot
    # La solution n'est présente que depuis le 05/06 : l'association part de là, pas de
    # l'origine de la culture.
    renewal = await client.post("/api/v1/cultures/solutions", json={
        "operation": "entry", "request_id": str(uuid.uuid4()), "kind": "renewal",
        "reservoir_id": "reservoir_2", "effective_at": "2026-06-05", "volume_l": 20},
        headers=headers)
    assert renewal.status == 200, await renewal.text()
    for command in (target(target="reservoir_2", start_at="2026-06-01"),
                    target(target=lot["subject_id"], start_at="2026-06-01",
                           ph_min="6,0", ph_max="6,6")):
        assert (await client.post("/api/v1/cultures/targets", json=command,
                                  headers=headers)).status == 200

    # Date couverte par l'association : la plage du sujet alimenté passe avant celle du
    # réservoir, sans fusion — c'est la plage du sujet qui est affichée, entière.
    page = await (await client.get("/cultures/targets?target=reservoir_2&at=2026-06-10")).text()
    assert 'data-target-source="fed_subject"' in page and ">sujet alimenté<" in page
    lisible = texte(page)
    assert "pH 6,00 à 6,60" in lisible
    assert "pH 5,80 à 6,40" not in texte(page.split('id="plages"')[0])
    assert "Sujets alimentés par cette solution à cette date : Lot alimenté." in page

    # Avant l'association, la même consultation retombe sur le réservoir : aucune
    # rétroactivité, une association ouverte plus tard ne remonte pas le temps.
    avant = await (await client.get("/cultures/targets?target=reservoir_2&at=2026-06-02")).text()
    assert 'data-target-source="reservoir"' in avant and ">réservoir<" in avant
    assert "pH 5,80 à 6,40" in texte(avant.split('id="plages"')[0])
    assert "Aucun sujet alimenté par cette solution à cette date." in avant

    # Consultée directement, la culture reste sa propre cible directe ; le réservoir qui
    # l'alimente est nommé comme un fait daté, jamais fusionné avec elle.
    fiche = await (await client.get(
        f"/cultures/targets?target={lot['subject_id']}&at=2026-06-10")).text()
    assert 'data-target-source="subject"' in fiche and ">cible directe<" in fiche
    assert "Réservoir déclaré alimentant cette culture à cette date :" in fiche
    # …et la page dit aussitôt que cette plage-là ne s’appliquera à aucun relevé de la
    # culture : un relevé vise une culture **ou** un réservoir, jamais les deux.
    assert "Sa plage ne s’applique pas aux relevés visant la culture" in fiche
