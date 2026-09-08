"""Erreurs rattachées à leur champ : contrat commun au magasin et aux API du carnet.

Le message reste inchangé et premier ; `field` porte le `name` du contrôle et `index` son
rang parmi les contrôles homonymes. Une indisponibilité du carnet n'a jamais de champ.
"""

import uuid

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
    ({"space_at": "2027-01-01"}, "space_at", None),
])
async def test_champ_fautif_de_la_creation(cultures, overrides, field, index):
    error = await failing(cultures, create(**overrides))
    assert (error.field, error.index) == (field, index)
    assert (await cultures.call("overview"))["total"] == 0


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
