"""Affectations d'équipements datées (lot G) : résolution, révisions et non-chevauchement."""

import json
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_equipment import resolve_equipment, validate_equipment_windows
from param.equipment_metadata import EquipmentMetadataStore, default_catalog
from tests.test_cultures import NOW, create, cultures  # noqa: F401  (fixture de carnet isolé)
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401  (serveur de test)
from utils.culture_backup import restore_copy

CATALOG = {key: value.model_dump() for key, value in default_catalog().items()}


def link(**overrides):
    return {"request_id": str(uuid.uuid4()), "operation": "link", "equipment_id": "cyclic_2",
            "usage": "irrigation espace 2", "scope": "space", "space": "space_2",
            "start_at": "2026-06-01", **overrides}


async def declare(store, catalog=None, **overrides):
    return await store.call("equipment_mutate", link(**overrides), catalog or CATALOG)


async def test_deux_usages_successifs_de_cyclic_2_resolus_a_leur_date(cultures):
    first = await declare(cultures, usage="irrigation espace 2")
    await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()), "operation": "close",
        "id": first["id"], "version": 1, "end_at": "2026-07-01"}, CATALOG)
    await declare(cultures, usage="brumisation espace 1", scope="space", space="space_1",
                  start_at="2026-07-01")

    juin = await cultures.call("equipment_links", {"at": "2026-06-15"}, CATALOG)
    assert juin["resolved"]["provenance"] == "link"
    assert [item["usage"] for item in juin["resolved"]["items"]] == ["irrigation espace 2"]
    juillet = await cultures.call("equipment_links", {"at": "2026-07-15"}, CATALOG)
    assert [item["usage"] for item in juillet["resolved"]["items"]] == ["brumisation espace 1"]
    assert juillet["resolved"]["items"][0]["space"] == "space_1"
    # Avant la première affectation, rien n'est inventé : ni catalogue courant, ni usage voisin.
    avant = await cultures.call("equipment_links", {"at": "2026-05-01"}, CATALOG)
    assert avant["resolved"]["provenance"] == "unknown" and avant["resolved"]["items"] == []


async def test_intervention_retrospective_retrouve_son_association_ou_declare_l_ignorer(cultures):
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "reservoir_2", "effective_at": "2026-06-05",
        "volume_l": 20}, CATALOG)
    ancienne = (await cultures.call("solution_data", {}))["items"][0]
    # Aucune affectation déclarée : la copie du catalogue portée par la saisie fait foi.
    assert ancienne["equipment"]["provenance"] == "snapshot"
    assert ancienne["equipment"]["recorded_at"] == ancienne["recorded_at"]
    assert "Sortie cyclique 2" in ancienne["equipment"]["label"]

    await declare(cultures, start_at="2026-06-01")
    retrouvee = (await cultures.call("solution_data", {}))["items"][0]
    assert retrouvee["equipment"]["provenance"] == "link"
    assert retrouvee["equipment"]["items"][0]["usage"] == "irrigation espace 2"

    # Une saisie sans copie de catalogue et hors de toute fenêtre reste explicitement inconnue.
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "renewal", "reservoir_id": "cuttings_1", "effective_at": "2026-05-01",
        "volume_l": 10}, {})
    inconnue = next(e for e in (await cultures.call("solution_data", {}))["items"]
                    if e["effective_at"] == "2026-05-01")
    assert inconnue["equipment"] == {"provenance": "unknown", "at": inconnue["sort_at"],
                                     "items": [], "label": "", "recorded_at": None}


async def test_renommer_un_equipement_ne_reecrit_aucun_libelle_enregistre(cultures, tmp_path):
    await declare(cultures)
    catalogue = EquipmentMetadataStore(tmp_path / "equipment_metadata.json")
    renomme = dict(catalogue.current)
    renomme["cyclic_2"] = renomme["cyclic_2"].model_copy(update={"display_name": "Brumisateur neuf"})
    catalogue.save(renomme)
    assert catalogue.payload()["cyclic_2"]["display_name"] == "Brumisateur neuf"

    data = await cultures.call("equipment_links", {}, catalogue.payload())
    groupe = next(g for g in data["equipments"] if g["equipment_id"] == "cyclic_2")
    # Le nom courant du catalogue change, le libellé copié à la saisie reste figé.
    assert groupe["current_name"] == "Brumisateur neuf"
    assert groupe["links"][0]["display_name"] == "Sortie cyclique 2"
    # Une correction sans changement d'équipement ne rafraîchit pas ce libellé non plus.
    await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "id": groupe["links"][0]["id"], "version": 1, "usage": "irrigation corrigée",
        "reason": "Usage précisé"}, catalogue.payload())
    corrige = (await cultures.call("equipment_links", {"equipment": "cyclic_2"},
                                   catalogue.payload()))["equipments"][0]["links"][0]
    assert corrige["display_name"] == "Sortie cyclique 2" and corrige["revision"] == 2
    assert corrige["usage"] == "irrigation corrigée"
    assert [old["usage"] for old in corrige["revisions"]] == ["irrigation espace 2"]


