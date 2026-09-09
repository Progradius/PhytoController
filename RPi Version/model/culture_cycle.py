"""Rappels, photos et qualité des synthèses : règles sans accès matériel."""

import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from model.culture import CultureError, text_value

REMINDER_STATES = {"planned": "Prévu", "postponed": "Reporté", "done": "Fait", "cancelled": "Annulé"}
CHECKLIST = {"lighting": ("Éclairage vérifié", "/conf#daily-timer-2"),
             "pump": ("Pompe vérifiée", "/conf#cyclic-1"),
             "ventilation": ("Ventilation commune vérifiée", "/conf#motor")}
# Espace 1 : mêmes organes, autres réglages. L'éclairage et la sortie locale y ont leur
# propre minuterie ; la ventilation est commune aux deux espaces et ne change pas de lien.
# Le gabarit portait cette table en clair ; elle est ici pour que la règle et la page ne
# puissent plus diverger.
SPACE_1_CHECKLIST = {"lighting": ("Éclairage vérifié", "/conf#daily-timer-1"),
                     "pump": ("Sortie locale vérifiée", "/conf#cyclic-2")}
# Vérifications pertinentes stade par stade, motif compris. Chaque stade nomme
# explicitement ses organes : aucun défaut implicite, aucune liste « toutes les cases »
# héritée d'un autre stade. Le séchage ne retient que la ventilation — la récolte a coupé
# l'alimentation déclarée et l'éclairage n'a plus d'objet —, et le maintien d'un pied mère
# ne dépend que de sa photopériode.
STAGE_CHECKS = {
    "germination": (("lighting", "La photopériode de levée est déclarée dans les minuteries."),
                    ("pump", "L’apport de solution conditionne la levée.")),
    "enracinement": (("lighting", "La photopériode d’enracinement est déclarée dans les minuteries."),
                     ("pump", "L’apport de solution conditionne la reprise des boutures.")),
    "vegetatif": (("lighting", "La photopériode végétative est déclarée dans les minuteries."),
                  ("pump", "L’apport de solution conditionne la croissance.")),
    "floraison": (("lighting", "La photopériode de floraison est déclarée dans les minuteries."),
                  ("pump", "L’apport de solution conditionne la floraison."),
                  ("ventilation", "Le renouvellement d’air limite l’humidité en floraison.")),
    "sechage": (("ventilation", "Le séchage dépend du seul renouvellement d’air : "
                                "l’alimentation est coupée depuis la récolte."),),
    "maintien": (("lighting", "Le maintien d’un pied mère dépend de sa photopériode."),),
}


def stage_checks(subject):
    """Vérifications pertinentes d'une culture, selon son stade **et** son espace.

    Règle pure : ni matériel, ni disque, ni horloge. Elle ne déclare rien et ne coche rien
    — elle nomme les réglages à relire et pourquoi, avec le lien de la page existante.

    Une culture archivée n'en a aucune : son parcours est clos, relire ses minuteries ne
    dirait plus rien de vrai. Un stade inconnu ou absent ne rend pas une liste par défaut :
    une absence reste une absence.
    """
    if subject.get("archived"):
        return []
    space_1 = subject.get("space") == "space_1"
    checks = []
    for key, reason in STAGE_CHECKS.get(subject.get("stage") or "", ()):
        label, href = (SPACE_1_CHECKLIST.get(key) or CHECKLIST[key]) if space_1 else CHECKLIST[key]
        checks.append({"key": key, "label": label, "href": href, "reason": reason})
    return checks
# Bloc « Aujourd'hui » de l'accueil : autant de cartes de rappel en retard et autant dues
# du jour, pas davantage. Même raison que `TODAY_JOURNAL` — l'accueil montre la prochaine
# action, il n'est pas une seconde page de rappels ; au-delà il renvoie à `/cultures/cycles`.
# Un carnet de deux ans peut porter des dizaines de rappels en retard, et chacun est un
# formulaire complet dans la page.
TODAY_REMINDERS = 10
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
MAX_MEDIA_BYTES = 256 * 1024 * 1024
MIN_FREE_BYTES = 128 * 1024 * 1024


def planned_date(value, field="due_date"):
    """Échéance d'un rappel ; le refus nomme le contrôle qui la porte.

    Le champ est nommé **ici**, dans la règle qui connaît la valeur refusée. Le magasin
    déduisait auparavant le contrôle du premier mot du message : le libellé devenait un
    contrat implicite, qu'une reformulation cassait sans rien faire échouer d'autre.
    Le formulaire de création et celui de report portent tous deux `name="due_date"`.
    """
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not 2000 <= parsed.year <= 2100:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise CultureError("Échéance attendue : date ISO de 2000 à 2100.", field) from None


