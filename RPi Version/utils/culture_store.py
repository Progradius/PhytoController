"""Carnet durable, écrivain unique SQLite dans un thread auxiliaire borné."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from model.culture import (SPACES, STAGES, CultureConflict, CultureError, backfill_stages,
                           creation_stages, event_payload, fiche_actions, observation_shortcut,
                           project, stamp, stage_options, text_value, validate_origin,
                           validate_origins, validate_spaces)
from model.culture_cycle import REMINDER_STATES, TODAY_REMINDERS, reminder_buckets, stage_checks
from model.culture_journal import TODAY_JOURNAL

from model.culture_solution import RESERVOIRS
from model.culture_text import search_key
from utils.culture_solution_store import SolutionStoreMixin, SOLUTION_SCHEMA, SOLUTION_TABLES

from utils.culture_cycle_store import CycleStoreMixin, CYCLE_SCHEMA, CYCLE_TABLES
from utils.culture_media_store import MediaStoreMixin
from utils.culture_checklist_store import ChecklistStoreMixin
from utils.culture_targets_store import TargetsStoreMixin
from utils.culture_light_store import LightStoreMixin
from utils.culture_equipment_store import EquipmentStoreMixin
from utils.culture_journal_store import JOURNAL_ORDER, JournalStoreMixin
from utils.culture_assistance_store import AssistanceStoreMixin
from model.culture_assistance import transition_summary
from utils.culture_schema_v4 import SCHEMA4_SQL, V4_TABLES

SCHEMA_VERSION = 4

# Taille de page des listes du carnet (cultures, journal d'une fiche). Elle voyage dans les
# réponses (`page`) : le gabarit construisait ses liens « Précédentes / Suivantes » avec sa
# propre constante, soit deux vérités pour un même découpage.
PAGE = 40
# La vue `culture_journal` est volontairement absente : elle ne contient rien que ses
# sources n'exportent déjà, et un SELECT * dessus dupliquerait tout le carnet.
TABLES = ("settings", "subjects", "origins", "events", "requests") + SOLUTION_TABLES + CYCLE_TABLES + V4_TABLES

BASE_SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE subjects (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('mother','lot')),
  name TEXT NOT NULL, variety TEXT NOT NULL, origin_type TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE origins (
  id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES subjects(id),
  mother_id TEXT REFERENCES subjects(id), label TEXT NOT NULL,
  count INTEGER NOT NULL CHECK(count>0));
CREATE TABLE events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL,
  subject_id TEXT NOT NULL REFERENCES subjects(id), revision INTEGER NOT NULL,
  kind TEXT NOT NULL, effective_at TEXT NOT NULL, precision TEXT NOT NULL,
  sort_at TEXT NOT NULL, recorded_at TEXT NOT NULL, clock_reliable INTEGER NOT NULL,
  payload TEXT NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0,
  reason TEXT NOT NULL DEFAULT '', equipment_context TEXT NOT NULL DEFAULT '{}',
  UNIQUE(id, revision));
CREATE INDEX events_subject ON events(subject_id, sort_at);
CREATE TABLE requests (key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL);
"""


class CultureUnavailable(RuntimeError):
    pass


