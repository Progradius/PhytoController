"""Rappels et agrégats durables dans le thread auxiliaire du carnet."""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from model.culture import CultureConflict, CultureError, SPACES, stamp, text_value
from model.culture_cycle import (CLIMATE_PAGE, MAX_SUMMARY_POINTS, REMINDER_STATES,
                                 climate_granularity, climate_point, climate_span, planned_date,
                                 reminder_buckets, reminder_values, trusted_value)
from model.culture_solution import RESERVOIRS
from utils.culture_checklist_store import CHECKLIST_OPERATIONS

CYCLE_TABLES = ("reminders", "culture_checklists", "climate_hours", "climate_minutes", "culture_media")
CYCLE_SCHEMA = """
CREATE TABLE reminders (id TEXT NOT NULL, revision INTEGER NOT NULL, parent_id TEXT,
 subject_id TEXT REFERENCES subjects(id), reservoir_id TEXT REFERENCES reservoirs(id),
 title TEXT NOT NULL, due_date TEXT NOT NULL, interval_days INTEGER NOT NULL,
 state TEXT NOT NULL, note TEXT NOT NULL, recorded_at TEXT NOT NULL, completed_at TEXT,
 PRIMARY KEY(id,revision));
CREATE INDEX reminder_dates ON reminders(due_date);
CREATE TABLE culture_checklists (id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES subjects(id),
 space TEXT, stage TEXT NOT NULL, effective_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
 lighting INTEGER NOT NULL, pump INTEGER NOT NULL, ventilation INTEGER NOT NULL, note TEXT NOT NULL);
CREATE TABLE climate_hours (sensor TEXT NOT NULL, hour INTEGER NOT NULL, label TEXT NOT NULL, unit TEXT NOT NULL,
 minimum REAL, maximum REAL, total REAL NOT NULL DEFAULT 0, valid_count INTEGER NOT NULL DEFAULT 0,
 observed_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(sensor,hour));
CREATE TABLE climate_minutes (sensor TEXT NOT NULL, minute INTEGER NOT NULL, PRIMARY KEY(sensor,minute));
CREATE TABLE culture_media (id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES subjects(id),
 event_id TEXT NOT NULL, event_revision INTEGER NOT NULL, name TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL, size INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 caption TEXT NOT NULL, recorded_at TEXT NOT NULL, FOREIGN KEY(event_id,event_revision) REFERENCES events(id,revision));
"""


