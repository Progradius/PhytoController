"""Équivalence entre les règles pures d'action et le gabarit rendu (lot UI 2, W1).

Ce fichier est écrit **avant** que le lot W3 touche `templates/cultures.html` : il fige
l'équivalence entre `allowed_actions`/`stage_options` et ce que le gabarit actuel rend
réellement. Lorsque W3 remplacera la condition en ligne par un appel aux fonctions pures,
c'est ce test qui prouvera qu'aucune action n'a été gagnée ni perdue au passage.
"""

import re

import pytest

from model.culture import (KINDS, STAGES, allowed_actions, creation_stages, fiche_actions,
                           first_stage, stage_options)

EVENT_FORM = re.compile(r'data-culture-event data-kind="([a-z]+)"')
# Le seul <select name="stage"> de la page ; les listes de précision de date portent aussi
# des <option>, il faut donc borner l'extraction au sélecteur de stade lui-même.
STAGE_SELECT = re.compile(r'<select name="stage">(.*?)</select>', re.S)
OPTION = re.compile(r'<option value="([a-z]+)"')


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


def render(item):
    from network.web.pages import render_template
    overview = {"timezone": "Europe/Paris", "today": "2026-09-07", "clock_reliable": True,
                "mothers": [], "occupants": [], "items": [], "offset": 0, "total": 0}
    detail = {"subject": item, "events": [], "total": 0, "offset": 0, "photos": [],
              "descendants": [], "backfill": {"stages": [], "spaces": [], "before": None}}
    return render_template("cultures.html", page_title=item["name"], current_page="cultures",
                           csrf_token="jeton", overview=overview, detail=detail, error=None,
                           archives=False, stages=STAGES, spaces={"space_1": "Espace 1", "space_2": "Espace 2"},
                           event_kinds=KINDS, lighting=[])


MATRIX = [subject(kind, stage, space, archived, origin_type)
          for kind, origin_type in (("mother", "mother"), ("lot", "seed"), ("lot", "cutting"))
          for stage in (None, "germination", "enracinement", "vegetatif", "floraison", "sechage", "maintien")
          for space in (None, "space_1", "space_2")
          for archived in (False, True)]


@pytest.mark.parametrize("item", MATRIX, ids=lambda item:
                         f"{item['origin_type']}-{item['stage']}-{item['space']}-{int(item['archived'])}")
def test_actions_pures_equivalentes_au_gabarit(item):
    html = render(item)
    assert EVENT_FORM.findall(html) == allowed_actions(item)


@pytest.mark.parametrize("item", [item for item in MATRIX if "stage" in allowed_actions(item)],
                         ids=lambda item: f"{item['origin_type']}-{item['stage']}")
def test_options_de_stade_equivalentes_au_gabarit(item):
    select = STAGE_SELECT.search(render(item))
    assert select is not None
    assert OPTION.findall(select.group(1)) == stage_options(item)


def test_stade_courant_affiche_toutes_les_options_en_correction():
    # Le gabarit ouvre la liste entière dès qu'un stade est déjà saisi (mode correction).
    item = subject(stage="floraison")
    assert stage_options(item) == []
    assert stage_options(item, current="vegetatif") == ["germination", "vegetatif", "floraison"]


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
