"""Équivalence entre les règles pures d'action et le gabarit rendu (lot UI 2, W1 puis W3).

Écrit **avant** que W3 touche `templates/cultures.html`, ce fichier a figé l'équivalence
entre `allowed_actions`/`stage_options` et ce que le gabarit rendait alors. W3 a remplacé
la condition en ligne par `detail.actions` : l'extraction suit désormais le nouveau
balisage — triade d'en-tête, repli « Autres opérations » et formulaire d'observation —
sans que la matrice ne perde une seule combinaison.
"""

import re
import uuid
from datetime import datetime, timezone

import pytest

from model.culture import (KINDS, STAGES, allowed_actions, creation_stages, fiche_actions,
                           first_stage, stage_options)
from model.culture_cycle import REMINDER_STATES, stage_checks
from utils.culture_store import PAGE, CultureStore

# Horloge figée, postérieure à toutes les dates saisies ici : le vert d'aujourd'hui ne doit
# pas dépendre du jour où la suite est lancée.
NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)

CREATION = {"mother": {"first": first_stage("mother", None), "stages": creation_stages("mother", None)},
            "seed": {"first": first_stage("lot", "seed"), "stages": creation_stages("lot", "seed")},
            "cutting": {"first": first_stage("lot", "cutting"), "stages": creation_stages("lot", "cutting")}}

EVENT_FORM = re.compile(r'data-culture-event data-kind="([a-z]+)"')
# La triade d'en-tête : le relevé est un lien, l'observation un formulaire dédié, et le
# contextuel un `<details id="action-…">`. Aucun de ces trois n'est deviné par le gabarit.
PRIMARY_ACTION = re.compile(r'id="action-([a-z]+)"')
# Le seul <select name="stage"> de la page ; les listes de précision de date portent aussi
# des <option>, il faut donc borner l'extraction au sélecteur de stade lui-même.
STAGE_SELECT = re.compile(r'<select name="stage">(.*?)</select>', re.S)
OPTION = re.compile(r'<option value="([a-z]+)"')
# Vérifications pertinentes : la liste rendue, lien et libellé, sans condition de stade en
# Jinja. Le bloc n'existe dans la page que si la règle pure a produit quelque chose.
CHECK_LIST = re.compile(r'<ul class="culture-checks">(.*?)</ul>', re.S)
CHECK_LINK = re.compile(r'<a href="([^"]+)">([^<]+)</a>')


def subject(kind="lot", stage="vegetatif", space="space_1", archived=False, origin_type="seed"):
    """Sujet projeté minimal : seules les clés lues par le gabarit sont nécessaires."""
    duration = {"days": 1, "weeks": 0, "remaining_days": 1, "week": 1}
    return {"id": "sujet-1", "kind": kind, "name": "Sujet", "variety": "Variété",
            "origin_type": origin_type, "version": 3, "stage": stage, "stage_at": "2026-08-01",
            "stage_precision": "date", "stage_end": "2026-09-01" if archived else None,
            "space": space, "archived": archived, "count": 3, "initial_count": 3,
            "origins": [], "periods": [], "occupations": [], "age": duration,
            "origin_at": "2026-08-01", "origin_precision": "date", "origin_age": duration,
            "clock_reliable": True, "stage_label": STAGES.get(stage, "À renseigner"),
            "latest_reading": None}


EMPTY_BUCKETS = {"overdue": [], "due_today": [], "upcoming": [], "done_today": []}


def build_detail(item, **overrides):
    """Contexte de fiche minimal, calqué sur `CultureStore._detail`.

    `stage_options` est transmis par la vue : le gabarit n'a plus sa table de rangs,
    l'équivalence porte donc sur la liste rendue par le magasin.
    """
    detail = {"subject": item, "events": [], "total": 0, "offset": 0, "page": PAGE, "photos": [],
              "descendants": [], "backfill": {"stages": [], "spaces": [], "before": None},
              "reminders": EMPTY_BUCKETS, "media": [], "actions": fiche_actions(item),
              "stage_checks": stage_checks(item),
              "stage_options": stage_options(item),
              "stage_options_full": stage_options(item, correction=True)}
    detail.update(overrides)
    return detail


