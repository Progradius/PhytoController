"""Vérifie et restaure une sauvegarde du carnet vers une nouvelle copie uniquement."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from model.culture import validate_spaces
from utils.culture_schema_v4 import V4_VIEWS
from utils.culture_store import CultureStore, CultureUnavailable, SCHEMA_VERSION


def restore_copy(source: Path, destination: Path, *, _bundle=False) -> None:
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
        if db.execute("PRAGMA user_version").fetchone()[0] not in (1, 2, 3, SCHEMA_VERSION):
            raise CultureUnavailable("Version de sauvegarde incompatible.")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone():
            raise CultureUnavailable("Intégrité de la sauvegarde invalide.")
        checker = CultureStore(source)
        checker._db = db
        checker.zone = db.execute("SELECT value FROM settings WHERE key='timezone'").fetchone()[0]
        projections = checker._projections()
        validate_spaces(projections)
        checker._validate_origins(projections)
        if db.execute("PRAGMA user_version").fetchone()[0] >= 2:
            checker._solution_rebuild(projections, validate_only=True)
        if db.execute("PRAGMA user_version").fetchone()[0] >= 3:
            photos = db.execute("SELECT id FROM culture_media").fetchall()
            if photos and not _bundle:
                raise CultureUnavailable("Cette base référence des photos ; utiliser la sauvegarde ZIP complète.")
            for photo in photos:
                from PIL import Image
                import io
                raw = checker._media_get(photo[0])
                row = db.execute("SELECT width,height FROM culture_media WHERE id=?", (photo[0],)).fetchone()
                with Image.open(io.BytesIO(raw), formats=("JPEG",)) as picture:
                    if picture.size != tuple(row) or max(picture.size) > 1600 or picture.getexif():
                        raise CultureUnavailable("Photo de sauvegarde incompatible avec les dimensions ou métadonnées attendues.")
                    picture.verify()
            checker._cycle_validate()
        if db.execute("PRAGMA user_version").fetchone()[0] >= 4:
            # Le journal transversal est une vue : une sauvegarde de version 4 qui ne la
            # porte pas est un schéma partiel, pas une base restaurable.
            for view in V4_VIEWS:
                if not db.execute("SELECT 1 FROM sqlite_schema WHERE type='view' AND name=?", (view,)).fetchone():
                    raise CultureUnavailable("Vue du journal absente de la sauvegarde ; schéma incomplet.")
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


def restore_bundle(source: Path, destination: Path) -> None:
    """Valide l'ensemble avant de publier un nouveau dossier isolé, jamais le carnet actif."""
    import hashlib
    import json
    import re
    import zipfile
    from model.culture_cycle import MAX_MEDIA_BYTES, MAX_PHOTO_BYTES

    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination == CultureStore.FILE.parent.resolve():
        raise CultureUnavailable("La restauration complète exige un nouveau dossier isolé.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".culture-bundle-", dir=destination.parent) as temporary:
        staged = Path(temporary)
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if len(names) > 5002 or len(set(names)) != len(names) or "manifest.json" not in names:
                raise CultureUnavailable("Manifeste ou liste de fichiers invalide.")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 2 * 1024 * 1024:
                raise CultureUnavailable("Manifeste trop volumineux.")
            manifest = json.loads(archive.read(manifest_info))
            files = manifest.get("files")
            if manifest.get("format") != "phyto-cultures-bundle" or manifest.get("version") != 1 or not isinstance(files, dict):
                raise CultureUnavailable("Format de sauvegarde complète incompatible.")
            if set(names) != set(files) | {"manifest.json"} or "cultures.sqlite3" not in files:
                raise CultureUnavailable("Contenu de sauvegarde différent du manifeste.")
            if sum(info.file_size for info in archive.infolist()) > MAX_MEDIA_BYTES + 130 * 1024 * 1024:
                raise CultureUnavailable("Sauvegarde décompressée trop volumineuse.")
            for name, expected in files.items():
                if name != "cultures.sqlite3" and not re.fullmatch(r"culture_media/[0-9a-f-]{36}\.jpg", name):
                    raise CultureUnavailable("Chemin de sauvegarde refusé.")
                info = archive.getinfo(name)
                maximum = 128 * 1024 * 1024 if name == "cultures.sqlite3" else MAX_PHOTO_BYTES
                if info.file_size > maximum or info.file_size != expected.get("size") or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise CultureUnavailable("Taille ou type de fichier invalide.")
                output = staged / name
                output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                digest = hashlib.sha256()
                count = 0
                with archive.open(info) as incoming, output.open("xb") as written:
                    output.chmod(0o600)
                    while True:
                        chunk = incoming.read(65536)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > maximum:
                            raise CultureUnavailable("Fichier décompressé trop volumineux.")
                        digest.update(chunk)
                        written.write(chunk)
                    written.flush()
                    os.fsync(written.fileno())
                if digest.hexdigest() != expected.get("sha256") or count != expected.get("size"):
                    raise CultureUnavailable("Empreinte de sauvegarde invalide.")
        # La vérification SQLite inclut les références et l'intégrité de chaque photo.
        verified = staged / "verified.sqlite3"
        restore_copy(staged / "cultures.sqlite3", verified, _bundle=True)
        with sqlite3.connect(verified) as db:
            expected_media = {"culture_media/" + row[0] for row in db.execute("SELECT name FROM culture_media")}
        if expected_media != set(files) - {"cultures.sqlite3"}:
            raise CultureUnavailable("Les photos du manifeste diffèrent des références SQLite.")
        # Publication exclusive. Un arrêt pendant cette phase laisse un dossier explicitement incomplet.
        destination.mkdir(mode=0o700)
        marker = destination / ".restauration-incomplete"
        with marker.open("x", encoding="utf-8") as output:
            output.write("Ne pas utiliser cette copie avant validation complète.\n")
            output.flush()
            os.fsync(output.fileno())
        for directory in (destination, destination.parent):
            descriptor = os.open(str(directory), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        os.replace(verified, destination / "cultures.sqlite3")
        if (staged / "culture_media").exists():
            os.replace(staged / "culture_media", destination / "culture_media")
            descriptor = os.open(str(destination / "culture_media"), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        # Les fichiers publiés doivent être durables avant de lever le marqueur d'incomplétude.
        descriptor = os.open(str(destination), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        marker.unlink()
        descriptor = os.open(str(destination), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
