"""Contrat des huit macros de présentation de la remédiation web (fiche R0.3).

Trois exigences y sont vérifiées, et aucune règle métier n'y est répliquée :

* les huit macros rendent, sous `StrictUndefined`, avec des données **minimales** puis
  **complètes** — c'est ce qui protège du piège des attributs optionnels, l'environnement
  de production (`network/web/pages.py`) étant lui en `Undefined` permissif ;
* le rendu reste autoéchappé et n'émet ni `<script`, ni `style=`, ni gestionnaire `on*=`,
  la CSP du dépôt étant sans `unsafe-inline` ;
* chaque exemple documenté dans `docs/development/contributing.md` **compile** : un exemple
  faux dans la documentation est un piège pour la page suivante qui le recopie.
"""

import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "network" / "web" / "templates"
CONTRIBUTING = ROOT / "docs" / "development" / "contributing.md"

MACROS = ("compact_header", "empty_state", "alarm_summary", "equipment_row", "journal_entry",
          "field_group", "chart_detail", "network_state")

# Un attribut `on*` réellement dangereux, sans attraper les mots qui finissent par « on »
# suivis d'un `=` dans du texte rendu.
INLINE_HANDLER = re.compile(r"\son[a-z]+\s*=", re.IGNORECASE)


@pytest.fixture(name="module")
def _module():
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined)
    return env.get_template("macros/ui.html").module


def sans_inline(rendered):
    """Aucun script, style inline ou gestionnaire d'événement dans le balisage produit."""
    assert "<script" not in rendered.lower()
    assert "style=" not in rendered.lower()
    assert not INLINE_HANDLER.search(rendered)


# Données minimales : uniquement ce que la signature exige. Les clés optionnelles sont
# volontairement absentes, puisque c'est le cas que `StrictUndefined` fait échouer.
MINIMAL = {
    "compact_header": lambda ui: ui.compact_header("Serre"),
    "empty_state": lambda ui: ui.empty_state("Aucun relevé", "Choisissez une cible."),
    "alarm_summary": lambda ui: ui.alarm_summary(
        {"problem": "Capteur absent", "consequence": "Mesure indisponible", "action": "Vérifier"}),
    "equipment_row": lambda ui: ui.equipment_row(
        {"id": "heater", "name": "Chauffage", "state": "Arrêt", "reason": "Consigne atteinte"}),
    "journal_entry": lambda ui: ui.journal_entry(
        {"date": "10/09/2026", "operation": "Observation", "target": "Mère A", "summary": "Feuillage"}),
    "field_group": lambda ui: ui.field_group("Observation"),
    "chart_detail": lambda ui: ui.chart_detail({"label": "Relevé", "cells": []}),
    "network_state": lambda ui: ui.network_state(),
}

# Données complètes : toutes les clés optionnelles renseignées.
COMPLETE = {
    "compact_header": lambda ui: ui.compact_header(
        "Serre", ["Données fraîches"], {"href": "#equipements", "label": "Équipements"},
        [{"href": "/conf", "label": "Configuration"}]),
    "empty_state": lambda ui: ui.empty_state(
        "Aucun relevé", "Choisissez une cible.", {"href": "#saisie", "label": "Saisir un relevé"}),
    "alarm_summary": lambda ui: ui.alarm_summary(
        {"problem": "Capteur absent", "consequence": "Mesure indisponible", "action": "Vérifier"}),
    "equipment_row": lambda ui: ui.equipment_row(
        {"id": "heater", "name": "Chauffage", "state": "Arrêt", "reason": "Consigne atteinte",
         "next_transition": "18:30"}, True),
    "journal_entry": lambda ui: ui.journal_entry(
        {"id": "abc", "date": "10/09/2026", "operation": "Observation", "target": "Mère A",
         "summary": "Feuillage", "photo": {"url": "/media/1.jpg", "caption": "Feuille"}}),
    "field_group": lambda ui: ui.field_group("Observation", "Déclaration dans le carnet"),
    "chart_detail": lambda ui: ui.chart_detail(
        {"label": "Relevé", "cells": [{"label": "pH", "value": "6,1"}, {"label": "EC", "value": None}]}),
    "network_state": lambda ui: ui.network_state(),
}