def render(item, detail=None):
    from network.web.pages import render_template
    overview = {"timezone": "Europe/Paris", "today": "2026-09-07", "clock_reliable": True,
                "mothers": [], "occupants": [], "items": [], "offset": 0, "total": 0,
                "page": PAGE, "reminder_states": REMINDER_STATES}
    return render_template("cultures.html", page_title=item["name"], current_page="cultures",
                           csrf_token="jeton", overview=overview,
                           detail=detail if detail is not None else build_detail(item), error=None,
                           archives=False, stages=STAGES, spaces={"space_1": "Espace 1", "space_2": "Espace 2"},
                           event_kinds=KINDS, creation=CREATION, lighting=[],
                           # R1.8 : `return_url` et son libellé sont décidés par
                           # `CultureViews.return_link` — ancre `#culture-{id}` comprise,
                           # puisqu'elle ne vaut que pour un retour vers la liste.
                           return_url="/cultures#culture-" + item["id"],
                           return_label="Retour aux cultures")


def assert_equivalence(html, item):
    """Le gabarit rendu ne gagne ni ne perd une action par rapport aux règles pures."""
    actions = fiche_actions(item)
    promoted = [name for name in actions["primary"] if name not in ("reading", "observation")]
    # Le contextuel promu vient en premier, puis le repli : ensemble ils rendent exactement
    # les formulaires d'événement, et la note reste portée par le seul formulaire
    # d'observation. Rien n'est gagné ni perdu par rapport aux règles pures.
    assert EVENT_FORM.findall(html) == promoted + actions["other"]
    assert PRIMARY_ACTION.findall(html) == promoted
    assert html.count("data-culture-observation") == 1
    assert set(EVENT_FORM.findall(html)) | {"note"} == set(allowed_actions(item))
    reading_href = (f'/cultures/solutions?target={item["id"]}'
                    '&amp;kind=reading&amp;view=saisir#saisie')
    assert html.count(f'href="{reading_href}"') >= 1
    assert '>Saisir un relevé</a>' in html
    assert f'href="/cultures#culture-{item["id"]}"' in html


MATRIX = [subject(kind, stage, space, archived, origin_type)
          for kind, origin_type in (("mother", "mother"), ("lot", "seed"), ("lot", "cutting"))
          for stage in (None, "germination", "enracinement", "vegetatif", "floraison", "sechage", "maintien")
          for space in (None, "space_1", "space_2")
          for archived in (False, True)]


@pytest.mark.parametrize("item", MATRIX, ids=lambda item:
                         f"{item['origin_type']}-{item['stage']}-{item['space']}-{int(item['archived'])}")
def test_actions_pures_equivalentes_au_gabarit(item):
    assert_equivalence(render(item), item)


@pytest.mark.parametrize("item", MATRIX, ids=lambda item:
                         f"{item['origin_type']}-{item['stage']}-{item['space']}-{int(item['archived'])}")
def test_verifications_pertinentes_equivalentes_au_gabarit(item):
    """Sur toute la matrice, les liens rendus sont exactement `stage_checks(item)`.

    Le gabarit portait la table des liens `/conf#…` et la condition « lot non archivé » ;
    la règle pure décide désormais des deux, et la page ne peut plus proposer de relire un
    organe que le stade ne concerne pas — ni en oublier un.
    """
    html = render(item)
    checks = stage_checks(item)
    block = CHECK_LIST.search(html)
    assert (block is not None) == bool(checks)
    assert "Vérifications pertinentes à ce stade" in html if checks else True
    rendered = CHECK_LINK.findall(block.group(1)) if block else []
    assert rendered == [(check["href"], check["label"]) for check in checks]
    for check in checks:
        assert check["reason"] in html


STAGE_CASES = [item for item in MATRIX if "stage" in allowed_actions(item)]


def test_la_matrice_couvre_encore_la_progression_de_stade():
    # Un paramétrage dérivé qui se vide n'échoue pas : il ne produit aucun cas et la suite
    # reste verte en n'ayant rien vérifié. Cette assertion transforme ce silence en échec.
    assert STAGE_CASES, "Aucun état de la matrice ne propose « stage » : règle pure changée."


@pytest.mark.parametrize("item", STAGE_CASES,
                         ids=lambda item: f"{item['origin_type']}-{item['stage']}")
def test_options_de_stade_equivalentes_au_gabarit(item):
    select = STAGE_SELECT.search(render(item))
    assert select is not None
    assert OPTION.findall(select.group(1)) == stage_options(item)


