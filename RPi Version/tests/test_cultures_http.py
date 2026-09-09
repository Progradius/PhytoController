import json
import uuid

import pytest

from tests.test_http_server import web_context, CSRF_TOKEN
from tests.test_cultures import create


@pytest.mark.parametrize("value, expected", [
    (None, "—"),
    ("2026-09-07", "07/09/2026"),
    ("2026-10-25T00:30:00Z", "25/10/2026 à 02:30:00 (UTC+0200)"),
    ("2026-10-25T01:30:00Z", "25/10/2026 à 02:30:00 (UTC+0100)"),
    ("2026-09-06T22:30:00Z", "07/09/2026 à 00:30:00 (UTC+0200)"),
])
def test_dates_lisibles_sans_ambiguite_au_changement_heure(value, expected):
    from network.web.pages import env
    assert env.filters["culture_date"](value, "Europe/Paris") == expected


@pytest.mark.parametrize("section", ["cycles", "light", "equipment"])
def test_navigation_vue_globale_reste_dans_la_rubrique_en_selection_multiple(section):
    from network.web.pages import env
    html = env.get_template("culture_navigation.html").render(
        culture_section=section, selected=["lot-a", "lot-b"])
    assert f'<a href="/cultures/{section}">Vue globale</a>' in html
    assert html.count('aria-current="page"') == 1
    if section == "cycles":
        assert "2 cultures sélectionnées pour la comparaison" in html
    else:
        assert "Contexte de retour : 2 cultures" in html and "comparaison" not in html


@pytest.mark.parametrize("context", [{"selected": None}, {"culture_subjects": None}, {}])
def test_navigation_tolere_une_selection_absente_ou_none(context):
    from network.web.pages import env
    html = env.get_template("culture_navigation.html").render(culture_section="cycles", **context)
    assert html.count('aria-current="page"') == 1 and "culture-context" not in html


async def test_carnet_http_securite_et_absence_effet_controle(web_context, monkeypatch):
    client, server, config, sensors, supervisor = web_context
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_args: writes.append("save"))
    monkeypatch.setattr(config, "commit", lambda *_args: writes.append("commit"))
    response = await client.get("/cultures")
    assert response.status == 200
    assert "Carnet durable" in await response.text()
    assert response.headers["Cache-Control"] == "no-store"
    command = create(name='<script>alert("x")</script>')
    assert (await client.post("/api/v1/cultures", json=command)).status == 403
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    assert (await client.post("/api/v1/cultures", json=command, headers={**headers, "Origin": "http://evil.example"})).status == 403
    response = await client.post("/api/v1/cultures", json=command, headers=headers)
    assert response.status == 200, await response.text()
    result = await response.json()
    response = await client.get("/cultures/" + result["subject_id"])
    assert response.status == 200
    html = await response.text()
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    detail = await (await client.get("/api/v1/cultures/" + result["subject_id"])).json()
    assert detail["subject"]["count"] == 8
    assert (await client.get("/api/v1/cultures?offset=-1")).status == 400
    assert (await client.post("/api/v1/cultures", json=[1], headers=headers)).status == 400
    assert (await client.post("/api/v1/cultures", data="{", headers={**headers, "Content-Type": "application/json"})).status == 400
    assert (await client.post("/api/v1/cultures", json={"note": "x" * 70000}, headers=headers)).status == 413
    for format_name in ("json", "csv", "sqlite3"):
        response = await client.get("/api/v1/cultures/export?format=" + format_name)
        assert response.status == 200 and "attachment" in response.headers["Content-Disposition"]
    assert config.current.to_json() == original and writes == []
    assert sensors.reconfigured == 0
    assert (await client.get("/health/ready")).status == 200


