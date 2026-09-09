"""Erreurs rattachées à leur champ : contrat commun au magasin et aux API du carnet.

Le message reste inchangé et premier ; `field` porte le `name` du contrôle et `index` son
rang parmi les contrôles homonymes. Une indisponibilité du carnet n'a jamais de champ.
"""

import json
import uuid
from urllib.parse import quote

import pytest

from model.culture import CultureError
from tests.test_cultures import create, cultures, event  # noqa: F401  (fixtures)
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401  (fixture)

HEADERS = {"X-CSRF-Token": CSRF_TOKEN}


async def failing(store, command):
    with pytest.raises(CultureError) as raised:
        await store.call("mutate", command)
    return raised.value


@pytest.mark.parametrize("overrides, field, index", [
    ({"name": ""}, "name", None),
    ({"variety": "v" * 200}, "variety", None),
    ({"origin_type": "inconnu"}, "origin_type", None),
    ({"origins": [{"label": "A", "count": 1}, {"label": "", "count": 1}]}, "origin_label", 1),
    ({"origins": [{"label": "A", "count": 0}]}, "origin_count", 0),
    ({"origin_type": "cutting"}, "mother_id", 0),
    ({"origin_at": "2027-01-01"}, "origin_at", None),
    ({"stage": "maintien"}, "stage", None),
    ({"stage": "inconnu"}, "stage", None),
    ({"stage_at": "2027-01-01"}, "stage_at", None),
    ({"space": "space_9"}, "space", None),
    # Une reprise en séchage hors de l'espace 2 : la projection le refusait déjà, mais sans
    # champ et seulement à l'insertion de la récolte, donc après tout le formulaire.
    ({"stage": "sechage", "space": "space_1"}, "space", None),
    ({"space_at": "2027-01-01"}, "space_at", None),
])
async def test_champ_fautif_de_la_creation(cultures, overrides, field, index):
    error = await failing(cultures, create(**overrides))
    assert (error.field, error.index) == (field, index)
    assert (await cultures.call("overview"))["total"] == 0


async def test_sechage_hors_espace_2_garde_le_message_de_la_projection(cultures):
    # Le contrôle anticipé ne doit pas introduire un second libellé pour la même règle.
    error = await failing(cultures, create(stage="sechage", space="space_1"))
    assert str(error) == "La récolte et le séchage ont lieu dans l'espace 2."


@pytest.mark.parametrize("overrides, field", [
    ({"name": "", "stage_at": "2027-01-01"}, "name"),
    ({"origins": [{"label": "A", "count": 0}], "origin_at": "2027-01-01"}, "origin_count"),
    ({"stage": "maintien", "space_at": "2027-01-01"}, "stage"),
    ({"origin_at": "2027-01-01", "space": "space_9"}, "origin_at"),
])
async def test_ordre_des_erreurs_suit_le_formulaire(cultures, overrides, field):
    # Plusieurs fautes cumulées : c'est toujours le champ le plus haut du formulaire qui
    # est signalé, même quand l'insertion métier valide ces champs dans un autre ordre.
    assert (await failing(cultures, create(**overrides))).field == field


@pytest.mark.parametrize("kind, payload, extra, field, index", [
    ("stage", {"stage": "inconnu"}, {}, "stage", None),
    ("move", {"space": "ailleurs"}, {}, "space", None),
    ("loss", {"count": 0}, {}, "count", None),
    ("loss", {"count": 1, "origin_id": 7}, {}, "origin_id", None),
    ("note", {"note": "Vue"}, {"effective_at": "2027-01-01"}, "effective_at", None),
    ("note", {"note": "Vue"}, {"reason": "m" * 600}, "reason", None),
    ("harvest", {"drying_at": "2027-01-01", "drying_precision": "date"}, {}, "drying_at", None),
])
async def test_champ_fautif_d_un_evenement(cultures, kind, payload, extra, field, index):
    lot = await cultures.call("mutate", create(space="space_2"))
    command = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": lot["subject_id"],
               "version": lot["version"], "kind": kind, "effective_at": "2026-08-05",
               "payload": payload, **extra}
    error = await failing(cultures, command)
    assert (error.field, error.index) == (field, index)


@pytest.mark.parametrize("payload, field, index", [
    ({"weight_g": "beaucoup"}, "weight_g", None),
    ({"origin_weights": [{"origin_id": "inconnue", "weight_g": -1}]}, "origin_weight", 0),
])
async def test_champ_fautif_du_bilan_de_recolte(cultures, payload, field, index):
    lot = await cultures.call("mutate", create(space="space_2"))
    lot = await event(cultures, lot, "harvest", "2026-08-10")
    command = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": lot["subject_id"],
               "version": lot["version"], "kind": "finish", "effective_at": "2026-08-15",
               "payload": payload}
    error = await failing(cultures, command)
    assert (error.field, error.index) == (field, index)


