"""Rappels, photos et qualité des synthèses : règles sans accès matériel."""

import math
from datetime import date

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


def trusted_value(reading):
    """Aucune valeur dégradée ou manquante n'alimente les statistiques de confiance."""
    value = reading.get("value")
    if (reading.get("status") != "normal" or not reading.get("enabled", True)
            or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
        return None
    return value
