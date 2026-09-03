# utils/atomic_io.py
# Author : Progradius
# License: AGPL-3.0
"""
Écriture atomique de fichiers texte (audit C7, M5).

`Path.write_text()` tronque puis réécrit : entre les deux, le fichier est vide
ou partiel. Deux conséquences observées sur `param.json` et
`sensor_stats.json` :
  • une boucle de contrôle qui relit le fichier dans cette fenêtre tombe sur un
    `JSONDecodeError` ;
  • une coupure secteur pendant l'écriture laisse un fichier tronqué de façon
    **permanente** — donc un boot mort.

Le remède est le trio classique : écrire à côté, `fsync`, puis `os.replace()`
qui est atomique au niveau du système de fichiers (le lecteur voit soit
l'ancien contenu complet, soit le nouveau, jamais un entre-deux).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Mode appliqué quand le fichier n'existe pas encore. Quand il existe, on
# reporte le sien : `os.replace()` remplace l'inode, et un fichier passé
# silencieusement en 0600 ferait apparaître un changement de mode dans git à
# chaque déploiement. Les fichiers vivants sont désormais ignorés par Git,
# mais cette règle reste utile pour les autres fichiers versionnés.
DEFAULT_MODE = 0o644


def write_text_atomic(path: Path, text: str, encoding: str = "utf-8") -> None:
    """
    Écrit `text` dans `path` de façon atomique et durable.

    Le fichier temporaire est créé dans le **même répertoire** : `os.replace()`
    n'est atomique qu'à l'intérieur d'un même système de fichiers.
    """
    path = Path(path)
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)

    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = DEFAULT_MODE

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(directory)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    except BaseException:
        # Y compris KeyboardInterrupt / SystemExit : on ne laisse jamais un
        # `.param.json.xxxx.tmp` traîner dans param/.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    # Le renommage n'est durable qu'une fois le répertoire lui-même synchronisé.
    try:
        dir_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)