async def solution_error(store, command):
    with pytest.raises(CultureError) as raised:
        await store.call("solution_mutate", {"request_id": str(uuid.uuid4()), **command})
    return raised.value


@pytest.mark.parametrize("command, field, index", [
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "ph": 99}, "ph", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "ec_unit": "ppm"}, "ec_unit", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "ec": 900}, "ec", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "context": "pendant"}, "context", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "compensation": "peut-être"}, "compensation", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "temperature_c": 500}, "temperature_c", None),
    ({"operation": "entry", "kind": "renewal", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "volume_l": -3}, "volume_l", None),
    # Volume absent d'un renouvellement : le refus est le même, il désigne le même champ.
    ({"operation": "entry", "kind": "topup", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01"}, "volume_l", None),
    ({"operation": "entry", "kind": "inconnu", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01"}, "kind", None),
    ({"operation": "entry", "kind": "reading", "targets": ["fantome"],
      "effective_at": "2026-09-01", "ph": 6}, "target", None),
    ({"operation": "entry", "kind": "reading", "reservoir_id": "reservoir_2",
      "effective_at": "2027-01-01", "ph": 6}, "effective_at", None),
    ({"operation": "entry", "kind": "nutrient", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01",
      "ingredients": [{"product": "A", "quantity": 1, "unit": "g"},
                      {"product": "B", "quantity": 1, "unit": "kg"}]}, "unit", 1),
    ({"operation": "entry", "kind": "nutrient", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01",
      "ingredients": [{"product": "A", "quantity": "beaucoup", "unit": "g"}]}, "quantity", 0),
    ({"operation": "recipe", "volume_l": 10,
      "ingredients": [{"product": "A", "quantity": 1, "unit": "g"}]}, "name", None),
    ({"operation": "entry", "kind": "nutrient", "reservoir_id": "reservoir_2",
      "effective_at": "2026-09-01", "volume_l": 10, "recipe_id": "inconnue", "recipe_revision": 1,
      "ingredients": [{"product": "A", "quantity": 1, "unit": "g"}]}, "recipe_id", None),
])
async def test_champ_fautif_d_une_solution(cultures, command, field, index):
    error = await solution_error(cultures, command)
    assert (error.field, error.index) == (field, index)


async def test_confirmation_de_date_est_un_champ(cultures):
    cultures.reliable = lambda: False
    assert (await failing(cultures, create())).field == "confirm_date"
    assert (await solution_error(cultures, {"operation": "entry", "kind": "reading",
        "reservoir_id": "reservoir_2", "effective_at": "2026-09-01", "ph": 6})).field == "confirm_date"


async def test_erreur_sans_champ_identifiable_reste_sans_champ(cultures):
    # Une commande mal formée ne désigne aucun contrôle : ne rien inventer vaut mieux
    # que rattacher le message au premier champ venu.
    assert (await failing(cultures, {**create(), "operation": "inconnue"})).field is None
    assert (await failing(cultures, {**create(), "origins": "invalide"})).field is None


async def test_champ_et_index_traversent_l_api(web_context):
    client, *_ = web_context
    response = await client.post("/api/v1/cultures", headers=HEADERS,
                                 json=create(origins=[{"label": "A", "count": 1}, {"label": "", "count": 2}]))
    assert response.status == 400
    body = await response.json()
    assert list(body)[0] == "error" and body["field"] == "origin_label" and body["index"] == 1
    assert body["error"] == "Origine obligatoire."
    response = await client.post("/api/v1/cultures", headers=HEADERS, json=create(name=""))
    body = await response.json()
    # Champ sans homonyme : aucun index inventé.
    assert body == {"error": "Nom obligatoire.", "field": "name"}
    response = await client.post("/api/v1/cultures/solutions", headers=HEADERS,
                                 json={"request_id": str(uuid.uuid4()), "operation": "entry",
                                       "kind": "reading", "reservoir_id": "reservoir_2",
                                       "effective_at": "2026-09-01", "ph": 99})
    assert response.status == 400 and (await response.json())["field"] == "ph"


# --- Lots D à H : plages, éclairage, équipements, vérifications, rappels, photos --------

TARGET = {"operation": "target", "target": "reservoir_2", "start_at": "2026-08-01",
          "ph_min": "5,8", "ph_max": "6,4"}
LIGHT = {"operation": "light", "scope": "global", "label": "Végétatif 18/6",
         "on_minutes": 1080, "off_minutes": 360, "start_at": "2026-08-01"}
EQUIPMENT = {"operation": "link", "equipment_id": "cyclic_2", "usage": "irrigation espace 2",
             "scope": "space", "space": "space_2", "start_at": "2026-06-01"}
REMINDER = {"operation": "reminder", "target": "reservoir_2", "title": "Renouveler le bac",
            "due_date": "2026-09-30", "interval_days": 7}


async def refuse(client, route, body):
    """Commande refusée par l'API : le statut est 400 et le corps porte le refus."""
    response = await client.post(route, json={"request_id": str(uuid.uuid4()), **body}, headers=HEADERS)
    assert response.status == 400, await response.text()
    return await response.json()


@pytest.mark.parametrize("route, body, field", [
    # Plages cibles (lot E) : bornes, unité, cible, fenêtre et contexte.
    ("/api/v1/cultures/targets", {**TARGET, "ph_min": 99}, "ph_min"),
    ("/api/v1/cultures/targets", {**TARGET, "ph_min": None, "ph_max": None}, "ph_min"),
    ("/api/v1/cultures/targets", {**TARGET, "ec_unit": "ppm"}, "ec_unit"),
    ("/api/v1/cultures/targets", {**TARGET, "target": "fantome"}, "target"),
    ("/api/v1/cultures/targets", {**TARGET, "stage": "inconnu"}, "stage"),
    ("/api/v1/cultures/targets", {**TARGET, "end_at": "2026-07-01"}, "end_at"),
    ("/api/v1/cultures/targets", {**TARGET, "start_at": "2027-01-01"}, "start_at"),
    # Repères d'éclairage (lot F) : le formulaire n'expose que la durée d'éclairage.
    ("/api/v1/cultures/light", {**LIGHT, "on_minutes": 2000, "off_minutes": -560}, "on_minutes"),
    ("/api/v1/cultures/light", {**LIGHT, "on_minutes": 900}, "on_minutes"),
    ("/api/v1/cultures/light", {**LIGHT, "scope": "ailleurs"}, "scope"),
    ("/api/v1/cultures/light", {**LIGHT, "scope": "space", "space": "space_9"}, "space"),
    ("/api/v1/cultures/light", {**LIGHT, "scope": "subject", "subject_id": "fantome"}, "subject_id"),
    ("/api/v1/cultures/light", {**LIGHT, "label": ""}, "label"),
    ("/api/v1/cultures/light", {**LIGHT, "stage": "inconnu"}, "stage"),
    ("/api/v1/cultures/light", {**LIGHT, "start_at": "2027-01-01"}, "start_at"),
    # Affectations d'équipements (lot G) : catalogue, portée, cible, usage et fenêtre.
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "equipment_id": "inconnu"}, "equipment_id"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "scope": "ailleurs"}, "scope"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "space": ""}, "space"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "scope": "reservoir", "space": None,
                                    "reservoir_id": "fantome"}, "reservoir_id"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "usage": ""}, "usage"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "source": "ailleurs"}, "source"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "end_at": "2026-05-01"}, "end_at"),
    ("/api/v1/cultures/equipment", {**EQUIPMENT, "note": "n" * 5000}, "note"),
    # Rappels (lot D) : les libellés viennent des règles pures, le champ du formulaire.
    ("/api/v1/cultures/cycles", {**REMINDER, "title": ""}, "title"),
    ("/api/v1/cultures/cycles", {**REMINDER, "due_date": "30/09/2026"}, "due_date"),
    ("/api/v1/cultures/cycles", {**REMINDER, "interval_days": 400}, "interval_days"),
    ("/api/v1/cultures/cycles", {**REMINDER, "note": "n" * 5000}, "note"),
    ("/api/v1/cultures/cycles", {**REMINDER, "target": "fantome"}, "target"),
])
async def test_champ_fautif_des_lots_d_a_h_traverse_l_api(web_context, route, body, field):
    client, *_ = web_context
    payload = await refuse(client, route, body)
    # Ces domaines n'ont aucun groupe répété : aucun rang n'est inventé.
    assert payload["field"] == field and "index" not in payload
    assert list(payload)[0] == "error" and payload["error"]


