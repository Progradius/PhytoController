"""Normalisation des textes de recherche du carnet : règle pure, sans état ni entrée-sortie.

Une recherche saisie sans accent doit trouver un nom accentué, et l'inverse. Le pliage de
casse seul ne le fait pas : « epinard » et « Épinard » restent deux chaînes différentes après
`lower()`. La clé ci-dessous est la **seule** définition de cette équivalence côté serveur ;
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

    La casse est pliée par `lower()`, et **non** par `casefold()`, qui plie plus : il rendrait
    « ß » en « ss », ce que le `toLowerCase()` de JavaScript ne fait pas. Le serveur retiendrait
    alors « Straßburg » pour la saisie « strassburg » et le filtre du navigateur masquerait
    aussitôt ce choix. Une seule règle des deux côtés vaut mieux qu'une règle plus savante d'un
    seul : « ß » reste « ß » ici comme là-bas.
    """
    decomposed = unicodedata.normalize("NFD", "" if value is None else str(value))
    return "".join(char for char in decomposed if not unicodedata.category(char).startswith("M")).lower()
