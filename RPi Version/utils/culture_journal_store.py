"""Journal transversal et observations d'espace (lot H), dans le thread SQLite du carnet.

Le journal est une **vue** `culture_journal` (une ligne par opération, cibles jointes à la
demande), jamais une table matérialisée : une copie serait une seconde vérité à
resynchroniser après chaque correction rétrospective. La vue est donc exclue de l'export,
qui reprend déjà ses trois sources.

`space_events` porte les observations d'espace sans créer de fausse plante et sans entrer
dans l'historique opérateur purgé à 72 h. Les photos facultatives de ces observations
passent par le magasin de photos existant, généralisé à `owner_kind` : mêmes plafonds,
même réencodage, même budget disque, une seule voie d'écriture.

La pagination est faite **en SQL** sur la vue (`LIMIT/OFFSET` plus un `COUNT(*)` séparé) :
l'enrichissement — libellés, cibles, photos, révisions précédentes — ne porte que sur les
40 lignes réellement affichées. Une entrée multi-cibles reste une ligne et compte pour 1.
"""

import csv
import io
import json
import uuid
from zoneinfo import ZoneInfo

from model.culture import KINDS, SPACES, CultureConflict, CultureError, stamp, text_value
from model.culture_journal import (JOURNAL_PAGE, JOURNAL_SOURCES, JOURNAL_TYPES,
                                   SPACE_EVENT_KINDS, journal_filters, journal_target_kind,
                                   journal_window, space_event_payload, validate_space_events)
from model.culture_solution import RESERVOIRS, SOLUTION_KINDS

# Colonnes écrites par une saisie ou une correction d'observation d'espace.
SPACE_EVENT_COLUMNS = ("id", "revision", "space", "kind", "effective_at", "precision", "sort_at",
                       "recorded_at", "clock_reliable", "payload", "cancelled", "reason",
                       "equipment_context")
# Clé de tri totale de la vue : sans elle, deux opérations de même date changeraient de
# page d'une requête à l'autre et la pagination perdrait des lignes.
JOURNAL_ORDER = "j.sort_at DESC, j.ordinal DESC, j.source, j.entry_id"


