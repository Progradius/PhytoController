"""Vérifications déclaratives du carnet (lot D) : saisie, lecture et invariants.

Une case cochée est une déclaration de l'opérateur, jamais une commande : rien ici
n'accède au GPIO ni à la configuration. Le schéma 4 rend ces lignes versionnées
(`PRIMARY KEY(id, revision)`) et conserve le contexte connu au moment de la saisie
(`stage_at`, `stage_precision`, `subject_version`), distinct du stade affiché aujourd'hui.
Les lignes migrées depuis le schéma 3 gardent ces trois colonnes à NULL : l'information
n'existait pas et n'est pas inventée.

Le lot D complète ce module (corrections, annulations avec motif, conflit dérivé avec une
correction rétrospective du parcours) sans toucher aux autres magasins.
"""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from model.culture import CultureConflict, CultureError, stamp, text_value
from model.culture_cycle import CHECKLIST

# Colonnes écrites par une saisie neuve ; l'ordre suit celui de l'insertion.
CHECKLIST_COLUMNS = ("id", "revision", "subject_id", "space", "stage", "stage_at", "stage_precision",
                     "subject_version", "effective_at", "precision", "recorded_at", "clock_reliable",
                     "lighting", "pump", "ventilation", "note", "reason", "cancelled", "equipment_context")


class ChecklistStoreMixin:
    def _checklists(self, subject_id):
        """Révisions courantes d'un sujet : une ligne par vérification, annulées comprises.

        Les vérifications annulées restent restituées avec leur drapeau `cancelled` :
        l'historique d'une case cochée par erreur ne doit pas disparaître de la lecture.
        """
        rows = self._db.execute(
            "SELECT c.* FROM culture_checklists c WHERE c.subject_id=?"
            " AND c.revision=(SELECT MAX(v.revision) FROM culture_checklists v WHERE v.id=c.id)"
            " ORDER BY c.recorded_at DESC, c.id", (subject_id,))
        return [dict(row) for row in rows]

    def _checklist_mutate(self, command):
        """Enregistre une vérification déclarative dans sa propre transaction idempotente."""
        if not isinstance(command, dict) or set(command) - {
                "request_id", "operation", "confirm_date", "subject_id", "version", "effective_at", "checks", "note"}:
            raise CultureError("Commande de vérification invalide.")

        def work():
            subject = next((s for s in self._projections() if s["id"] == command.get("subject_id")), None)
            if not subject or subject["kind"] != "lot" or subject["archived"]:
                raise CultureError("Lot inconnu.")
            if type(command.get("version")) is not int or command["version"] != subject["version"]:
                raise CultureConflict("Le parcours du lot a changé ; relire la liste de vérification.")
            effective = command.get("effective_at")
            stamp(effective, "date", self.zone, self.now())
            stage_key = stamp(subject["stage_at"], subject["stage_precision"], self.zone, self.now())[0]
            # Une date sans heure peut désigner le jour même d'un changement horodaté.
            stage_date = datetime.fromisoformat(stage_key).astimezone(ZoneInfo(self.zone)).date().isoformat()
            if effective < stage_date:
                raise CultureError("La vérification précède le début du stade actuel.")
            checks = command.get("checks")
            if not isinstance(checks, dict) or set(checks) != set(CHECKLIST) or any(type(v) is not bool for v in checks.values()):
                raise CultureError("Renseigner les trois vérifications déclaratives.")
            identifier = str(uuid.uuid4())
            self._db.execute(
                f"INSERT INTO culture_checklists ({','.join(CHECKLIST_COLUMNS)})"
                f" VALUES ({','.join('?' for _ in CHECKLIST_COLUMNS)})",
                (identifier, 1, subject["id"], subject["space"], subject["stage"],
                 subject["stage_at"], subject["stage_precision"], subject["version"],
                 effective, "date", self.now().isoformat(), int(self.reliable()),
                 *[int(checks[key]) for key in CHECKLIST],
                 text_value(command.get("note", ""), "Note", 4000, False), "", 0, "{}"))
            return {"saved": True, "id": identifier}
        return self._aux_transaction(command, work)

    def _validate_checklists(self):
        """Révisions sans trou depuis 1 et cases strictement booléennes."""
        revisions = {}
        for row in self._db.execute("SELECT id, revision, lighting, pump, ventilation, cancelled FROM culture_checklists"):
            if any(row[key] not in (0, 1) for key in ("lighting", "pump", "ventilation", "cancelled")):
                raise CultureError("Vérification de sauvegarde incohérente.")
            revisions.setdefault(row["id"], []).append(row["revision"])
        for values in revisions.values():
            if sorted(values) != list(range(1, len(values) + 1)):
                raise CultureError("Révisions de vérification manquantes ou dupliquées.")