async def test_champ_fautif_d_une_verification(web_context):
    client, *_ = web_context
    created = await client.post("/api/v1/cultures", headers=HEADERS,
                                json=create("Lot vérifié", space="space_1"))
    assert created.status == 200, await created.text()
    lot = await created.json()
    saisie = {"operation": "checklist", "subject_id": lot["subject_id"], "version": lot["version"],
              "effective_at": "2026-09-06",
              "checks": {"lighting": True, "pump": True, "ventilation": True}}
    # Le groupe entier manque : le refus vise sa première case, jamais un champ inventé.
    assert (await refuse(client, "/api/v1/cultures/cycles",
                         {**saisie, "checks": {"lighting": True}}))["field"] == "lighting"
    assert (await refuse(client, "/api/v1/cultures/cycles",
                         {**saisie, "effective_at": "2026-07-01"}))["field"] == "effective_at"
    assert (await refuse(client, "/api/v1/cultures/cycles",
                         {**saisie, "note": "n" * 5000}))["field"] == "note"
    response = await client.post("/api/v1/cultures/cycles", headers=HEADERS,
                                 json={"request_id": str(uuid.uuid4()), **saisie})
    assert response.status == 200, await response.text()
    verification = await response.json()
    correction = {"operation": "checklist_correct", "id": verification["id"],
                  "version": verification["revision"], "effective_at": "2026-09-06",
                  "checks": saisie["checks"], "note": "", "reason": ""}
    assert (await refuse(client, "/api/v1/cultures/cycles", correction))["field"] == "reason"
    annulation = {"operation": "checklist_cancel", "id": verification["id"],
                  "version": verification["revision"], "reason": ""}
    assert (await refuse(client, "/api/v1/cultures/cycles", annulation))["field"] == "reason"