def reminder_buckets(rows, today, zone="UTC"):
    """Classe des rappels en quatre seaux, sans base ni horloge implicite.

    `today` est la date locale déjà calculée par l'appelant ; `zone` ne sert qu'à ramener
    l'horodatage de clôture (`completed_at`, sinon `recorded_at`) à cette même date locale.
    Comparer la seule chaîne UTC ferait basculer « clos aujourd'hui » une heure trop tôt ou
    trop tard selon la saison — un rappel clos à 23 h 30 heure d'été disparaîtrait de la
    journée où il a été fait.

    Un rappel ouvert (`planned`/`postponed`) tombe dans `overdue`, `due_today` ou
    `upcoming` selon sa seule échéance ; un rappel clos n'apparaît que s'il l'a été
    aujourd'hui. Aucun seau n'invente d'entrée : une absence reste une liste vide.
    """
    buckets = {"overdue": [], "due_today": [], "upcoming": [], "done_today": []}
    for row in rows:
        state = row.get("state")
        if state in ("planned", "postponed"):
            due = row.get("due_date")
            buckets["overdue" if due < today else "due_today" if due == today else "upcoming"].append(row)
        elif state in ("done", "cancelled") and local_day(row.get("completed_at") or row.get("recorded_at"), zone) == today:
            buckets["done_today"].append(row)
    return buckets


def local_day(value, zone):
    """Jour local d'une date seule ou d'un instant ISO ; `None` si la valeur est illisible.

    Fonction unique du carnet : il en existait deux, l'une pour les clôtures de rappel
    (toujours des instants) et l'autre pour les dates de vérification (souvent des dates
    seules), et elles ne répondaient pas la même chose sur la même entrée. Les deux
    conventions sont ici explicites et compatibles :

    * une date seule (`AAAA-MM-JJ`) **est déjà** un jour local et reste telle quelle —
      aucune heure n'est inventée, exactement comme `model.culture.age` ;
    * un instant est ramené au fuseau du carnet, sans quoi une clôture à 23 h 30 heure
      d'été changerait de journée ;
    * une absence ou une chaîne illisible ne devient jamais une date : elle vaut `None`,
      et l'appelant décide ce qu'une absence signifie chez lui.
    """
    if not isinstance(value, str) or not value:
        return None
    if len(value) == 10:
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(zone)).date().isoformat()
    except (ValueError, TypeError, KeyError):
        return None


def reminder_values(raw):
    """Valeurs d'un rappel, chaque refus désignant le contrôle du formulaire qui le porte.

    Les `name` sont ceux de `culture_cycles.html` (création d'un rappel) : `title`,
    `due_date`, `interval_days` et `note`. `_cycle_validate` revalide des lignes déjà
    écrites avec la même fonction : le champ y désigne alors une saisie qui n'existe plus,
    mais ce refus-là ne remonte pas à un formulaire, il fait échouer une restauration.
    """
    interval = raw.get("interval_days", 0)
    if type(interval) is not int or not 0 <= interval <= 366:
        raise CultureError("Récurrence : nombre entier de jours, de 0 (ponctuel) à 366.", "interval_days")
    return {"title": text_value(raw.get("title"), "Rappel", 160, field="title"),
            "due_date": planned_date(raw.get("due_date")), "interval_days": interval,
            "note": text_value(raw.get("note", ""), "Note", 4000, False, field="note")}


# Synthèse climatique d'un cycle : seaux alignés sur des multiples entiers de leur
# durée depuis l'époque Unix, exactement comme la clé « hour » de climate_hours.
# La convention reste donc UTC et invariante au changement d'heure ; un seau
# « jour » est un jour UTC et un seau « semaine » commence un jeudi 00:00 UTC.
CLIMATE_GRANULARITIES = ((3600, "heure"), (86400, "jour"), (604800, "semaine"), (2419200, "quatre semaines"))
MAX_SUMMARY_BUCKETS = 200
MAX_SUMMARY_POINTS = 2000
CLIMATE_PAGE = 60


def climate_granularity(start_hour, end_hour):
    """Pas le plus fin qui couvre tout le cycle sous le plafond de périodes."""
    for seconds, label in CLIMATE_GRANULARITIES:
        if end_hour // seconds - start_hour // seconds + 1 <= MAX_SUMMARY_BUCKETS:
            return seconds, label
    return CLIMATE_GRANULARITIES[-1]


def climate_span(bucket, seconds, start_hour, end_hour):
    """Heures du seau réellement comprises dans le cycle ; les bords restent partiels."""
    first = max(bucket, start_hour)
    last = min(bucket + seconds - 3600, end_hour)
    return max(0, (last - first) // 3600 + 1)


def climate_point(sensor, label, unit, bucket, span_hours, row=None):
    """Moyenne pondérée par les effectifs fiables ; une absence reste une lacune, jamais un zéro."""
    valid = int(row["valid_count"]) if row is not None else 0
    observed = int(row["observed_count"]) if row is not None else 0
    hours = int(row["hours"]) if row is not None else 0
    total = float(row["total"]) if row is not None else 0.0
    return {"sensor": sensor, "label": label, "unit": unit, "hour": bucket,
            "at": datetime.fromtimestamp(bucket, timezone.utc).isoformat(),
            "minimum": row["minimum"] if row is not None else None,
            "maximum": row["maximum"] if row is not None else None,
            "mean": total / valid if valid else None,
            "valid_count": valid, "observed_count": observed,
            "hours": hours, "span_hours": span_hours,
            "coverage": valid / (60 * span_hours) if span_hours else 0.0,
            "hour_coverage": hours / span_hours if span_hours else 0.0,
            "missing": hours == 0}


def trusted_value(reading):
    """Aucune valeur dégradée ou manquante n'alimente les statistiques de confiance."""
    value = reading.get("value")
    if (reading.get("status") != "normal" or not reading.get("enabled", True)
            or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
        return None
    return value
