# utils/csrf.py
# Author : Progradius
# License: AGPL-3.0
"""
Jeton CSRF persistant entre deux démarrages.

Un jeton tiré à chaque lancement paraît plus sûr, mais il ne l'est pas : il
n'ajoute rien face à un attaquant (qui n'a jamais pu le lire, la lecture
cross-origin étant interdite par le navigateur) et il casse toutes les pages
restées ouvertes pendant un `systemctl restart` — la sauvegarde suivante part
en 403 alors que rien d'anormal ne s'est produit. Sur un contrôleur qu'on
redéploie souvent, c'est une gêne quotidienne pour zéro gain.

Le jeton est donc écrit une fois dans `param/.csrf_token`, en 0600, hors de
git. Il joue le rôle d'une clé de signature : sa confidentialité repose sur les
droits du fichier, pas sur sa durée de vie. En cas d'échec d'écriture, on
retombe sur un jeton en mémoire — l'interface reste protégée, seule la
persistance est perdue.
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path

from utils.atomic_io import write_text_atomic
from utils.pretty_console import debug, warning

LOGGER_NAME = "http"

TOKEN_FILE = Path(__file__).parent.parent / "param" / ".csrf_token"
TOKEN_BYTES = 32
FILE_MODE = 0o600

# `secrets.token_urlsafe(32)` produit 43 caractères de l'alphabet base64 URL.
# Un fichier tronqué, vidé ou bricolé à la main ne doit jamais devenir un jeton.
_VALID_TOKEN = re.compile(r"\A[A-Za-z0-9_-]{40,128}\Z")


def load_or_create_token(path: Path = TOKEN_FILE) -> str:
    """Retourne le jeton persistant, en le créant à la première utilisation."""
    token = _read_token(path)
    if token is not None:
        debug("Jeton CSRF repris du fichier existant", name=LOGGER_NAME)
        return token

    token = secrets.token_urlsafe(TOKEN_BYTES)
    if _write_token(path, token):
        debug("Jeton CSRF créé et persisté", name=LOGGER_NAME)
    return token


def _read_token(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        warning(
            f"Jeton CSRF illisible ({exc.__class__.__name__}) → jeton temporaire",
            name=LOGGER_NAME,
        )
        return None
    if not _VALID_TOKEN.match(raw):
        warning("Jeton CSRF invalide → régénération", name=LOGGER_NAME)
        return None
    return raw


def _write_token(path: Path, token: str) -> bool:
    """Écrit le jeton en 0600. Un échec n'est jamais fatal pour le serveur."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            # Créer le fichier vide en 0600 **avant** l'écriture atomique :
            # `write_text_atomic()` reporte le mode existant, il n'y a donc
            # aucune fenêtre pendant laquelle le jeton serait en 0644.
            os.close(os.open(path, os.O_CREAT | os.O_WRONLY, FILE_MODE))
        write_text_atomic(path, token + "\n")
    except OSError as exc:
        warning(
            f"Jeton CSRF non persisté ({exc.__class__.__name__}) : les pages "
            "ouvertes seront invalidées au prochain redémarrage",
            name=LOGGER_NAME,
        )
        return False
    return True
