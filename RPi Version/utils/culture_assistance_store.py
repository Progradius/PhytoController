"""Lectures et prévalidation auxiliaires, sur le thread unique du carnet."""

from zoneinfo import ZoneInfo

from model.culture import CultureError, stamp
from model.culture_assistance import (feeding_lines, previous_reading, range_lines,
                                      similar_readings, suggestions)
from model.culture_solution import RESERVOIRS, measurements
from model.culture_targets import resolve_targets


class AssistanceStoreMixin:
    def _assistance_token(self, subject_id, version, latest):
        """Jeton opaque de fraîcheur d'une fiche : version du parcours **et** ses sources.

        La version du sujet ne bouge qu'aux événements de parcours (`UPDATE subjects SET
        version`). Les aides, elles, dépendent aussi des rappels, des vérifications, des
        photos du stade et du dernier relevé : un rappel marqué fait laissait donc l'aide
        « Ouvrir le rappel » affichée jusqu'au rechargement de la page, puisque le serveur
        répondait « inchangé ».

        L'empreinte reste bon marché — des `COUNT`/`MAX(revision)` bornés au sujet, sur des
        colonnes indexées, plus le dernier relevé que la réponse complète calcule de toute
        façon. Aucune projection n'est faite ici. Le jeton n'a pas de sens hors du serveur :
        le client le renvoie tel quel, il ne le lit pas.
        """
        counts = self._db.execute(
            "SELECT (SELECT COUNT(*) FROM reminders WHERE subject_id=:s),"
            " (SELECT COALESCE(MAX(revision),0) FROM reminders WHERE subject_id=:s),"
            " (SELECT COUNT(*) FROM culture_checklists WHERE subject_id=:s),"
            " (SELECT COALESCE(MAX(revision),0) FROM culture_checklists WHERE subject_id=:s),"
            " (SELECT COUNT(*) FROM culture_media WHERE owner_kind='event' AND subject_id=:s)",
            {"s": subject_id}).fetchone()
        reading = "-" if latest is None else "|".join(
            str(latest.get(key)) for key in ("effective_at", "precision", "ph", "ec"))
        return ":".join([str(version)] + [str(value) for value in counts] + [reading])

    def _assistance(self, subject_id, version=None):
        """Aides éphémères d'une fiche ; `version` évite de tout recalculer pour rien.

        Une fiche laissée ouverte redemande ses aides à chaque retour de visibilité. Rien
        n'est mémorisé entre deux requêtes : le client renvoie le jeton qu'il affiche et le
        serveur le compare à celui qu'il vient de calculer (`_assistance_token`), par
        quelques agrégats bornés au sujet. Égaux, la réponse est `{"unchanged": true}` —
        sans projection, sans rappel ni vérification détaillés. Les aides ne dépendent que
        de ces sources et de la date du jour ; un changement de jour se traduit dans les
        faits par un rappel qui devient dû, et la fiche est de toute façon rechargée. Un
        jeton absent ou différent refait le calcul complet.
        """
        row = self._db.execute("SELECT version FROM subjects WHERE id=?", (subject_id,)).fetchone()
        if row is None:
            raise CultureError("Culture introuvable.")
        # Le dernier relevé du seul sujet affiché : l'export intégral du journal n'a jamais
        # servi qu'à en extraire une ligne, et il coûtait une seconde projection complète.
        # Il entre dans le jeton, il est donc lu avant la comparaison, pas deux fois.
        latest = self._latest_reading(subject_id)
        token = self._assistance_token(subject_id, row["version"], latest)
        if version is not None and version == token:
            return {"unchanged": True, "version": token, "valid_for_seconds": 30,
                    "generated_at": self.now().isoformat()}
        subject = next((s for s in self._projections() if s["id"] == subject_id), None)
        if subject is None:
            raise CultureError("Culture introuvable.")
        subject["latest_reading"] = latest
        today = self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()
        # Révisions courantes uniquement : aucune lecture des anciennes révisions pour l'aide.
        checks = [dict(r) for r in self._db.execute(
            "SELECT c.* FROM culture_checklists c WHERE subject_id=? AND "
            "revision=(SELECT MAX(v.revision) FROM culture_checklists v WHERE v.id=c.id)", (subject_id,))]
        rows = self._reminders(subject_id, revisions=False)
        # Les photos ne sont pas dans la projection : une seule requête bornée au sujet et
        # au stade courant, jamais la galerie entière. Une culture sans stade daté n'a pas
        # de fenêtre à interroger, et l'absence de compte reste zéro photo connue.
        photos = self._db.execute(
            "SELECT COUNT(*) FROM culture_media WHERE owner_kind='event' AND subject_id=? AND recorded_at>=?",
            (subject_id, subject.get("stage_at") or "")).fetchone()[0] if subject.get("stage_at") else 0
        return {"items": suggestions(subject, checks, rows, today, self.zone, self.reliable(), photos),
                "version": token, "generated_at": self.now().isoformat(), "valid_for_seconds": 30}

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
            return {"valid": True, "replay": True, "summary": [], "similar": [], "links": []}
        summary = result.get("preview_summary", ["Saisie cohérente avec le carnet actuel. La validation finale sera répétée à l’enregistrement."])
        similar = []
        # `summary` reste une liste de chaînes ; `links` porte à part les actions nommées,
        # pour qu'une phrase n'ait jamais à contenir son propre lien.
        links = []
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
            summary.extend(self._range_summary(command, at))
            for target in command.get("targets") or []:
                # Toutes les associations couvrant l'instant, sans `LIMIT` : borner la
                # requête à deux lignes faisait répondre « non unique » sans savoir
                # combien, et confondait le cas « rien n'est déclaré » avec « deux le sont ».
                declared = [{"reservoir_id": row["reservoir_id"], "start_at": row["start_at"],
                             "name": RESERVOIRS[row["reservoir_id"]][0]}
                            for row in self._db.execute(
                                "SELECT p.reservoir_id, l.start_at FROM solution_links l "
                                "JOIN solution_periods p ON p.id=l.period_id "
                                "WHERE l.subject_id=? AND l.start_at<=? AND (l.end_at IS NULL OR l.end_at>?) "
                                "ORDER BY l.start_at, p.reservoir_id", (target, at, at))]
                for line, link in feeding_lines(self._subject_name(target), declared):
                    summary.append(line)
                    links.append(link)
            similar = [{"id": r["id"], "effective_at": r["effective_at"], "ph": r["ph"], "ec": r["ec"]}
                       for r in similar_readings(command, rows, self.zone)]
        return {"valid": True, "summary": summary, "similar": similar, "links": links,
                "similar_scope": "200 derniers relevés courants ; même jour, cibles, contexte et valeurs.",
                "generated_at": self.now().isoformat()}

    def _subject_name(self, subject_id):
        """Nom déclaré d'une culture, lu par identifiant ; un sujet inconnu reste anonyme."""
        row = self._db.execute("SELECT name FROM subjects WHERE id=?", (subject_id,)).fetchone()
        return row["name"] if row else "cette cible"

    def _range_summary(self, command, at):
        """Plage cible applicable au relevé saisi, à sa date, et écart de chaque mesure.

        La résolution est celle du carnet — `resolve_targets`, ordre strict cible directe →
        sujet alimenté → réservoir, sans fusion et sans rétroactivité. Les sujets alimentés
        sont reconstruits ici comme dans `_solution_data` : ce sont les associations du
        réservoir de la saisie couvrant cet instant, moins les cibles déjà visées
        directement. Rien n'est prérempli et aucune plage par défaut n'est inventée.
        """
        values = measurements(command)
        direct = [t for t in (command.get("targets") or []) if isinstance(t, str)]
        reservoir = command.get("reservoir_id") or None
        fed = [row[0] for row in self._db.execute(
            "SELECT l.subject_id FROM solution_links l JOIN solution_periods p ON p.id=l.period_id "
            "WHERE p.reservoir_id=? AND l.start_at<=? AND (l.end_at IS NULL OR l.end_at>?)",
            (reservoir, at, at))] if reservoir else []
        ranges = self._current_targets()
        resolved = resolve_targets({"sort_at": at, "targets": direct, "fed_subjects": fed,
                                    "reservoir_id": reservoir}, ranges)
        name, start = "", ""
        if resolved:
            name = (RESERVOIRS[resolved["reservoir_id"]][0] if resolved["source"] == "reservoir"
                    else self._subject_name(resolved["subject_id"]))
            # Date déclarée de la plage, pas sa clé de tri : celle-ci est en UTC et
            # reculerait la date d'un jour pour toute plage ouverte un 1er du mois à Paris.
            start = next((row["start_at"] for row in ranges if row["id"] == resolved["id"]), "")
        return range_lines(values, resolved, name, start)
