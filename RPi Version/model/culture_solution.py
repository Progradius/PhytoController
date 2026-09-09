"""Validation pure des relevés et mélanges, sans conseil de dosage."""

import math
from datetime import datetime
from zoneinfo import ZoneInfo

from model.culture import CultureError, text_value

RESERVOIRS = {"reservoir_2": ("Réservoir de l’espace 2", "space_2"),
              "cuttings_1": ("Bac de bouturage de l’espace 1", "space_1")}
SOLUTION_KINDS = {"reading": "Relevé", "renewal": "Renouvellement", "water": "Arrosage",
                  "topup": "Appoint d’eau", "nutrient": "Ajout de nutriments", "ph": "Correction pH"}
UNITS = ("mL", "g", "L", "mg")
# Repères de lecture des courbes : une variante de forme et de teinte par source, bornée.
# Au-delà, les sources restantes partagent la variante de repli et la légende le dit, plutôt
# que de laisser croire à un repère propre à chacune.
CHART_SOURCE_VARIANTS = 6


def number(value, label, minimum=0, maximum=1000000, required=False, *, field=None, index=None):
    if value is None or value == "":
        if required:
            raise CultureError(f"{label} obligatoire.", field, index)
        return None
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError()
        result = float(value.replace(",", ".") if isinstance(value, str) else value)
        if not math.isfinite(result) or not minimum <= result <= maximum:
            raise ValueError()
        return result
    except (ValueError, OverflowError):
        raise CultureError(f"{label} : nombre attendu entre {minimum} et {maximum}.", field, index) from None


def ingredients(raw, factor=1):
    if not isinstance(raw, list) or len(raw) > 40:
        raise CultureError("Liste de 40 ingrédients maximum attendue.")
    result = []
    for position, item in enumerate(raw):
        if not isinstance(item, dict) or set(item) - {"product", "quantity", "unit"}:
            raise CultureError("Ingrédient invalide.")
        if item.get("unit") not in UNITS:
            raise CultureError("Unité de produit attendue : mL, g, L ou mg.", "unit", position)
        quantity = number(item.get("quantity"), "Quantité", required=True,
                          field="quantity", index=position) * factor
        result.append({"product": text_value(item.get("product"), "Produit", field="product", index=position),
                       "quantity": number(quantity, "Quantité calculée", required=True,
                                          field="quantity", index=position), "unit": item["unit"]})
    return result


def measurements(raw):
    unit = raw.get("ec_unit", "mS/cm")
    if unit not in ("mS/cm", "µS/cm"):
        raise CultureError("EC : choisir mS/cm ou µS/cm ; les ppm ne sont pas convertis.", "ec_unit")
    ec = number(raw.get("ec"), "EC", maximum=100000 if unit == "µS/cm" else 100, field="ec")
    context = raw.get("context", "independent")
    if context not in ("independent", "before", "after"):
        raise CultureError("Contexte attendu : indépendant, avant ou après.", "context")
    compensation = raw.get("compensation", "unknown")
    if compensation not in ("unknown", "yes", "no"):
        raise CultureError("Compensation de température invalide.", "compensation")
    return {"ph": number(raw.get("ph"), "pH", maximum=14, field="ph"),
            "ec": ec / 1000 if ec is not None and unit == "µS/cm" else ec,
            "temperature_c": number(raw.get("temperature_c"), "Température (°C)", minimum=-20,
                                    maximum=100, field="temperature_c"),
            "volume_l": number(raw.get("volume_l"), "Volume (L)", field="volume_l"),
            "context": context, "compensation": compensation}


def _chart_day(value, zone):
    """Date locale d'un point de courbe. Aucune horloge : seule la valeur portée compte."""
    if not value:
        return ""
    if len(value) == 10:
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(zone)).date().isoformat()


def _readable_day(value):
    return f"{value[8:10]}/{value[5:7]}/{value[0:4]}" if len(value) == 10 else value


def _count(number_of, singular, plural=None):
    """Un compte et son mot accordé ; zéro reste zéro *occurrence*, jamais une mesure nulle."""
    return f"{number_of} {singular if number_of <= 1 else (plural or singular + 's')}"