async def test_contradictions_refusees_et_aucune_ecriture_partielle(cultures):
    first = await declare(cultures, start_at="2026-06-01")
    with pytest.raises(CultureError, match="recouvrent"):
        await declare(cultures, usage="autre usage", start_at="2026-06-10")
    data = await cultures.call("equipment_links", {"equipment": "cyclic_2"}, CATALOG)
    assert len(data["equipments"][0]["links"]) == 1

    with pytest.raises(CultureConflict, match="a changé"):
        await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()),
            "operation": "close", "id": first["id"], "version": 7, "end_at": "2026-07-01"}, CATALOG)
    with pytest.raises(CultureError, match="suit son début"):
        await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()),
            "operation": "close", "id": first["id"], "version": 1, "end_at": "2026-05-01"}, CATALOG)
    with pytest.raises(CultureError, match="Équipement inconnu"):
        await declare(cultures, equipment_id="pompe_inconnue", start_at="2026-08-01")
    with pytest.raises(CultureError, match="réservoir"):
        await declare(cultures, equipment_id="motor", scope="reservoir", space="space_2",
                      start_at="2026-08-01")
    assert len((await cultures.call("equipment_links", {}, CATALOG))["equipments"]) == 6
    assert (await cultures.call("equipment_links", {}, CATALOG))["total"] == 1


async def test_annulation_conserve_l_historique_et_libere_la_fenetre(cultures):
    first = await declare(cultures, start_at="2026-06-01")
    await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()), "operation": "cancel",
        "id": first["id"], "version": 1, "reason": "Saisie erronée"}, CATALOG)
    # La période annulée ne résout plus rien, mais reste lisible dans le carnet.
    resolu = await cultures.call("equipment_links", {"at": "2026-06-15"}, CATALOG)
    assert resolu["resolved"]["provenance"] == "unknown"
    groupe = next(g for g in resolu["equipments"] if g["equipment_id"] == "cyclic_2")
    assert groupe["links"][0]["cancelled"] == 1 and groupe["links"][0]["reason"] == "Saisie erronée"
    # La fenêtre libérée accepte une nouvelle affectation sur les mêmes dates.
    await declare(cultures, usage="irrigation corrigée", start_at="2026-06-01")
    assert (await cultures.call("equipment_links", {"at": "2026-06-15"},
                                CATALOG))["resolved"]["provenance"] == "link"


async def test_idempotence_et_commande_bornee(cultures):
    command = link(request_id="cle-affectation")
    first = await cultures.call("equipment_mutate", command, CATALOG)
    assert await cultures.call("equipment_mutate", dict(command), CATALOG) == first
    with pytest.raises(CultureConflict, match="autre saisie"):
        await cultures.call("equipment_mutate", {**command, "usage": "autre"}, CATALOG)
    with pytest.raises(CultureError, match="Commande d'affectation invalide"):
        await cultures.call("equipment_mutate", {**link(), "cablage": "gpio 13"}, CATALOG)
    with pytest.raises(CultureError, match="Opération attendue"):
        await cultures.call("equipment_mutate", {**link(), "operation": "rebrancher"}, CATALOG)
    with pytest.raises(CultureError, match="Filtre d'affectation inconnu"):
        await cultures.call("equipment_links", {"pin": "13"}, CATALOG)


