"""Repères d'éclairage informatifs (lot F) : squelette enregistré par la migration 4.

`culture_light_targets` naît vide : 18 h / 6 h et 12 h / 12 h sont des préremplissages de
formulaire, jamais des données existantes. Un repère ne commande rien — le rapprochement
avec les horaires réellement configurés se fait en lecture depuis la configuration déjà
distribuée, sans calcul de régulation ni acquisition.

Le validateur est appelé par `_cycle_validate` et rejoué par `restore_copy`.
"""

import uuid
from datetime import timezone
from zoneinfo import ZoneInfo

from model.culture import STAGES, SPACES, CultureConflict, CultureError, stamp, text_value
from model.culture_light import (LIGHT_PRESETS, LIGHT_SCOPES, MAX_LIGHT_ROWS, light_label,
                                 light_minutes, resolve_light, validate_light_windows)

# Colonnes écrites par une révision ; l'ordre suit celui de l'insertion.
LIGHT_COLUMNS = ("id", "revision", "scope", "subject_id", "space", "stage", "label",
                 "on_minutes", "off_minutes", "start_at", "start_precision", "start_sort_at",
                 "end_at", "end_precision", "end_sort_at", "note", "reason", "cancelled",
                 "recorded_at", "clock_reliable")
LIGHT_OPERATIONS = ("light", "light_close", "light_cancel")
LIGHT_FIELDS = {"request_id", "operation", "confirm_date", "id", "version", "scope", "subject_id",
                "space", "stage", "label", "on_minutes", "off_minutes", "start_at",
                "start_precision", "end_at", "end_precision", "note", "reason"}


