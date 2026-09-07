"""Identité immuable du code chargé par le processus courant."""

from __future__ import annotations

import os
from pathlib import Path


def _git_directory(start: Path) -> Path | None:
    for parent in (start, *start.parents):
        marker = parent / ".git"
        if marker.is_dir() and (marker / "HEAD").is_file():
            return marker
        if marker.is_file():
            try:
                declaration = marker.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if declaration.startswith("gitdir:"):
                target = Path(declaration.removeprefix("gitdir:").strip())
                return target if target.is_absolute() else (parent / target).resolve()
    return None


def _resolve_ref(git_dir: Path, ref_name: str) -> str | None:
    loose_ref = git_dir / ref_name
    try:
        if loose_ref.is_file():
            return loose_ref.read_text(encoding="ascii").strip()
        for line in (git_dir / "packed-refs").read_text(encoding="ascii").splitlines():
            if line and not line.startswith(("#", "^")):
                revision, name = line.split(" ", 1)
                if name == ref_name:
                    return revision
    except (OSError, ValueError):
        return None
    return None


def deployed_version(start: Path | None = None) -> str:
    """Retourne le commit figé au chargement, sans lancer de sous-processus.

    Le déploiement de production utilise un HEAD détaché. La résolution des
    références symboliques garde néanmoins une valeur utile en développement.
    Une image sans métadonnées Git peut fournir explicitement PHYTO_VERSION.
    """
    override = os.getenv("PHYTO_VERSION", "").strip()
    if override:
        return override

    git_dir = _git_directory((start or Path(__file__)).resolve())
    if git_dir is None:
        return "unknown"
    try:
        head = (git_dir / "HEAD").read_text(encoding="ascii").strip()
    except OSError:
        return "unknown"
    if head.startswith("ref:"):
        head = _resolve_ref(git_dir, head.removeprefix("ref:").strip()) or "unknown"
    return head if len(head) == 40 and all(c in "0123456789abcdefABCDEF" for c in head) else "unknown"


DEPLOYED_VERSION = deployed_version()
