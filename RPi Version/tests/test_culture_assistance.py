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
    """Zéro, une, puis deux associations : trois constats distincts, jamais confondus.

    « Rien n'est déclaré » appelle une saisie, « deux choses le sont » une correction : les
    réunir sous « inconnue ou non unique » répondait la même chose aux deux (R3.5).
    """
    lot = await cultures.call("mutate", create(space="space_2"))
    identifier = lot["subject_id"]
    reading = {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": "reading",
               "targets": [identifier], "effective_at": "2026-08-05", "ph": 6.0}

    async def preview():
        return await cultures.call("preview", "solution", {**reading, "request_id": str(uuid.uuid4())})

    async def lines():
        return [line for line in (await preview())["summary"] if "limentation" in line]

    # Aucune solution déclarée à cette date : l'absence est nommée, avec l'action qui la lève.
    assert await lines() == ["Aucune alimentation déclarée à cette date pour Semis. "
                             "La cible saisie est conservée."]
    assert {"label": "Déclarer la solution présente",
            "href": "/cultures/solutions#saisie"} in (await preview())["links"]

    await cultures.call("solution_mutate", entry())
    assert len(await lines()) == 1
    single = (await lines())[0]
    assert single.startswith("Alimentation déclarée à cette date pour Semis : Réservoir de l’espace 2")
    assert "(association depuis 2026-07-31)" in single
    assert {"label": "Ouvrir Réservoir de l’espace 2",
            "href": "/cultures/solutions?target=reservoir_2#reservoirs"} in (await preview())["links"]

    # Deux associations simultanées sont hors d'atteinte du parcours normal — un lot
    # n'occupe qu'un espace — mais la branche existe et doit les nommer toutes les deux.
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
    several = (await lines())[0]
    assert len(await lines()) == 1 and several.startswith("Plusieurs alimentations déclarées à cette date pour Semis : ")
    assert "Réservoir de l’espace 2" in several and "Bac de bouturage de l’espace 1" in several
    assert {"label": "Vérifier les solutions déclarées",
            "href": "/cultures/solutions#reservoirs"} in (await preview())["links"]


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
    # Le début du séchage voyage dans la charge utile : annoncé s'il est saisi, jamais inventé.
    with_drying = transition_summary(before, after, {"kind": "harvest", "effective_at": "2026-09-07",
                                                     "payload": {"drying_at": "2026-09-08"}})
    assert "Début du séchage déclaré : 2026-09-08" in with_drying
    assert not any("séchage déclaré" in line for line in lines)


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


async def test_plages_applicables_ordre_strict_ecart_et_absence(cultures):
    """Une ligne par mesure renseignée, la source nommée, l'absence dite (R3.4).

    L'ordre de résolution est celui du carnet et il est strict : cible directe, puis sujet
    alimenté, puis réservoir, sans qu'aucune borne ne soit fusionnée entre deux sources.
    """
    from tests.test_culture_targets import target

    lot = await cultures.call("mutate", create(space="space_2"))
    identifier = lot["subject_id"]
    await cultures.call("solution_mutate", entry())

    async def lines(command, **extra):
        preview = await cultures.call("preview", "solution",
                                      {**command, "request_id": str(uuid.uuid4()), **extra})
        return [line for line in preview["summary"] if "lage applicable" in line]

    # Relevé du réservoir : le lot de l'espace 2 en est le sujet alimenté à cette date.
    measured = entry("reading", "2026-08-05", ph=6.5)
    # Aucune plage enregistrée : l'absence est explicite et ne devient jamais un zéro.
    assert await lines(measured) == ["Aucune plage applicable à cette cible à cette date (pH)."]

    await cultures.call("target_mutate", target(ph_min="5,8", ph_max="6,4"))
    assert await lines(measured) == ["Plage applicable pH 5,8–6,4 (source : Réservoir de la mesure "
                                     "— Réservoir de l’espace 2, plage du 2026-08-01) ; écart : +0,1."]

    # Une plage du sujet alimenté l'emporte sur celle du réservoir, sans mélange des bornes.
    await cultures.call("target_mutate", target(target=identifier, ph_min="5,5", ph_max="6"))
    fed = ("Plage applicable pH 5,5–6 (source : Sujet alimenté par la solution — Semis, "
           "plage du 2026-08-01) ; écart : +0,5.")
    assert await lines(measured) == [fed]
    # Écart négatif, et EC non renseignée : aucune ligne d'EC, donc aucun écart inventé.
    assert await lines(measured, ph=5.0) == ["Plage applicable pH 5,5–6 (source : Sujet alimenté "
                                             "par la solution — Semis, plage du 2026-08-01) ; écart : -0,5."]
    # Une mesure dans la plage le dit aussi, plutôt que de taire l'écart.
    assert "écart : aucun, la mesure est dans la plage" in (await lines(measured, ph=5.7))[0]
    # EC renseignée alors que la plage ne borne que le pH : la cible d'EC n'est pas fabriquée.
    assert await lines(measured, ec=1.4) == [fed, "Aucune plage applicable à cette cible à cette date (EC)."]

    # Relevé visant la culture elle-même : la cible directe est la source retenue.
    direct = {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": "reading",
              "targets": [identifier], "effective_at": "2026-08-05", "ph": 6.5}
    assert await lines(direct) == ["Plage applicable pH 5,5–6 (source : Cible directe de la mesure "
                                   "— Semis, plage du 2026-08-01) ; écart : +0,5."]


