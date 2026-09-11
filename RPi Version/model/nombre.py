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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ABSENCE = "—"


def nombre_texte(value, decimals, unit=None) -> str:
    """Nombre à virgule française, décimales fixes, en texte nu.

    `None`, une valeur non numérique ou non finie s'écrivent « — » : une absence n'est
    jamais un zéro, et un zéro s'écrit `0,00`, jamais comme une absence. Une **chaîne** peut
    arriver d'une saisie réaffichée après refus (`/conf`, formulaires du carnet) ; elle porte
    alors la virgule française et est relue comme telle — la rejeter afficherait « — » à la
    place de ce que l'opérateur vient de taper, exactement quand il relit sa saisie. Le
    nombre de décimales est borné à 0–6 ; pas de séparateur de milliers.

    **L'arrondi est celui du navigateur**, et non celui de `f"{x:.2f}"`. `format` arrondit le
    binaire au pair : `0,015` s'écrivait « 0,01 » ici et « 0,02 » dans l'infobulle du même
    point (`toLocaleString`, arrondi à l'écart depuis la représentation décimale courte), et
    `2,5` à zéro décimale « 2 » contre « 3 ». Sur 1 400 valeurs en `x,xx5`, la moitié
    divergeait ; une température DS18B20 (multiples de 0,0625) comme 21,125 s'écrivait 21,12
    dans un tableau serveur et 21,13 dans l'infobulle de la même mesure. `repr(float(...))`
    donne la représentation décimale courte — celle que le navigateur arrondit —, et
    `ROUND_HALF_UP` arrondit les milieux à l'écart de zéro, comme `halfExpand`, le mode par
    défaut d'`Intl.NumberFormat`. Les vecteurs partagés `tests/fixtures/nombre-vecteurs.json`
    confrontent les deux implémentations.
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
    try:
        arrondi = Decimal(repr(number)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    except InvalidOperation:  # nombre gigantesque : le format brut reste plus juste qu'une absence
        arrondi = Decimal(f"{number:.{places}f}")
    result = f"{arrondi:f}".replace(".", ",")
    return f"{result} {unit}" if unit else result
