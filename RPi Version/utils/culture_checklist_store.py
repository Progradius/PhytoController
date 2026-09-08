"""Vérifications déclaratives du carnet (lot D) : saisie, correction, annulation et lecture.

Une case cochée est une déclaration de l'opérateur, jamais une commande : rien ici
n'accède au GPIO ni à la configuration. Le schéma 4 rend ces lignes versionnées
(`PRIMARY KEY(id, revision)`) et conserve le contexte connu au moment de la saisie
(`stage_at`, `stage_precision`, `subject_version`), distinct du stade affiché aujourd'hui.
Les lignes migrées depuis le schéma 3 gardent ces trois colonnes à NULL : l'information
n'existait pas et n'est pas inventée.

Une correction ou une annulation ajoute une révision motivée : l'historique d'une case
cochée par erreur ne disparaît jamais. Le conflit avec une correction rétrospective du
parcours est dérivé à la lecture (`model.culture_checklist.conflict`), jamais stocké.
"""

import uuid

from model.culture import CultureConflict, CultureError, stamp, text_value
from model.culture_checklist import PRECISIONS, check_values, conflict, context_at, reason_value

# Colonnes écrites par une saisie neuve ; l'ordre suit celui de l'insertion.
CHECKLIST_COLUMNS = ("id", "revision", "subject_id", "space", "stage", "stage_at", "stage_precision",
                     "subject_version", "effective_at", "precision", "recorded_at", "clock_reliable",
                     "lighting", "pump", "ventilation", "note", "reason", "cancelled", "equipment_context")
CHECKLIST_OPERATIONS = ("checklist", "checklist_correct", "checklist_cancel")
CHECKLIST_FIELDS = {"request_id", "operation", "confirm_date", "subject_id", "version",
                    "effective_at", "checks", "note", "id", "reason"}


