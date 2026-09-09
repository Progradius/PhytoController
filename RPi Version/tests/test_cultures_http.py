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


async def test_carte_de_rappel_offre_fait_et_reporter_en_deux_boutons(web_context):
    """Deux gestes, deux boutons d'envoi : la valeur est portée par le bouton cliqué.

    Le sélecteur d'action disparaît ; l'annulation, qui n'est pas un geste du quotidien,
    reste offerte sous un repli. La route et la charge utile ne changent pas.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot boutons"), headers=headers)).json()
    reminder = {"request_id": str(uuid.uuid4()), "operation": "reminder", "title": "Rincer le bac",
                "target": saved["subject_id"], "due_date": "2020-01-01", "interval_days": 0, "note": ""}
    assert (await client.post("/api/v1/cultures/cycles", json=reminder, headers=headers)).status == 200
    page = await (await client.get("/cultures")).text()
    assert 'data-operation="reminder_action"' in page and 'data-cycle-return="agenda"' in page
    assert 'name="action" value="done" data-reminder-action="done">Fait<' in page
    assert 'name="action" value="postponed" data-reminder-action="postponed">Reporter<' in page
    assert 'name="action" value="cancelled" data-reminder-action="cancelled">Annuler ce rappel<' in page
    assert "<summary>Autres actions</summary>" in page
    assert 'data-reminder-action><option value="done">' not in page
    assert "Enregistrer le suivi" not in page
    # Sans script, la nouvelle échéance reste visible : c'est le script qui la replie.
    assert 'data-reminder-postpone><label>Nouvelle échéance' in page
    # Soumission implicite : le bouton par défaut est le premier bouton d'envoi de l'arbre.
    # Entrée dans la nouvelle échéance doit reporter, jamais clore le rappel : le premier
    # bouton du formulaire porte donc « postponed », et il est masqué.
    form = page[page.index('data-operation="reminder_action"'):]
    form = form[:form.index("</form>")]
    assert form.index('value="postponed" data-reminder-action="postponed" hidden') < form.index('value="done"')

    # La page des cycles rend la même carte : deux boutons, le repli « Autres actions » et
    # le même bouton par défaut. Le sélecteur d'action y a disparu aussi.
    cycles = await (await client.get("/cultures/cycles")).text()
    assert 'data-operation="reminder_action"' in cycles
    assert "<label>Action sur le rappel<select" not in cycles and "Enregistrer le suivi" not in cycles
    assert 'name="action" value="done" data-reminder-action="done">Fait<' in cycles
    assert "<summary>Autres actions</summary>" in cycles
    block = cycles[cycles.index('data-operation="reminder_action"'):]
    block = block[:block.index("</form>")]
    assert block.index('value="postponed" data-reminder-action="postponed" hidden') < block.index('value="done"')


async def test_transitions_guidees_marquees_par_la_regle_pure(web_context):
    """`data-guided` suit `fiche_actions`, jamais une liste écrite dans le gabarit.

    Une progression de stade, un déplacement ou une récolte changent l'état lu en tête de
    fiche ; une perte ou une correction d'identité, non. L'ancre des vérifications, elle,
    existe à tout stade : c'est là qu'atterrit une transition confirmée.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create("Lot guidé"), headers=headers)).json()
    page = await (await client.get("/cultures/" + saved["subject_id"])).text()
    detail = await (await client.get("/api/v1/cultures/" + saved["subject_id"])).json()
    guided = detail["actions"]["guided"]
    assert guided and "loss" not in guided and "identity" not in guided
    for kind in detail["actions"]["other"] + [a for a in detail["actions"]["primary"]
                                              if a not in ("reading", "observation")]:
        marked = f'data-culture-event data-kind="{kind}" data-subject="{saved["subject_id"]}"' in page
        assert marked
        form = page[page.index(f'data-kind="{kind}" data-subject'):]
        assert ("data-guided" in form[:form.index(">")]) == (kind in guided), kind
    # La correction rejoue une saisie passée : elle ne déplace pas l'état de la fiche.
    assert "data-culture-correct" in page and "data-culture-correct data-guided" not in page
    assert 'id="verifications" class="culture-checks-section" tabindex="-1"' in page