async def test_export_puis_restauration_conserve_affectations_et_revisions(cultures, tmp_path):
    await cultures.call("mutate", create(), CATALOG)
    first = await declare(cultures, start_at="2026-06-01")
    await cultures.call("equipment_mutate", {"request_id": str(uuid.uuid4()), "operation": "close",
        "id": first["id"], "version": 1, "end_at": "2026-07-01"}, CATALOG)
    await declare(cultures, usage="brumisation", start_at="2026-07-01")
    export = await cultures.call("export")
    assert export["schema_version"] == 4
    assert len(export["tables"]["culture_equipment_links"]) == 3

    source = tmp_path / "sauvegarde.sqlite3"
    source.write_bytes(await cultures.call("backup"))
    destination = tmp_path / "copie-isolee.sqlite3"
    restore_copy(source, destination)
    assert destination.exists()

    import sqlite3
    db = sqlite3.connect(destination)
    try:
        rows = db.execute("SELECT id,revision,usage,display_name FROM culture_equipment_links"
                          " ORDER BY start_sort_at,revision").fetchall()
    finally:
        db.close()
    assert [row[1] for row in rows] == [1, 2, 1]
    assert {row[3] for row in rows} == {"Sortie cyclique 2"}


async def test_restauration_refuse_des_fenetres_incoherentes(cultures, tmp_path):
    await declare(cultures, start_at="2026-06-01")

    def corrupt():
        cultures._db.execute("UPDATE culture_equipment_links SET revision=3")
        cultures._db.commit()
    cultures._corrupt_equipment = corrupt
    await cultures.call("corrupt_equipment")
    source = tmp_path / "cassee.sqlite3"
    source.write_bytes(await cultures.call("backup"))
    from utils.culture_store import CultureUnavailable
    with pytest.raises((CultureError, CultureUnavailable)):
        restore_copy(source, tmp_path / "refusee.sqlite3")


def test_validation_pure_des_fenetres_et_de_la_cascade():
    base = {"id": "a", "revision": 1, "equipment_id": "cyclic_2", "scope": "space",
            "space": "space_2", "reservoir_id": None, "usage": "irrigation", "display_name": "",
            "start_at": "2026-06-01", "start_precision": "date",
            "start_sort_at": "2026-06-01T00:00:00+00:00", "end_at": None, "end_precision": None,
            "end_sort_at": None, "source": "operator", "cancelled": 0,
            "recorded_at": "2026-06-01T10:00:00+00:00"}
    validate_equipment_windows([base])
    with pytest.raises(CultureError, match="Révisions d'affectation"):
        validate_equipment_windows([{**base, "revision": 2}])
    with pytest.raises(CultureError, match="Équipement inconnu"):
        validate_equipment_windows([{**base, "equipment_id": "inconnu"}])
    with pytest.raises(CultureError, match="recouvrent"):
        validate_equipment_windows([base, {**base, "id": "b",
                                           "start_sort_at": "2026-07-01T00:00:00+00:00"}])
    # Une fenêtre close puis une suivante ne se recouvrent pas.
    validate_equipment_windows([{**base, "end_at": "2026-07-01", "end_precision": "date",
                                 "end_sort_at": "2026-07-01T00:00:00+00:00"},
                                {**base, "id": "b", "start_sort_at": "2026-07-01T00:00:00+00:00"}])

    at = "2026-06-15T00:00:00+00:00"
    assert resolve_equipment(at, [base], {})["provenance"] == "link"
    assert resolve_equipment(at, [{**base, "cancelled": 1}], {})["provenance"] == "unknown"
    contexte = json.loads(json.dumps(CATALOG))
    resolu = resolve_equipment(at, [], contexte, recorded_at="2026-09-01T00:00:00+00:00")
    assert resolu["provenance"] == "snapshot" and resolu["recorded_at"] == "2026-09-01T00:00:00+00:00"
    assert len(resolu["items"]) == 6
    # Hors fenêtre : la copie de catalogue reprend la main, jamais le catalogue courant.
    hors = resolve_equipment("2026-05-01T00:00:00+00:00", [base], contexte)
    assert hors["provenance"] == "snapshot"
    assert resolve_equipment("2026-05-01T00:00:00+00:00", [base], {})["provenance"] == "unknown"


def test_l_heure_de_reference_du_carnet_reste_inchangee():
    # Garde-fou : le lot G n'introduit aucune horloge propre.
    assert NOW.year == 2026