class ChecklistStoreMixin:
    def _checklists(self, subject):
        """Révisions courantes d'un sujet : une ligne par vérification, annulées comprises.

        Les vérifications annulées restent restituées avec leur drapeau `cancelled` et leur
        motif : l'historique d'une case cochée par erreur ne doit pas disparaître de la
        lecture. Chaque ligne porte ses anciennes révisions et le verdict de conflit
        recalculé face au parcours d'aujourd'hui.
        """
        rows = self._db.execute(
            "SELECT c.* FROM culture_checklists c WHERE c.subject_id=?"
            " AND c.revision=(SELECT MAX(v.revision) FROM culture_checklists v WHERE v.id=c.id)"
            " ORDER BY c.recorded_at DESC, c.id", (subject["id"],))
        entries = []
        for row in rows:
            entry = dict(row)
            entry["revisions"] = [dict(old) for old in self._db.execute(
                "SELECT * FROM culture_checklists WHERE id=? AND revision<? ORDER BY revision",
                (entry["id"], entry["revision"]))]
            entry["conflict"], entry["conflict_unknown"] = conflict(entry, subject, self.zone)
            entries.append(entry)
        return entries

    def _checklist_mutate(self, command):
        """Saisie, correction ou annulation dans une transaction idempotente dédiée."""
        if not isinstance(command, dict) or set(command) - CHECKLIST_FIELDS:
            raise CultureError("Commande de vérification invalide.")
        operation = command.get("operation")
        if operation not in CHECKLIST_OPERATIONS:
            raise CultureError("Opération de vérification inconnue.")

        def work():
            if operation == "checklist":
                return self._checklist_create(command)
            return self._checklist_revise(command, operation)
        return self._aux_transaction(command, work)

    def _checklist_subject(self, subject_id):
        subject = next((s for s in self._projections() if s["id"] == subject_id), None)
        if subject is None or subject["kind"] != "lot":
            raise CultureError("Lot inconnu.")
        return subject

    def _checklist_insert(self, row):
        self._db.execute(
            f"INSERT INTO culture_checklists ({','.join(CHECKLIST_COLUMNS)})"
            f" VALUES ({','.join('?' for _ in CHECKLIST_COLUMNS)})",
            tuple(row[column] for column in CHECKLIST_COLUMNS))
        return {"saved": True, "id": row["id"], "revision": row["revision"]}

    def _checklist_create(self, command):
        subject = self._checklist_subject(command.get("subject_id"))
        if subject["archived"]:
            raise CultureError("Lot inconnu.")
        if type(command.get("version")) is not int or command["version"] != subject["version"]:
            raise CultureConflict("Le parcours du lot a changé ; relire la liste de vérification.")
        effective = command.get("effective_at")
        stamp(effective, "date", self.zone, self.now())
        # Une date sans heure peut désigner le jour même d'un changement horodaté.
        stage_date = context_at(subject, effective, self.zone)
        if stage_date is None or subject["stage"] != stage_date["stage"]:
            raise CultureError("La vérification précède le début du stade actuel.")
        checks = check_values(command.get("checks"))
        return self._checklist_insert({
            "id": str(uuid.uuid4()), "revision": 1, "subject_id": subject["id"],
            "space": subject["space"], "stage": subject["stage"], "stage_at": subject["stage_at"],
            "stage_precision": subject["stage_precision"], "subject_version": subject["version"],
            "effective_at": effective, "precision": "date", "recorded_at": self.now().isoformat(),
            "clock_reliable": int(self.reliable()), **checks,
            "note": text_value(command.get("note", ""), "Note", 4000, False),
            "reason": "", "cancelled": 0, "equipment_context": "{}"})

    def _checklist_revise(self, command, operation):
        """Correction ou annulation motivée : une révision de plus, jamais une réécriture.

        La règle « la vérification ne précède pas le stade courant » ne s'applique qu'à une
        saisie neuve : une case cochée par erreur doit rester corrigeable quand le lot a
        déjà progressé. Une correction réenregistre le contexte réel à sa date effective,
        ce qui lève le conflit dérivé — mais seulement parce que l'opérateur l'a demandé.
        """
        identifier = text_value(command.get("id"), "Identifiant")
        old = self._db.execute("SELECT * FROM culture_checklists WHERE id=? ORDER BY revision DESC LIMIT 1",
                               (identifier,)).fetchone()
        if old is None:
            raise CultureError("Vérification introuvable.")
        if type(command.get("version")) is not int or command["version"] != old["revision"]:
            raise CultureConflict("Cette vérification a changé ; actualiser avant de poursuivre.")
        if old["cancelled"]:
            raise CultureError("Cette vérification est déjà annulée ; en saisir une nouvelle.")
        row = {**dict(old), "revision": old["revision"] + 1, "recorded_at": self.now().isoformat(),
               "clock_reliable": int(self.reliable())}
        if operation == "checklist_cancel":
            if set(command) - {"request_id", "operation", "confirm_date", "id", "version", "reason"}:
                raise CultureError("Une annulation ne porte qu'un motif.")
            row.update(cancelled=1, reason=reason_value(command.get("reason"), "Motif de l'annulation"))
            return self._checklist_insert(row)
        subject = self._checklist_subject(old["subject_id"])
        effective = command.get("effective_at", old["effective_at"])
        stamp(effective, "date", self.zone, self.now())
        context = context_at(subject, effective, self.zone)
        if context is None:
            raise CultureError("La vérification précède l'origine de la culture.")
        row.update(effective_at=effective, subject_version=subject["version"], cancelled=0,
                   reason=reason_value(command.get("reason"), "Motif de la correction"),
                   note=text_value(command.get("note", ""), "Note", 4000, False),
                   **context, **check_values(command.get("checks")))
        return self._checklist_insert(row)

    def _validate_checklists(self):
        """Révisions sans trou depuis 1, cases booléennes, précisions connues, annulation terminale."""
        revisions = {}
        for row in self._db.execute("SELECT id, revision, lighting, pump, ventilation, cancelled,"
                                    " precision, stage_precision FROM culture_checklists"):
            if any(row[key] not in (0, 1) for key in ("lighting", "pump", "ventilation", "cancelled")):
                raise CultureError("Vérification de sauvegarde incohérente.")
            if row["precision"] not in PRECISIONS or (row["stage_precision"] is not None
                                                      and row["stage_precision"] not in PRECISIONS):
                raise CultureError("Précision de vérification inconnue.")
            revisions.setdefault(row["id"], []).append((row["revision"], row["cancelled"]))
        for values in revisions.values():
            values.sort()
            if [revision for revision, _ in values] != list(range(1, len(values) + 1)):
                raise CultureError("Révisions de vérification manquantes ou dupliquées.")
            flags = [flag for _, flag in values]
            # Une annulation est terminale : la relever exigerait une nouvelle saisie, pas
            # une révision qui ferait réapparaître une déclaration retirée.
            if any(flags[index] and not flags[index + 1] for index in range(len(flags) - 1)):
                raise CultureError("Une vérification annulée ne peut pas redevenir active.")
