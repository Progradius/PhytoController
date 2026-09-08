"""Validation pure des relevés et mélanges, sans conseil de dosage."""

import math

from model.culture import CultureError, text_value

RESERVOIRS = {"reservoir_2": ("Réservoir de l’espace 2", "space_2"),
              "cuttings_1": ("Bac de bouturage de l’espace 1", "space_1")}
SOLUTION_KINDS = {"reading": "Relevé", "renewal": "Renouvellement", "water": "Arrosage",
                  "topup": "Appoint d’eau", "nutrient": "Ajout de nutriments", "ph": "Correction pH"}
UNITS = ("mL", "g", "L", "mg")


def number(value, label, minimum=0, maximum=1000000, required=False):
    if value is None or value == "":
        if required:
            raise CultureError(f"{label} obligatoire.")
        return None
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError()
        result = float(value.replace(",", ".") if isinstance(value, str) else value)
        if not math.isfinite(result) or not minimum <= result <= maximum:
            raise ValueError()
        return result
    except (ValueError, OverflowError):
        raise CultureError(f"{label} : nombre attendu entre {minimum} et {maximum}.") from None


def ingredients(raw, factor=1):
    if not isinstance(raw, list) or len(raw) > 40:
        raise CultureError("Liste de 40 ingrédients maximum attendue.")
    result = []
    for item in raw:
        if not isinstance(item, dict) or set(item) - {"product", "quantity", "unit"}:
            raise CultureError("Ingrédient invalide.")
        if item.get("unit") not in UNITS:
            raise CultureError("Unité de produit attendue : mL, g, L ou mg.")
        quantity = number(item.get("quantity"), "Quantité", required=True) * factor
        result.append({"product": text_value(item.get("product"), "Produit"),
                       "quantity": number(quantity, "Quantité calculée", required=True), "unit": item["unit"]})
    return result


def measurements(raw):
    unit = raw.get("ec_unit", "mS/cm")
    if unit not in ("mS/cm", "µS/cm"):
        raise CultureError("EC : choisir mS/cm ou µS/cm ; les ppm ne sont pas convertis.")
    ec = number(raw.get("ec"), "EC", maximum=100000 if unit == "µS/cm" else 100)
    context = raw.get("context", "independent")
    if context not in ("independent", "before", "after"):
        raise CultureError("Contexte attendu : indépendant, avant ou après.")
    compensation = raw.get("compensation", "unknown")
    if compensation not in ("unknown", "yes", "no"):
        raise CultureError("Compensation de température invalide.")
    return {"ph": number(raw.get("ph"), "pH", maximum=14),
            "ec": ec / 1000 if ec is not None and unit == "µS/cm" else ec,
            "temperature_c": number(raw.get("temperature_c"), "Température (°C)", minimum=-20, maximum=100),
            "volume_l": number(raw.get("volume_l"), "Volume (L)"),
            "context": context, "compensation": compensation}
