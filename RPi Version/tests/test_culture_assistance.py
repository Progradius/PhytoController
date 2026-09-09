"""Assistance sans persistance, rejeu final et invalidation des faits."""

import uuid

import pytest

from model.culture import CultureError, CultureConflict
from model.culture_assistance import similar_readings, suggestions
from tests.test_cultures import create, cultures, event
from tests.test_culture_solutions import entry
from tests.test_culture_cycles import reminder
from tests.test_http_server import web_context, CSRF_TOKEN


async def test_preview_creation_transition_et_erreur_ne_persistent_rien(cultures):
    initial = await cultures.call("export")
    command = create(space="space_2", stage="vegetatif")
    preview = await cultures.call("preview", "culture", command)
    assert preview["valid"] and "Après" in preview["summary"][0]
    assert await cultures.call("export") == initial
    saved = await cultures.call("mutate", command)
    initial = await cultures.call("export")
    transition = {"operation": "event", "request_id": str(uuid.uuid4()), "subject_id": saved["subject_id"],
                  "version": saved["version"], "kind": "stage", "effective_at": "2026-09-01",
                  "payload": {"stage": "floraison"}}
    preview = await cultures.call("preview", "culture", transition)
    assert "Avant" in preview["summary"][0] and "Floraison" in preview["summary"][1]
    assert await cultures.call("export") == initial
    with pytest.raises(CultureError, match="déjà occupé.*Semis"):
        await cultures.call("preview", "culture", create(name="Conflit", space="space_2"))
    assert await cultures.call("export") == initial
    await event(cultures, saved, "note", "2026-09-01", {"note": "Nouvelle donnée"})
    with pytest.raises(CultureConflict):
        await cultures.call("mutate", transition)
    assert (await cultures.call("preview", "culture", command))["replay"]


async def test_releves_ressemblants_normalises_annulation_et_rejeu(cultures):
    await cultures.call("solution_mutate", entry())
    command = entry("reading", ph=6, ec=1.2)
    initial = await cultures.call("export")
    assert not (await cultures.call("preview", "solution", command))["similar"]
    assert await cultures.call("export") == initial
    saved = await cultures.call("solution_mutate", command)
    duplicate = {**command, "request_id": str(uuid.uuid4()), "ec": 1200, "ec_unit": "µS/cm"}
    preview = await cultures.call("preview", "solution", duplicate)
    assert preview["similar"][0]["id"] == saved["id"]
    assert (await cultures.call("preview", "solution", command))["replay"]
    assert not (await cultures.call("preview", "solution", {**duplicate, "ph": 6.1}))["similar"]
    assert not (await cultures.call("preview", "solution", {**duplicate, "effective_at": "2026-08-02"}))["similar"]
    # Une vraie seconde mesure reste acceptée par le serveur.
    second = await cultures.call("solution_mutate", duplicate)
    assert second["id"] != saved["id"]
    for original, result in ((command, saved), (duplicate, second)):
        await cultures.call("solution_mutate", {**original, "operation": "correct",
            "request_id": str(uuid.uuid4()), "id": result["id"], "version": result["version"],
            "cancelled": True, "reason": "Mesure saisie par erreur"})
    assert not (await cultures.call("preview", "solution", {**command, "request_id": str(uuid.uuid4())}))["similar"]



async def test_suggestions_disparaissent_apres_action_et_horloge_non_fiable(cultures):
    saved = await cultures.call("mutate", create(stage="floraison", space="space_2"))
    identifier = saved["subject_id"]
    rows = (await cultures.call("assistance", identifier))["items"]
    assert any(r["id"] == "check-stage" for r in rows)
    await cultures.call("cycle_mutate", {"operation": "checklist", "request_id": str(uuid.uuid4()),
        "subject_id": identifier, "version": saved["version"], "effective_at": "2026-09-07",
        "checks": {"lighting": True, "pump": True, "ventilation": True}, "note": "Vérifié"})
    assert not any(r["id"] == "check-stage" for r in (await cultures.call("assistance", identifier))["items"])
    r = await cultures.call("cycle_mutate", reminder(identifier, due_date="2026-09-07"))
    assert any(i["id"] == "reminder-" + r["id"] for i in (await cultures.call("assistance", identifier))["items"])
    await cultures.call("cycle_mutate", {"operation": "reminder_action", "request_id": str(uuid.uuid4()),
        "id": r["id"], "version": r["version"], "action": "done"})
    assert not any(i["id"] == "reminder-" + r["id"] for i in (await cultures.call("assistance", identifier))["items"])
    cultures.reliable = lambda: False
    assert (await cultures.call("assistance", identifier))["items"] == []


