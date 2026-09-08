"""Extension structurée du carnet ; toutes les méthodes tournent dans son thread SQLite."""

import csv
import hashlib
import io
import json
import uuid
from zoneinfo import ZoneInfo

from model.culture import CultureConflict, CultureError, age, stamp, text_value
from model.culture_solution import RESERVOIRS, SOLUTION_KINDS, ingredients, measurements, number
# Lot E : la plage cible d'un relevé est résolue à la date de ce relevé, jamais rétroactivement.
from model.culture_targets import resolve_targets, target_bands, target_text

SOLUTION_TABLES = ("reservoirs", "recipes", "solution_entries", "solution_targets", "solution_periods", "solution_links")
# Fenêtre proposée dans le sélecteur d'intervention : jamais tout le carnet d'un coup.
INTERVENTION_PAGE = 200
SOLUTION_SCHEMA = """
CREATE TABLE reservoirs (id TEXT PRIMARY KEY, name TEXT NOT NULL, space TEXT NOT NULL UNIQUE);
CREATE TABLE recipes (id TEXT NOT NULL, revision INTEGER NOT NULL, name TEXT NOT NULL,
 volume_l REAL NOT NULL, ingredients TEXT NOT NULL, recorded_at TEXT NOT NULL, PRIMARY KEY(id,revision));
CREATE TABLE solution_entries (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, revision INTEGER NOT NULL,
 kind TEXT NOT NULL, reservoir_id TEXT REFERENCES reservoirs(id),
 effective_at TEXT NOT NULL, precision TEXT NOT NULL, sort_at TEXT NOT NULL, recorded_at TEXT NOT NULL,
 clock_reliable INTEGER NOT NULL, cancelled INTEGER NOT NULL, reason TEXT NOT NULL, note TEXT NOT NULL,
 ph REAL, ec REAL, temperature_c REAL, volume_l REAL, context TEXT NOT NULL, compensation TEXT NOT NULL,
 intervention_id TEXT, recipe_id TEXT, recipe_revision INTEGER, ingredients TEXT NOT NULL,
 UNIQUE(id,revision), FOREIGN KEY(recipe_id,recipe_revision) REFERENCES recipes(id,revision));
CREATE INDEX solution_date ON solution_entries(sort_at,reservoir_id);
CREATE TABLE solution_targets (entry_id TEXT NOT NULL, revision INTEGER NOT NULL,
 subject_id TEXT NOT NULL REFERENCES subjects(id), PRIMARY KEY(entry_id,revision,subject_id),
 FOREIGN KEY(entry_id,revision) REFERENCES solution_entries(id,revision));
CREATE TABLE solution_periods (id TEXT PRIMARY KEY, reservoir_id TEXT NOT NULL REFERENCES reservoirs(id),
 start_at TEXT NOT NULL, end_at TEXT);
CREATE TABLE solution_links (period_id TEXT NOT NULL REFERENCES solution_periods(id),
 subject_id TEXT NOT NULL REFERENCES subjects(id), start_at TEXT NOT NULL, end_at TEXT,
 PRIMARY KEY(period_id,subject_id,start_at));
"""