class JournalStoreMixin:
    def _space_event_mutate(self, command):
        """Créer, corriger ou annuler une observation d'espace, sans toucher aux cultures."""
        allowed = {"request_id", "operation", "confirm_date", "id", "version", "space", "kind",
                   "effective_at", "precision", "note", "cancelled", "reason"}
        if not isinstance(command, dict) or set(command) - allowed:
            raise CultureError("Commande d'observation invalide.")

        def work():
            operation = command.get("operation")
            if operation not in ("space_event", "correct"):
                raise CultureError("Opération attendue : space_event ou correct.")
            now = self.now()
            old = None
            revision = 1
            if operation == "correct":
                identifier = text_value(command.get("id"), "Identifiant")
                old = self._db.execute("SELECT * FROM space_events WHERE id=? ORDER BY revision DESC LIMIT 1",
                                       (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Observation introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Cette observation a changé ; relire sa version actuelle avant de corriger.")
                revision = old["revision"] + 1
            elif command.get("id"):
                raise CultureError("Une nouvelle observation ne porte pas d'identifiant.")
            else:
                identifier = str(uuid.uuid4())
            space = command.get("space", old["space"] if old else None)
            kind = command.get("kind", old["kind"] if old else "observation")
            if space not in SPACES:
                raise CultureError("Espace d'observation inconnu.")
            if old is not None and (space != old["space"] or kind != old["kind"]):
                # L'identité de la cible et du genre fait la trace : la déplacer réécrirait
                # l'histoire au lieu de la corriger. Annuler puis ressaisir reste possible.
                raise CultureError("L'espace et le genre d'une observation ne se corrigent pas ; annuler puis ressaisir.")
            effective = command.get("effective_at", old["effective_at"] if old else None)
            precision = command.get("precision", old["precision"] if old else "date")
            sort_at = stamp(effective, precision, self.zone, now, field="effective_at")[0]
            previous = json.loads(old["payload"])["note"] if old is not None else None
            payload = space_event_payload(kind, {"note": command.get("note", previous)})
            cancelled = command.get("cancelled", False)
            if type(cancelled) is not bool:
                raise CultureError("Annulation : booléen attendu.")
            reason = text_value(command.get("reason", ""), "Motif", 500, operation == "correct", field="reason")
            self._db.execute(
                f"INSERT INTO space_events ({','.join(SPACE_EVENT_COLUMNS)})"
                f" VALUES ({','.join('?' for _ in SPACE_EVENT_COLUMNS)})",
                (identifier, revision, space, kind, effective, precision, sort_at, now.isoformat(),
                 int(self.reliable()), json.dumps(payload, ensure_ascii=False, allow_nan=False),
                 int(cancelled), reason, "{}"))
            return {"saved": True, "id": identifier, "version": revision, "space": space}
        return self._aux_transaction(command, work)

    def _journal_where(self, filters):
        """Clause SQL du filtre, cibles comprises ; une ligne reste unique quel qu'en soit le nombre."""
        filters = journal_filters(filters)
        clauses, params = [], {}
        start, end = journal_window(filters, self.zone)
        if start:
            clauses.append("j.sort_at >= :start")
            params["start"] = start
        if end:
            clauses.append("j.sort_at < :end")
            params["end"] = end
        if filters.get("type"):
            source, _, kind = filters["type"].partition(":")
            clauses.append("j.source = :source AND j.kind = :kind")
            params.update(source=source, kind=kind)
        if filters.get("target"):
            target = filters["target"]
            journal_target_kind(target, {row[0] for row in self._db.execute("SELECT id FROM subjects")})
            params["target"] = target
            # Les cibles d'un arrosage partagé et les sujets alimentés passent par des
            # EXISTS : la ligne de la vue n'est jamais dupliquée par une jointure.
            clauses.append("""(j.subject_id = :target OR j.space = :target OR j.reservoir_id = :target
              OR EXISTS(SELECT 1 FROM solution_targets t
                         WHERE t.entry_id = j.entry_id AND t.revision = j.revision AND t.subject_id = :target)
              OR EXISTS(SELECT 1 FROM solution_links l JOIN solution_periods p ON p.id = l.period_id
                         WHERE l.subject_id = :target AND p.reservoir_id = j.reservoir_id
                           AND p.start_at <= j.sort_at AND j.sort_at < COALESCE(p.end_at,'9999')
                           AND l.start_at <= j.sort_at AND j.sort_at < COALESCE(l.end_at,'9999')))""")
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params, filters

    def _journal_position(self, where, params, focus):
        """Décalage de la page contenant une opération, compté en SQL sur la clé de tri totale."""
        row = self._db.execute("SELECT sort_at, ordinal, source, entry_id FROM culture_journal"
                               " WHERE entry_id=? LIMIT 1", (focus,)).fetchone()
        if row is None:
            return None
        anchor = {"a_sort": row["sort_at"], "a_ordinal": row["ordinal"],
                  "a_source": row["source"], "a_entry": row["entry_id"]}
        before = self._db.execute(
            f"SELECT COUNT(*) FROM culture_journal j{where}{' AND' if where else ' WHERE'}"
            " (j.sort_at > :a_sort OR (j.sort_at = :a_sort AND j.ordinal > :a_ordinal)"
            "  OR (j.sort_at = :a_sort AND j.ordinal = :a_ordinal AND j.source < :a_source)"
            "  OR (j.sort_at = :a_sort AND j.ordinal = :a_ordinal AND j.source = :a_source"
            "      AND j.entry_id < :a_entry))", {**params, **anchor}).fetchone()[0]
        return before // JOURNAL_PAGE * JOURNAL_PAGE

    def _journal_enrich(self, rows):
        """Libellés, cibles, photos et versions précédentes de la seule page affichée."""
        names = {row["id"]: row["name"] for row in self._db.execute("SELECT id, name FROM subjects")}
        items = []
        for row in rows:
            item = dict(row)
            entry, revision = item["entry_id"], item["revision"]
            item["cancelled"] = bool(item["cancelled"])
            item["source_label"] = JOURNAL_SOURCES[item["source"]]
            item["type"] = f"{item['source']}:{item['kind']}"
            item["type_label"] = JOURNAL_TYPES.get(item["type"], item["kind"])
            item.update(note="", reason="", targets=[], photos=[], revisions=[], measures=None, editable=False)
            if item["source"] == "event":
                full = self._db.execute("SELECT * FROM events WHERE id=? AND revision=?", (entry, revision)).fetchone()
                payload = json.loads(full["payload"])
                item["note"] = payload.get("note", "") or payload.get("lessons", "")
                item["reason"] = full["reason"]
                item["kind_label"] = KINDS.get(item["kind"], item["kind"])
                item["targets"] = [{"kind": "subject", "id": item["subject_id"],
                                    "name": names.get(item["subject_id"], item["subject_id"])}]
                item["link"] = "/cultures/" + item["subject_id"]
                item["photos"] = self._media_for_events([entry])
                item["revisions"] = [dict(old) for old in self._db.execute(
                    "SELECT revision, recorded_at, cancelled, reason FROM events"
                    " WHERE id=? AND revision<? ORDER BY revision", (entry, revision))]
            elif item["source"] == "solution":
                full = self._db.execute("SELECT * FROM solution_entries WHERE id=? AND revision=?",
                                        (entry, revision)).fetchone()
                item["note"] = full["note"]
                item["reason"] = full["reason"]
                item["kind_label"] = SOLUTION_KINDS.get(item["kind"], item["kind"])
                item["measures"] = {key: full[key] for key in ("ph", "ec", "volume_l")}
                item["targets"] = [{"kind": "subject", "id": row[0], "name": names.get(row[0], row[0])}
                                   for row in self._db.execute(
                                       "SELECT subject_id FROM solution_targets WHERE entry_id=? AND revision=?"
                                       " ORDER BY subject_id", (entry, revision))]
                if item["reservoir_id"]:
                    item["targets"].append({"kind": "reservoir", "id": item["reservoir_id"],
                                            "name": RESERVOIRS[item["reservoir_id"]][0]
                                            if item["reservoir_id"] in RESERVOIRS else item["reservoir_id"]})
                item["link"] = "/cultures/solutions?entry=" + entry
                item["revisions"] = [dict(old) for old in self._db.execute(
                    "SELECT revision, recorded_at, cancelled, reason FROM solution_entries"
                    " WHERE id=? AND revision<? ORDER BY revision", (entry, revision))]
            else:
                full = self._db.execute("SELECT * FROM space_events WHERE id=? AND revision=?",
                                        (entry, revision)).fetchone()
                item["note"] = json.loads(full["payload"])["note"]
                item["reason"] = full["reason"]
                item["kind_label"] = SPACE_EVENT_KINDS.get(item["kind"], item["kind"])
                item["targets"] = [{"kind": "space", "id": item["space"],
                                    "name": SPACES.get(item["space"], item["space"])}]
                item["link"] = "/cultures/journal?focus=" + entry
                item["photos"] = self._media_for_events([entry], "space_event")
                item["editable"] = not item["cancelled"]
                item["revisions"] = []
                for old in self._db.execute("SELECT revision, recorded_at, cancelled, reason, payload"
                                            " FROM space_events WHERE id=? AND revision<? ORDER BY revision",
                                            (entry, revision)):
                    previous = dict(old)
                    previous["note"] = json.loads(previous.pop("payload"))["note"]
                    item["revisions"].append(previous)
            item["target_label"] = " et ".join(target["name"] for target in item["targets"]) or "—"
            items.append(item)
        return items

    def _journal(self, filters=None, offset=0, focus=None):
        """Page bornée du journal transversal : LIMIT/OFFSET en SQL, jamais tout le carnet."""
        where, params, filters = self._journal_where(filters)
        total = self._db.execute(f"SELECT COUNT(*) FROM culture_journal j{where}", params).fetchone()[0]
        try:
            offset = int(offset)
        except (TypeError, ValueError):
            raise CultureError("Pagination du journal invalide.") from None
        offset = max(0, min(offset, max(total - 1, 0))) // JOURNAL_PAGE * JOURNAL_PAGE
        if focus:
            position = self._journal_position(where, params, text_value(focus, "Opération", 100))
            if position is not None:
                offset = position
        rows = self._db.execute(
            f"SELECT j.* FROM culture_journal j{where} ORDER BY {JOURNAL_ORDER} LIMIT :limit OFFSET :offset",
            {**params, "limit": JOURNAL_PAGE, "offset": offset}).fetchall()
        subjects = [{"id": s["id"], "name": s["name"], "kind": s["kind"]} for s in
                    self._db.execute("SELECT id, name, kind FROM subjects ORDER BY name")]
        return {"items": self._journal_enrich(rows), "total": total, "offset": offset,
                "page": JOURNAL_PAGE, "filters": filters, "focus": focus or "",
                "subjects": subjects, "spaces": SPACES, "types": JOURNAL_TYPES,
                "reservoirs": {key: value[0] for key, value in RESERVOIRS.items()},
                "kinds": SPACE_EVENT_KINDS, "storage": self._media_storage(),
                "timezone": self.zone, "clock_reliable": self.reliable(),
                "today": self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()}

    def _journal_csv(self, filters=None):
        """Export du filtre courant : une ligne par opération, cibles en JSON, textes neutralisés."""
        where, params, _filters = self._journal_where(filters)
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["source", "operation_id", "revision", "type", "date_effective", "precision",
                         "saisi_le", "annule", "cibles", "note", "motif"])

        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value

        rows = self._db.execute(f"SELECT j.* FROM culture_journal j{where} ORDER BY {JOURNAL_ORDER}", params).fetchall()
        for item in self._journal_enrich(rows):
            writer.writerow([safe(value) for value in (
                item["source"], item["entry_id"], item["revision"], item["type"], item["effective_at"],
                item["precision"], item["recorded_at"], int(item["cancelled"]),
                json.dumps(item["targets"], ensure_ascii=False), item["note"], item["reason"])])
        return output.getvalue()

    def _validate_journal(self):
        """Invariants des observations d'espace, rejoués à chaque restauration vérifiée."""
        validate_space_events(self._db.execute("SELECT * FROM space_events"))