async def test_http_preview_csrf_validation_et_aucune_ecriture(web_context):
    client, server, config, sensors, supervisor = web_context
    command = create()
    url = "/api/v1/cultures/preview/culture"
    assert (await client.post(url, json=command)).status == 403
    original = config.current.to_json()
    response = await client.post(url, json=command, headers={"X-CSRF-Token": CSRF_TOKEN})
    assert response.status == 200, await response.text()
    assert response.headers["Cache-Control"] == "no-store"
    assert (await (await client.get("/api/v1/cultures")).json())["total"] == 0
    assert config.current.to_json() == original


@pytest.mark.parametrize("archived,space,reliable,expected", [
    (True, "space_2", True, ["release"]), (True, None, True, []),
    (False, "space_1", False, []),
])
def test_regles_pures_archive_et_horloge(archived, space, reliable, expected):
    from tests.test_culture_actions import subject
    item = subject(archived=archived, space=space)
    assert [r["id"] for r in suggestions(item, [], [], "2026-09-07", "Europe/Paris", reliable)] == expected


def test_ressemblance_pure_jour_local_absence_contexte_et_cibles():
    command = {"operation": "entry", "kind": "reading", "effective_at": "2026-09-07", "ph": 6,
               "targets": ["a", "b"], "context": "independent"}
    row = {"id": "r", "kind": "reading", "effective_at": "2026-09-06T22:30:00Z",
           "ph": 6, "ec": None, "temperature_c": None, "context": "independent", "compensation": "unknown",
           "targets": ["b", "a"], "reservoir_id": None, "intervention_id": None, "cancelled": 0}
    assert similar_readings(command, [row], "Europe/Paris") == [row]
    for change in ({"cancelled": 1}, {"ec": 0}, {"targets": ["a"]}, {"context": "after"}):
        assert similar_readings(command, [{**row, **change}], "Europe/Paris") == []
    assert similar_readings(command, [row], "UTC") == []


def test_repere_anterieur_pur_utilise_la_date_effective_pas_l_ordre_de_saisie():
    from model.culture_assistance import previous_reading
    command = {"targets": ["a"]}
    common = {"kind": "reading", "cancelled": 0, "reservoir_id": None, "targets": ["a"],
              "context": "independent", "intervention_id": None}
    old = {**common, "sort_at": "2026-08-01"}
    recent = {**common, "sort_at": "2026-09-01"}
    future = {**common, "sort_at": "2026-09-08"}
    assert previous_reading(command, [old, future, recent], "2026-09-07") == recent
    assert previous_reading({"targets": ["b"]}, [old, recent], "2026-09-07") is None


async def test_preview_refuse_un_domaine_ou_une_commande_hors_forme(cultures):
    for domain, command in (("inconnu", create()), ("culture", []), ("solution", "texte"),
                            ("cultures", create()), ("culture", None)):
        with pytest.raises(CultureError, match="Prévalidation de culture ou de solution attendue"):
            await cultures.call("preview", domain, command)


async def test_preview_sous_horloge_non_fiable_designe_la_confirmation(cultures):
    cultures.reliable = lambda: False
    for domain, command in (("culture", create()), ("solution", entry())):
        with pytest.raises(CultureError) as refused:
            await cultures.call("preview", domain, command)
        # Le refus désigne la case à cocher, pas une faute de saisie : sans champ, le socle
        # n'aurait qu'un résumé en tête de formulaire et l'opérateur chercherait ailleurs.
        assert refused.value.field == "confirm_date"
    assert (await cultures.call("preview", "culture", {**create(), "confirm_date": True}))["valid"]


