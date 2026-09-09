"""Aides explicables du carnet : faits datés, aucune action implicite."""

from urllib.parse import quote

from model.culture import SPACES, STAGES, backfill_stages
from model.culture_checklist import conflict, local_day
from model.culture_solution import measurements


def suggestions(subject, checks, reminders, today, zone, reliable):
    """Suggestions éphémères, limitées à quatre et dérivées du contexte courant."""
    if not reliable:
        return []
    result = []
    identifier = quote(subject["id"], safe="")
    base = f"/cultures/{identifier}"

    def add(code, category, reason, action, href, fact):
        result.append({"id": code, "category": category, "target": subject["name"],
                       "reason": reason, "action": action, "href": href, "fact_date": fact,
                       "expires_when": "Date, parcours, relevés ou vérifications modifiés ; actualisation sous 30 secondes."})

    for row in reminders:
        if row["state"] in ("planned", "postponed") and row["due_date"] <= today:
            add("reminder-" + row["id"], "À faire", f"{row['title']} : échéance déclarée au {row['due_date']}.",
                "Ouvrir le rappel", base + "#reminder-" + quote(row["id"], safe=""), row["due_date"])
            if len(result) == 4:
                return result
    if subject["archived"]:
        if subject["space"]:
            add("release", "À vérifier", "La culture est archivée et occupe encore un espace déclaré.",
                "Déclarer la libération réelle", base + "#action-release", today)
        return result[:4]
    if subject["kind"] == "lot" and subject["stage"] in ("floraison", "sechage"):
        valid = any(not c["cancelled"] and not any(conflict(c, subject, zone))
                    and c["stage"] == subject["stage"] and c["space"] == subject["space"]
                    and local_day(c["effective_at"], zone) >= local_day(subject["stage_at"], zone)
                    and all(c[k] for k in ("lighting", "pump", "ventilation")) for c in checks)
        if not valid:
            add("check-stage", "À vérifier", f"Stade {subject['stage_label']} depuis le {subject['stage_at']} : aucune vérification complète valable pour ce contexte.",
                "Vérifier les équipements", f"/cultures/cycles?subject={identifier}#verifications-{identifier}", subject["stage_at"])
    if backfill_stages(subject):
        add("backfill", "Information manquante", "Certaines étapes antérieures ne sont pas renseignées. Compléter seulement les dates connues, avant le stade courant.",
            "Consulter le parcours", base + "#journal", subject["stage_at"])
    reading = subject.get("latest_reading")
    add("reading", "Information", (f"Dernier relevé saisi : {reading['effective_at']}. Cette ancienneté seule ne signale pas un problème."
                                   if reading else "Aucun relevé disponible pour cette culture ; aucune valeur ne peut être déduite."),
        "Saisir un relevé", f"/cultures/solutions?target={identifier}&kind=reading#saisie",
        reading["effective_at"] if reading else today)
    return result[:4]


def transition_summary(before, after, command):
    """Conséquences d'une projection validée, y compris correction et libération."""
    def state(subject):
        return (f"{STAGES.get(subject['stage'], subject['stage'])} · "
                f"{SPACES.get(subject['space'], 'Espace libéré')} · "
                f"{'Archivé' if subject['archived'] else 'En cours'}")
    lines = (["Avant : " + state(before)] if before else []) + ["Après : " + state(after)]
    lines.append("Date déclarée : " + str(command.get("effective_at") or command.get("stage_at") or "voir les étapes saisies"))
    if command.get("kind") == "harvest":
        lines.append("La récolte coupe l’alimentation déclarée ; l’occupation reste jusqu’à sa libération explicite.")
    lines.append("Les horaires, sorties et réglages physiques restent à vérifier séparément.")
    return lines


def similar_readings(command, rows, zone):
    """Rapprochement prudent : même jour local, cibles, contexte, mesures et intervention.

    Fenêtre fournie bornée par le magasin. Une ressemblance ne prouve pas un doublon.
    Les unités sont normalisées et les absences restent des absences.
    """
    if command.get("operation") != "entry" or command.get("kind") != "reading":
        return []
    values = measurements(command)
    day = local_day(command["effective_at"], zone)
    return [r for r in rows if not r["cancelled"] and r["kind"] == "reading"
            and local_day(r["effective_at"], zone) == day
            and (r["reservoir_id"] or None) == (command.get("reservoir_id") or None)
            and set(r["targets"]) == set(command.get("targets", []))
            and (r["intervention_id"] or None) == (command.get("intervention_id") or None)
            and all(r[k] == values[k] for k in ("ph", "ec", "temperature_c", "context", "compensation"))][:3]


def previous_reading(command, rows, at):
    """Repère antérieur de même cible/contexte, ordonné par date effective, pas de saisie."""
    return max((r for r in rows if not r["cancelled"] and r["kind"] == "reading" and r["sort_at"] <= at
                and (r["reservoir_id"] or None) == (command.get("reservoir_id") or None)
                and set(r["targets"]) == set(command.get("targets", []))
                and r["context"] == command.get("context", "independent")
                and (r["intervention_id"] or None) == (command.get("intervention_id") or None)),
               key=lambda r: r["sort_at"], default=None)