async def test_recherche_de_l_accueil_est_un_formulaire_get_borne(web_context):
    """`?q=` retrouve une culture au-delà de la première page, sans charger le carnet.

    Le champ est un formulaire GET natif : il fonctionne sans script, et le filtre local
    des cartes déjà rendues n'en est qu'un raffinement.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    cherche = await (await client.post("/api/v1/cultures", json=create("Lot ancien", variety="Kush"),
                                       headers=headers)).json()
    for index in range(40):
        assert (await client.post("/api/v1/cultures", json=create(f"Lot {index:02d}", variety="Haze"),
                                  headers=headers)).status == 200

    page = await (await client.get("/cultures")).text()
    assert '<form class="culture-search" method="get" action="/cultures"' in page
    assert 'name="q"' in page and 'data-culture-search' in page
    # La liste est paginée à quarante : la plus ancienne culture n'y figure pas. Elle reste
    # visible parmi les occupants des espaces, qui ne sont pas une liste paginée.
    listing = page[page.index('id="liste"'):]
    assert listing.count('data-culture-item=') == 40
    assert f'/cultures/{cherche["subject_id"]}' not in listing

    found = await (await client.get("/cultures?q=kush")).text()
    assert f'/cultures/{cherche["subject_id"]}' in found and "Lot ancien" in found
    assert found.count('data-culture-item=') == 1
    # La recherche voyage avec la pagination et se laisse effacer.
    assert "Effacer la recherche" in found
    data = await (await client.get("/api/v1/cultures?q=kush")).json()
    assert [item["id"] for item in data["items"]] == [cherche["subject_id"]]
    assert data["total"] == 1 and data["search"] == "kush"

    empty = await (await client.get("/cultures?q=introuvable")).text()
    assert "Aucune culture ne porte « introuvable »" in empty
    assert "Le carnet est vide" not in empty
    # Une recherche trop longue est un refus de saisie : la page répond 400 et l'API rend
    # le contrat JSON du carnet, avec le champ en cause — jamais un texte brut à part.
    assert (await client.get("/cultures?q=" + "x" * 121)).status == 400
    refused = await client.get("/api/v1/cultures?q=" + "x" * 121)
    assert refused.status == 400
    assert await refused.json() == {"error": "Recherche trop longue.", "field": "q"}


async def test_saisie_ouverte_depuis_une_fiche_montre_l_alimentation_declaree(web_context):
    """R3.5 : la source est affichée à côté du champ, le choix reste à l'opérateur.

    Ouvrir la saisie depuis une fiche (`?target=…`) énonce l'alimentation déclarée à la
    date de la saisie et sa provenance. Rien n'est sélectionné à la place de l'opérateur :
    l'association déclarée n'est pas forcément la cible qu'il veut viser, et le carnet
    n'invente aucune alimentation. Les trois cas — aucune, une, plusieurs — restent
    distincts, comme à la prévalidation.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    fed = await (await client.post("/api/v1/cultures", json=create("Lot alimenté", space="space_2"),
                                   headers=headers)).json()
    alone = await (await client.post("/api/v1/cultures", json=create("Lot sans solution", space="space_1"),
                                     headers=headers)).json()
    renewal = {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": "renewal",
               "reservoir_id": "reservoir_2", "effective_at": "2026-08-01", "volume_l": 20}
    assert (await client.post("/api/v1/cultures/solutions", json=renewal, headers=headers)).status == 200

    page = await (await client.get("/cultures/solutions?target=" + fed["subject_id"])).text()
    assert "Alimentation déclarée à cette date pour Lot alimenté : Réservoir de l’espace 2" in page
    assert "Ouvrir Réservoir de l’espace 2" in page
    # Aucune sélection automatique : la cible reste celle demandée, le réservoir n'est pas
    # coché à la place de l'opérateur.
    form = page[page.index('<form class="culture-form solution-form" data-solution-entry'):]
    form = form[:form.index("</form>")]
    assert f'<option value="{fed["subject_id"]}" data-subject-kind="lot" selected>' in form
    assert '<option value="reservoir_2" data-reservoir selected>' not in form

    empty = await (await client.get("/cultures/solutions?target=" + alone["subject_id"])).text()
    assert "Aucune alimentation déclarée à cette date pour Lot sans solution." in empty
    # Sans cible demandée, aucun repère : il n'y a pas de sujet dont parler.
    assert "data-solution-feeding" not in await (await client.get("/cultures/solutions")).text()


