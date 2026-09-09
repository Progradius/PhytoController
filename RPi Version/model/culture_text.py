"""Normalisation des textes de recherche du carnet : règle pure, sans état ni entrée-sortie.

Une recherche saisie sans accent doit trouver un nom accentué, et l'inverse. Le pliage de
casse seul ne le fait pas : « epinard » et « Épinard » restent deux chaînes différentes après
`casefold()`. La clé ci-dessous est la **seule** définition de cette équivalence côté serveur ;
son équivalent JavaScript (`String.normalize("NFD").replace(/\\p{M}/gu, "").toLowerCase()`)
doit rester aligné sur elle, sans quoi le filtre du navigateur masquerait des choix que le
serveur a retenus.
"""

import unicodedata


def search_key(value):
    """Clé de comparaison d'une chaîne : décomposition NFD, marques retirées, casse pliée.

    La décomposition canonique sépare la lettre de ses signes ; toutes les marques (catégorie
    Unicode `M*`, ce que `\\p{M}` désigne en JavaScript) sont ensuite supprimées. Aucune table
    de correspondance et aucune locale ne sont utilisées : le verdict ne doit pas dépendre de
    la langue du navigateur ni de celle du système.
    """
    decomposed = unicodedata.normalize("NFD", "" if value is None else str(value))
    return "".join(char for char in decomposed if not unicodedata.category(char).startswith("M")).casefold()
