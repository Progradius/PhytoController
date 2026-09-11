"""Mise en forme française des nombres affichés — règle unique, pure, sans dépendance web.

Seule définition de l'arrondi d'affichage du carnet côté serveur : les filtres Jinja
`nombre` / `nombre_texte` (`network/web/pages.py`) et les phrases de présentation
calculées par les modèles (`model.culture_solution.chart_summary`, repères de
`model.culture_assistance`) y délèguent tous. Les valeurs saisies, l'API chiffrée, les
exports CSV et la persistance gardent la précision complète : arrondir est une affaire de
présentation seulement. Côté navigateur, la réplique alignée est `formatNombre`
(`culture_analysis.js`, `history.js`).
"""

from __future__ import annotations

import math

ABSENCE = "—"


def nombre_texte(value, decimals, unit=None) -> str:
    """Nombre à virgule française, décimales fixes, en texte nu.

    `None`, une valeur non numérique ou non finie s'écrivent « — » : une absence n'est
    jamais un zéro, et un zéro s'écrit `0,00`, jamais comme une absence. Une **chaîne** peut
    arriver d'une saisie réaffichée après refus (`/conf`, formulaires du carnet) ; elle porte
    alors la virgule française et est relue comme telle — la rejeter afficherait « — » à la
    place de ce que l'opérateur vient de taper, exactement quand il relit sa saisie. Le
    nombre de décimales est borné à 0–6 ; pas de séparateur de milliers.
    """
    if value is None:
        return ABSENCE
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        number = float(value)
        places = max(0, min(6, int(decimals)))
        if not math.isfinite(number):
            return ABSENCE
    except (TypeError, ValueError):
        return ABSENCE
    result = f"{number:.{places}f}".replace(".", ",")
    return f"{result} {unit}" if unit else result