def _target_names(target, names):
    """Une cible de courbe peut réunir plusieurs sujets arrosés ensemble : ils gardent
    chacun leur nom, la clé technique ne servant que de repli quand il est inconnu."""
    parts = [part for part in str(target or "").split(",") if part]
    return [names.get(part, part) for part in parts] or ["cible inconnue"]


def source_label(target, period, names):
    """Nom lisible d'une source de courbe : la cible telle qu'elle est nommée et la période
    de solution qui la portait. Mise en mots, sans règle métier ni interprétation."""
    return f"{' et '.join(_target_names(target, names))} · solution {period[:8] if period else 'manuelle'}"


def chart_sources(points, names):
    """Une variante de repère par couple (cible, période de solution), dans l'ordre d'apparition.

    Deux sources ne sont jamais fondues ni reliées : elles ne partagent une variante que dans
    le repli, qui est annoncé par sa propre entrée de légende. Renvoie les variantes alignées
    sur `points` — l'appelant les pose sur ses points — et la légende qui les nomme.

    Chaque entrée porte `label`, la source entière (cibles et période), et `target`, les seules
    cibles nommées : le tableau équivalent a une colonne « Cible ou capteur » et une colonne
    « Période », qui ne doivent pas répéter la même phrase. L'entrée de repli n'est la
    désignation d'aucune source : son `target` est vide, et l'appelant sait ainsi qu'il ne peut
    pas s'en servir pour nommer un point.
    """
    ranks = {}
    for point in points:
        key = (point.get("target") or "", point.get("period") or "")
        ranks.setdefault(key, len(ranks))
    legend = [{"variant": rank, "label": source_label(key[0], key[1], names),
               "target": " et ".join(_target_names(key[0], names))}
              for key, rank in sorted(ranks.items(), key=lambda item: item[1])[:CHART_SOURCE_VARIANTS]]
    overflow = len(ranks) - CHART_SOURCE_VARIANTS
    if overflow > 0:
        legend.append({"variant": CHART_SOURCE_VARIANTS, "target": "",
                       "label": f"{_count(overflow, 'autre source', 'autres sources')} · "
                                "même repère, faute de variantes distinctes"})
    variants = [min(ranks[(p.get("target") or "", p.get("period") or "")], CHART_SOURCE_VARIANTS)
                for p in points]
    return {"legend": legend, "variants": variants}


def chart_summary(points, metric, label, unit, zone, names):
    """Synthèse littérale d'une courbe de solution, calculée sur les points déjà bornés.

    Période couverte, nombre de mesures, minimum, moyenne, maximum, lacunes et cibles
    présentes — rien d'autre : aucune interprétation agronomique, aucun verdict, aucune
    tendance, aucun écart à une plage cible. Une absence de mesure reste une absence et
    n'entre dans aucun calcul : elle est comptée comme lacune, jamais comme un zéro.
    La moyenne est pondérée par le nombre de mesures de chaque point, pour qu'un agrégat
    journalier ne pèse pas comme une mesure isolée.
    """
    suffix = f" {unit}" if unit else ""
    if not points:
        return f"{label} · aucune mesure sur ce filtre."
    days = sorted(_chart_day(point.get("at"), zone) for point in points)
    period = f"du {_readable_day(days[0])} au {_readable_day(days[-1])}"
    total, weighted, lowest, highest, gaps = 0, 0.0, None, None, 0
    for point in points:
        value = point.get(metric)
        if value is None:
            gaps += 1
            continue
        weight = point.get(metric + "_count") or 1
        total += weight
        weighted += value * weight
        low = point.get(metric + "_min")
        high = point.get(metric + "_max")
        low = value if low is None else low
        high = value if high is None else high
        lowest = low if lowest is None else min(lowest, low)
        highest = high if highest is None else max(highest, high)
    targets = []
    for point in points:
        for name in _target_names(point.get("target"), names):
            if name not in targets:
                targets.append(name)
    parts = [label, period]
    if total:
        parts.append(_count(total, "mesure"))
        parts.append(f"minimum {lowest:.2f}{suffix}, moyenne {weighted / total:.2f}{suffix}, "
                     f"maximum {highest:.2f}{suffix}")
    else:
        parts.append("aucune mesure")
    parts.append(_count(gaps, "lacune"))
    parts.append("cibles : " + ", ".join(targets))
    return " · ".join(parts) + "."
