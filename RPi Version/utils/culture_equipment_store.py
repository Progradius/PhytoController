"""Affectations d'équipements datées (lot G) : squelette enregistré par la migration 4.

`culture_equipment_links` naît vide : la migration n'invente aucune date de réaffectation
passée. Le contexte connu à la saisie reste porté par `equipment_context` (événements,
relevés, vérifications, observations d'espace) ; à défaut, l'interface doit dire
« association inconnue à cette date » plutôt que retomber sur le catalogue courant.

`equipment_id` est validé en Python contre `EQUIPMENT_IDS` : le catalogue est du code, pas
du schéma. Le lot G remplit ce module et son validateur, déjà appelé par `_cycle_validate`.

Tout est déclaratif : ce magasin ne touche ni le GPIO, ni `param.json`, ni
`param/equipment_metadata.json`. Le catalogue courant lui est **passé** par la vue, en
lecture seule, pour figer un libellé au moment de la saisie.
"""

import json
import uuid

from zoneinfo import ZoneInfo

from model.culture import CultureConflict, CultureError, SPACES, stamp, text_value
from model.culture_equipment import (EQUIPMENT_SCOPES, EQUIPMENT_SOURCES, USAGE_SUGGESTIONS,
                                     equipment_value, resolve_equipment, scope_target,
                                     source_value, usage_value, validate_equipment_windows)
from model.culture_solution import RESERVOIRS
from param.equipment_metadata import EQUIPMENT_IDS

EQUIPMENT_COLUMNS = ("id", "revision", "equipment_id", "scope", "space", "reservoir_id", "usage",
                     "display_name", "start_at", "start_precision", "start_sort_at", "end_at",
                     "end_precision", "end_sort_at", "source", "note", "reason", "cancelled",
                     "recorded_at", "clock_reliable")
EQUIPMENT_FIELDS = {"request_id", "operation", "confirm_date", "id", "version", "equipment_id",
                    "scope", "space", "reservoir_id", "usage", "start_at", "start_precision",
                    "end_at", "end_precision", "source", "note", "reason"}
EQUIPMENT_OPERATIONS = ("link", "correct", "close", "cancel")


