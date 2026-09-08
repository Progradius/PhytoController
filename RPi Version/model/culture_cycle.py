"""Rappels, photos et qualité des synthèses : règles sans accès matériel."""

import math
from datetime import date, datetime, timezone

from model.culture import CultureError, text_value

REMINDER_STATES = {"planned": "Prévu", "postponed": "Reporté", "done": "Fait", "cancelled": "Annulé"}
CHECKLIST = {"lighting": ("Éclairage vérifié", "/conf#daily-timer-2"),
             "pump": ("Pompe vérifiée", "/conf#cyclic-1"),
             "ventilation": ("Ventilation commune vérifiée", "/conf#motor")}
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
MAX_MEDIA_BYTES = 256 * 1024 * 1024
MIN_FREE_BYTES = 128 * 1024 * 1024


def planned_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or not 2000 <= parsed.year <= 2100:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise CultureError("Échéance attendue : date ISO de 2000 à 2100.") from None


def reminder_values(raw):
    interval = raw.get("interval_days", 0)
    if type(interval) is not int or not 0 <= interval <= 366:
        raise CultureError("Récurrence : nombre entier de jours, de 0 (ponctuel) à 366.")
    return {"title": text_value(raw.get("title"), "Rappel", 160),
            "due_date": planned_date(raw.get("due_date")), "interval_days": interval,
            "note": text_value(raw.get("note", ""), "Note", 4000, False)}


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