def test_stade_courant_affiche_toutes_les_options_en_correction():
    # Le gabarit ouvre la liste entière dès qu'un stade est déjà saisi (mode correction) :
    # la branche `payload.stage` du formulaire de correction, qui n'était rendue par aucun
    # test tant que le journal restait vide.
    item = subject(stage="floraison")
    assert stage_options(item) == []
    complete = stage_options(item, correction=True)
    assert complete == ["germination", "vegetatif", "floraison"]
    correction = {"id": "evt-1", "kind": "stage", "effective_at": "2026-08-15",
                  "precision": "date", "payload": {"stage": "vegetatif"}, "cancelled": False,
                  "revision": 1, "recorded_at": "2026-08-15T10:00:00+00:00",
                  "clock_reliable": True, "equipment_context": "{}", "reason": "",
                  "revisions": []}
    html = render(item, detail=build_detail(item, events=[correction], total=1))
    selects = [OPTION.findall(block) for block in STAGE_SELECT.findall(html)]
    assert complete in selects, selects
    assert '<option value="vegetatif" selected>' in html


@pytest.mark.parametrize("kind, origin_type, expected", [
    ("mother", "mother", "maintien"), ("lot", "seed", "germination"), ("lot", "cutting", "enracinement")])
def test_premier_stade_du_parcours(kind, origin_type, expected):
    assert first_stage(kind, origin_type) == expected
    assert creation_stages(kind, origin_type)[0] == expected


@pytest.mark.parametrize("item, promoted", [
    (subject("mother", "maintien", "space_1", False, "mother"), "archive"),
    (subject("mother", "maintien", None, True, "mother"), None),
    (subject("mother", "maintien", "space_1", True, "mother"), "release"),
    (subject("lot", "germination"), "stage"),
    (subject("lot", "enracinement", origin_type="cutting"), "stage"),
    (subject("lot", "vegetatif"), "stage"),
    (subject("lot", "floraison", "space_2"), "harvest"),
    (subject("lot", "floraison", "space_1"), "move"),
    (subject("lot", "sechage", "space_2"), "finish"),
    (subject("lot", "sechage", "space_2", archived=True), "release"),
    (subject("lot", "sechage", None, archived=True), None),
])
def test_triade_de_la_fiche(item, promoted):
    actions = fiche_actions(item)
    assert actions["primary"] == ["reading", "observation"] + ([promoted] if promoted else [])
    # Le contextuel promu et la note (fondue dans l'observation) ne sont jamais répétés.
    assert promoted not in actions["other"] and "note" not in actions["other"]
    assert set(actions["other"]) | {"note"} | ({promoted} if promoted else set()) == set(allowed_actions(item))


REAL_CASES = [
    ("mère en maintien", {"kind": "mother", "name": "Mère", "stage": "maintien"}),
    ("semis en germination", {"name": "Semis", "stage": "germination", "space": "space_1"}),
    ("bouture reprise en floraison", {"name": "Reprise", "origin_type": "cutting",
                                      "stage": "floraison", "space": "space_2"}),
]


@pytest.mark.parametrize("label, overrides", REAL_CASES, ids=[case[0] for case in REAL_CASES])
async def test_vue_detail_publie_les_regles_pures(tmp_path, label, overrides):
    """La fiche rendue part du contexte réel du magasin, pas d'un contexte fabriqué ici.

    Injecter `fiche_actions(item)` dans le contexte prouvait seulement que le gabarit lit la
    clé qu'on venait d'y mettre : la vue `_detail` pouvait cesser de la publier sans qu'un
    test ne bouge. On passe donc par `CultureStore.detail`, puis on rejoue l'équivalence.
    """
    store = CultureStore(tmp_path / "cultures.sqlite3", now=lambda: NOW)
    try:
        kind = overrides.get("kind", "lot")
        if overrides.get("origin_type") == "cutting":
            # Une bouture exige une mère existante : elle est créée d'abord, jamais devinée.
            mother = await store.call("mutate", {
                "request_id": str(uuid.uuid4()), "operation": "create", "kind": "mother",
                "name": "Mère de la reprise", "stage": "maintien", "origins": [],
                "origin_at": "2026-05-01", "space_at": "2026-05-01", "stage_at": "2026-05-01"})
            origins = [{"mother_id": mother["subject_id"], "count": 6}]
        else:
            origins = [] if kind == "mother" else [{"label": "Semences A", "count": 8}]
        command = {"request_id": str(uuid.uuid4()), "operation": "create", "kind": kind,
                   "origin_at": "2026-06-01", "space_at": "2026-06-01", "stage_at": "2026-06-01",
                   "origins": origins, **overrides}
        result = await store.call("mutate", command)
        detail = await store.call("detail", result["subject_id"])
    finally:
        await store.close()
    item = detail["subject"]
    assert detail["actions"] == fiche_actions(item)
    assert detail["stage_checks"] == stage_checks(item)
    assert detail["stage_options"] == stage_options(item)
    assert detail["stage_options_full"] == stage_options(item, correction=True)
    assert_equivalence(render(item, detail=detail), item)