async def test_champ_fautif_d_une_photo(web_context):
    client, *_ = web_context
    response = await client.post("/api/v1/cultures/journal", headers=HEADERS,
                                 json={"request_id": str(uuid.uuid4()), "operation": "space_event",
                                       "space": "space_2", "kind": "observation",
                                       "effective_at": "2026-09-01", "note": "Bac nettoyé"})
    assert response.status == 200, await response.text()
    observation = await response.json()

    async def envoi(metadata, raw):
        return await client.post(
            "/api/v1/cultures/journal/photos", data=raw,
            headers={**HEADERS, "Content-Type": "application/octet-stream",
                     "X-Culture-Metadata": quote(json.dumps(
                         {"request_id": str(uuid.uuid4()), **metadata}))})

    base = {"space_event_id": observation["id"], "space_event_revision": observation["version"]}
    refus = await envoi({**base, "caption": "l" * 600}, b"x")
    assert refus.status == 400 and (await refus.json())["field"] == "caption"
    # Le fichier choisi est une saisie : son refus désigne le contrôle qui le porte.
    refus = await envoi({**base, "caption": ""}, b"<svg></svg>")
    assert refus.status == 400 and (await refus.json())["field"] == "photo"


async def test_champ_fautif_d_une_observation_d_espace(web_context):
    """Observations d'espace (lot H) : le refus désigne le contrôle du formulaire.

    Les `name` sont ceux de `culture_journal.html` : `space`, `kind`, `effective_at`,
    `note` (« Observation », « Observation corrigée ») et `reason`.
    """
    client, *_ = web_context
    saisie = {"operation": "space_event", "space": "space_2", "kind": "observation",
              "effective_at": "2026-09-01", "note": "Bac nettoyé"}
    route = "/api/v1/cultures/journal"
    for body, field in (({**saisie, "space": "space_9"}, "space"),
                        ({**saisie, "kind": "inconnu"}, "kind"),
                        ({**saisie, "effective_at": "2027-01-01"}, "effective_at"),
                        ({**saisie, "note": "n" * 5000}, "note")):
        payload = await refuse(client, route, body)
        assert payload["field"] == field and "index" not in payload
        assert list(payload)[0] == "error" and payload["error"]
    response = await client.post(route, headers=HEADERS,
                                 json={"request_id": str(uuid.uuid4()), **saisie})
    assert response.status == 200, await response.text()
    observation = await response.json()
    # Une correction sans motif : le refus vise « Motif de la correction ».
    correction = {"operation": "correct", "id": observation["id"], "version": observation["version"],
                  "space": "space_2", "kind": "observation", "effective_at": "2026-09-01",
                  "note": "Bac nettoyé et rincé", "reason": ""}
    assert (await refuse(client, route, correction))["field"] == "reason"


async def test_indisponibilite_reste_sans_champ(web_context, monkeypatch):
    from utils.culture_store import CultureUnavailable
    client, server, *_ = web_context
    async def failed(*_args):
        raise CultureUnavailable("Carnet indisponible ; aucune écriture confirmée.")
    monkeypatch.setattr(server.cultures.store, "call", failed)
    for path in ("/api/v1/cultures/journal", "/api/v1/cultures/targets", "/api/v1/cultures/light",
                 "/api/v1/cultures/equipment", "/api/v1/cultures/cycles"):
        response = await client.get(path)
        assert response.status == 503 and set(await response.json()) == {"error"}
    response = await client.post("/api/v1/cultures", headers=HEADERS, json=create())
    assert response.status == 503 and set(await response.json()) == {"error"}