async def test_backfill_http_complete_le_passe_sans_toucher_au_stade(web_context):
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    command = create("Reprise", stage="floraison", space="space_2",
                     origin_at="2026-06-01", space_at="2026-08-01", stage_at="2026-08-01")
    saved = await (await client.post("/api/v1/cultures", json=command, headers=headers)).json()
    detail = await (await client.get("/api/v1/cultures/" + saved["subject_id"])).json()
    assert detail["backfill"] == {"stages": ["germination", "vegetatif"],
                                  "spaces": ["space_1", "space_2"], "before": "2026-08-01"}
    step = {"kind": "move", "effective_at": "2026-06-05", "precision": "date", "payload": {"space": "space_1"}}
    body = {"request_id": str(uuid.uuid4()), "operation": "backfill", "subject_id": saved["subject_id"],
            "version": saved["version"], "steps": [step]}
    response = await client.post("/api/v1/cultures", json=body, headers=headers)
    assert response.status == 200, await response.text()
    updated = await response.json()
    # Onglet périmé : la version attendue protège la saisie, même sur une étape passée.
    assert (await client.post("/api/v1/cultures", json={**body, "request_id": str(uuid.uuid4())}, headers=headers)).status == 409
    late = {**body, "request_id": str(uuid.uuid4()), "version": updated["version"],
            "steps": [{"kind": "stage", "effective_at": "2026-08-01", "precision": "date",
                       "payload": {"stage": "vegetatif"}}]}
    assert (await client.post("/api/v1/cultures", json=late, headers=headers)).status == 400
    detail = await (await client.get("/api/v1/cultures/" + saved["subject_id"])).json()
    assert detail["subject"]["stage"] == "floraison" and detail["subject"]["stage_at"] == "2026-08-01"
    assert [period["stage"] for period in detail["subject"]["periods"]] == ["floraison"]
    assert [space["space"] for space in detail["subject"]["occupations"]] == ["space_1", "space_2"]
    page = await (await client.get("/cultures/" + saved["subject_id"])).text()
    assert "Compléter le parcours passé" in page and "Ajouter une étape passée" in page
    # La section est atteignable : c'est l'ancre que vise la suggestion de rattrapage.
    assert 'id="backfill"' in page
    aid = await (await client.get("/api/v1/cultures/assistance/" + saved["subject_id"])).json()
    row = next(item for item in aid["items"] if item["id"] == "backfill")
    assert row["href"] == f"/cultures/{saved['subject_id']}#backfill"
    assert row["category"] == "Information manquante"


async def test_panne_carnet_ne_degrade_pas_controle(web_context, monkeypatch):
    from utils.culture_store import CultureUnavailable
    client, server, *_ = web_context
    async def failed(*_args):
        raise CultureUnavailable("Carnet indisponible")
    monkeypatch.setattr(server.cultures.store, "call", failed)
    assert (await client.get("/cultures")).status == 503
    assert (await client.get("/api/v1/cultures")).status == 503
    assert (await client.get("/")).status == 200
    assert (await client.get("/health/ready")).status == 200


async def test_accueil_vide_propose_la_premiere_culture_sans_inventer_de_zero(web_context):
    client, *_ = web_context
    page = await (await client.get("/cultures")).text()
    assert 'id="agenda"' in page and "Ajouter ma première culture" in page
    # Un carnet vide n'a rien à compter : aucune ligne ne doit annoncer un total nul.
    assert "Aucun rappel en cours dans le carnet." in page
    assert "Aucune opération enregistrée pour l’instant." in page
    assert "0 à venir" not in page and "0 culture" not in page
    assert "<script>" not in page


