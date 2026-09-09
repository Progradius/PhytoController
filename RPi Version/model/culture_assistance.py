"""Aides explicables du carnet : faits datés, aucune action implicite."""

from datetime import date
from urllib.parse import quote

from model.culture import SPACES, STAGES, backfill_stages
from model.culture_checklist import conflict, local_day
from model.culture_solution import measurements
from model.culture_targets import SOURCES

# Trois catégories, et seulement trois. « Information » n'en était pas une : elle mêlait
# un fait daté à relire et une donnée qui manque, alors que l'opérateur n'en fait pas la
# même chose. L'ordre du tuple est **l'ordre de priorité d'affichage** : ce qui se fait,
# puis ce qui se relit, puis ce qui manque.
CATEGORIES = ("À faire", "À vérifier", "Information manquante")
MAX_SUGGESTIONS = 4


def suggestions(subject, checks, reminders, today, zone, reliable, final_photos=0):
    """Suggestions éphémères, limitées à quatre et dérivées du contexte courant.

    `final_photos` : nombre de photos enregistrées depuis le début du stade courant, lu par
    le magasin — la projection ne porte pas les médias. Zéro reste zéro photo connue, jamais
    « pas de photo » supposé.

    Les aides sont produites dans l'ordre où les faits se lisent, puis **classées par
    catégorie** avant d'être bornées : une culture chargée de rappels ne doit pas faire
    disparaître un manque, et un manque ne doit pas passer devant une échéance dépassée.
    """
    if not reliable:
        return []
    result = []
    identifier = quote(subject["id"], safe="")
    base = f"/cultures/{identifier}"

    def add(code, category, reason, action, href, fact):
        result.append({"id": code, "category": category, "target": subject["name"],
                       "reason": reason, "action": action, "href": href, "fact_date": fact,
                       "expires_when": "Date, parcours, relevés ou vérifications modifiés ; actualisation sous 30 secondes."})

    def ranked():
        # Tri stable : à catégorie égale, l'ordre de production est conservé.
        return sorted(result, key=lambda item: CATEGORIES.index(item["category"]))[:MAX_SUGGESTIONS]

    for row in reminders:
        if row["state"] in ("planned", "postponed") and row["due_date"] <= today:
            add("reminder-" + row["id"], "À faire", f"{row['title']} : échéance déclarée au {row['due_date']}.",
                "Ouvrir le rappel", base + "#reminder-" + quote(row["id"], safe=""), row["due_date"])
    if subject["archived"]:
        if subject["space"]:
            add("release", "À vérifier", "La culture est archivée et occupe encore un espace déclaré.",
                "Déclarer la libération réelle", base + "#action-release", today)
        return ranked()
    if subject["kind"] == "lot" and subject["stage"] in ("floraison", "sechage"):
        valid = any(not c["cancelled"] and not any(conflict(c, subject, zone))
                    and c["stage"] == subject["stage"] and c["space"] == subject["space"]
                    and local_day(c["effective_at"], zone) >= local_day(subject["stage_at"], zone)
                    and all(c[k] for k in ("lighting", "pump", "ventilation")) for c in checks)
        if not valid:
            add("check-stage", "À vérifier", f"Stade {subject['stage_label']} depuis le {subject['stage_at']} : aucune vérification complète valable pour ce contexte.",
                "Vérifier les équipements", f"/cultures/cycles?subject={identifier}#verifications-{identifier}", subject["stage_at"])
    if backfill_stages(subject):
        # Le rattrapage a sa propre section : le journal n'en est pas l'ancre.
        add("backfill", "Information manquante", "Certaines étapes antérieures ne sont pas renseignées. Compléter seulement les dates connues, avant le stade courant.",
            "Compléter le parcours passé", base + "#backfill", subject["stage_at"])
    if subject["kind"] == "lot" and subject["stage"] == "sechage" \
            and (subject.get("balance") or {}).get("weight_g") is None and not final_photos:
        add("balance", "Information manquante",
            f"Lot en séchage depuis le {subject['stage_at']} : ni poids sec ni photo enregistrés depuis ce stade. "
            "Ces deux données se saisissent en terminant le séchage ; la libération de l’espace y reste une case explicite.",
            "Terminer le séchage", base + "#action-finish", subject["stage_at"])
    reading = subject.get("latest_reading")
    day = local_day(reading["effective_at"], zone) if reading else None
    if reading is None:
        add("reading", "Information manquante",
            "Aucun relevé disponible pour cette culture ; aucune valeur ne peut être déduite.",
            "Saisir un relevé", f"/cultures/solutions?target={identifier}&kind=reading#saisie", today)
    else:
        add("reading", "À vérifier", _reading_age(day, today, reading["effective_at"]),
            "Saisir un relevé", f"/cultures/solutions?target={identifier}&kind=reading#saisie",
            reading["effective_at"])
    return ranked()