class SolutionStoreMixin:
    def _solution_entries(self, revisions=False):
        sql = "SELECT e.* FROM solution_entries e"
        if not revisions:
            sql += " WHERE revision=(SELECT MAX(v.revision) FROM solution_entries v WHERE v.id=e.id)"
        sql += " ORDER BY sort_at, (SELECT MIN(v.sequence) FROM solution_entries v WHERE v.id=e.id)"
        targets = {}
        for row in self._db.execute("SELECT * FROM solution_targets"):
            targets.setdefault((row["entry_id"], row["revision"]), []).append(row["subject_id"])
        rows = []
        for row in self._db.execute(sql):
            item = dict(row)
            item["ingredients"] = json.loads(item["ingredients"])
            item["targets"] = targets.get((item["id"], item["revision"]), [])
            rows.append(item)
        return rows

    def _recipes(self):
        return [{**dict(r), "ingredients": json.loads(r["ingredients"])} for r in self._db.execute(
            "SELECT r.* FROM recipes r WHERE revision=(SELECT MAX(v.revision) FROM recipes v WHERE v.id=r.id) ORDER BY name")]

    def _solution_interventions(self, entries, subjects, search="", offset=0, linked=()):
        """Fenêtre bornée d'interventions sélectionnables, plus les liens déjà utilisés.

        La recherche porte sur le type, la date effective, la cible et la référence : une
        intervention ancienne reste atteignable sans charger tout le carnet dans un select.
        """
        names = {s["id"]: s["name"] for s in subjects}
        catalogue = {}
        for entry in reversed(entries):
            if entry["kind"] == "reading":
                continue
            target = (RESERVOIRS[entry["reservoir_id"]][0] if entry["reservoir_id"] in RESERVOIRS
                      else " et ".join(names.get(t, t) for t in entry["targets"]))
            catalogue[entry["id"]] = {"id": entry["id"], "kind": entry["kind"], "effective_at": entry["effective_at"],
                                      "reservoir_id": entry["reservoir_id"], "targets": entry["targets"],
                                      "target_label": target, "cancelled": bool(entry["cancelled"]),
                                      "linked": entry["id"] in linked}
        needle = " ".join(search.lower().split())
        candidates = [item for item in catalogue.values() if not item["cancelled"] and (not needle or needle in " ".join(
            (SOLUTION_KINDS[item["kind"]], item["effective_at"], item["target_label"], item["id"])).lower())]
        window = candidates[offset:offset + INTERVENTION_PAGE]
        shown = {item["id"] for item in window}
        # Une intervention déjà associée reste proposée même hors de la fenêtre ou de la recherche.
        window = window + [catalogue[key] for key in dict.fromkeys(linked) if key in catalogue and key not in shown]
        return {"interventions": window, "interventions_total": len(candidates),
                "interventions_offset": offset, "interventions_search": search,
                "interventions_page": INTERVENTION_PAGE}

    def _solution_rebuild(self, subjects=None, validate_only=False):
        """Revalide puis reconstruit les intervalles dérivés dans la transaction de l'appelant."""
        subjects = subjects if subjects is not None else self._projections()
        index = {s["id"]: s for s in subjects}
        entries = [e for e in self._solution_entries() if not e["cancelled"]]
        by_id = {e["id"]: e for e in entries}
        periods = []
        for reservoir in RESERVOIRS:
            renewals = [e for e in entries if e["kind"] == "renewal" and e["reservoir_id"] == reservoir]
            for i, entry in enumerate(renewals):
                end = renewals[i + 1]["sort_at"] if i + 1 < len(renewals) else None
                if end == entry["sort_at"]:
                    raise CultureError("Deux renouvellements au même instant : préciser leurs heures.")
                periods.append({"id": entry["id"], "reservoir_id": reservoir, "start_at": entry["sort_at"], "end_at": end})
        for entry in entries:
            for target in entry["targets"]:
                subject = index.get(target)
                if subject is None:
                    raise CultureError("Cible de carnet inconnue.")
                start = stamp(subject["origin_at"], subject["origin_precision"], self.zone, self.now())[0]
                if entry["sort_at"] < start:
                    raise CultureError("Une intervention précède l’origine de sa cible.")
                if entry["kind"] == "water":
                    cuts = [e["sort_at"] for e in self._events(target) if not e["cancelled"] and e["kind"] in ("harvest", "archive", "finish")]
                    if cuts and entry["sort_at"] >= min(cuts):
                        raise CultureError("Un arrosage ne peut pas suivre la coupe ou l’archivage.")
            intervention = by_id.get(entry["intervention_id"])
            if entry["intervention_id"]:
                if (entry["kind"] != "reading" or intervention is None or intervention["kind"] == "reading"
                        or intervention["reservoir_id"] != entry["reservoir_id"]
                        or set(intervention["targets"]) != set(entry["targets"])):
                    raise CultureError("Le relevé doit viser les mêmes cibles qu’une intervention existante.")
                if entry["context"] == "independent" or (entry["context"] == "before" and entry["sort_at"] > intervention["sort_at"]) or (entry["context"] == "after" and entry["sort_at"] < intervention["sort_at"]):
                    raise CultureError("La date du relevé contredit son contexte avant/après.")
            elif entry["kind"] == "reading" and entry["context"] != "independent":
                raise CultureError("Choisir l’intervention associée au relevé avant/après.")
            if entry["reservoir_id"] and entry["kind"] != "renewal":
                at = entry["sort_at"]
                before = intervention and intervention["kind"] == "renewal" and entry["context"] == "before" and at == intervention["sort_at"]
                matching = [p for p in periods if p["reservoir_id"] == entry["reservoir_id"] and
                            (p["start_at"] < at <= (p["end_at"] or "9999") if before else p["start_at"] <= at < (p["end_at"] or "9999"))]
                if not matching:
                    raise CultureError("Renseigner d’abord la solution présente à la date de cette intervention.")
        if validate_only:
            return
        self._db.execute("DELETE FROM solution_links")
        self._db.execute("DELETE FROM solution_periods")
        events = self._events()
        for period in periods:
            self._db.execute("INSERT INTO solution_periods VALUES (:id,:reservoir_id,:start_at,:end_at)", period)
            space = RESERVOIRS[period["reservoir_id"]][1]
            for subject in subjects:
                if subject["kind"] != "lot" or (space == "space_1" and subject["origin_type"] != "cutting"):
                    continue
                cuts = [e["sort_at"] for e in events if e["subject_id"] == subject["id"] and e["kind"] == "harvest" and not e["cancelled"]]
                for occupation in subject["occupations"]:
                    if occupation["space"] != space:
                        continue
                    start = max(occupation["start"], period["start_at"])
                    end = min(occupation["end"] or "9999", period["end_at"] or "9999", min(cuts) if cuts else "9999")
                    if start < end:
                        self._db.execute("INSERT INTO solution_links VALUES (?,?,?,?)", (period["id"], subject["id"], start, None if end == "9999" else end))

    def _solution_mutate(self, command, equipment=None):
        if not isinstance(command, dict):
            raise CultureError("Objet JSON attendu.")
        # Copie du catalogue connue à la saisie, comme pour les événements de culture :
        # renommer un équipement plus tard ne réécrit aucun contexte enregistré.
        self._equipment_context = json.dumps(equipment or {}, ensure_ascii=False)
        allowed = {"request_id", "operation", "confirm_date", "id", "version", "kind", "reservoir_id", "targets",
                   "effective_at", "precision", "cancelled", "reason", "note", "ph", "ec", "ec_unit", "temperature_c",
                   "volume_l", "context", "compensation", "intervention_id", "recipe_id", "recipe_revision", "ingredients", "name"}
        if set(command) - allowed:
            raise CultureError("Champ de saisie inconnu.")
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
                raise CultureError("Horloge non fiable : vérifier et confirmer la date.")
            operation = command.get("operation")
            if operation not in ("recipe", "entry", "correct"):
                raise CultureError("Opération attendue : recipe, entry ou correct.")
            identifier = command.get("id")
            revision = 1
            old = None
            if identifier:
                identifier = text_value(identifier, "Identifiant")
                table = "recipes" if operation == "recipe" else "solution_entries"
                old = self._db.execute(f"SELECT * FROM {table} WHERE id=? ORDER BY revision DESC LIMIT 1", (identifier,)).fetchone()
                if old is None:
                    raise CultureError("Entrée introuvable.")
                if type(command.get("version")) is not int or command["version"] != old["revision"]:
                    raise CultureConflict("Cette entrée a changé ; ouvrir la version actuelle avant de corriger.")
                if operation == "entry":
                    raise CultureError("Utiliser une correction pour modifier une entrée.")
                revision = old["revision"] + 1
            elif operation == "correct":
                raise CultureError("Identifiant de l’entrée à corriger obligatoire.")
            else:
                identifier = str(uuid.uuid4())
            now = self.now()
            if operation == "recipe":
                volume = number(command.get("volume_l"), "Volume de référence (L)", minimum=0.001, required=True)
                recipe_ingredients = ingredients(command.get("ingredients", []))
                if not recipe_ingredients:
                    raise CultureError("Une recette nécessite au moins un produit.")
                self._db.execute("INSERT INTO recipes VALUES (?,?,?,?,?,?)", (identifier, revision,
                    text_value(command.get("name"), "Nom de recette"), volume,
                    json.dumps(recipe_ingredients, ensure_ascii=False), now.isoformat()))
            else:
                if old is not None:
                    # Une correction muette sur l'association conserve celle de la version précédente :
                    # corriger un pH ou une note ne doit ni perdre ni changer l'intervention liée.
                    command = {**{field: old[field] for field in ("intervention_id", "context") if old[field] is not None},
                               **command}
                kind = command.get("kind")
                if not isinstance(kind, str) or kind not in SOLUTION_KINDS or (old and old["kind"] != kind):
                    raise CultureError("Type d’intervention invalide ou modifié.")
                reservoir = command.get("reservoir_id") or None
                if reservoir is not None and (not isinstance(reservoir, str) or reservoir not in RESERVOIRS):
                    raise CultureError("Réservoir inconnu.")
                targets = command.get("targets", [])
                if not isinstance(targets, list) or len(targets) > 50 or any(not isinstance(t, str) for t in targets) or len(set(targets)) != len(targets):
                    raise CultureError("Cibles invalides ou dupliquées (50 maximum).")
                if (reservoir and targets) or (not reservoir and not targets) or (kind == "water" and reservoir) or (kind not in ("reading", "water") and not reservoir):
                    raise CultureError("Choisir un réservoir, ou les cultures pour un relevé/arrosage manuel.")
                subjects = {s["id"]: s for s in self._projections()}
                if any(t not in subjects for t in targets) or (len(targets) > 1 and any(subjects[t]["kind"] != "mother" for t in targets)):
                    raise CultureError("Choisir une culture ou plusieurs pieds mères.")
                values = measurements(command)
                if kind == "reading" and values["ph"] is None and values["ec"] is None:
                    raise CultureError("Renseigner au moins le pH ou l’EC.")
                if kind in ("renewal", "topup") and (values["volume_l"] is None or values["volume_l"] <= 0):
                    raise CultureError("Volume strictement positif obligatoire.")
                recipe_id = command.get("recipe_id") or None
                recipe_revision = command.get("recipe_revision") if recipe_id else None
                frozen = ingredients(command.get("ingredients", []))
                if recipe_id:
                    recipe_id = text_value(recipe_id, "Recette")
                    if type(recipe_revision) is not int:
                        raise CultureError("Version de recette obligatoire.")
                    recipe = self._db.execute("SELECT * FROM recipes WHERE id=? AND revision=?", (recipe_id, recipe_revision)).fetchone()
                    if recipe is None or not values["volume_l"]:
                        raise CultureError("Recette inconnue ou volume de préparation manquant.")
                    expected = ingredients(json.loads(recipe["ingredients"]), values["volume_l"] / recipe["volume_l"])
                    if frozen != expected:
                        raise CultureConflict("Les quantités doivent correspondre à l’aperçu de cette version de recette.")
                if old and not recipe_id and frozen == json.loads(old["ingredients"]) and values["volume_l"] == old["volume_l"]:
                    recipe_id, recipe_revision = old["recipe_id"], old["recipe_revision"]
                if kind in ("reading", "topup") and (frozen or recipe_id):
                    raise CultureError("Ce type de saisie ne contient pas de produits.")
                if kind in ("nutrient", "ph") and not frozen:
                    raise CultureError("Renseigner les produits et quantités ajoutés.")
                if kind != "reading" and command.get("intervention_id"):
                    raise CultureError("Seul un relevé peut être lié à une autre intervention.")
                if kind != "reading" and values["context"] == "before":
                    raise CultureError("Utiliser un relevé distinct pour une mesure avant intervention.")
                effective = command.get("effective_at")
                precision = command.get("precision", "date")
                sort_at = stamp(effective, precision, self.zone, now)[0]
                cancelled = command.get("cancelled", False)
                if type(cancelled) is not bool:
                    raise CultureError("Annulation : booléen attendu.")
                intervention_id = command.get("intervention_id") or None
                if intervention_id:
                    intervention_id = text_value(intervention_id, "Intervention")
                row = {"id": identifier, "revision": revision, "kind": kind, "reservoir_id": reservoir,
                       "effective_at": effective, "precision": precision, "sort_at": sort_at, "recorded_at": now.isoformat(),
                       "clock_reliable": int(self.reliable()), "cancelled": int(cancelled),
                       "reason": text_value(command.get("reason", ""), "Motif", 500, False),
                       "note": text_value(command.get("note", ""), "Note", 4000, False), **values,
                       "intervention_id": intervention_id, "recipe_id": recipe_id, "recipe_revision": recipe_revision,
                       "ingredients": json.dumps(frozen, ensure_ascii=False),
                       "equipment_context": self._equipment_context}
                columns = ",".join(row)
                self._db.execute(f"INSERT INTO solution_entries ({columns}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))
                self._db.executemany("INSERT INTO solution_targets VALUES (?,?,?)", [(identifier, revision, t) for t in targets])
                self._solution_rebuild(list(subjects.values()))
            result = {"saved": True, "id": identifier, "version": revision}
            self._db.execute("INSERT INTO requests VALUES (?,?,?)", (key, fingerprint, json.dumps(result)))
        return result

    def _solution_data(self, filters=None, offset=0, export=False, focus=None, search=None, search_offset=0):
        if search is not None:
            # Mode recherche : réponse bornée au seul bloc d'interventions, sans courbe ni journal.
            search = text_value(search, "Recherche d’intervention", 100, False)
            return self._solution_interventions(self._solution_entries(), self._projections(), search, search_offset)
        filters = filters or {}
        if set(filters) - {"target", "kind", "start", "end"}:
            raise CultureError("Filtre inconnu.")
        start = stamp(filters["start"], "date", self.zone, self.now())[0] if filters.get("start") else ""
        end_date = filters.get("end", "")
        if end_date:
            stamp(end_date, "date", self.zone, self.now())
        if filters.get("start") and end_date and filters["start"] > end_date:
            raise CultureError("La fin du filtre précède son début.")
        kind = filters.get("kind", "")
        if kind and kind not in SOLUTION_KINDS:
            raise CultureError("Type de filtre inconnu.")
        entries = self._solution_entries()
        periods = [dict(r) for r in self._db.execute("SELECT * FROM solution_periods ORDER BY start_at")]
        for period in periods:
            renewal = next((e for e in entries if e["id"] == period["id"]), None)
            period["preparation"] = dict(renewal) if renewal else None
            period["age"] = age(renewal["effective_at"] if renewal else period["start_at"], period["end_at"], self.now(), self.zone)
        links = [dict(r) for r in self._db.execute("SELECT * FROM solution_links ORDER BY start_at")]
        subjects = self._projections()
        target = filters.get("target", "")
        if target and target not in RESERVOIRS and target not in {s["id"] for s in subjects}:
            raise CultureError("Cible de filtre inconnue.")
        active = {e["id"]: e for e in entries if not e["cancelled"]}
        # Lot E : révisions courantes des plages cibles, lues une seule fois pour tout le lot.
        target_ranges = self._current_targets()
        for entry in entries:
            at = entry["sort_at"]
            intervention = active.get(entry["intervention_id"])
            before = intervention and intervention["kind"] == "renewal" and entry["context"] == "before" and at == intervention["sort_at"]
            matched = [p for p in periods if p["reservoir_id"] == entry["reservoir_id"] and
                       (p["start_at"] < at <= (p["end_at"] or "9999") if before else p["start_at"] <= at < (p["end_at"] or "9999"))]
            entry["period_id"] = matched[0]["id"] if matched else None
            entry["fed_subjects"] = [link["subject_id"] for link in links if link["period_id"] == entry["period_id"] and
                                     (link["start_at"] < at <= (link["end_at"] or "9999") if before else link["start_at"] <= at < (link["end_at"] or "9999"))]
            # Lot E : plage cible applicable à cette date, ou None. Aucune plage par défaut,
            # aucun diagnostic ni dosage ; c'est un repère de lecture attaché au relevé.
            entry["target"] = resolve_targets(entry, target_ranges)
        selected = [e for e in entries if (not target or target == e["reservoir_id"] or target in e["targets"] or target in e["fed_subjects"])
                    and (not kind or kind == e["kind"]) and e["sort_at"] >= start
                    and (not end_date or stamp(e["effective_at"], e["precision"], self.zone, self.now())[1] <= end_date)]
        selected.reverse()
        if export:
            return selected
        if focus:
            position = next((i for i, e in enumerate(selected) if e["id"] == focus), None)
            if position is not None:
                offset = position // 40 * 40
        chart_entries = [e for e in selected if not e["cancelled"]]
        chart = []
        aggregated = len(chart_entries) > 1000
        if aggregated:
            # Agrégats journaliers par cible et solution : aucune moyenne ne traverse un renouvellement.
            buckets = {}
            for entry in chart_entries:
                day = stamp(entry["effective_at"], entry["precision"], self.zone, self.now())[1]
                target_key = entry["reservoir_id"] or ",".join(sorted(entry["targets"]))
                key = (day, target_key, entry["period_id"])
                bucket = buckets.setdefault(key, {"at": stamp(day, "date", self.zone, self.now())[0],
                    "target": target_key, "period": entry["period_id"], "ph_values": [], "ec_values": [],
                    "annotations": [], "target_range": entry["target"]})
                # Un agrégat journalier ne porte une plage que si toutes ses mesures partagent
                # la même : deux contextes ne se moyennent pas en une cible intermédiaire.
                if (bucket["target_range"] or {}).get("id") != (entry["target"] or {}).get("id"):
                    bucket["target_range"] = None
                for metric in ("ph", "ec"):
                    if entry[metric] is not None:
                        bucket[metric + "_values"].append(entry[metric])
                if entry["kind"] != "reading":
                    bucket["annotations"].append(SOLUTION_KINDS[entry["kind"]])
            for bucket in buckets.values():
                for metric in ("ph", "ec"):
                    values = bucket.pop(metric + "_values")
                    bucket[metric] = sum(values) / len(values) if values else None
                    bucket[metric + "_count"] = len(values)
                    bucket[metric + "_min"] = min(values) if values else None
                    bucket[metric + "_max"] = max(values) if values else None
                bucket["label"] = "Moyenne journalière"
                bucket["annotations"] = sorted(set(bucket["annotations"]))
                chart.append(bucket)
        else:
            chart = [{"at": e["sort_at"], "ph": e["ph"], "ec": e["ec"], "target": e["reservoir_id"] or ",".join(e["targets"]),
                      "period": e["period_id"], "label": SOLUTION_KINDS[e["kind"]], "target_range": e["target"],
                      "annotations": [SOLUTION_KINDS[e["kind"]]] if e["kind"] != "reading" else []} for e in chart_entries]
        chart.sort(key=lambda p: p["at"])
        truncated = len(chart) > 2000
        chart = chart[-2000:]
        # Lot E : bandes de référence dérivées des plages réellement résolues, jamais prolongées
        # sur une période sans cible ni inventées avant la première plage saisie.
        bands = target_bands([{"at": point["at"], "target": point.pop("target_range")} for point in chart])
        chart_start = min((p["at"] for p in chart), default="9999")
        chart_end = max((p["at"] for p in chart), default="")
        stage_subjects = {s["id"] for s in subjects if s["id"] == target or any(link["subject_id"] == s["id"] and
            (not target or any(p["id"] == link["period_id"] and p["reservoir_id"] == target for p in periods)) for link in links)}
        stages = [{"at": e["sort_at"], "label": ("Récolte" if e["kind"] == "harvest" else "Stade : " + e["payload"]["stage"]),
                   "subject_id": e["subject_id"]} for e in self._events() if not e["cancelled"] and e["kind"] in ("stage", "harvest")
                  and e["subject_id"] in stage_subjects and chart_start <= e["sort_at"] <= chart_end]
        page = selected[offset:offset + 40]
        revisions = self._solution_entries(revisions=True)
        for entry in page:
            entry["revisions"] = [r for r in revisions if r["id"] == entry["id"] and r["revision"] < entry["revision"]]
            # Lot G : contexte d'équipement résolu à la date effective de l'intervention,
            # avec sa provenance ; jamais un repli sur le catalogue courant.
            entry["equipment"] = self._equipment_context_at(entry["sort_at"], entry.get("equipment_context"), entry["recorded_at"])
        linked = [e["intervention_id"] for e in page if e["intervention_id"]]
        return {"items": page, "chart": chart, "chart_targets": bands, "chart_aggregated": aggregated, "chart_truncated": truncated, "stages": stages, "total": len(selected), "offset": offset, "periods": periods, "links": links,
                "reservoirs": [dict(r) for r in self._db.execute("SELECT * FROM reservoirs")],
                "recipes": self._recipes(), "subjects": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "archived": s["archived"]} for s in subjects],
                **self._solution_interventions(entries, subjects, "", 0, linked),
                "latest": next((e for e in selected if not e["cancelled"] and (e["ph"] is not None or e["ec"] is not None)), None),
                "timezone": self.zone, "clock_reliable": self.reliable(),
                "today": self.now().astimezone(ZoneInfo(self.zone)).date().isoformat()}

    def _solution_csv(self, filters=None):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        fields = ["id", "revision", "cancelled", "kind", "reservoir_id", "period_id", "effective_at", "precision", "recorded_at",
                  "ph", "ec", "ph_cible", "ec_cible", "temperature_c", "volume_l", "context", "compensation", "intervention_id", "targets", "fed_subjects", "ingredients", "note", "reason"]
        writer.writerow(["EC_mS_cm" if f == "ec" else f for f in fields])
        for entry in self._solution_data(filters, export=True):
            row = []
            for field in fields:
                # Lot E : la cible est celle résolue à la date du relevé ; une absence reste vide.
                value = target_text(entry.get("target"), field[:2]) if field.endswith("_cible") else entry.get(field)
                value = "" if value is None else json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
                if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                    value = "'" + value
                row.append(value)
            writer.writerow(row)
        return output.getvalue()

    def _latest_solution_readings(self):
        latest = {}
        for entry in self._solution_data(export=True):
            if entry["cancelled"] or (entry["ph"] is None and entry["ec"] is None):
                continue
            for target in entry["targets"] + entry["fed_subjects"]:
                latest.setdefault(target, {key: entry[key] for key in ("ph", "ec", "effective_at", "precision")})
        return latest