async def test_accueil_montre_le_rappel_en_retard_et_son_suivi(web_context):
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot agenda"), headers=headers)).json()
    reminder = {"request_id": str(uuid.uuid4()), "operation": "reminder", "title": "Rincer le bac",
                "target": saved["subject_id"], "due_date": "2020-01-01", "interval_days": 0, "note": ""}
    created = await (await client.post("/api/v1/cultures/cycles", json=reminder, headers=headers)).json()
    page = await (await client.get("/cultures")).text()
    assert f'id="reminder-{created["id"]}"' in page and "tabindex=\"-1\"" in page
    assert "En retard" in page and "Rincer le bac" in page
    # Le suivi part de l'accueil et y revient : même opération que sur les cycles, retour distinct.
    assert 'data-operation="reminder_action"' in page and 'data-cycle-return="agenda"' in page
    assert 'data-reminder-postpone' in page
    # L'agenda précède l'occupation des espaces : c'est la première chose lue.
    assert page.index('id="agenda"') < page.index('aria-label="Occupation des espaces"')


async def test_archives_sans_agenda_ni_occupation_en_tete(web_context):
    client, *_ = web_context
    page = await (await client.get("/cultures?archives=1")).text()
    assert 'id="agenda"' not in page
    assert 'aria-label="Occupation des espaces"' not in page
    assert "<h1>Archives</h1>" in page and "Aucune archive." in page


async def test_fiche_porte_l_entete_la_triade_et_ses_ancres(web_context):
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot fiche"), headers=headers)).json()
    subject_id = saved["subject_id"]
    page = await (await client.get("/cultures/" + subject_id)).text()
    assert '<header class="culture-head">' in page and "<h1>Lot fiche</h1>" in page
    assert "8 plantes restantes · 8 au départ" in page and "Espace 1 · En cours" in page
    # Le relevé est un lien contextualisé, jamais un formulaire de plus sur la fiche.
    assert f'href="/cultures/solutions?target={subject_id}&amp;kind=reading#saisie"' in page
    assert "data-culture-observation" in page and 'id="observation"' in page
    assert 'id="synthese"' in page and 'id="releves"' in page and 'id="photos"' in page and 'id="bilan"' in page
    detail = await (await client.get("/api/v1/cultures/" + subject_id)).json()
    assert detail["events"], "la création écrit au moins une entrée"
    for event in detail["events"]:
        assert f'id="event-{event["id"]}"' in page
    assert "Aucune photo pour cette culture." in page
    assert "<script>" not in page


async def test_fiche_archivee_garde_son_dernier_releve(web_context):
    # Le relevé était retrouvé en balayant les listes d'accueil : une mère archivée puis
    # libérée n'y figure plus (ni dans `items`, filtré sur l'archivage, ni dans `occupants`,
    # dont l'espace est retombé à None) et son relevé disparaissait de sa propre fiche.
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Mère relevé", kind="mother"),
                                     headers=headers)).json()
    subject_id = saved["subject_id"]
    reading = {"request_id": str(uuid.uuid4()), "operation": "entry", "kind": "reading",
               "targets": [subject_id], "effective_at": "2026-09-02", "ph": 6.2}
    response = await client.post("/api/v1/cultures/solutions", json=reading, headers=headers)
    assert response.status == 200, await response.text()
    archive = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": subject_id,
               "version": saved["version"], "kind": "archive", "effective_at": "2026-09-03",
               "payload": {"note": "Mère retirée"}}
    assert (await client.post("/api/v1/cultures", json=archive, headers=headers)).status == 200

    overview = await (await client.get("/api/v1/cultures")).json()
    assert all(item["id"] != subject_id for item in overview["items"] + overview["occupants"])
    page = await (await client.get("/cultures/" + subject_id)).text()
    assert "Dernier relevé : 02/09/2026 · pH 6.2" in page
    assert "Aucun relevé rattaché à cette culture" not in page