async def test_bornes_des_ressemblances_et_des_suggestions(cultures):
    """Trois ressemblances au plus, quatre aides au plus : des repères, pas une liste."""
    await cultures.call("solution_mutate", entry())
    command = entry("reading", ph=6, ec=1.2)
    for _ in range(5):
        await cultures.call("solution_mutate", {**command, "request_id": str(uuid.uuid4())})
    preview = await cultures.call("preview", "solution", {**command, "request_id": str(uuid.uuid4())})
    assert len(preview["similar"]) == 3

    saved = await cultures.call("mutate", create(stage="floraison", space="space_2"))
    for day in range(1, 7):
        await cultures.call("cycle_mutate", reminder(saved["subject_id"],
            due_date=f"2026-09-0{day}", interval_days=0, title=f"Rappel {day}"))
    items = (await cultures.call("assistance", saved["subject_id"]))["items"]
    assert len(items) == 4 and all(item["id"].startswith("reminder-") for item in items)


async def test_lignes_d_association_de_reservoir_selon_le_nombre_de_liens(cultures):
    """Zéro, une, puis deux associations : chaque cas produit une ligne, aucune ne manque.

    Le texte de « aucune » et de « plusieurs » est aujourd'hui le même (R3.5 le sépare) ;
    ce test verrouille la présence de la ligne, pas sa formulation.
    """
    lot = await cultures.call("mutate", create(space="space_2"))
    identifier = lot["subject_id"]
    reading = {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": "reading",
               "targets": [identifier], "effective_at": "2026-08-05", "ph": 6.0}

    async def lines():
        preview = await cultures.call("preview", "solution", {**reading, "request_id": str(uuid.uuid4())})
        return [line for line in preview["summary"] if "ssociation" in line or "limentation déclarée" in line]

    # Aucune solution déclarée à cette date : l'association est inconnue.
    assert len(await lines()) == 1 and "inconnue ou non unique" in (await lines())[0]
    await cultures.call("solution_mutate", entry())
    assert len(await lines()) == 1 and "Alimentation déclarée" in (await lines())[0]

    # Deux associations simultanées sont hors d'atteinte du parcours normal — un lot
    # n'occupe qu'un espace — mais la branche existe et doit rendre une ligne.
    def duplicate():
        with cultures._db:
            period = cultures._db.execute("SELECT id FROM solution_periods LIMIT 1").fetchone()[0]
            row = cultures._db.execute("SELECT * FROM solution_links WHERE subject_id=?", (identifier,)).fetchone()
            cultures._db.execute("INSERT INTO solution_periods VALUES ('bis','cuttings_1',?,NULL)", (row["start_at"],))
            cultures._db.execute("INSERT INTO solution_links VALUES ('bis',?,?,?)",
                                 (identifier, row["start_at"], row["end_at"]))
        return period
    cultures._duplicate_link = duplicate
    await cultures.call("duplicate_link")
    assert len(await lines()) == 1 and "inconnue ou non unique" in (await lines())[0]


def test_resume_de_transition_d_une_recolte_annonce_la_coupe_d_alimentation():
    from model.culture_assistance import transition_summary
    before = {"stage": "floraison", "space": "space_2", "archived": False}
    after = {"stage": "sechage", "space": "space_2", "archived": False}
    lines = transition_summary(before, after, {"kind": "harvest", "effective_at": "2026-09-07"})
    assert lines[0].startswith("Avant : Floraison") and lines[1].startswith("Après : Séchage")
    assert lines[2] == "Date déclarée : 2026-09-07"
    assert any("coupe l’alimentation déclarée" in line for line in lines)
    # Sans récolte, aucune ligne n'invente cette conséquence.
    assert not any("alimentation" in line for line in
                   transition_summary(before, after, {"kind": "stage", "effective_at": "2026-09-07"}))


async def test_http_assistance_version_inchangee_et_fiche_inconnue(web_context):
    client, server, *_ = web_context
    saved = await server.cultures.store.call("mutate", create())
    url = f"/api/v1/cultures/assistance/{saved['subject_id']}"
    response = await client.get(f"{url}?version={saved['version']}")
    assert response.status == 200 and response.headers["Cache-Control"] == "no-store"
    assert await response.json() == {"unchanged": True, "version": saved["version"],
                                     "valid_for_seconds": 30,
                                     "generated_at": (await response.json())["generated_at"]}
    # Une version illisible n'est pas un refus : elle vaut « je n'en ai pas ».
    for query in ("", "?version=", "?version=abc", "?version=1.5"):
        assert "items" in await (await client.get(url + query)).json()
    assert (await client.get("/api/v1/cultures/assistance/inconnu?version=1")).status == 404
