"""Photos privées du carnet : décodage borné et sauvegarde cohérente, hors event loop."""

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import uuid
import warnings
import zipfile
from pathlib import Path

from model.culture import CultureConflict, CultureError, text_value
from model.culture_cycle import MAX_MEDIA_BYTES, MAX_PHOTO_BYTES, MAX_PHOTO_PIXELS, MIN_FREE_BYTES
from model.culture_journal import MAX_SPACE_PHOTOS


def image_bytes(raw):
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        from utils.culture_store import CultureUnavailable
        raise CultureUnavailable("Module photo absent ; installer les dépendances du carnet.") from None
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PHOTO_BYTES:
        raise CultureError("Photo vide ou supérieure à 5 Mio.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as picture:
                if max(picture.size) > 8192 or picture.width * picture.height > MAX_PHOTO_PIXELS or getattr(picture, "n_frames", 1) != 1:
                    raise CultureError("Photo limitée à 20 mégapixels, 8 192 pixels par côté, sans animation.")
                picture.verify()
            with Image.open(io.BytesIO(raw), formats=("JPEG", "PNG", "WEBP")) as picture:
                picture.load()
                oriented = ImageOps.exif_transpose(picture)
                oriented.thumbnail((1600, 1600))
                clean = Image.new("RGB", oriented.size, "white")
                if "A" in oriented.getbands():
                    rgba = oriented.convert("RGBA")
                    clean.paste(rgba, mask=rgba.getchannel("A"))
                else:
                    clean.paste(oriented.convert("RGB"))
                output = io.BytesIO()
                clean.save(output, format="JPEG", quality=85)
                return output.getvalue(), clean.width, clean.height
    except CultureError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise CultureError("Photo invalide : JPEG, PNG ou WebP non animé attendu.") from None


class MediaStoreMixin:
    @property
    def media_path(self):
        return self.path.parent / "culture_media"

    def _media_storage(self):
        used = self._db.execute("SELECT COALESCE(SUM(size),0) FROM culture_media").fetchone()[0]
        free = shutil.disk_usage(self.path.parent).free
        return {"used_bytes": used, "budget_bytes": MAX_MEDIA_BYTES, "free_bytes": free,
                "reserve_bytes": MIN_FREE_BYTES, "photo_limit_bytes": MAX_PHOTO_BYTES,
                "count": self._db.execute("SELECT COUNT(*) FROM culture_media").fetchone()[0]}

    def _media_list(self, subject_id=None, offset=0, owner_kind="event", space=None):
        """Galerie bornée d'un propriétaire donné.

        Le genre reste `event` par défaut : la galerie des cycles montre les photos de
        cultures, celle du journal les photos d'observation d'espace. Mélanger les deux
        casserait le lien « fiche de culture » d'une vignette dont le sujet est NULL.
        """
        clauses, args = ["owner_kind=?"], [owner_kind]
        if subject_id:
            clauses.append("subject_id=?")
            args.append(subject_id)
        if space:
            clauses.append("space=?")
            args.append(space)
        return [dict(r) for r in self._db.execute(
            "SELECT * FROM culture_media WHERE " + " AND ".join(clauses)
            + " ORDER BY recorded_at DESC,id LIMIT 100 OFFSET ?", args + [offset])]

    def _media_for_events(self, event_ids, owner_kind="event"):
        """Photos attachées à des événements de culture ou à des observations d'espace."""
        if not event_ids:
            return []
        column = "event_id" if owner_kind == "event" else "space_event_id"
        return [dict(r) for r in self._db.execute(
            f"SELECT * FROM culture_media WHERE owner_kind=? AND {column} IN ({','.join('?' for _ in event_ids)})"
            " ORDER BY recorded_at", [owner_kind] + list(event_ids))]

    def _media_add(self, command, raw):
        if not isinstance(command, dict) or set(command) - {"request_id", "confirm_date", "subject_id",
                "event_id", "event_revision", "space_event_id", "space_event_revision", "caption"}:
            raise CultureError("Métadonnées de photo invalides.")
        if not isinstance(raw, bytes) or len(raw) > MAX_PHOTO_BYTES:
            raise CultureError("Photo limitée à 5 Mio.")
        # Les deux propriétaires sont exclusifs, comme les deux clés étrangères de la table.
        space_owner = bool(command.get("space_event_id"))
        if space_owner and (command.get("event_id") or command.get("subject_id")):
            raise CultureError("Une photo appartient à un événement de culture ou à une observation d’espace, jamais aux deux.")
        written = []
        def work():
            caption = text_value(command.get("caption", ""), "Légende", 500, False)
            if space_owner:
                space_event_id = text_value(command.get("space_event_id"), "Observation")
                observation = self._db.execute("SELECT * FROM space_events WHERE id=? ORDER BY revision DESC LIMIT 1",
                                               (space_event_id,)).fetchone()
                if not observation or observation["cancelled"]:
                    raise CultureError("Observation d’espace inconnue ou annulée.")
                if type(command.get("space_event_revision")) is not int or command["space_event_revision"] != observation["revision"]:
                    raise CultureConflict("L’observation a changé ; relire son contenu avant d’ajouter une photo.")
                if self._db.execute("SELECT COUNT(*) FROM culture_media WHERE owner_kind='space_event' AND space_event_id=?",
                                    (space_event_id,)).fetchone()[0] >= MAX_SPACE_PHOTOS:
                    raise CultureError("Quatre photos maximum par observation d’espace.")
                identifier, name, digest, size, width, height = self._media_write(raw, written)
                # Photo d'observation d'espace : les colonnes d'événement de culture restent
                # NULL, l'exclusivité des deux propriétaires étant garantie par les CHECK.
                self._db.execute("""INSERT INTO culture_media
                    (id,owner_kind,subject_id,space,event_id,event_revision,space_event_id,space_event_revision,
                     name,sha256,size,width,height,caption,recorded_at)
                    VALUES (?,'space_event',NULL,?,NULL,NULL,?,?,?,?,?,?,?,?,?)""",
                    (identifier, observation["space"], space_event_id, observation["revision"], name,
                     digest, size, width, height, caption, self.now().isoformat()))
                return {"saved": True, "id": identifier, "space": observation["space"],
                        "space_event_id": space_event_id}
            subject_id = text_value(command.get("subject_id"), "Culture")
            event_id = text_value(command.get("event_id"), "Événement")
            event = self._db.execute("SELECT * FROM events WHERE id=? AND subject_id=? ORDER BY revision DESC LIMIT 1", (event_id, subject_id)).fetchone()
            if not event or event["cancelled"]:
                raise CultureError("Événement inconnu ou annulé.")
            if type(command.get("event_revision")) is not int or command["event_revision"] != event["revision"]:
                raise CultureConflict("L’événement a changé ; relire son contenu avant d’ajouter une photo.")
            if self._db.execute("SELECT COUNT(*) FROM culture_media WHERE owner_kind='event' AND event_id=?", (event_id,)).fetchone()[0] >= MAX_SPACE_PHOTOS:
                raise CultureError("Quatre photos maximum par événement.")
            identifier, name, digest, size, width, height = self._media_write(raw, written)
            # Photo d'événement de culture : les colonnes d'observation d'espace restent
            # NULL, l'exclusivité des deux propriétaires étant garantie par les CHECK.
            self._db.execute("""INSERT INTO culture_media
                (id,owner_kind,subject_id,space,event_id,event_revision,space_event_id,space_event_revision,
                 name,sha256,size,width,height,caption,recorded_at)
                VALUES (?,'event',?,NULL,?,?,NULL,NULL,?,?,?,?,?,?,?)""", (identifier, subject_id, event_id,
                event["revision"], name, digest, size, width, height, caption, self.now().isoformat()))
            return {"saved": True, "id": identifier, "subject_id": subject_id}
        try:
            return self._aux_transaction({**command, "photo_sha256": hashlib.sha256(raw).hexdigest()}, work)
        except BaseException:
            for path in written:
                path.unlink(missing_ok=True)
            raise

    def _media_write(self, raw, written):
        """Réencodage, budget disque et écriture durable : voie unique quel que soit le propriétaire.

        Généralisée au lot H sans second chemin d'écriture : plafonds, réserve
        `MIN_FREE_BYTES` et nettoyage des orphelins restent ceux des photos de culture.
        """
        jpeg, width, height = image_bytes(raw)
        self.media_path.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._media_clean_orphans()
        storage = self._media_storage()
        physical = sum(p.stat().st_size for p in self.media_path.iterdir() if p.is_file())
        if storage["count"] >= 5000 or max(storage["used_bytes"], physical) + len(jpeg) > MAX_MEDIA_BYTES or storage["free_bytes"] - len(jpeg) < MIN_FREE_BYTES:
            raise CultureError("Budget photos ou réserve disque atteint ; aucune ancienne photo n’est supprimée.")
        identifier = str(uuid.uuid4())
        name = identifier + ".jpg"
        destination = self.media_path / name
        with tempfile.NamedTemporaryFile(dir=self.media_path, prefix=".upload-", delete=False) as temporary:
            staged = Path(temporary.name)
            written.append(staged)
            temporary.write(jpeg)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(staged, destination)
        written.append(destination)
        descriptor = os.open(str(self.media_path), os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return identifier, name, hashlib.sha256(jpeg).hexdigest(), len(jpeg), width, height

    def _media_clean_orphans(self):
        """Ne nettoie que les fichiers internes orphelins âgés, au plus 40 par passage."""
        known = {r[0] for r in self._db.execute("SELECT name FROM culture_media")}
        cutoff = self.now().timestamp() - 86400
        removed = 0
        for path in self.media_path.iterdir():
            if removed >= 40:
                break
            generated = re.fullmatch(r"[0-9a-f-]{36}\.jpg", path.name) or path.name.startswith(".upload-")
            if generated and path.name not in known and path.is_file() and path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1

    def _media_get(self, identifier):
        row = self._db.execute("SELECT * FROM culture_media WHERE id=?", (text_value(identifier, "Photo"),)).fetchone()
        if not row:
            raise CultureError("Photo introuvable.")
        if row["name"] != row["id"] + ".jpg" or not re.fullmatch(r"[0-9a-f-]{36}", row["id"]):
            raise CultureError("Chemin de photo invalide.")
        path = self.media_path / row["name"]
        if path.is_symlink() or path.stat().st_size > MAX_PHOTO_BYTES:
            raise CultureError("Fichier photo invalide.")
        raw = path.read_bytes()
        if len(raw) != row["size"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise CultureError("Photo endommagée ; conserver le carnet et restaurer une copie vérifiée.")
        return raw

    def _bundle(self):
        """Même thread que toutes les écritures : base et médias appartiennent au même instant."""
        database = self._backup()
        storage = self._media_storage()
        if len(database) > 128 * 1024 * 1024:
            raise CultureError("Base supérieure à la limite de 128 Mio de la sauvegarde complète ; conserver un export SQLite séparé.")
        if storage["free_bytes"] < len(database) + storage["used_bytes"] + MIN_FREE_BYTES:
            raise CultureError("Espace disque insuffisant pour préparer la sauvegarde complète.")
        # Un fichier temporaire évite de cumuler toutes les photos en mémoire.
        descriptor, filename = tempfile.mkstemp(prefix="phyto-cultures-", suffix=".zip")
        os.close(descriptor)
        path = Path(filename)
        try:
            manifest = {"format": "phyto-cultures-bundle", "version": 1, "created_at": self.now().isoformat(), "files": {}}
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("cultures.sqlite3", database)
                manifest["files"]["cultures.sqlite3"] = {"size": len(database), "sha256": hashlib.sha256(database).hexdigest()}
                for row in self._db.execute("SELECT id,name FROM culture_media ORDER BY id"):
                    raw = self._media_get(row["id"])
                    name = "culture_media/" + row["name"]
                    archive.writestr(name, raw)
                    manifest["files"][name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            return str(path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