class CultureStore(SolutionStoreMixin, CycleStoreMixin, MediaStoreMixin, ChecklistStoreMixin,
                   TargetsStoreMixin, LightStoreMixin, EquipmentStoreMixin, JournalStoreMixin, AssistanceStoreMixin):
    FILE = Path(__file__).resolve().parents[1] / "param" / "cultures.sqlite3"

    def __init__(self, path=None, *, now=None, reliable=None, zone="Europe/Paris"):
        self.path = Path(path) if path is not None else self.FILE
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.reliable = reliable or (lambda: True)
        ZoneInfo(zone)
        self.zone = zone
        self._executor = None
        self._db = None
        self._pending = 0
        self._closing = False

    @contextmanager
    def _culture_transaction(self, preview=False):
        """Transaction d'écriture du carnet ; une prévalidation la referme sans rien garder.

        Elle sert `_mutate` et `_solution_mutate` : sa place est ici, dans le magasin qui
        possède la connexion, et non dans le mixin d'assistance qui n'en est qu'un des
        appelants.
        """
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            finally:
                if preview:
                    self._db.rollback()

    async def call(self, operation, *args):
        if self._closing or self._pending >= 8:
            raise CultureUnavailable("Carnet occupé ; réessayer dans un instant.")
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phyto-cultures")
        self._pending += 1
        future = asyncio.get_running_loop().run_in_executor(self._executor, self._call, operation, args)
        # Une déconnexion ne libère pas artificiellement une place : le travail SQL continue.
        future.add_done_callback(lambda _future: setattr(self, "_pending", self._pending - 1))
        return await asyncio.shield(future)

    def _call(self, operation, args):
        try:
            self._open()
            return getattr(self, "_" + operation)(*args)
        except (sqlite3.Error, OSError) as exc:
            if self._db:
                self._db.rollback()
            raise CultureUnavailable("Carnet indisponible ; aucune écriture confirmée. Réessayer avec la même clé.") from exc

    def _open(self):
        if self._db is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        db = sqlite3.connect(str(self.path), timeout=2)
        db.row_factory = sqlite3.Row
        try:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise CultureUnavailable("Carnet corrompu conservé sur disque ; restaurer une sauvegarde.")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (1, 2, 3, SCHEMA_VERSION) and (version != 0 or existed):
                raise CultureUnavailable("Schéma du carnet incompatible ; données conservées.")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            if version == 0:
                db.executescript("BEGIN IMMEDIATE;" + BASE_SCHEMA + "PRAGMA user_version=1;")
                db.execute("INSERT INTO settings VALUES ('timezone',?)", (self.zone,))
                db.commit()
            if version in (0, 1):
                if version == 1:
                    self._migration_backup(db, 2)
                try:
                    db.executescript("BEGIN IMMEDIATE;" + SOLUTION_SCHEMA)
                    db.executemany("INSERT INTO reservoirs VALUES (?,?,?)", [(key, *value) for key, value in RESERVOIRS.items()])
                    db.execute("PRAGMA user_version=2")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            if version in (0, 1, 2):
                if version in (1, 2):
                    self._migration_backup(db, 3)
                try:
                    db.executescript("BEGIN IMMEDIATE;" + CYCLE_SCHEMA)
                    db.execute("PRAGMA user_version=3")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
            if version in (0, 1, 2, 3):
                if version in (1, 2, 3):
                    self._migration_backup(db, 4)
                # La recréation de tables enfants (vérifications, photos) exige de relâcher
                # les clés étrangères, et ce PRAGMA est sans effet à l'intérieur d'une transaction.
                db.execute("PRAGMA foreign_keys=OFF")
                try:
                    db.executescript("BEGIN IMMEDIATE;" + SCHEMA4_SQL)
                    # Contrepartie du relâchement : rien ne sort de la transaction avec une
                    # référence pendante ; sinon la base reste en version 3, intacte.
                    if db.execute("PRAGMA foreign_key_check").fetchone():
                        raise CultureUnavailable("Références incohérentes après migration ; données conservées.")
                    db.execute("PRAGMA user_version=4")
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise
                finally:
                    db.execute("PRAGMA foreign_keys=ON")
            setting = db.execute("SELECT value FROM settings WHERE key='timezone'").fetchone()
            if setting is None:
                raise CultureUnavailable("Fuseau du carnet manquant ; données conservées.")
            self.zone = setting[0]
            try:
                ZoneInfo(self.zone)
            except (KeyError, ValueError, TypeError):
                raise CultureUnavailable("Fuseau du carnet invalide ; données conservées.") from None
            self._db = db
        except BaseException:
            db.close()
            raise

    def _migration_backup(self, db, target_version):
        backup_path = self.path.with_name(self.path.name + f".before-v{target_version}.sqlite3")
        if backup_path.exists():
            raise CultureUnavailable("Sauvegarde avant migration déjà présente ; vérifier cette copie avant de réessayer.")
        with tempfile.TemporaryDirectory(dir=self.path.parent, prefix=".culture-migrate-") as directory:
            temporary = Path(directory) / "backup.sqlite3"
            backup = sqlite3.connect(str(temporary))
            try:
                db.backup(backup)
            finally:
                backup.close()
            temporary.chmod(0o600)
            with temporary.open("rb") as source:
                os.fsync(source.fileno())
            os.link(temporary, backup_path)
            descriptor = os.open(str(self.path.parent), os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def _events(self, subject_id=None, revisions=False):
        sql = "SELECT e.*, (SELECT MIN(v.sequence) FROM events v WHERE v.id=e.id) AS logical_sequence FROM events e WHERE 1=1"
        params = []
        if subject_id:
            sql += " AND e.subject_id=?"
            params.append(subject_id)
        if not revisions:
            sql += " AND e.revision=(SELECT MAX(v.revision) FROM events v WHERE v.id=e.id)"
        sql += " ORDER BY e.sort_at DESC,logical_sequence DESC,e.revision DESC"
        rows = []
        for row in self._db.execute(sql, params):
            event = dict(row)
            event["sequence"] = event.pop("logical_sequence")
            event["payload"] = json.loads(event["payload"])
            rows.append(event)
        return rows

    def _projections(self):
        events = self._events()
        origins = [dict(row) for row in self._db.execute("SELECT * FROM origins")]
        now, reliable = self.now(), self.reliable()
        return [project(dict(s), [e for e in events if e["subject_id"] == s["id"]],
                        [o for o in origins if o["subject_id"] == s["id"]], now, self.zone, reliable)
                for s in self._db.execute("SELECT * FROM subjects ORDER BY rowid DESC")]

    def _reminder_view(self, row, names):
        """Rappel réduit à ce qu'une carte affiche, cible déjà résolue.

        Le nom est repris des sujets **déjà projetés** ou du catalogue de réservoirs : le
        bloc « Aujourd'hui » ne doit pas coûter une projection ni une requête de plus.
        """
        if row["reservoir_id"]:
            target = {"kind": "reservoir", "id": row["reservoir_id"],
                      "name": RESERVOIRS[row["reservoir_id"]][0] if row["reservoir_id"] in RESERVOIRS
                      else row["reservoir_id"]}
        else:
            target = {"kind": "culture", "id": row["subject_id"],
                      "name": names.get(row["subject_id"], row["subject_id"])}
        return {"id": row["id"], "revision": row["revision"], "title": row["title"],
                "due_date": row["due_date"], "state": row["state"],
                "interval_days": row["interval_days"], "completed_at": row["completed_at"],
                "target": target}

    def _reminder_view_buckets(self, rows, names, today):
        buckets = reminder_buckets(rows, today, self.zone)
        return {name: [self._reminder_view(row, names) for row in bucket]
                for name, bucket in buckets.items()}

    def _agenda(self, subjects, today):
        """Bloc « Aujourd'hui » : rappels classés et dernières opérations, sans projection neuve.

        Les deux seaux affichés sont bornés à `TODAY_REMINDERS` cartes, chacune étant un
        formulaire complet : un carnet de deux ans peut porter des dizaines de rappels en
        retard, et l'accueil doit rester la page de la prochaine action. Le reste n'est pas
        perdu — il est compté (`overdue_more`, `due_today_more`) et la page renvoie à
        `/cultures/cycles#rappels`, qui les affiche tous. Les seaux sont déjà classés par
        échéance puis identifiant par `_reminders` : la tranche est donc la plus urgente,
        pas une sélection arbitraire.
        """
        names = {s["id"]: s["name"] for s in subjects}
        buckets = reminder_buckets(self._reminders(revisions=False), today, self.zone)
        reminders = {"upcoming_count": len(buckets["upcoming"]),
                     "done_today": [self._reminder_view(row, names) for row in buckets["done_today"]]}
        for bucket in ("overdue", "due_today"):
            rows = buckets[bucket]
            reminders[bucket] = [self._reminder_view(row, names) for row in rows[:TODAY_REMINDERS]]
            reminders[bucket + "_more"] = max(0, len(rows) - TODAY_REMINDERS)
        # Une ligne de plus que la borne : elle ne sert qu'à savoir s'il en reste.
        rows = self._db.execute(f"SELECT j.* FROM culture_journal j ORDER BY {JOURNAL_ORDER} LIMIT ?",
                                (TODAY_JOURNAL + 1,)).fetchall()
        return {"reminders": reminders,
                "journal": self._journal_enrich(rows[:TODAY_JOURNAL]),
                "journal_truncated": len(rows) > TODAY_JOURNAL}

    def _overview(self, archived=False, offset=0, agenda=False, search=""):
        subjects = self._projections()
        # Les projections déjà faites sont passées telles quelles : le dernier relevé de
        # chaque culture ne doit pas coûter une seconde projection complète du carnet.
        readings = self._latest_solution_readings(subjects)
        for subject in subjects:
            subject["latest_reading"] = readings.get(subject["id"])
        selected = [s for s in subjects if s["archived"] == archived]
        # Recherche de l'accueil : elle porte sur le nom et la variété **projetés**, les
        # seuls affichés. Une entrée `identity` les corrige sans jamais réécrire la ligne
        # `subjects` : un `LIKE` SQL répondrait sur l'ancien nom et manquerait le nouveau,
        # soit deux vérités pour une même culture. Le filtre s'applique donc à la
        # projection déjà faite pour cette page — aucune lecture de plus — et la tranche
        # de quarante reste celle de la pagination existante. Un `%` ou un `_` tapés dans
        # la recherche y restent des caractères ordinaires, sans échappement à inventer.
        # Même clé que le sélecteur de comparaison et le journal : sans accents ni casse.
        needle = search_key((search or "").strip())
        if needle:
            selected = [s for s in selected if needle in search_key(f"{s['name']} {s['variety']}")]
        today = self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()
        overview = {"available": True, "timezone": self.zone, "clock_reliable": self.reliable(),
                    "today": today, "search": (search or "").strip(),
                    "items": selected[offset:offset + PAGE], "total": len(selected), "offset": offset,
                    "page": PAGE,
                    # Libellés d'état des rappels : la table pure du modèle, jamais recopiée
                    # dans un gabarit.
                    "reminder_states": REMINDER_STATES,
                    "occupants": [s for s in subjects if s["space"]],
                    "mothers": [{"id": s["id"], "name": s["name"], "archived": s["archived"]}
                                for s in subjects if s["kind"] == "mother"]}
        # Raccourci « Noter une observation » : règle pure, jamais une condition de gabarit.
        overview["observation_shortcut"] = observation_shortcut(overview)
        if agenda:
            overview["agenda"] = self._agenda(subjects, today)
        return overview

    def _detail(self, subject_id, offset=0):
        subjects = self._projections()
        subject = next((s for s in subjects if s["id"] == subject_id), None)
        if subject is None:
            raise CultureError("Culture introuvable.")
        # Le dernier relevé est porté par la fiche elle-même, comme sur l'accueil : le
        # gabarit n'a donc plus à retrouver le sujet dans une liste d'accueil qui, pour une
        # culture archivée ou libérée, ne le contient plus. Une fiche n'en affiche qu'un :
        # elle le lit pour son seul sujet, sans exporter le journal ni reprojeter le carnet.
        subject["latest_reading"] = self._latest_reading(subject_id)
        events = self._events(subject_id)
        versions = self._events(subject_id, revisions=True)
        for event in events:
            event["revisions"] = [v for v in versions if v["id"] == event["id"] and v["revision"] < event["revision"]]
        names = {s["id"]: s["name"] for s in subjects}
        today = self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()
        return {"subject": subject, "events": events[offset:offset + PAGE], "total": len(events),
                "offset": offset, "page": PAGE, "timezone": self.zone, "clock_reliable": self.reliable(),
                "backfill": {"stages": backfill_stages(subject),
                             "spaces": ["space_1"] if subject["kind"] == "mother" else list(SPACES),
                             "before": subject.get("stage_at")},
                "photos": self._media_for_events([e["id"] for e in events[offset:offset + PAGE]]),
                # Rappels du seul sujet, classés comme sur l'accueil : la fiche montre ce qui
                # est en retard ou dû aujourd'hui sans rouvrir la page des cycles.
                "reminders": self._reminder_view_buckets(
                    self._reminders(subject_id, revisions=False), names, today),
                "media": self._media_list(subject_id),
                "actions": fiche_actions(subject),
                # Vérifications pertinentes au stade et à l'espace : règle pure, le gabarit
                # n'a plus de condition de stade ni de table de liens `/conf#…`.
                "stage_checks": stage_checks(subject),
                # Stades proposables pour une progression : la règle reste dans le modèle pur,
                # le gabarit n'a plus de rang de stade à connaître.
                "stage_options": stage_options(subject),
                # Correction d'un stade déjà saisi : tout le parcours redevient proposable.
                "stage_options_full": stage_options(subject, correction=True),
                "descendants": [{"id": s["id"], "name": s["name"]} for s in subjects
                                if any(o["mother_id"] == subject_id for o in s["origins"])]}

    def _insert_event(self, subject_id, kind, raw, now, context, *, event_id=None, revision=1):
        """`context` : copie JSON du catalogue d'équipements connue à la saisie.

        Elle voyage en paramètre et non en attribut d'instance : une prévalidation
        arrivée entre deux écritures écrasait la copie de l'écriture en cours.
        """
        precision = raw.get("precision", "date")
        effective = raw.get("effective_at")
        key, _local = stamp(effective, precision, self.zone, now, field="effective_at")
        data = event_payload(kind, raw.get("payload", {}))
        if kind == "create":
            subject = self._db.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
            if "origins" in data:
                self._write_origins(subject_id, subject["origin_type"], subject["kind"], data["origins"])
            data["origins"] = [dict(row) for row in self._db.execute("SELECT * FROM origins WHERE subject_id=?", (subject_id,))]
        if kind == "harvest":
            if not data["drying_at"]:
                data.update(drying_at=effective, drying_precision=precision)
            if stamp(data["drying_at"], data["drying_precision"], self.zone, now, field="drying_at")[0] < key:
                raise CultureError("Le séchage ne peut pas commencer avant la coupe.", "drying_at")
        cancelled = raw.get("cancelled", False)
        if not isinstance(cancelled, bool):
            raise CultureError("Annulation : booléen attendu.")
        if cancelled and kind == "create":
            raise CultureError("L'origine ne peut pas être annulée.")
        event_id = event_id or str(uuid.uuid4())
        # Les révisions conservent l'ordre logique des événements de même date.
        self._db.execute("""INSERT INTO events
          (id,subject_id,revision,kind,effective_at,precision,sort_at,recorded_at,clock_reliable,payload,cancelled,reason,equipment_context)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (event_id, subject_id, revision, kind, effective, precision, key, now.isoformat(),
           int(self.reliable()), json.dumps(data, ensure_ascii=False, allow_nan=False), int(cancelled),
           text_value(raw.get("reason", ""), "Motif", 500, False, field="reason"), context))
        # L'identité complète de la ligne écrite : l'appelant peut renvoyer une ancre et une
        # photo peut être rattachée à cette révision précise, sans relire le journal.
        return {"id": event_id, "revision": revision}

    def _mutate(self, command, equipment=None, *, preview=False):
        if not isinstance(command, dict):
            raise CultureError("Objet JSON attendu.")
        # Copie locale, jamais un attribut d'instance : deux appels concurrents sur le
        # thread du magasin se seraient volé leur catalogue.
        context = json.dumps(equipment or {}, ensure_ascii=False)
        fields = {"request_id", "operation", "confirm_date", "kind", "name", "variety", "origin_type",
                  "origins", "origin_at", "origin_precision", "stage", "stage_at", "stage_precision",
                  "space", "space_at", "space_precision", "subject_id", "version", "event_id",
                  "effective_at", "precision", "payload", "cancelled", "reason", "steps"}
        if set(command) - fields:
            raise CultureError("Champ de commande inconnu.")
        key = text_value(command.get("request_id"), "Clé de requête", 100)
        try:
            fingerprint = hashlib.sha256(json.dumps(command, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (ValueError, TypeError):
            raise CultureError("Valeurs JSON invalides.") from None
        with self._culture_transaction(preview):
            previous = self._db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise CultureConflict("Cette clé appartient à une autre saisie.")
                result = json.loads(previous["result"])
                # Le rejeu est constaté ici, dans la transaction, par la lecture qui le
                # décide déjà : la prévalidation n'a plus son propre `SELECT` en amont.
                if preview:
                    result["replayed"] = True
                return result
            if not self.reliable() and command.get("confirm_date") is not True:
                raise CultureError("Horloge non fiable : vérifier les dates puis confirmer explicitement.", "confirm_date")
            operation = command.get("operation")
            now = self.now()
            before = next((s for s in self._projections() if s["id"] == command.get("subject_id")), None) if preview else None
            inserted = None
            if operation == "create":
                subject_id = self._create(command, now, context)
            elif operation in ("event", "correct", "backfill"):
                if type(command.get("version")) is not int:
                    raise CultureError("Version entière obligatoire.")
                subject_id = text_value(command.get("subject_id"), "Identifiant")
                subject = self._db.execute("SELECT * FROM subjects WHERE id=?", (subject_id,)).fetchone()
                if subject is None:
                    raise CultureError("Culture introuvable.")
                if command.get("version") != subject["version"]:
                    raise CultureConflict("Cette fiche a changé. Actualiser avant de reprendre la saisie.")
                if operation == "correct":
                    old = next((e for e in self._events(subject_id) if e["id"] == command.get("event_id")), None)
                    if old is None:
                        raise CultureError("Événement introuvable.")
                    inserted = self._insert_event(subject_id, old["kind"], command, now, context,
                                                  event_id=old["id"], revision=old["revision"] + 1)
                elif operation == "backfill":
                    self._backfill(subject_id, command, now, context)
                else:
                    if command.get("kind") == "create":
                        raise CultureError("Origine déjà enregistrée.")
                    inserted = self._insert_event(subject_id, command.get("kind"), command, now, context)
                self._db.execute("UPDATE subjects SET version=version+1 WHERE id=?", (subject_id,))
            else:
                raise CultureError("Opération inconnue.")
            projections = self._projections()
            validate_spaces(projections)
            self._validate_origins(projections)
            self._solution_rebuild(projections)
            result = {"subject_id": subject_id, "saved": True,
                      "version": next(s["version"] for s in projections if s["id"] == subject_id)}
            if inserted is not None:
                # Une entrée unique et identifiable : l'interface peut y renvoyer et y
                # rattacher une photo. Une création ou une reprise en écrit plusieurs et
                # n'en désigne aucune ; un backfill non plus.
                result["event_id"] = inserted["id"]
                result["event_revision"] = inserted["revision"]
            self._db.execute("INSERT INTO requests VALUES (?,?,?)", (key, fingerprint, json.dumps(result)))
            if preview:
                result["preview_summary"] = transition_summary(before, next(s for s in projections if s["id"] == subject_id), command)
        return result

    def _backfill(self, subject_id, command, now, context):
        """Complète les étapes passées connues d'un parcours repris en cours de cycle.

        Chaque étape est un événement daté avant le début du stade courant : la projection
        replace donc ces étapes à leur date, sans déplacer le stade affiché ni la clôture.
        Toutes les étapes entrent dans la transaction de l'appelant : aucune n'est écrite
        si l'une d'elles, l'occupation des espaces ou les liens aux solutions sont refusés.
        """
        steps = command.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 12:
            raise CultureError("Renseigner de 1 à 12 étapes passées.")
        subject = next(s for s in self._projections() if s["id"] == subject_id)
        if not subject.get("stage_at"):
            raise CultureError("Renseigner le stade courant avant de compléter le passé.")
        # Borne stricte : à date égale l'ordre dépendrait de la seule séquence d'insertion.
        limit = stamp(subject["stage_at"], subject["stage_precision"], self.zone, now)[0]
        allowed = backfill_stages(subject)
        spaces = ["space_1"] if subject["kind"] == "mother" else list(SPACES)
        for step in steps:
            if not isinstance(step, dict) or set(step) - {"kind", "effective_at", "precision", "payload", "reason"}:
                raise CultureError("Étape passée invalide.")
            kind = step.get("kind")
            if kind not in ("stage", "move"):
                raise CultureError("Seuls un stade ou un déplacement passés peuvent être complétés.")
            payload = step.get("payload") or {}
            if not isinstance(payload, dict):
                raise CultureError("Étape passée invalide.")
            if kind == "stage" and payload.get("stage") not in allowed:
                raise CultureError("Ce stade n'est pas une étape antérieure manquante de ce parcours.")
            if kind == "move" and payload.get("space") not in spaces:
                raise CultureError("Espace inconnu pour cette culture.")
            if stamp(step.get("effective_at"), step.get("precision", "date"), self.zone, now,
                     field="effective_at")[0] >= limit:
                raise CultureError("Une étape passée doit précéder le début du stade courant.")
            self._insert_event(subject_id, kind, step, now, context)

    def _prevalidate_create(self, command, now):
        """Contrôles purs de la création, **dans l'ordre du formulaire**.

        Les insertions qui suivent gardent leur ordre métier — le déplacement précède le
        stade et la récolte —, mais cet ordre-là n'est pas celui que l'opérateur voit. Sans
        cette passe, une commande cumulant deux fautes signalerait la plus tardive à
        l'écran : le champ désigné serait plus bas que le premier vraiment fautif.
        Aucun accès à la base ici : l'existence d'une mère reste vérifiée par
        `_write_origins`, à sa place, après tous les contrôles de forme.
        """
        kind = command.get("kind")
        origin_type = command.get("origin_type", "mother" if kind == "mother" else "seed")
        text_value(command.get("name"), "Nom", field="name")
        text_value(command.get("variety", ""), "Variété", required=False, field="variety")
        if kind not in ("mother", "lot") or origin_type not in (("mother",) if kind == "mother" else ("seed", "cutting")):
            raise CultureError("Type de culture ou d'origine invalide.", "origin_type")
        origins = command.get("origins", [])
        validate_origins(origins, kind)
        for position, origin in enumerate(origins):
            validate_origin(origin, origin_type, position)
        stamp(command.get("origin_at"), command.get("origin_precision", "date"), self.zone, now, field="origin_at")
        stage = command.get("stage", "maintien" if kind == "mother" else "vegetatif")
        if not isinstance(stage, str) or stage not in STAGES:
            raise CultureError("Stade inconnu.", "stage")
        if stage not in creation_stages(kind, origin_type):
            # Messages inchangés : ce sont ceux que la projection produirait de toute façon.
            raise CultureError("Un pied mère possède une seule période de maintien." if kind == "mother"
                               else "Les stades doivent progresser dans l'ordre du parcours.", "stage")
        stamp(command.get("stage_at"), command.get("stage_precision", "date"), self.zone, now, field="stage_at")
        space = command.get("space", "space_1")
        if not isinstance(space, str) or space not in SPACES:
            raise CultureError("Espace inconnu.", "space")
        # Message inchangé : c'est celui que la projection produirait à l'insertion de la
        # récolte, mais elle le lèverait sans champ, donc après le formulaire entier.
        if kind == "lot" and stage == "sechage" and space != "space_2":
            raise CultureError("La récolte et le séchage ont lieu dans l'espace 2.", "space")
        stamp(command.get("space_at"), command.get("space_precision", "date"), self.zone, now, field="space_at")
        return kind, origin_type, origins, stage, space

    def _create(self, command, now, context):
        kind, origin_type, origins, stage, space = self._prevalidate_create(command, now)
        subject_id = str(uuid.uuid4())
        self._db.execute("INSERT INTO subjects VALUES (?,?,?,?,?,1)",
                         (subject_id, kind, text_value(command.get("name"), "Nom", field="name"),
                          text_value(command.get("variety", ""), "Variété", required=False, field="variety"), origin_type))
        self._write_origins(subject_id, origin_type, kind, origins)
        self._insert_event(subject_id, "create", {"effective_at": command.get("origin_at"),
                           "precision": command.get("origin_precision", "date")}, now, context)
        self._insert_event(subject_id, "move", {"effective_at": command.get("space_at"),
                           "precision": command.get("space_precision", "date"), "payload": {"space": space}}, now, context)
        self._insert_event(subject_id, "harvest" if stage == "sechage" else "stage", {
            "effective_at": command.get("stage_at"), "precision": command.get("stage_precision", "date"),
            "payload": {} if stage == "sechage" else {"stage": stage}}, now, context)
        return subject_id

    def _write_origins(self, subject_id, origin_type, kind, origins):
        validate_origins(origins, kind)
        old_ids = {row[0] for row in self._db.execute("SELECT id FROM origins WHERE subject_id=?", (subject_id,))}
        self._db.execute("DELETE FROM origins WHERE subject_id=?", (subject_id,))
        seen = set()
        ids = set()
        for position, origin in enumerate(origins):
            mother, label, count = validate_origin(origin, origin_type, position)
            if mother:
                row = self._db.execute("SELECT kind FROM subjects WHERE id=?", (mother,)).fetchone()
                if not row or row[0] != "mother" or mother in seen:
                    raise CultureError("Mère inconnue ou dupliquée.", "mother_id", position)
                seen.add(mother)
            origin_id = origin.get("id") or str(uuid.uuid4())
            if not isinstance(origin_id, str) or origin_id in ids or (origin.get("id") and origin_id not in old_ids):
                raise CultureError("Identifiant d'origine inconnu ou dupliqué.")
            ids.add(origin_id)
            self._db.execute("INSERT INTO origins VALUES (?,?,?,?,?)",
                             (origin_id, subject_id, mother, label, count))

    def _validate_origins(self, subjects):
        index = {s["id"]: s for s in subjects}
        for subject in subjects:
            for origin in subject["origins"]:
                if origin["mother_id"]:
                    mother = index[origin["mother_id"]]
                    child_start = stamp(subject["origin_at"], subject["origin_precision"], self.zone, self.now())[0]
                    mother_start = stamp(mother["origin_at"], mother["origin_precision"], self.zone, self.now())[0]
                    if child_start < mother_start:
                        raise CultureError("Un prélèvement ne peut pas précéder l'origine de sa mère.")
                    if mother.get("stage_end"):
                        end_precision = "date" if len(mother["stage_end"]) == 10 else "instant"
                        if child_start > stamp(mother["stage_end"], end_precision, self.zone, self.now())[0]:
                            raise CultureError("Le prélèvement suit l'archivage de la mère.")

    def _export(self):
        return {"format": "phyto-cultures", "schema_version": SCHEMA_VERSION,
                "exported_at": self.now().isoformat(),
                "tables": {name: [dict(row) for row in self._db.execute(f"SELECT * FROM {name}")]
                           for name in TABLES}}

    def _csv(self):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["culture_id", "evenement_id", "type", "date_effective", "precision", "saisi_le", "revision", "annule", "details"])
        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value
        for event in self._events(revisions=True):
            writer.writerow([safe(value) for value in (event["subject_id"], event["id"], event["kind"],
                event["effective_at"], event["precision"], event["recorded_at"], event["revision"],
                event["cancelled"], json.dumps(event["payload"], ensure_ascii=False))])
        return output.getvalue()

    def _backup(self):
        # API SQLite : cohérent avec le WAL, sans copier le fichier vivant.
        with tempfile.TemporaryDirectory(prefix="phyto-culture-backup-") as temporary:
            path = Path(temporary) / "cultures.sqlite3"
            target = sqlite3.connect(str(path))
            try:
                self._db.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CultureUnavailable("Sauvegarde invalide.")
            finally:
                target.close()
            return path.read_bytes()

    async def close(self):
        self._closing = True
        if self._executor:
            def close_db():
                if self._db:
                    self._db.close()
                    self._db = None
            await asyncio.get_running_loop().run_in_executor(self._executor, close_db)
            self._executor.shutdown(wait=False)
            self._executor = None
        self._closing = False