class EquipmentStoreMixin:
    def _equipment_rows(self, revisions=False):
        sql = "SELECT c.* FROM culture_equipment_links c"
        if not revisions:
            sql += (" WHERE c.revision=(SELECT MAX(v.revision) FROM culture_equipment_links v"
                    " WHERE v.id=c.id)")
        sql += " ORDER BY c.equipment_id, c.start_sort_at, c.id, c.revision"
        return [dict(row) for row in self._db.execute(sql)]

    def _equipment_context_at(self, at, recorded_context=None, recorded_at=None, links=None):
        """Résolution réutilisable par les autres lots : contexte d'équipement à une date.

        Aucune lecture du catalogue courant n'entre ici : une association inconnue reste
        inconnue. `recorded_context` est la copie de catalogue portée par la saisie.
        """
        if isinstance(recorded_context, (str, bytes)):
            try:
                recorded_context = json.loads(recorded_context)
            except (ValueError, TypeError):
                recorded_context = {}
        rows = self._equipment_rows() if links is None else links
        return resolve_equipment(at, rows, recorded_context, recorded_at=recorded_at)

    def _equipment_links(self, filters=None, catalog=None):
        """Catalogue courant en lecture seule, périodes par équipement et résolution datée."""
        filters = filters or {}
        if not isinstance(filters, dict) or set(filters) - {"at", "equipment"}:
            raise CultureError("Filtre d'affectation inconnu.")
        equipment = filters.get("equipment") or ""
        if equipment:
            equipment_value(equipment)
        at = filters.get("at") or ""
        at_key = None
        if at:
            at_key = stamp(at, "date" if len(at) == 10 else "instant", self.zone, self.now())[0]
        catalog = catalog if isinstance(catalog, dict) else {}
        rows = self._equipment_rows()
        history = self._equipment_rows(revisions=True)
        for row in rows:
            row["revisions"] = [old for old in history
                                if old["id"] == row["id"] and old["revision"] < row["revision"]]
        groups = []
        for key in EQUIPMENT_IDS:
            entry = catalog.get(key) if isinstance(catalog.get(key), dict) else {}
            groups.append({"equipment_id": key,
                           # Nom courant du catalogue : source de vérité, jamais réécrit ici.
                           "current_name": entry.get("display_name", ""),
                           "current_usage": entry.get("usage_type", ""),
                           "zone": entry.get("zone", ""),
                           "out_of_service": bool(entry.get("out_of_service", False)),
                           "known": key in catalog,
                           "links": [row for row in rows if row["equipment_id"] == key]})
        selected = [group for group in groups if not equipment or group["equipment_id"] == equipment]
        return {"available": True, "timezone": self.zone, "clock_reliable": self.reliable(),
                "today": self.now().astimezone(ZoneInfo(self.zone)).date().isoformat(),
                "equipments": selected, "total": sum(len(group["links"]) for group in selected),
                "at": at, "at_key": at_key,
                "resolved": self._equipment_context_at(at_key, None, None, rows) if at_key else None,
                "scopes": EQUIPMENT_SCOPES, "sources": EQUIPMENT_SOURCES,
                "usages": list(USAGE_SUGGESTIONS), "spaces": SPACES,
                "reservoirs": {key: value[0] for key, value in RESERVOIRS.items()}}

    def _equipment_mutate(self, command, catalog=None):
        """Créer, corriger, clore ou annuler une affectation, dans une transaction idempotente."""
        if not isinstance(command, dict) or set(command) - EQUIPMENT_FIELDS:
            raise CultureError("Commande d'affectation invalide.")
        catalog = catalog if isinstance(catalog, dict) else {}

        def work():
            operation = command.get("operation")
            if operation not in EQUIPMENT_OPERATIONS:
                raise CultureError("Opération attendue : créer, corriger, clore ou annuler.")
            now = self.now()
            identifier = command.get("id")
            old, revision = None, 1
            if identifier:
                identifier = text_value(identifier, "Identifiant")
                old = self._db.execute("SELECT * FROM culture_equipment_links WHERE id=?"
                                       " ORDER BY revision DESC LIMIT 1", (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Affectation introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Cette affectation a changé ; actualiser avant de corriger.")
                old = dict(old)
                revision = old["revision"] + 1
            elif operation != "link":
                raise CultureError("Identifiant de l'affectation obligatoire.")
            else:
                identifier = str(uuid.uuid4())
            if old and old["cancelled"] and operation != "correct":
                raise CultureError("Cette affectation est annulée ; en saisir une nouvelle.")
            if operation == "cancel":
                row = {**old, "revision": revision, "cancelled": 1,
                       "reason": text_value(command.get("reason"), "Motif d'annulation", 500),
                       "recorded_at": now.isoformat(), "clock_reliable": int(self.reliable())}
            elif operation == "close":
                if old["end_at"]:
                    raise CultureError("Cette affectation est déjà close ; la corriger pour changer sa fin.")
                end_at = command.get("end_at")
                end_precision = command.get("end_precision", "date")
                if not end_at:
                    raise CultureError("Renseigner la date de fin de l'affectation.")
                end_key = stamp(end_at, end_precision, self.zone, now)[0]
                if end_key <= old["start_sort_at"]:
                    raise CultureError("La fin d'une affectation suit son début.")
                row = {**old, "revision": revision, "end_at": end_at, "end_precision": end_precision,
                       "end_sort_at": end_key, "recorded_at": now.isoformat(),
                       "clock_reliable": int(self.reliable()),
                       "reason": text_value(command.get("reason", ""), "Motif", 500, False)}
            else:
                base = old or {}
                equipment_id = equipment_value(command.get("equipment_id") or base.get("equipment_id"))
                # Une correction muette conserve la valeur précédente ; changer la portée
                # impose de redonner sa cible, sinon un espace resterait accroché à un
                # réservoir.
                if "scope" in command or not base:
                    scope, space, reservoir_id = (command.get("scope"), command.get("space"),
                                                  command.get("reservoir_id"))
                else:
                    scope, space, reservoir_id = (base.get("scope"), base.get("space"),
                                                  base.get("reservoir_id"))
                scope, space, reservoir_id = scope_target(scope, space, reservoir_id)
                usage = usage_value(command.get("usage") if command.get("usage") is not None else base.get("usage"))
                start_at = command.get("start_at") or base.get("start_at")
                start_precision = command.get("start_precision") or base.get("start_precision") or "date"
                start_key = stamp(start_at, start_precision, self.zone, now)[0]
                if "end_at" in command:
                    end_at = command.get("end_at") or None
                    end_precision = command.get("end_precision", "date") if end_at else None
                else:
                    end_at, end_precision = base.get("end_at"), base.get("end_precision")
                end_key = None
                if end_at:
                    end_key = stamp(end_at, end_precision, self.zone, now)[0]
                    if end_key <= start_key:
                        raise CultureError("La fin d'une affectation suit son début.")
                else:
                    end_at, end_precision = None, None
                # Le libellé est figé à la saisie : il n'est recopié du catalogue que pour
                # une affectation neuve ou un changement d'équipement, jamais rafraîchi.
                previous_name = base.get("display_name", "") if base.get("equipment_id") == equipment_id else ""
                entry = catalog.get(equipment_id) if isinstance(catalog.get(equipment_id), dict) else {}
                row = {"id": identifier, "revision": revision, "equipment_id": equipment_id,
                       "scope": scope, "space": space, "reservoir_id": reservoir_id, "usage": usage,
                       "display_name": previous_name or str(entry.get("display_name", ""))[:64],
                       "start_at": start_at, "start_precision": start_precision, "start_sort_at": start_key,
                       "end_at": end_at, "end_precision": end_precision, "end_sort_at": end_key,
                       "source": source_value(command.get("source") or base.get("source")),
                       "note": text_value(command.get("note", base.get("note", "")), "Note", 4000, False),
                       "reason": text_value(command.get("reason", ""), "Motif", 500, False),
                       "cancelled": 0, "recorded_at": now.isoformat(),
                       "clock_reliable": int(self.reliable())}
            values = tuple(row[column] for column in EQUIPMENT_COLUMNS)
            self._db.execute(
                f"INSERT INTO culture_equipment_links ({','.join(EQUIPMENT_COLUMNS)})"
                f" VALUES ({','.join('?' for _ in EQUIPMENT_COLUMNS)})", values)
            # Les contradictions sont refusées dans la transaction : rien n'est écrit si
            # deux affectations du même équipement se recouvrent.
            self._validate_equipment()
            return {"saved": True, "id": identifier, "version": revision,
                    "equipment_id": row["equipment_id"]}
        return self._aux_transaction(command, work)

    def _validate_equipment(self):
        """Invariants des affectations d'équipements, rejoués aussi à la restauration.

        Révisions 1..n sans trou, `equipment_id` dans `EQUIPMENT_IDS`, portées cohérentes
        et fenêtres non chevauchantes par équipement.
        """
        validate_equipment_windows(self._equipment_rows(revisions=True))