def _reading_age(day, today, effective_at):
    """Ancienneté du dernier relevé en jours, énoncée sans jugement.

    Une date illisible n'invente pas une ancienneté : elle se contente de la date lue. Le
    seuil au-delà duquel un relevé serait « trop vieux » n'existe pas ici — il dépendrait
    du stade, du réservoir et de la saison, et l'aide n'a pas à le trancher.
    """
    if not day:
        return f"Dernier relevé saisi : {effective_at}. Son ancienneté n’est pas calculable."
    try:
        days = (date.fromisoformat(today) - date.fromisoformat(day)).days
    except ValueError:
        return f"Dernier relevé saisi : {effective_at}. Son ancienneté n’est pas calculable."
    if days <= 0:
        return f"Dernier relevé saisi aujourd’hui ({day})."
    return f"Dernier relevé saisi il y a {days} jour{'s' if days > 1 else ''} (le {day})."


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


# --- Repères de lecture d'un relevé : plages cibles et alimentation déclarée -------------
# Rien ici ne préremplit un champ, ne conseille un dosage ni ne refuse une saisie. Ce sont
# des phrases, dérivées de faits déjà enregistrés, qui accompagnent la prévalidation.

MEASURES = (("ph", "pH", ""), ("ec", "EC", " mS/cm"))


def decimal(value):
    """Nombre lisible en français : virgule décimale, zéros inutiles retirés."""
    text = f"{float(value):.4f}".rstrip("0").rstrip(".")
    return (text or "0").replace(".", ",")


def range_text(resolved, metric):
    """Bornes d'une plage rendues lisibles ; une borne absente n'est jamais complétée."""
    low, high = resolved.get(metric + "_min"), resolved.get(metric + "_max")
    if low is None and high is None:
        return ""
    if low is None:
        return "≤ " + decimal(high)
    if high is None:
        return "≥ " + decimal(low)
    return f"{decimal(low)}–{decimal(high)}"


def gap_text(value, resolved, metric):
    """Écart signé à la borne franchie ; à l'intérieur, l'écart est nul et le dit."""
    low, high = resolved.get(metric + "_min"), resolved.get(metric + "_max")
    if high is not None and value > high:
        delta = value - high
    elif low is not None and value < low:
        delta = value - low
    else:
        return "écart : aucun, la mesure est dans la plage"
    return f"écart : {'+' if delta > 0 else '-'}{decimal(abs(delta))}"


def range_lines(values, resolved, source_name="", start_label=""):
    """Une ligne par mesure renseignée : la plage applicable, ou son absence explicite.

    `resolved` vient de `model.culture_targets.resolve_targets` — ordre strict cible
    directe → sujet alimenté → réservoir, sans fusion et sans rétroactivité. Une mesure non
    renseignée ne produit **aucune** ligne : elle n'a pas d'écart, et un zéro serait faux.
    Une plage qui ne borne pas cette mesure vaut absence de plage pour elle : une cible
    « pH seul » ne fabrique pas de cible d'EC.

    `start_label` est la date **déclarée** du début de la plage ; à défaut, la clé de tri
    est tronquée, ce qui peut la reculer d'un jour selon le fuseau. On cite donc ce que
    l'opérateur a saisi, pas la clé UTC qui en dérive.
    """
    lines = []
    for metric, label, unit in MEASURES:
        value = values.get(metric)
        if value is None:
            continue
        text = range_text(resolved, metric) if resolved else ""
        if not text:
            lines.append(f"Aucune plage applicable à cette cible à cette date ({label}).")
            continue
        source = SOURCES[resolved["source"]] + (f" — {source_name}" if source_name else "")
        ambiguous = " ; plusieurs plages applicables à cette date, la plus récemment ouverte est retenue" \
            if resolved.get("multiple") else ""
        lines.append(f"Plage applicable {label} {text}{unit} (source : {source}, plage du "
                     f"{start_label or resolved['start_sort_at'][:10]}) ; "
                     f"{gap_text(value, resolved, metric)}{ambiguous}.")
    return lines


def feeding_lines(target_name, links):
    """Alimentation déclarée d'une cible à une date : aucune, une seule, ou plusieurs.

    Les trois cas sont distincts et le disent. Les confondre sous « inconnue ou non unique »
    répondait la même chose à « rien n'est déclaré » et à « deux choses le sont », alors que
    la première demande une saisie et la seconde une correction.

    Renvoie des couples `(ligne, lien)` : le lien nomme l'action, jamais la page seule.
    """
    if not links:
        return [(f"Aucune alimentation déclarée à cette date pour {target_name}. "
                 "La cible saisie est conservée.",
                 {"label": "Déclarer la solution présente",
                  "href": "/cultures/solutions#saisie"})]
    if len(links) == 1:
        row = links[0]
        return [(f"Alimentation déclarée à cette date pour {target_name} : {row['name']} "
                 f"(association depuis {row['start_at'][:10]}). La cible saisie est conservée.",
                 {"label": f"Ouvrir {row['name']}",
                  "href": f"/cultures/solutions?target={quote(row['reservoir_id'], safe='')}#reservoirs"})]
    names = ", ".join(row["name"] for row in links)
    return [(f"Plusieurs alimentations déclarées à cette date pour {target_name} : {names}. "
             "La cible saisie est conservée ; corriger les solutions déclarées lève l’ambiguïté.",
             {"label": "Vérifier les solutions déclarées", "href": "/cultures/solutions#reservoirs"})]