async def test_raccourci_observation_selon_le_nombre_de_cultures(web_context):
    """Une seule culture : le raccourci l'ouvre. Plusieurs : il ouvre le sélecteur."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    first = await (await client.post("/api/v1/cultures", json=create("Lot unique"), headers=headers)).json()
    page = await (await client.get("/cultures")).text()
    assert f'href="/cultures/{first["subject_id"]}#observation">Noter une observation</a>' in page
    assert 'id="choisir-observation"' not in page

    second = await (await client.post("/api/v1/cultures", json=create("Lot second"), headers=headers)).json()
    page = await (await client.get("/cultures")).text()
    assert 'href="#choisir-observation">Noter une observation</a>' in page
    picker = page[page.index('id="choisir-observation"'):]
    picker = picker[:picker.index("</details>")]
    for subject_id in (first["subject_id"], second["subject_id"]):
        assert f'href="/cultures/{subject_id}#observation"' in picker


async def test_archives_signalent_l_espace_encore_occupe_et_les_durees_par_stade(web_context):
    """R3.5 : le signalement et le bilan de durées vivent sur la carte d'archive.

    Le marqueur d'occupation n'existait que dans le bloc d'accueil, absent de la page
    Archives : un lot terminé sans libération n'y disait plus qu'il tenait l'espace 2. Les
    durées viennent des périodes déjà projetées ; aucune projection nouvelle n'est faite.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    saved = await (await client.post("/api/v1/cultures", json=create(
        "Lot archivé", stage="floraison", space="space_2"), headers=headers)).json()
    harvest = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": saved["subject_id"],
               "version": saved["version"], "kind": "harvest", "effective_at": "2026-08-20",
               "payload": {"drying_at": "2026-08-20", "drying_precision": "date"}}
    saved = await (await client.post("/api/v1/cultures", json=harvest, headers=headers)).json()
    finish = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": saved["subject_id"],
              "version": saved["version"], "kind": "finish", "effective_at": "2026-09-01",
              "payload": {"release": False, "weight_g": 42, "lessons": "Séchage lent"}}
    assert (await client.post("/api/v1/cultures", json=finish, headers=headers)).status == 200

    page = await (await client.get("/cultures?archives=1")).text()
    assert "<h1>Archives</h1>" in page and "Lot archivé" in page
    assert "Espace encore occupé · à libérer : Espace 2" in page
    assert "Durées par stade : Floraison 19 j, Séchage 12 j" in page
    # L'accueil garde son propre signalement : la page Archives ne l'a pas déplacé.
    home = await (await client.get("/cultures")).text()
    assert 'aria-label="Occupation des espaces"' in home and "Espace encore occupé" in home


async def test_courbes_de_solutions_portent_synthese_et_legende(web_context):
    """R3.1 et R3.3 : chaque figure annonce ce qu'elle montre et la clé de ses tracés.

    La synthèse est calculée côté serveur ; la légende nomme les encodages et une entrée par
    source. La consigne d'usage n'est plus dupliquée : le fragment de l'explorateur la rend.
    """
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    lot = await (await client.post("/api/v1/cultures", json=create("Lot courbes"), headers=headers)).json()
    renewal = {"request_id": str(uuid.uuid4()), "operation": "entry", "kind": "renewal",
               "reservoir_id": "reservoir_2", "effective_at": "2026-08-01", "volume_l": 20}
    assert (await client.post("/api/v1/cultures/solutions", json=renewal, headers=headers)).status == 200
    for day, ph in (("2026-08-02", 6.1), ("2026-08-03", 6.5)):
        reading = {"request_id": str(uuid.uuid4()), "operation": "entry", "kind": "reading",
                   "targets": [lot["subject_id"]], "effective_at": day, "ph": ph}
        assert (await client.post("/api/v1/cultures/solutions", json=reading, headers=headers)).status == 200

    page = await (await client.get("/cultures/solutions")).text()
    assert 'id="resume-ph"' in page and 'id="legende-ph"' in page
    assert 'aria-describedby="resume-ph legende-ph"' in page
    assert "2 mesures · minimum 6.10, moyenne 6.30, maximum 6.50" in page
    # Une absence reste une absence : aucune moyenne d'EC n'est inventée à 0.
    assert "EC · du 01/08/2026 au 03/08/2026 · aucune mesure · 3 lacunes" in page
    assert "Bande : plage cible résolue à la date des mesures." in page
    assert "Barre verticale : minimum et maximum du jour." in page
    assert "Lot courbes · solution manuelle" in page
    assert 'class="legend-mark legend-dot solution-source-0"' in page
    # La consigne d'usage est rendue une seule fois, par le fragment de l'explorateur.
    assert "Toucher le graphique pour choisir le point le plus proche" not in page


async def test_journal_relie_chaque_photo_a_son_entree_focalisable(web_context):
    """R1.5 b : la légende d'une photo du journal porte le lien vers son entrée.

    Sans lien dans la légende, le bouton « Ouvrir l’entrée liée » de la galerie restait caché
    précisément là où il était revendiqué. L'entrée visée est focalisable (`tabindex="-1"`),
    sans quoi le retour de focus décrit par la convention du lot 2 n'aurait nulle part où aller.
    """
    from urllib.parse import quote
    from tests.test_culture_cycles import photo_bytes
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": "space_2",
            "kind": "observation", "effective_at": "2026-09-01", "note": "Traces d’humidité"}
    saved = await (await client.post("/api/v1/cultures/journal", json=body, headers=headers)).json()
    metadata = quote(json.dumps({"request_id": str(uuid.uuid4()), "space_event_id": saved["id"],
                                 "space_event_revision": 1, "caption": "Coin nord"}))
    response = await client.post("/api/v1/cultures/journal/photos", data=photo_bytes(),
                                 headers={**headers, "Content-Type": "application/octet-stream",
                                          "X-Culture-Metadata": metadata})
    assert response.status == 200, await response.text()

    page = await (await client.get("/cultures/journal")).text()
    assert f'id="entry-{saved["id"]}" tabindex="-1"' in page
    assert f'<a href="#entry-{saved["id"]}">Ouvrir l’entrée liée</a>' in page