async def test_creation_propose_les_deux_situations_et_ses_stades(web_context):
    from model.culture import creation_stages, first_stage
    client, *_ = web_context
    page = await (await client.get("/cultures")).text()
    # Les deux entrées sont un choix explicite, coché par défaut sur « Je démarre ».
    assert '<input type="radio" name="situation" value="new" checked> Je démarre une culture' in page
    assert '<input type="radio" name="situation" value="ongoing"> Elle est déjà en cours' in page
    assert page.count('name="situation"') == 4
    # Regroupement identité/origine puis situation actuelle, et frise avant validation.
    assert page.count("<legend>Identité et origine</legend>") == 2
    assert page.count("<legend>Situation actuelle</legend>") == 2
    assert page.count("<ol data-creation-summary></ol>") == 2
    # La frise n'est pas une annonce : elle se relit, elle ne se fait pas lire à chaque frappe.
    recap = page[page.index('class="culture-creation-summary"'):]
    assert "aria-live" not in recap[:recap.index("</section>")]
    # Stades et premier stade du parcours : rendus depuis les règles pures, pas devinés.
    assert f'data-first-stage="{first_stage("mother", None)}"' in page
    assert f'data-first-stage="{first_stage("lot", "seed")}"' in page
    assert f'data-stages-mother="{",".join(creation_stages("mother", None))}"' in page
    assert f'data-stages-seed="{",".join(creation_stages("lot", "seed"))}"' in page
    assert f'data-stages-cutting="{",".join(creation_stages("lot", "cutting")) }"' in page
    assert f'data-first-stage-cutting="{first_stage("lot", "cutting")}"' in page
    # Le lot propose l'union des deux parcours ; le script n'en masque que les absents.
    lot = page[page.index('id="creer-lot"'):]
    options = lot[lot.index('<select name="stage">'):]
    options = options[:options.index("</select>")]
    rendered = [part.split('"')[0] for part in options.split('<option value="')[1:]]
    assert rendered == ["germination", "enracinement", "vegetatif", "floraison", "sechage"]
    assert set(rendered) == set(creation_stages("lot", "seed")) | set(creation_stages("lot", "cutting"))
    assert "<script>" not in page


async def test_changement_de_stade_rend_exactement_les_options_pures(web_context):
    from model.culture import stage_options
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot stades"), headers=headers)).json()
    page = await (await client.get("/cultures/" + saved["subject_id"])).text()
    detail = await (await client.get("/api/v1/cultures/" + saved["subject_id"])).json()
    select = page[page.index('<select name="stage">'):]
    rendered = [line.split('"')[0] for line in select[:select.index("</select>")].split('<option value="')[1:]]
    assert rendered == detail["stage_options"] == stage_options(detail["subject"])


async def test_fiche_rend_les_verifications_du_stade_et_annonce_ses_aides(web_context):
    """Vérifications propres au stade et à l'espace, zone d'aides annoncée aux lecteurs.

    Un semis en germination à l'espace 1 ne relit ni la ventilation (le stade ne la
    concerne pas) ni les réglages de l'espace 2 : la page ne propose plus une liste fixe.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot vérifs"), headers=headers)).json()
    page = await (await client.get("/cultures/" + saved["subject_id"])).text()
    assert "Vérifications pertinentes à ce stade" in page
    assert '<a href="/conf#daily-timer-1">Éclairage vérifié</a>' in page
    assert '<a href="/conf#cyclic-2">Sortie locale vérifiée</a>' in page
    assert "Ventilation commune vérifiée" not in page and "/conf#daily-timer-2" not in page
    detail = await (await client.get("/api/v1/cultures/" + saved["subject_id"])).json()
    assert detail["stage_checks"] == [
        {"key": "lighting", "label": "Éclairage vérifié", "href": "/conf#daily-timer-1",
         "reason": "La photopériode de levée est déclarée dans les minuteries."},
        {"key": "pump", "label": "Sortie locale vérifiée", "href": "/conf#cyclic-2",
         "reason": "L’apport de solution conditionne la levée."}]
    aid = await (await client.get(f"/api/v1/cultures/assistance/{saved['subject_id']}")).json()
    assert {item["category"] for item in aid["items"]} <= {"À faire", "À vérifier", "Information manquante"}
    assert 'aria-live="polite"' in page
