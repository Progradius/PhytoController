"""Règle unique de mise en forme des nombres affichés (`model/nombre.py`, fiche R1.7).

Le module est pur : aucune dépendance web. Les filtres Jinja et les phrases de présentation
des modèles y délèguent ; ces tests figent la règle et vérifient que ses consommateurs
écrivent un même nombre de la même façon.
"""

import math

import pytest

from model.nombre import nombre_texte


@pytest.mark.parametrize("value,decimals,unit,expected", [
    # Arrondi à décimales fixes, virgule française, pas de séparateur de milliers.
    (6.1, 2, None, "6,10"),
    (1.1 + 0.35, 2, None, "1,45"),          # 1.4500000000000002 persisté, 1,45 affiché
    (12.125, 1, None, "12,1"),
    (2.5, 0, None, "2"),                    # arrondi au pair de Python, comme le filtre historique
    (12345.678, 2, None, "12345,68"),
    (-0.5, 2, None, "-0,50"),
    # Zéro est une valeur, jamais une absence.
    (0, 2, None, "0,00"),
    # Absences : None, NaN, infini, texte non numérique.
    (None, 2, None, "—"),
    (math.nan, 2, None, "—"),
    (math.inf, 2, None, "—"),
    ("abc", 2, None, "—"),
    # Chaîne à virgule d'une saisie réaffichée après refus, et chaîne à point.
    ("5,8", 2, None, "5,80"),
    (" 1.25 ", 1, None, "1,2"),
    # Unité : ajoutée après une espace, jamais à une absence convertie en zéro.
    (1.8, 2, "mS/cm", "1,80 mS/cm"),
    (None, 2, "mS/cm", "—"),
    (1.8, 2, "", "1,80"),
    # Décimales bornées à 0–6.
    (1 / 3, 9, None, "0,333333"),
    (1.6, -1, None, "2"),
])
def test_regle_unique(value, decimals, unit, expected):
    assert nombre_texte(value, decimals, unit) == expected


def test_module_pur_sans_dependance_web():
    """Le module se charge sans Jinja, aiohttp ni aucun paquet `network`."""
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "model" / "nombre.py"
    imports = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
    assert imports <= {"__future__", "math"}


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
    assert rendu == "minimum 1,45 mS/cm, moyenne 1,62 mS/cm, maximum 1,80 mS/cm"
    assert rendu in synthese
    assert "1.4500000000000002" not in synthese and "1.45" not in synthese
