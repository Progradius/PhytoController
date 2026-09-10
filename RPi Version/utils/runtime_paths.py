# utils/runtime_paths.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Emplacement des données écrites à l'exécution
# -------------------------------------------------------------
"""
Résolution unique du répertoire des **données vivantes**.

Pourquoi ce module existe : le 08/09/2026, un `git checkout master` sur le Pi a
écrasé `param/param.json`. La branche déployée ne suivait pas ce fichier, mais
la révision visée le suivait encore ; passer de l'une à l'autre fait que Git
**matérialise le fichier du commit par-dessus la configuration vivante**, sans
avertissement et sans que rien ne le détecte. Vingt-six heures d'éclairage et
de cycle ont été perdues avant qu'on s'en aperçoive.

Aucune garde côté déploiement ne ferme ce trou : `scripts/deploy.sh` ne protège
que ce qui passe par lui, et tous les commits antérieurs à `5cddf2f` suivent
encore `param.json`. La seule réponse solide est de **sortir les fichiers
écrits à l'exécution du répertoire de travail Git** : ce qui n'est pas dans
l'arbre de travail ne peut être ni écrasé, ni supprimé, ni restauré par un
checkout, un merge, un reset ou un `git clean -xdf`.

Deux règles tiennent le module :

1. **Une seule résolution pour tout le processus.** `PHYTO_DATA_DIR` si elle est
   définie et non vide, sinon le `param/` du dépôt — le comportement historique,
   qui garde le développement, les tests et l'image Docker inchangés. Le chemin
   est rendu absolu (`expanduser` + `resolve`) parce que l'unité systemd fait un
   `cd` avant de lancer `main.py` : un chemin relatif désignerait deux endroits
   différents selon l'appelant. Il est mémorisé pour qu'une modification tardive
   de l'environnement ne puisse pas créer une seconde vérité en cours de route.
2. **`data_dir()` et `data_file()` ne créent rien et ne vérifient rien.** Elles
   sont appelées à l'import des modules qui déclarent leurs chemins ; un import
   ne doit ni créer de répertoire, ni lever. La création et le contrôle
   d'écriture appartiennent à `ensure_data_dir()`, que `main.py` appelle au
   démarrage.

`ensure_data_dir()` **échoue bruyamment** si `PHYTO_DATA_DIR` est définie mais
inutilisable. Ne jamais y ajouter de repli silencieux vers `param/` : le
processus se remettrait à écrire dans le dépôt, c'est-à-dire exactement la
situation que ce module supprime, et personne ne le verrait.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "PHYTO_DATA_DIR"

#: Emplacement historique, conservé comme valeur par défaut.
REPO_DEFAULT = Path(__file__).resolve().parents[1] / "param"

DIR_MODE = 0o700

_resolved: Path | None = None


def data_dir() -> Path:
    """Répertoire des fichiers écrits à l'exécution. Ne crée rien."""
    global _resolved
    if _resolved is None:
        raw = os.getenv(ENV_VAR, "").strip()
        _resolved = Path(raw).expanduser().resolve() if raw else REPO_DEFAULT
    return _resolved


def data_file(name: str) -> Path:
    """Chemin d'un fichier vivant, par son nom de base. Fonction pure."""
    return data_dir() / name


def ensure_data_dir() -> Path:
    """
    Crée le répertoire des données vivantes et vérifie qu'il est écrivable.

    Appelée une fois au démarrage, avant tout accès fichier. Lève une
    `RuntimeError` explicite plutôt que de retomber sur `param/` : un repli
    silencieux ramènerait les écritures dans le répertoire de travail Git.
    """
    target = data_dir()
    try:
        target.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"Répertoire des données vivantes inutilisable ({target}) : {exc}. "
            f"Vérifier {ENV_VAR} et les droits du compte de service."
        ) from exc
    if not os.access(target, os.W_OK | os.X_OK):
        raise RuntimeError(
            f"Répertoire des données vivantes non écrivable ({target}). "
            f"Vérifier {ENV_VAR} et les droits du compte de service."
        )
    return target


def _reset_for_tests() -> None:
    """Oublie la résolution mémorisée. Réservé aux tests de ce module."""
    global _resolved
    _resolved = None
