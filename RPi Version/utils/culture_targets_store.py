"""Plages cibles pH/EC historisées (lot E) : saisie, lecture et invariants.

La table `culture_targets` naît vide au schéma 4 : aucune plage par défaut n'est inventée,
ni à la migration ni à la lecture. Une plage est une déclaration ; rien ici n'accède au GPIO,
à `param.json` ou aux alarmes de contrôle.

Toutes les méthodes tournent dans le thread SQLite unique du carnet, dans la transaction
idempotente de `CycleStoreMixin._aux_transaction`. Les règles pures (bornes, unités,
fenêtres, résolution du contexte) vivent dans `model/culture_targets.py`.
"""

import csv
import io
import uuid
from zoneinfo import ZoneInfo

from model.culture import CultureConflict, CultureError, STAGES, stamp, text_value
from model.culture_solution import RESERVOIRS
from model.culture_targets import bounds, resolve_targets, validate_target_windows

TARGET_COLUMNS = ("id", "revision", "scope", "subject_id", "reservoir_id", "stage", "label",
                  "ph_min", "ph_max", "ec_min", "ec_max", "start_at", "start_precision", "start_sort_at",
                  "end_at", "end_precision", "end_sort_at", "note", "reason", "cancelled",
                  "recorded_at", "clock_reliable")
TARGET_FIELDS = {"request_id", "operation", "confirm_date", "id", "version", "target", "stage",
                 "label", "ph_min", "ph_max", "ec_min", "ec_max", "ec_unit", "start_at",
                 "start_precision", "end_at", "end_precision", "note", "reason", "action"}
TARGET_PAGE = 40