def test_les_huit_macros_sont_exportees(module):
    assert set(MACROS) <= set(vars(module))


@pytest.mark.parametrize("name", MACROS)
def test_rendu_minimal_sans_inline(module, name):
    rendered = MINIMAL[name](module)
    assert rendered.strip(), f"{name} ne rend rien avec des données minimales."
    sans_inline(rendered)


@pytest.mark.parametrize("name", MACROS)
def test_rendu_complet_sans_inline(module, name):
    rendered = COMPLETE[name](module)
    assert rendered.strip(), f"{name} ne rend rien avec des données complètes."
    sans_inline(rendered)


def test_autoechappement(module):
    """Une valeur hostile est échappée, dans le texte comme dans un attribut."""
    rendered = module.alarm_summary(
        {"problem": "<capteur>", "consequence": '"guillemets"', "action": "a & b"})
    assert "&lt;capteur&gt;" in rendered
    assert "<capteur>" not in rendered
    assert "a &amp; b" in rendered

    lien = module.empty_state("Vide", "Texte", {"href": '"><script>x</script>', "label": "Aller"})
    assert "<script>" not in lien
    sans_inline(lien)


def test_attributs_data_attendus(module):
    """Les seuls attributs `data-*` du contrat, ceux que les JS existants peuvent lire."""
    assert 'data-equipment="heater"' in COMPLETE["equipment_row"](module)
    assert "data-network-state" in COMPLETE["network_state"](module)


def test_journal_entry_pose_l_ancre_focalisable(module):
    """`event-{id}` en `tabindex="-1"` : le retour après enregistrement focalise l'élément."""
    avec_id = COMPLETE["journal_entry"](module)
    assert 'id="event-abc"' in avec_id
    assert 'tabindex="-1"' in avec_id
    # Sans identifiant, aucune ancre inventée : un `event-` vide serait une cible morte.
    assert "id=\"event-" not in MINIMAL["journal_entry"](module)


def test_chart_detail_rend_non_renseigne_jamais_zero(module):
    rendered = module.chart_detail({"label": "Relevé", "cells": [{"label": "pH", "value": None}]})
    assert "Non renseigné" in rendered
    assert ">0<" not in rendered


def test_equipment_row_utilise_le_caller(module):
    """Le bloc `caller` remplace le motif par défaut, il ne s'y ajoute pas."""
    equipment = {"id": "heater", "name": "Chauffage", "state": "Arrêt", "reason": "Motif par défaut"}
    with_caller = module.equipment_row(equipment, caller=lambda: Markup("<p>Détail fourni</p>"))
    assert "Détail fourni" in with_caller
    assert "Motif par défaut" not in with_caller


def exemples_documentes():
    """Les lignes du bloc ```jinja de `contributing.md`, une par macro."""
    texte = CONTRIBUTING.read_text(encoding="utf-8")
    blocs = re.findall(r"```jinja\n(.*?)```", texte, re.DOTALL)
    assert blocs, "Aucun bloc d'exemple ```jinja dans contributing.md."
    lignes = [ligne.strip() for bloc in blocs for ligne in bloc.splitlines() if ligne.strip()]
    assert lignes, "Le bloc d'exemples de contributing.md est vide."
    return lignes


def test_chaque_macro_a_un_exemple_documente():
    lignes = exemples_documentes()
    for name in MACROS:
        assert any(f"ui.{name}(" in ligne for ligne in lignes), f"{name} n'a pas d'exemple documenté."


@pytest.mark.parametrize("ligne", exemples_documentes())
def test_les_exemples_de_contributing_compilent(ligne):
    """Un exemple faux dans la documentation est recopié tel quel dans la page suivante."""
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True, undefined=StrictUndefined)
    source = "{% import 'macros/ui.html' as ui %}\n" + ligne
    rendered = env.from_string(source).render()
    assert rendered.strip(), f"L'exemple documenté ne rend rien : {ligne}"
    sans_inline(rendered)
