"""Règle unique de mise en forme des nombres affichés (`model/nombre.py`, fiche R1.7).

Le module est pur : aucune dépendance web. Les filtres Jinja et les phrases de présentation
des modèles y délèguent ; ces tests figent la règle et vérifient que ses consommateurs
écrivent un même nombre de la même façon.
"""

import json
import math
from pathlib import Path

import pytest

from model.nombre import nombre_texte


VECTEURS = json.loads((Path(__file__).resolve().parent / "fixtures" / "nombre-vecteurs.json")
                      .read_text(encoding="utf-8"))["cas"]

SPECIAUX = {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}


def _valeur(cas):
    return SPECIAUX[cas["special"]] if "special" in cas else cas["valeur"]


def _nom(cas):
    return f"{cas.get('special', cas.get('valeur'))}@{cas['decimales']}"


@pytest.mark.parametrize("cas", VECTEURS, ids=_nom)
def test_regle_unique(cas):
    """Les vecteurs sont **partagés** avec `tests/js/nombre_format.test.cjs`.

    Figer les valeurs d'un seul côté laissait passer une divergence d'arrondi : `f"{x:.2f}"`
    arrondit le binaire au pair, `Intl.NumberFormat` arrondit les milieux à l'écart de zéro.
    Les deux implémentations sont donc éprouvées sur la même liste, cas limites compris
    (`x,xx5`, multiples de 0,0625 d'un DS18B20, absences, bornes de décimales).
    """
    assert nombre_texte(_valeur(cas), cas["decimales"], cas.get("unite")) == cas["attendu"]


def test_vecteurs_couvrent_les_milieux_et_les_absences():
    """Le fichier de vecteurs reste une garde, pas une liste qu'on peut vider."""
    textes = {_nom(cas) for cas in VECTEURS}
    assert {"2.5@0", "0.015@2", "1.005@2", "21.125@2", "nan@2", "None@2"} <= textes
    # L'arrondi du navigateur, pas celui de `format` : ces trois-là les séparent.
    attendus = {_nom(cas): cas["attendu"] for cas in VECTEURS}
    assert attendus["2.5@0"] == "3" and attendus["0.015@2"] == "0,02" and attendus["21.125@2"] == "21,13"
    assert f"{2.5:.0f}" == "2" and f"{0.015:.2f}" == "0.01"


def test_module_pur_sans_dependance_web():
    """Le module n'importe que la bibliothèque standard : ni Jinja, ni aiohttp, ni `network`."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "model" / "nombre.py"
    imports = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
    assert imports <= {"__future__", "decimal", "math"}


@pytest.mark.parametrize("value,decimals,unit", [
    (6.1, 2, None), (1.1 + 0.35, 2, "mS/cm"), (None, 2, None), ("5,8", 1, None), (math.nan, 2, None),
])
def test_filtres_jinja_delegent_a_la_regle(value, decimals, unit):
    from network.web import pages

    attendu = nombre_texte(value, decimals, unit)
    assert pages.env.filters["nombre_texte"](value, decimals, unit) == attendu
    assert pages.env.filters["nombre"](value, decimals, unit) == f'<span class="num">{attendu}</span>'


def test_synthese_de_courbe_et_filtre_ecrivent_le_meme_nombre():
    """`chart_summary` (modèle, publié par l'API) et le filtre des gabarits : même texte."""
    from model.culture_solution import chart_summary
    from network.web import pages

    points = [{"at": "2026-08-02T10:00:00+00:00", "target": "reservoir_2", "period": "p1", "ec": 1.1 + 0.35},
              {"at": "2026-08-03T10:00:00+00:00", "target": "reservoir_2", "period": "p1", "ec": 1.8}]
    synthese = chart_summary(points, "ec", "EC", "mS/cm", "Europe/Paris", {"reservoir_2": "Réservoir"})
    rendu = pages.env.from_string(
        "minimum {{ a|nombre_texte(2, u) }}, moyenne {{ m|nombre_texte(2, u) }}, maximum {{ b|nombre_texte(2, u) }}"
    ).render(a=1.1 + 0.35, m=(1.1 + 0.35 + 1.8) / 2, b=1.8, u="mS/cm")
    assert rendu == "minimum 1,45 mS/cm, moyenne 1,63 mS/cm, maximum 1,80 mS/cm"
    assert rendu in synthese
    assert "1.4500000000000002" not in synthese and "1.45" not in synthese
