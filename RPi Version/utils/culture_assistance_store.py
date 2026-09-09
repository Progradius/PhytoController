"""Lectures et prévalidation auxiliaires, sur le thread unique du carnet."""

from zoneinfo import ZoneInfo

from model.culture import CultureError, stamp
from model.culture_assistance import previous_reading, similar_readings, suggestions
from model.culture_solution import RESERVOIRS


class AssistanceStoreMixin:
    def _assistance(self, subject_id, version=None):
        """Aides éphémères d'une fiche ; `version` évite de tout recalculer pour rien.

        Une fiche laissée ouverte redemande ses aides à chaque retour de visibilité. Rien
        n'est mémorisé entre deux requêtes : le client renvoie la version qu'il affiche et
        le serveur la compare à celle du sujet, par une seule lecture d'un entier. Égales,
        la réponse est `{"unchanged": true}` — sans projection, sans rappel, sans
        vérification lues. Les aides ne dépendent que du parcours (dont toute modification
        incrémente la version), des rappels et de la date du jour ; un changement de jour
        se traduit dans les faits par un rappel qui devient dû, et la fiche est de toute
        façon rechargée. Une version absente ou différente refait le calcul complet.
        """
        if version is not None:
            row = self._db.execute("SELECT version FROM subjects WHERE id=?", (subject_id,)).fetchone()
            if row is None:
                raise CultureError("Culture introuvable.")
            if row["version"] == version:
                return {"unchanged": True, "version": version, "valid_for_seconds": 30,
                        "generated_at": self.now().isoformat()}
        subject = next((s for s in self._projections() if s["id"] == subject_id), None)
        if subject is None:
            raise CultureError("Culture introuvable.")
        # Le dernier relevé du seul sujet affiché : l'export intégral du journal n'a jamais
        # servi qu'à en extraire une ligne, et il coûtait une seconde projection complète.
        subject["latest_reading"] = self._latest_reading(subject_id)
        today = self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()
        # Révisions courantes uniquement : aucune lecture des anciennes révisions pour l'aide.
        checks = [dict(r) for r in self._db.execute(
            "SELECT c.* FROM culture_checklists c WHERE subject_id=? AND "
            "revision=(SELECT MAX(v.revision) FROM culture_checklists v WHERE v.id=c.id)", (subject_id,))]
        rows = self._reminders(subject_id, revisions=False)
        return {"items": suggestions(subject, checks, rows, today, self.zone, self.reliable()),
                "version": subject["version"], "generated_at": self.now().isoformat(), "valid_for_seconds": 30}

    def _preview(self, domain, command, equipment=None):
        if domain not in ("culture", "solution") or not isinstance(command, dict):
            raise CultureError("Prévalidation de culture ou de solution attendue.")
        mutate = self._mutate if domain == "culture" else self._solution_mutate
        result = mutate(command, equipment, preview=True)
        # La clé identique après réponse perdue doit rester rejouable, même si la version a
        # changé. Le constat vient de la mutation elle-même, qui lit déjà la table des
        # requêtes dans sa transaction : un `SELECT` de plus en amont posait la question
        # deux fois et hors de la transaction qui y répond.
        if result.get("replayed"):
            return {"valid": True, "replay": True, "summary": [], "similar": []}
        summary = result.get("preview_summary", ["Saisie cohérente avec le carnet actuel. La validation finale sera répétée à l’enregistrement."])
        similar = []
        if domain == "solution" and command.get("operation") == "entry" and command.get("kind") == "reading":
            # Fenêtre récente explicite : aucun chargement de tout le journal dans le navigateur.
            rows = []
            for row in self._db.execute(
                "SELECT e.* FROM solution_entries e WHERE kind='reading' AND cancelled=0 "
                "AND revision=(SELECT MAX(v.revision) FROM solution_entries v WHERE v.id=e.id) "
                "ORDER BY recorded_at DESC, sequence DESC LIMIT 200"):
                item = dict(row)
                item["targets"] = [r[0] for r in self._db.execute(
                    "SELECT subject_id FROM solution_targets WHERE entry_id=? AND revision=?", (item["id"], item["revision"]))]
                rows.append(item)
            at = stamp(command["effective_at"], command.get("precision", "date"), self.zone, self.now())[0]
            previous = previous_reading(command, rows, at)
            if previous:
                summary.append(f"Relevé antérieur de même cible et contexte (fenêtre de 200) : {previous['effective_at']}, "
                               f"pH {previous['ph'] if previous['ph'] is not None else '—'}, "
                               f"EC {previous['ec'] if previous['ec'] is not None else '—'} mS/cm. "
                               "Ces valeurs restent des repères ; elles ne remplissent aucun champ.")
            if command.get("targets"):
                for target in command["targets"]:
                    links = list(self._db.execute("SELECT p.reservoir_id, l.start_at FROM solution_links l JOIN solution_periods p ON p.id=l.period_id "
                        "WHERE l.subject_id=? AND l.start_at<=? AND (l.end_at IS NULL OR l.end_at>?) LIMIT 2", (target, at, at)))
                    if len(links) == 1:
                        summary.append(f"Alimentation déclarée à cette date : {RESERVOIRS[links[0]['reservoir_id']][0]} "
                                       f"(association depuis {links[0]['start_at']}). La cible saisie est conservée.")
                    else:
                        summary.append("Association à un réservoir inconnue ou non unique à cette date. La cible saisie est conservée.")
            similar = [{"id": r["id"], "effective_at": r["effective_at"], "ph": r["ph"], "ec": r["ec"]}
                       for r in similar_readings(command, rows, self.zone)]
        return {"valid": True, "summary": summary, "similar": similar,
                "similar_scope": "200 derniers relevés courants ; même jour, cibles, contexte et valeurs.",
                "generated_at": self.now().isoformat()}