async def test_page_affectations_sans_effet_sur_la_configuration(web_context, monkeypatch):  # noqa: F811
    client, _server, config, sensors, _supervisor = web_context
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_args: writes.append("save"))
    monkeypatch.setattr(config, "commit", lambda *_args: writes.append("commit"))
    headers = {"X-CSRF-Token": CSRF_TOKEN}

    response = await client.get("/cultures/equipment")
    assert response.status == 200 and response.headers["Cache-Control"] == "no-store"
    page = await response.text()
    assert "Sortie cyclique 2" in page and "cyclic_2" in page
    assert "Catalogue courant, en lecture seule" in page

    command = {"request_id": str(uuid.uuid4()), "operation": "link", "equipment_id": "cyclic_2",
               "usage": "irrigation espace 2", "scope": "space", "space": "space_2",
               "start_at": "2026-06-01"}
    assert (await client.post("/api/v1/cultures/equipment", json=command)).status == 403
    response = await client.post("/api/v1/cultures/equipment", json=command, headers=headers)
    assert response.status == 200, await response.text()
    assert (await client.post("/api/v1/cultures/equipment", json={**command,
            "request_id": str(uuid.uuid4()), "start_at": "2026-06-10"}, headers=headers)).status == 400
    assert (await client.post("/api/v1/cultures/equipment", json={**command, "id": "inconnu",
            "request_id": str(uuid.uuid4()), "operation": "correct", "version": 1},
            headers=headers)).status == 400
    # Une même clé rejouée avec une autre saisie reste un conflit explicite.
    assert (await client.post("/api/v1/cultures/equipment", json={**command, "usage": "autre"},
                              headers=headers)).status == 409
    assert (await client.post("/api/v1/cultures/equipment", json={"note": "x" * 70000},
                              headers=headers)).status == 413

    data = await (await client.get("/api/v1/cultures/equipment?at=2026-06-15")).json()
    assert data["resolved"]["provenance"] == "link"
    inconnue = await (await client.get("/api/v1/cultures/equipment?at=2026-05-01")).json()
    assert inconnue["resolved"]["provenance"] == "unknown"
    assert (await client.get("/api/v1/cultures/equipment?equipment=inconnu")).status == 400
    assert "Association inconnue à cette date" in await (
        await client.get("/cultures/equipment?at=2026-05-01")).text()

    # Aucune écriture de configuration, aucune reconfiguration capteur : le lot reste déclaratif.
    assert config.current.to_json() == original and writes == []
    assert sensors.reconfigured == 0
    assert (await client.get("/health/ready")).status == 200


async def test_page_affectations_en_vue_principale_et_catalogue_replie(web_context):  # noqa: F811
    """R2.7 : sélecteur, puis les affectations, puis l'appliqué ; catalogue replié."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = await (await client.get("/cultures/equipment")).text()
    # Les libellés imposés sont vérifiés sur les titres, pas sur les liens de la page.
    assert body.index('id="selection"') < body.index("<h2>Déclaré dans le carnet</h2>")
    assert body.index("<h2>Déclaré dans le carnet</h2>") < body.index("<h2>Appliqué maintenant</h2>")
    # Le catalogue de référence est replié et passe après les deux blocs.
    assert body.index("<h2>Appliqué maintenant</h2>") < body.index('<details id="catalogue"')
    assert "Catalogue courant, en lecture seule" in body
    assert "Comment cette valeur est choisie" in body
    # Sans affectation déclarée, la valeur appliquée est explicitement inconnue.
    assert "Association inconnue à cette date" in body and ">inconnu<" in body
    assert "affectation du" not in body

    command = {"request_id": str(uuid.uuid4()), "operation": "link", "equipment_id": "cyclic_2",
               "usage": "irrigation espace 2", "scope": "space", "space": "space_2",
               "start_at": "2026-06-01"}
    assert (await client.post("/api/v1/cultures/equipment", json=command,
                              headers=headers)).status == 200
    page = await (await client.get("/cultures/equipment")).text()
    # Indication courte contre la valeur résolue, et copie de catalogue nommée comme telle.
    assert "affectation du 01/06/2026" in page
    assert "contexte copié à la saisie" in page
    # Hors de la fenêtre, aucun repli sur le catalogue courant : l'association reste inconnue.
    ancienne = await (await client.get("/cultures/equipment?at=2026-05-01")).text()
    assert ">inconnu<" in ancienne and "affectation du" not in ancienne
    # Consulter un équipement ne retire pas les autres du formulaire de déclaration.
    filtree = await (await client.get("/cultures/equipment?equipment=cyclic_2")).text()
    assert 'value="cyclic_1"' in filtree and 'value="cyclic_2"' in filtree