def test_categories_priorite_et_ancienneté_du_dernier_releve():
    """Trois catégories, un ordre d'affichage, et une ancienneté énoncée sans jugement."""
    from tests.test_culture_actions import subject

    item = subject(stage="floraison", space="space_2")
    rows = suggestions(item, [], [], "2026-09-07", "Europe/Paris", True)
    assert {r["category"] for r in rows} <= {"À faire", "À vérifier", "Information manquante"}
    reading = next(r for r in rows if r["id"] == "reading")
    assert reading["category"] == "Information manquante"
    assert reading["reason"].startswith("Aucun relevé disponible")

    dated = {**item, "latest_reading": {"effective_at": "2026-09-02", "ph": 6.0, "ec": None}}
    reading = next(r for r in suggestions(dated, [], [], "2026-09-07", "Europe/Paris", True)
                   if r["id"] == "reading")
    assert reading["category"] == "À vérifier"
    assert reading["reason"] == "Dernier relevé saisi il y a 5 jours (le 2026-09-02)."
    today = {**item, "latest_reading": {"effective_at": "2026-09-07"}}
    assert "aujourd’hui" in next(r for r in suggestions(today, [], [], "2026-09-07", "Europe/Paris", True)
                                if r["id"] == "reading")["reason"]

    # Priorité : une échéance dépassée passe devant la vérification, elle-même devant le manque.
    # Le parcours est complet ici : le rattrapage n'a rien à signaler et ne brouille pas l'ordre.
    complete = {**item, "periods": [{"stage": stage, "start": "2026-08-01", "end": None,
                                     "precision": "date"} for stage in ("germination", "vegetatif")]}
    due = [{"id": "r1", "state": "planned", "due_date": "2026-09-01", "title": "Taille"}]
    ordered = suggestions(complete, [], due, "2026-09-07", "Europe/Paris", True)
    assert [r["category"] for r in ordered] == ["À faire", "À vérifier", "Information manquante"]
    assert [r["id"] for r in ordered] == ["reminder-r1", "check-stage", "reading"]


def test_manque_du_poids_et_de_la_photo_finale_d_un_lot_en_sechage():
    """Un lot en séchage sans poids ni photo : une information manquante, pas une alarme."""
    from tests.test_culture_actions import subject

    item = subject(stage="sechage", space="space_2")
    rows = suggestions(item, [], [], "2026-09-07", "Europe/Paris", True)
    balance = next(r for r in rows if r["id"] == "balance")
    assert balance["category"] == "Information manquante"
    assert balance["href"].endswith("#action-finish") and balance["action"] == "Terminer le séchage"
    # Une photo déjà enregistrée depuis ce stade suffit à retirer l'aide : elle ne réclame
    # pas les deux données, elle signale qu'aucune des deux n'existe.
    assert not any(r["id"] == "balance" for r in
                   suggestions(item, [], [], "2026-09-07", "Europe/Paris", True, 1))
    # Un poids déjà déclaré la retire également.
    weighed = {**item, "balance": {"weight_g": 120}}
    assert not any(r["id"] == "balance" for r in
                   suggestions(weighed, [], [], "2026-09-07", "Europe/Paris", True))
    # Aucun autre stade ne la produit.
    assert not any(r["id"] == "balance" for r in
                   suggestions(subject(stage="floraison", space="space_2"), [], [],
                               "2026-09-07", "Europe/Paris", True))


def test_le_rattrapage_pointe_sa_propre_section():
    """R1.6 : la suggestion de rattrapage vise `#backfill`, pas le journal."""
    from tests.test_culture_actions import subject

    item = subject(stage="floraison", space="space_2")
    item["periods"] = [{"stage": "floraison", "start": "2026-08-01", "end": None, "precision": "date"}]
    row = next(r for r in suggestions(item, [], [], "2026-09-07", "Europe/Paris", True)
               if r["id"] == "backfill")
    assert row["href"] == "/cultures/sujet-1#backfill"
