"""Vérifie et restaure une sauvegarde du carnet vers une nouvelle copie uniquement."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from model.culture import validate_spaces
from utils.culture_store import CultureStore, CultureUnavailable, SCHEMA_VERSION


def restore_copy(source: Path, destination: Path) -> None:
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination == CultureStore.FILE.resolve() or destination.exists() or any(
        Path(str(destination) + suffix).exists() for suffix in ("-wal", "-shm")
    ):
        raise CultureUnavailable("La restauration exige une nouvelle destination isolée, jamais le carnet actif.")
    if not source.is_file():
        raise CultureUnavailable("Sauvegarde source introuvable.")
    db = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA trusted_schema=OFF")
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            raise CultureUnavailable("Version de sauvegarde incompatible.")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise CultureUnavailable("Intégrité de la sauvegarde invalide.")
        checker = CultureStore(source)
        checker._db = db
        checker.zone = db.execute("SELECT value FROM settings WHERE key='timezone'").fetchone()[0]
        projections = checker._projections()
        validate_spaces(projections)
        checker._validate_origins(projections)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".culture-restore-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "cultures.sqlite3"
            copy = sqlite3.connect(str(staged))
            try:
                db.backup(copy)
                copy.execute("PRAGMA journal_mode=DELETE")
            finally:
                copy.close()
            staged.chmod(0o600)
            with staged.open("rb") as saved:
                os.fsync(saved.fileno())
            # Publication exclusive, atomique, sans écraser une destination apparue entre-temps.
            os.link(staged, destination)
            descriptor = os.open(str(destination.parent), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        db.close()