class TargetsStoreMixin:
    def _current_targets(self):
        """Révisions courantes de toutes les plages, annulées comprises."""
        return [dict(row) for row in self._db.execute(
            "SELECT t.* FROM culture_targets t"
            " WHERE t.revision=(SELECT MAX(v.revision) FROM culture_targets v WHERE v.id=t.id)"
            " ORDER BY t.start_sort_at DESC, t.id")]

    def _targets_selected(self, filters, subjects):
        """Plages courantes retenues par le filtre ; l'export n'est jamais paginé."""
        filters = filters or {}
        if set(filters) - {"target", "scope"}:
            raise CultureError("Filtre de plage cible inconnu.")
        target = filters.get("target", "")
        if target and target not in RESERVOIRS and target not in {s["id"] for s in subjects}:
            raise CultureError("Cible de filtre inconnue.")
        scope = filters.get("scope", "")
        if scope and scope not in ("subject", "reservoir"):
            raise CultureError("Portée de filtre inconnue.")
        return [row for row in self._current_targets()
                if (not target or target in (row["subject_id"], row["reservoir_id"]))
                and (not scope or scope == row["scope"])]

    def _targets(self, filters=None, offset=0):
        """Plages courantes filtrées, leurs révisions, et le contexte de saisie."""
        subjects = self._projections()
        selected = self._targets_selected(filters, subjects)
        page = selected[offset:offset + TARGET_PAGE]
        for row in page:
            row["revisions"] = [dict(old) for old in self._db.execute(
                "SELECT * FROM culture_targets WHERE id=? AND revision<? ORDER BY revision",
                (row["id"], row["revision"]))]
        return {"items": page, "total": len(selected), "offset": offset,
                "reservoirs": [dict(row) for row in self._db.execute("SELECT * FROM reservoirs")],
                "subjects": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "archived": s["archived"]}
                             for s in subjects],
                "stages": STAGES, "timezone": self.zone, "clock_reliable": self.reliable(),
                "today": self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()}

    def _target_resolution(self, target=None, at=None):
        """Plage applicable à une cible consultée, à une date, avec sa source.

        Lecture seule et bornée : les révisions courantes des plages, les associations
        d'alimentation déclarées à cette date (`_feeding_at`, domaine des solutions), puis
        la règle **pure** `resolve_targets` — priorité stricte cible directe → sujet
        alimenté → réservoir, sans fusion et sans rétroactivité. Aucune projection du
        carnet n'est refaite et rien n'est écrit.

        L'entrée est exactement celle d'un relevé de cette cible à cette date :
        * un **réservoir** consulté alimente des sujets, qui passent avant lui — c'est là
          que la source « sujet alimenté » se produit ;
        * une **culture** consultée est la cible directe, et **rien d'autre** : sa cascade
          s'arrête là, puisqu'un relevé la visant ne porte pas de réservoir. Les réservoirs
          qui l'alimentent sont rendus dans `reservoirs` à titre d'information, jamais
          comme une étape de résolution.

        Les identifiants sont rendus tels quels : les noms affichés viennent des
        projections déjà envoyées à la page, jamais d'une seconde vérité recopiée ici.
        """
        target = text_value(target, "Cible", field="target")
        known = self._db.execute("SELECT id FROM subjects WHERE id=?", (target,)).fetchone()
        if target not in RESERVOIRS and known is None:
            raise CultureError("Cible de plage cible inconnue.", "target")
        key = stamp(at, "date", self.zone, self.now(), field="at")[0]
        feeding = self._feeding_at(target, key)
        if target in RESERVOIRS:
            entry = {"sort_at": key, "targets": [], "fed_subjects": feeding["fed_subjects"],
                     "reservoir_id": target}
        else:
            # Un relevé qui vise une culture ne porte **jamais** de réservoir : le carnet
            # refuse `targets` et `reservoir_id` ensemble (`_solution_mutate`). Fabriquer
            # ici un `reservoir_id` ferait annoncer une plage « réservoir » qu'aucun relevé
            # de cette culture ne recevrait — la page mentirait sur ce qui s'applique.
            # Le réservoir alimentant reste rendu à part, comme un fait daté.
            entry = {"sort_at": key, "targets": [target], "fed_subjects": [],
                     "reservoir_id": None}
        rows = self._current_targets()
        resolved = resolve_targets(entry, rows)
        if resolved is not None:
            row = next(item for item in rows if item["id"] == resolved["id"])
            # Dates **déclarées**, pas les clés de tri : celles-ci sont en UTC et
            # reculeraient d'un jour toute plage ouverte un 1er du mois à Paris.
            resolved.update({field: row[field] for field in
                             ("start_at", "start_precision", "end_at", "end_precision")})
        return {"at": at, "at_key": key, "target": target,
                "kind": "reservoir" if target in RESERVOIRS else "subject",
                "range": resolved, "fed_subjects": feeding["fed_subjects"],
                "reservoirs": feeding["reservoirs"],
                "ambiguous_reservoir": len(feeding["reservoirs"]) > 1}

    def _target_mutate(self, command):
        """Crée, corrige, clôt ou annule une plage cible ; chaque écriture est une révision."""
        if not isinstance(command, dict) or set(command) - TARGET_FIELDS:
            raise CultureError("Commande de plage cible invalide.")

        def work():
            operation = command.get("operation")
            if operation not in ("target", "target_action"):
                raise CultureError("Opération de plage cible inconnue.")
            now = self.now()
            identifier = command.get("id")
            old, revision = None, 1
            if identifier:
                identifier = text_value(identifier, "Identifiant")
                old = self._db.execute(
                    "SELECT * FROM culture_targets WHERE id=? ORDER BY revision DESC LIMIT 1",
                    (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Plage cible introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Cette plage cible a changé ; actualiser avant de poursuivre.")
                revision = old["revision"] + 1
            elif operation == "target_action":
                raise CultureError("Identifiant de plage cible obligatoire.")
            else:
                identifier = str(uuid.uuid4())
            if operation == "target":
                row = self._target_row(command, identifier, revision, now, old)
            else:
                row = self._target_action(command, dict(old), revision, now)
            self._db.execute(
                f"INSERT INTO culture_targets ({','.join(TARGET_COLUMNS)})"
                f" VALUES ({','.join('?' for _ in TARGET_COLUMNS)})",
                tuple(row[column] for column in TARGET_COLUMNS))
            # Les fenêtres sont revalidées dans la transaction : un chevauchement introduit
            # par cette révision annule l'écriture, il n'est jamais commis puis signalé.
            validate_target_windows(self._current_targets())
            return {"saved": True, "id": identifier, "version": revision}
        return self._aux_transaction(command, work)

    def _target_row(self, command, identifier, revision, now, old=None):
        """Ligne complète d'une saisie ou d'une correction : tout est resaisi, rien n'est hérité.

        Une annulation reste acquise : corriger une plage annulée ne la remet pas en vigueur,
        sinon le motif d'annulation serait effacé par une simple resaisie.
        """
        if old is not None and old["cancelled"]:
            raise CultureError("Une plage annulée conserve son historique ; créer une nouvelle plage.")
        target = text_value(command.get("target"), "Cible", field="target")
        if target in RESERVOIRS:
            scope, subject_id, reservoir_id = "reservoir", None, target
        elif self._db.execute("SELECT id FROM subjects WHERE id=?", (target,)).fetchone():
            scope, subject_id, reservoir_id = "subject", target, None
        else:
            raise CultureError("Cible de plage cible inconnue.", "target")
        stage = command.get("stage") or None
        if stage is not None and stage not in STAGES:
            raise CultureError("Stade de contexte inconnu.", "stage")
        start_precision = command.get("start_precision", "date")
        start_sort_at = stamp(command.get("start_at"), start_precision, self.zone, now, field="start_at")[0]
        end_at, end_precision, end_sort_at = self._target_end(command, start_sort_at, now)
        return {"id": identifier, "revision": revision, "scope": scope, "subject_id": subject_id,
                "reservoir_id": reservoir_id, "stage": stage,
                "label": text_value(command.get("label", ""), "Intitulé", 120, False, field="label"),
                **bounds(command), "start_at": command.get("start_at"), "start_precision": start_precision,
                "start_sort_at": start_sort_at, "end_at": end_at, "end_precision": end_precision,
                "end_sort_at": end_sort_at,
                "note": text_value(command.get("note", ""), "Note", 4000, False, field="note"),
                "reason": text_value(command.get("reason", ""), "Motif", 500, False, field="reason"),
                "cancelled": 0, "recorded_at": now.isoformat(),
                "clock_reliable": int(self.reliable())}

    def _target_end(self, command, start_sort_at, now):
        """Fin de validité facultative ; elle doit suivre strictement le début."""
        if not command.get("end_at"):
            return None, None, None
        precision = command.get("end_precision", "date")
        key = stamp(command["end_at"], precision, self.zone, now, field="end_at")[0]
        if key <= start_sort_at:
            raise CultureError("La fin de validité doit suivre le début de la plage.", "end_at")
        return command["end_at"], precision, key

    def _target_action(self, command, old, revision, now):
        """Clôture ou annulation : la plage garde ses bornes, seule sa validité change."""
        action = command.get("action")
        if action not in ("end", "cancel"):
            raise CultureError("Action attendue : clore la validité ou annuler.")
        if action == "cancel" and old["cancelled"]:
            raise CultureError("Cette plage cible est déjà annulée.")
        row = {**old, "revision": revision, "recorded_at": now.isoformat(),
               "clock_reliable": int(self.reliable()),
               "reason": text_value(command.get("reason", ""), "Motif", 500, action == "cancel",
                                    field="reason")}
        if action == "cancel":
            row["cancelled"] = 1
            return row
        if old["cancelled"]:
            raise CultureError("Une plage annulée ne se clôt pas ; créer une nouvelle plage.")
        end_at, end_precision, end_sort_at = self._target_end(command, old["start_sort_at"], now)
        if end_sort_at is None:
            raise CultureError("Renseigner la date de fin de validité.", "end_at")
        row.update(end_at=end_at, end_precision=end_precision, end_sort_at=end_sort_at)
        return row

    def _targets_csv(self, filters=None):
        """Export dédié des plages elles-mêmes ; les relevés portent leur cible résolue."""
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        fields = ["id", "revision", "scope", "subject_id", "reservoir_id", "stage", "label",
                  "ph_min", "ph_max", "ec_min", "ec_max", "start_at", "start_precision",
                  "end_at", "end_precision", "cancelled", "recorded_at", "note", "reason"]
        writer.writerow(["ec_min_mS_cm" if f == "ec_min" else "ec_max_mS_cm" if f == "ec_max" else f
                         for f in fields])
        for row in self._targets_selected(filters, self._projections()):
            line = []
            for field in fields:
                value = row.get(field)
                value = "" if value is None else str(value)
                if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                    value = "'" + value
                line.append(value)
            writer.writerow(line)
        return output.getvalue()

    def _validate_targets(self):
        """Révisions sans trou depuis 1, bornes finies et fenêtres non chevauchantes."""
        revisions = {}
        for row in self._db.execute("SELECT id, revision, cancelled FROM culture_targets"):
            if row["cancelled"] not in (0, 1):
                raise CultureError("Plage cible de sauvegarde incohérente.")
            revisions.setdefault(row["id"], []).append(row["revision"])
        for values in revisions.values():
            if sorted(values) != list(range(1, len(values) + 1)):
                raise CultureError("Révisions de plage cible manquantes ou dupliquées.")
        rows = self._current_targets()
        known = {row[0] for row in self._db.execute("SELECT id FROM reservoirs")}
        for row in rows:
            if row["reservoir_id"] is not None and row["reservoir_id"] not in known:
                raise CultureError("Réservoir de plage cible inconnu.")
            if row["stage"] is not None and row["stage"] not in STAGES:
                raise CultureError("Stade de plage cible inconnu.")
        validate_target_windows(rows)