class LightStoreMixin:
    def _light_rows(self, revisions=False):
        """Révisions courantes (ou toutes) des repères, annulations comprises."""
        sql = "SELECT l.* FROM culture_light_targets l"
        if not revisions:
            sql += " WHERE l.revision=(SELECT MAX(v.revision) FROM culture_light_targets v WHERE v.id=l.id)"
        sql += " ORDER BY l.start_sort_at DESC, l.id, l.revision DESC"
        return [dict(row) for row in self._db.execute(sql)]

    def _light_targets(self, filters=None):
        """Repères consultables, filtrés sur la portée, la cible et le stade."""
        filters = filters or {}
        if not isinstance(filters, dict) or set(filters) - {"scope", "target", "stage"}:
            raise CultureError("Filtre de repère inconnu.")
        scope, target, stage = filters.get("scope"), filters.get("target"), filters.get("stage")
        if scope and scope not in LIGHT_SCOPES:
            raise CultureError("Portée de repère inconnue.")
        if stage and stage not in STAGES:
            raise CultureError("Stade inconnu.")
        history = self._light_rows(revisions=True)
        rows = []
        for row in self._light_rows():
            if scope and row["scope"] != scope:
                continue
            if target and target not in (row["subject_id"], row["space"]):
                continue
            if stage and row["stage"] != stage:
                continue
            row["window_label"] = light_label(row["on_minutes"], row["off_minutes"])
            row["stage_label"] = STAGES.get(row["stage"]) if row["stage"] else None
            row["scope_label"] = LIGHT_SCOPES[row["scope"]]
            row["revisions"] = sorted((old for old in history
                                       if old["id"] == row["id"] and old["revision"] < row["revision"]),
                                      key=lambda old: old["revision"])
            rows.append(row)
        return rows[:MAX_LIGHT_ROWS]

    def _light_data(self, filters=None):
        """Repères, cultures en place et repère applicable à chacune, à cet instant.

        Le rapprochement avec les horaires configurés n'a pas sa place ici : le magasin
        ne lit jamais la configuration. La vue ajoute les horaires et l'état opérationnel.
        """
        now = self.now()
        at = now.astimezone(timezone.utc).isoformat()
        current = [row for row in self._light_rows() if not row["cancelled"]]
        subjects = self._projections()
        occupants = []
        for subject in subjects:
            if subject["archived"] or not subject["space"]:
                continue
            reference = resolve_light(at, subject["stage"], subject["id"], subject["space"], current)
            if reference:
                reference["window_label"] = light_label(reference["on_minutes"], reference["off_minutes"])
                reference["scope_label"] = LIGHT_SCOPES[reference["scope"]]
            occupants.append({"id": subject["id"], "name": subject["name"], "kind": subject["kind"],
                              "space": subject["space"], "stage": subject["stage"],
                              "stage_label": subject["stage_label"], "reference": reference})
        return {"available": True, "timezone": self.zone, "clock_reliable": self.reliable(),
                "today": now.astimezone(ZoneInfo(self.zone)).date().isoformat(),
                "at": at, "targets": self._light_targets(filters), "occupants": occupants,
                "presets": {stage: {"on_minutes": values[0], "off_minutes": values[1],
                                    "label": light_label(*values)}
                            for stage, values in LIGHT_PRESETS.items()},
                "subjects": [{"id": item["id"], "name": item["name"], "kind": item["kind"],
                              "archived": item["archived"]} for item in subjects]}

    def _light_mutate(self, command):
        """Saisie, correction, clôture et annulation d'un repère, dans sa transaction.

        Rien n'est écrit hors de `culture_light_targets` : ni configuration, ni sortie,
        ni alarme. Un repère refusé laisse la table dans son état antérieur.
        """
        if not isinstance(command, dict) or set(command) - LIGHT_FIELDS:
            raise CultureError("Commande de repère d'éclairage invalide.")

        def work():
            operation = command.get("operation")
            if operation not in LIGHT_OPERATIONS:
                raise CultureError("Opération de repère inconnue.")
            now = self.now()
            identifier, old, revision = command.get("id"), None, 1
            if identifier:
                identifier = text_value(identifier, "Identifiant", 100)
                old = self._db.execute("SELECT * FROM culture_light_targets WHERE id=?"
                                       " ORDER BY revision DESC LIMIT 1", (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Repère d'éclairage introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Ce repère a changé ; actualiser avant de poursuivre.")
                if old["cancelled"]:
                    raise CultureError("Ce repère est annulé ; en saisir un nouveau plutôt que le modifier.")
                revision = old["revision"] + 1
            elif operation != "light":
                raise CultureError("Identifiant de repère obligatoire.")
            else:
                identifier = str(uuid.uuid4())
            reason = text_value(command.get("reason", ""), "Motif", 500, revision > 1)
            if operation == "light":
                row = self._light_row(command, now)
            else:
                row = {key: old[key] for key in LIGHT_COLUMNS}
                if operation == "light_close":
                    end_at = command.get("end_at")
                    end_precision = command.get("end_precision", "date")
                    row["end_sort_at"] = stamp(end_at, end_precision, self.zone, now)[0]
                    row.update(end_at=end_at, end_precision=end_precision)
                else:
                    row["cancelled"] = 1
            row.update(id=identifier, revision=revision, reason=reason,
                       recorded_at=now.isoformat(), clock_reliable=int(self.reliable()))
            self._db.execute(
                f"INSERT INTO culture_light_targets ({','.join(LIGHT_COLUMNS)})"
                f" VALUES ({','.join('?' for _ in LIGHT_COLUMNS)})",
                tuple(row[key] for key in LIGHT_COLUMNS))
            # Tout le jeu de repères est revalidé avant commit : un chevauchement
            # introduit par une correction est refusé comme une saisie neuve.
            self._validate_light()
            return {"saved": True, "id": identifier, "version": revision}
        return self._aux_transaction(command, work)

    def _light_row(self, command, now):
        """Repère complet issu de la commande ; aucune valeur par défaut n'est inventée."""
        scope = command.get("scope")
        if scope not in LIGHT_SCOPES:
            raise CultureError("Portée attendue : toutes les cultures, un espace ou une culture.")
        subject_id, space = None, None
        if scope == "subject":
            subject_id = text_value(command.get("subject_id"), "Culture visée", 100)
            if self._db.execute("SELECT id FROM subjects WHERE id=?", (subject_id,)).fetchone() is None:
                raise CultureError("Culture visée introuvable.")
        if scope == "space":
            space = command.get("space")
            if space not in SPACES:
                raise CultureError("Espace visé inconnu.")
        stage = command.get("stage") or None
        if stage is not None and stage not in STAGES:
            raise CultureError("Stade de repère inconnu.")
        on_minutes, off_minutes = light_minutes(command.get("on_minutes"), command.get("off_minutes"))
        start_at = command.get("start_at")
        start_precision = command.get("start_precision", "date")
        start_sort_at = stamp(start_at, start_precision, self.zone, now)[0]
        end_at = command.get("end_at") or None
        end_precision, end_sort_at = None, None
        if end_at is not None:
            end_precision = command.get("end_precision", "date")
            end_sort_at = stamp(end_at, end_precision, self.zone, now)[0]
        return {"id": None, "revision": 1, "scope": scope, "subject_id": subject_id, "space": space,
                "stage": stage, "label": text_value(command.get("label"), "Nom du repère", 160),
                "on_minutes": on_minutes, "off_minutes": off_minutes,
                "start_at": start_at, "start_precision": start_precision, "start_sort_at": start_sort_at,
                "end_at": end_at, "end_precision": end_precision, "end_sort_at": end_sort_at,
                "note": text_value(command.get("note", ""), "Note", 4000, False),
                "reason": "", "cancelled": 0, "recorded_at": now.isoformat(),
                "clock_reliable": int(self.reliable())}

    def _validate_light(self):
        """Révisions 1..n sans trou, cycle de 24 h, fenêtres non chevauchantes."""
        validate_light_windows(self._light_rows(revisions=True))