class CycleStoreMixin:
    def _aux_transaction(self, command, work):
        if not isinstance(command, dict):
            raise CultureError("Objet JSON attendu.")
        key = text_value(command.get("request_id"), "Clé de requête", 100)
        try:
            fingerprint = hashlib.sha256(json.dumps(command, sort_keys=True, allow_nan=False).encode()).hexdigest()
        except (ValueError, TypeError):
            raise CultureError("Valeurs JSON invalides.") from None
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            previous = self._db.execute("SELECT * FROM requests WHERE key=?", (key,)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise CultureConflict("Cette clé appartient à une autre saisie.")
                return json.loads(previous["result"])
            if not self.reliable() and command.get("confirm_date") is not True:
                raise CultureError("Horloge non fiable : vérifier puis confirmer explicitement la date.", "confirm_date")
            result = work()
            self._db.execute("INSERT INTO requests VALUES (?,?,?)", (key, fingerprint, json.dumps(result)))
        return result

    def _reminders(self, target=None, *, revisions=True, states=None):
        """Rappels courants, éventuellement filtrés, avec leurs seaux de classement.

        Le classement lui-même est pur (`reminder_buckets`) : le magasin ne fait plus que
        lire les lignes et reporter les seaux sur elles. `revisions=False` supprime la
        requête par rappel, inutile pour l'accueil qui n'affiche aucun historique.
        """
        sql = "SELECT r.* FROM reminders r WHERE revision=(SELECT MAX(v.revision) FROM reminders v WHERE v.id=r.id)"
        rows = [dict(r) for r in self._db.execute(sql + " ORDER BY due_date,id")]
        if target:
            rows = [r for r in rows if target in (r["subject_id"], r["reservoir_id"])]
        if states is not None:
            rows = [r for r in rows if r["state"] in states]
        today = self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()
        buckets = reminder_buckets(rows, today, self.zone)
        overdue = {(r["id"], r["revision"]) for r in buckets["overdue"]}
        due_today = {(r["id"], r["revision"]) for r in buckets["due_today"]}
        for row in rows:
            row["overdue"] = (row["id"], row["revision"]) in overdue
            row["due_today"] = (row["id"], row["revision"]) in due_today
            if revisions:
                row["revisions"] = [dict(r) for r in self._db.execute("SELECT * FROM reminders WHERE id=? AND revision<? ORDER BY revision", (row["id"], row["revision"]))]
        return rows

    def _cycle_mutate(self, command):
        # Les vérifications ont leur propre magasin et leur propre transaction depuis le
        # schéma 4 ; la route et le formulaire existants restent inchangés.
        if isinstance(command, dict) and command.get("operation") in CHECKLIST_OPERATIONS:
            return self._checklist_mutate(command)
        if not isinstance(command, dict) or set(command) - {"request_id", "operation", "confirm_date", "id", "version", "target",
                "title", "due_date", "interval_days", "note", "action"}:
            raise CultureError("Commande de carnet invalide.")
        def work():
            operation = command.get("operation")
            now = self.now().isoformat()
            identifier = command.get("id")
            if operation not in ("reminder", "reminder_action"):
                raise CultureError("Opération de carnet inconnue.")
            old = None
            revision = 1
            if identifier:
                identifier = text_value(identifier, "Identifiant")
                old = self._db.execute("SELECT * FROM reminders WHERE id=? ORDER BY revision DESC LIMIT 1", (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Rappel introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Ce rappel a changé ; actualiser avant de poursuivre.")
                revision = old["revision"] + 1
            elif operation == "reminder_action":
                raise CultureError("Identifiant de rappel obligatoire.")
            else:
                identifier = str(uuid.uuid4())
            if operation == "reminder":
                if old and old["state"] in ("done", "cancelled"):
                    raise CultureError("Un rappel clos conserve son historique ; créer un nouveau rappel.")
                values = reminder_values(command)
                target = text_value(command.get("target"), "Cible", field="target")
                if target in RESERVOIRS:
                    subject_id, reservoir_id = None, target
                elif self._db.execute("SELECT id FROM subjects WHERE id=?", (target,)).fetchone():
                    subject_id, reservoir_id = target, None
                else:
                    raise CultureError("Cible de rappel inconnue.", "target")
                row = {"id": identifier, "revision": revision, "parent_id": old["parent_id"] if old else None,
                       "subject_id": subject_id, "reservoir_id": reservoir_id, **values,
                       "state": old["state"] if old else "planned", "recorded_at": now, "completed_at": None}
            else:
                if old["state"] not in ("planned", "postponed"):
                    raise CultureError("Ce rappel est déjà clos.")
                action = command.get("action")
                if action not in ("done", "postponed", "cancelled"):
                    raise CultureError("Action attendue : fait, reporté ou annulé.", "action")
                row = {**dict(old), "revision": revision, "state": action, "recorded_at": now,
                       "note": text_value(command.get("note", ""), "Note", 4000, False, field="note")}
                if action == "postponed":
                    row["due_date"] = planned_date(command.get("due_date"))
                    if row["due_date"] <= old["due_date"]:
                        raise CultureError("Un report doit déplacer l’échéance vers une date ultérieure.",
                                           "due_date")
                if action == "done":
                    row["completed_at"] = now
            columns = ",".join(row)
            self._db.execute(f"INSERT INTO reminders ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
            next_id = None
            if operation == "reminder_action" and row["state"] == "done" and row["interval_days"]:
                next_id = str(uuid.uuid4())
                # La prochaine échéance part de l'accomplissement réel, sans inventer les passages manqués.
                due = self.now().astimezone(ZoneInfo(self.zone)).date() + timedelta(days=row["interval_days"])
                following = {**row, "id": next_id, "revision": 1, "parent_id": identifier,
                             "due_date": due.isoformat(), "state": "planned", "completed_at": None}
                self._db.execute(f"INSERT INTO reminders ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(following.values()))
            return {"saved": True, "id": identifier, "version": revision, "next_id": next_id}
        return self._aux_transaction(command, work)

    def _climate_sample(self, snapshot, metadata):
        if not self.reliable():
            return {"saved": False, "reason": "horloge non synchronisée"}
        minute = int(self.now().timestamp()) // 60
        hour = minute // 60 * 3600
        with self._db:
            for sensor, item in snapshot.items():
                if sensor not in metadata or not item.get("enabled", True):
                    continue
                last = self._db.execute("SELECT MAX(minute) FROM climate_minutes WHERE sensor=?", (sensor,)).fetchone()[0]
                if last is not None and minute <= last:
                    continue
                inserted = self._db.execute("INSERT OR IGNORE INTO climate_minutes VALUES (?,?)", (sensor, minute)).rowcount
                if not inserted:
                    continue
                value = trusted_value(item)
                label, unit = metadata[sensor]
                self._db.execute("""INSERT INTO climate_hours
                    (sensor,hour,label,unit,minimum,maximum,total,valid_count,observed_count) VALUES (?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(sensor,hour) DO UPDATE SET
                    minimum=CASE WHEN excluded.minimum IS NULL THEN minimum WHEN minimum IS NULL THEN excluded.minimum ELSE MIN(minimum,excluded.minimum) END,
                    maximum=CASE WHEN excluded.maximum IS NULL THEN maximum WHEN maximum IS NULL THEN excluded.maximum ELSE MAX(maximum,excluded.maximum) END,
                    total=total+excluded.total, valid_count=valid_count+excluded.valid_count, observed_count=observed_count+1""",
                    (sensor, hour, label, unit, value, value, value or 0, int(value is not None)))
            # Seules les clés de dédoublonnage anciennes sont purgées ; les agrégats restent durables.
            self._db.execute("DELETE FROM climate_minutes WHERE minute<?", (minute - 7 * 24 * 60,))
        return {"saved": True}

    def _climate_summary(self, start_hour, end_hour):
        """Synthèse bornée couvrant tout le cycle : agrégation groupée en SQL, jamais en mémoire."""
        seconds, label = climate_granularity(start_hour, end_hour)
        rows = self._db.execute(
            """SELECT sensor, MAX(label) AS label, MAX(unit) AS unit, hour/?*? AS bucket,
               MIN(minimum) AS minimum, MAX(maximum) AS maximum, SUM(total) AS total,
               SUM(valid_count) AS valid_count, SUM(observed_count) AS observed_count,
               COUNT(*) AS hours FROM climate_hours WHERE hour>=? AND hour<=?
               GROUP BY sensor, bucket ORDER BY bucket, sensor LIMIT ?""",
            (seconds, seconds, start_hour, end_hour, MAX_SUMMARY_POINTS + 1)).fetchall()
        truncated = len(rows) > MAX_SUMMARY_POINTS
        rows = rows[:MAX_SUMMARY_POINTS]
        sensors, found = {}, {}
        for row in rows:
            sensors.setdefault(row["sensor"], (row["label"], row["unit"]))
            found[(row["sensor"], row["bucket"])] = row
        buckets = range(start_hour // seconds * seconds, end_hour // seconds * seconds + 1, seconds)
        # Les seaux sans agrégat sont restitués comme lacunes explicites, jamais comme des zéros.
        complete = not truncated and len(buckets) * max(len(sensors), 1) <= MAX_SUMMARY_POINTS
        points, gaps = [], 0
        for bucket in buckets:
            span = climate_span(bucket, seconds, start_hour, end_hour)
            for sensor, (name, unit) in sensors.items():
                row = found.get((sensor, bucket))
                if row is None:
                    gaps += 1
                    if not complete:
                        continue
                points.append(climate_point(sensor, name, unit, bucket, span, row))
        return {"granularity_seconds": seconds, "granularity_label": label, "points": points,
                "bucket_count": len(buckets), "sensor_count": len(sensors), "gap_count": gaps,
                "gaps_shown": complete, "truncated": truncated, "start": start_hour, "end": end_hour,
                "start_at": datetime.fromtimestamp(start_hour, timezone.utc).isoformat(),
                "end_at": datetime.fromtimestamp(end_hour, timezone.utc).isoformat()}

    def _climate_detail(self, start_hour, end_hour, offset=0, climate_at=None):
        """Détail horaire paginé en SQL : aucune lecture de tout l'historique pour tronquer ensuite."""
        total = self._db.execute("SELECT COUNT(*) FROM climate_hours WHERE hour>=? AND hour<=?",
                                 (start_hour, end_hour)).fetchone()[0]
        if climate_at is not None:
            wanted = min(max(int(climate_at), start_hour), end_hour + 1)
            position = self._db.execute("SELECT COUNT(*) FROM climate_hours WHERE hour>=? AND hour<?",
                                        (start_hour, wanted)).fetchone()[0]
            offset = position
        offset = max(0, min(int(offset), max(total - 1, 0))) // CLIMATE_PAGE * CLIMATE_PAGE
        rows = []
        for row in self._db.execute("SELECT * FROM climate_hours WHERE hour>=? AND hour<=? ORDER BY hour,sensor LIMIT ? OFFSET ?",
                                    (start_hour, end_hour, CLIMATE_PAGE, offset)):
            point = dict(row)
            point["mean"] = point["total"] / point["valid_count"] if point["valid_count"] else None
            point["coverage"] = point["valid_count"] / 60
            point["at"] = datetime.fromtimestamp(point["hour"], timezone.utc).isoformat()
            rows.append(point)
        return {"rows": rows, "total": total, "offset": offset, "page": CLIMATE_PAGE,
                "previous": offset - CLIMATE_PAGE if offset else None,
                "next": offset + CLIMATE_PAGE if offset + CLIMATE_PAGE < total else None}

    def _cycle_data(self, selected=None, offset=0, focus=None, climate_offset=0, climate_at=None, search="", selection_offset=0):
        selected = selected or []
        if not isinstance(selected, list) or len(selected) > 4 or any(not isinstance(s, str) for s in selected):
            raise CultureError("Comparer au maximum quatre cultures.")
        subjects = self._projections()
        by_id = {s["id"]: s for s in subjects}
        if any(identifier not in by_id for identifier in selected):
            raise CultureError("Culture inconnue.")
        chosen = [by_id[identifier] for identifier in selected]
        summaries = []
        for subject in chosen:
            start = stamp(subject["origin_at"], subject["origin_precision"], self.zone, self.now())[0]
            end = stamp(subject["stage_end"], "date" if len(subject["stage_end"]) == 10 else "instant", self.zone, self.now())[0] if subject.get("stage_end") else self.now().isoformat()
            start_epoch = int(datetime.fromisoformat(start).timestamp())
            end_epoch = int(datetime.fromisoformat(end).timestamp())
            start_hour = start_epoch // 3600 * 3600
            end_hour = end_epoch // 3600 * 3600
            climate = self._climate_summary(start_hour, end_hour)
            # Le détail horaire n'est paginé que sur une sélection unique : une comparaison
            # de cycles reste bornée à des synthèses dont la granularité est affichée.
            detail = self._climate_detail(start_hour, end_hour, climate_offset, climate_at) if len(chosen) == 1 else None
            measures = self._reading_summary(subject["id"])
            summaries.append({"subject": subject, "climate": climate, "climate_detail": detail,
                              "measures": measures, "periods": subject["periods"],
                              "checklists": self._checklists(subject)})
        needle = str(search or "").strip()[:120].casefold()
        matches = [s for s in subjects if needle in (s["name"] + " " + s.get("variety", "")).casefold()]
        choices = matches[selection_offset:selection_offset + 40]
        choices = chosen + [s for s in choices if s["id"] not in selected]
        target = selected[0] if len(selected) == 1 else None
        reminders = self._reminders(target)
        reminders.sort(key=lambda r: (r["state"] in ("done", "cancelled"), r["due_date"], r["id"]))
        if focus:
            position = next((i for i, r in enumerate(reminders) if r["id"] == focus), None)
            if position is not None:
                offset = position // 40 * 40
        return {"comparison_choices": [{key: s[key] for key in ("id", "name", "variety", "archived")} for s in choices],
                "selection_total": len(matches),
                "selection_offset": selection_offset, "search": str(search or "").strip()[:120],
                "subjects": [{"id": s["id"], "name": s["name"], "archived": s["archived"]} for s in subjects],
                "summaries": summaries, "reminders": reminders[offset:offset + 40], "reminder_total": len(reminders),
                "offset": offset, "media": self._media_list(subjects=selected), "storage": self._media_storage(),
                "today": self.now().astimezone(ZoneInfo(self.zone)).date().isoformat(),
                "timezone": self.zone, "clock_reliable": self.reliable()}

    def _cycle_validate(self):
        """Vérifie les invariants exportables sans modifier la copie en lecture seule."""
        import math
        for row in self._db.execute("SELECT * FROM reminders"):
            reminder_values(dict(row))
            if row["state"] not in REMINDER_STATES or bool(row["subject_id"]) == bool(row["reservoir_id"]):
                raise CultureError("Rappel de sauvegarde incohérent.")
        for row in self._db.execute("SELECT * FROM climate_hours"):
            if not 0 <= row["valid_count"] <= row["observed_count"] <= 60 or row["hour"] % 3600:
                raise CultureError("Couverture climatique incohérente.")
            if not math.isfinite(row["total"]):
                raise CultureError("Somme climatique invalide.")
            if row["valid_count"]:
                if row["minimum"] is None or row["maximum"] is None or not math.isfinite(row["minimum"]) or not math.isfinite(row["maximum"]) or not row["minimum"] <= row["maximum"]:
                    raise CultureError("Étendue climatique incohérente.")
            elif row["minimum"] is not None or row["maximum"] is not None or row["total"] != 0:
                raise CultureError("Une absence climatique ne doit pas devenir une mesure.")
        if self._db.execute("PRAGMA user_version").fetchone()[0] < 4:
            # Une sauvegarde antérieure au schéma 4 ne porte pas ces colonnes ni ces tables :
            # exiger leurs invariants ferait échouer la restauration d'une base pourtant saine.
            return
        for row in self._db.execute("SELECT owner_kind,subject_id,space,event_id,space_event_id FROM culture_media"):
            # Exclusivité du propriétaire : une photo appartient à un événement de culture
            # ou à une observation d'espace, jamais aux deux, jamais à aucun.
            event = row["owner_kind"] == "event"
            if (event != (row["event_id"] is not None) or event == (row["space_event_id"] is not None)
                    or event != (row["subject_id"] is not None) or event == (row["space"] is not None)):
                raise CultureError("Propriétaire de photo incohérent.")
            if row["space"] is not None and row["space"] not in SPACES:
                raise CultureError("Espace de photo inconnu.")
        # Chaque lot D à H fournit son validateur ; l'ordre suit celui des lots.
        self._validate_checklists()
        self._validate_targets()
        self._validate_light()
        self._validate_equipment()
        self._validate_journal()
