"""Plages cibles pH/EC (lot E) : validation et résolution pures, sans disque ni matériel.

Une plage cible est une **déclaration** de l'opérateur : elle n'ordonne aucun dosage, ne
déclenche aucune alarme de contrôle et n'a aucune valeur par défaut. Une mesure antérieure
à toute plage reste sans cible, et c'est une réponse complète.

Unités : les bornes EC sont conservées en mS/cm, comme `solution_entries.ec`. La saisie peut
être exprimée en µS/cm ; la conversion (division par 1000) est faite ici, une seule fois,
avant toute écriture. Aucun ppm n'est converti.
"""

from model.culture import CultureError
from model.culture_solution import number

# Sentinelle de fin ouverte : au-delà de toute clé ISO, comme ailleurs dans le carnet.
OPEN_END = "9999"
BOUNDS = ("ph_min", "ph_max", "ec_min", "ec_max")
EC_UNITS = ("mS/cm", "µS/cm")
# Ordre de priorité de la résolution ; il est strict et sans fusion entre deux sources.
SOURCES = {"subject": "Cible directe de la mesure", "fed_subject": "Sujet alimenté par la solution",
           "reservoir": "Réservoir de la mesure"}


def bounds(raw):
    """Normalise les quatre bornes facultatives ; l'EC ressort toujours en mS/cm.

    `number` refuse déjà NaN, l'infini, les booléens et les valeurs hors bornes, et accepte
    la virgule décimale. Au moins une borne doit être renseignée : une plage vide ne dit rien.
    """
    if not isinstance(raw, dict):
        raise CultureError("Plage cible invalide.")
    unit = raw.get("ec_unit", "mS/cm")
    if unit not in EC_UNITS:
        raise CultureError("EC : choisir mS/cm ou µS/cm ; les ppm ne sont pas convertis.", "ec_unit")
    maximum = 100000 if unit == "µS/cm" else 100
    values = {
        "ph_min": number(raw.get("ph_min"), "pH minimum", maximum=14, field="ph_min"),
        "ph_max": number(raw.get("ph_max"), "pH maximum", maximum=14, field="ph_max"),
        "ec_min": number(raw.get("ec_min"), "EC minimum", maximum=maximum, field="ec_min"),
        "ec_max": number(raw.get("ec_max"), "EC maximum", maximum=maximum, field="ec_max"),
    }
    if unit == "µS/cm":
        for key in ("ec_min", "ec_max"):
            if values[key] is not None:
                values[key] = values[key] / 1000
    if all(values[key] is None for key in BOUNDS):
        # La première borne du formulaire porte le message : c'est là que la saisie manque.
        raise CultureError("Renseigner au moins une borne de pH ou d’EC.", "ph_min")
    check_bounds(values, saisie=True)
    return values


def check_bounds(values, saisie=False):
    """Ordre des bornes : un minimum ne peut pas dépasser son maximum.

    `saisie` distingue la validation d'un formulaire — le refus désigne alors le contrôle
    fautif — de la relecture d'une ligne déjà écrite, qui ne vient d'aucun champ.
    """
    if values["ph_min"] is not None and values["ph_max"] is not None and values["ph_min"] > values["ph_max"]:
        raise CultureError("pH : le minimum dépasse le maximum.", "ph_min" if saisie else None)
    if values["ec_min"] is not None and values["ec_max"] is not None and values["ec_min"] > values["ec_max"]:
        raise CultureError("EC : le minimum dépasse le maximum.", "ec_min" if saisie else None)


def validate_target_windows(rows):
    """Invariants non exprimables en SQL des plages cibles **courantes**.

    `rows` : les révisions courantes (annulées comprises, ignorées pour le chevauchement).
    Deux plages courantes non annulées de même cible ne peuvent pas se chevaucher : sinon
    la résolution devrait choisir, donc inventer.
    """
    windows = {}
    for raw in rows:
        row = dict(raw)
        values = {key: row.get(key) for key in BOUNDS}
        for key, value in values.items():
            if value is not None:
                number(value, "Borne de plage cible", maximum=14 if key.startswith("ph") else 100, required=True)
        if all(value is None for value in values.values()):
            raise CultureError("Plage cible sans aucune borne.")
        check_bounds(values)
        if row.get("scope") not in ("subject", "reservoir"):
            raise CultureError("Portée de plage cible inconnue.")
        if (row.get("scope") == "subject") != bool(row.get("subject_id")) or bool(row.get("subject_id")) == bool(row.get("reservoir_id")):
            raise CultureError("Cible de plage incohérente : un sujet ou un réservoir, jamais les deux.")
        start, end = row.get("start_sort_at"), row.get("end_sort_at")
        if not isinstance(start, str) or not start:
            raise CultureError("Début de plage cible manquant.")
        if end is not None and (not isinstance(end, str) or end <= start):
            raise CultureError("La fin de validité d’une plage cible doit suivre son début.")
        if row.get("cancelled"):
            continue
        key = (row["scope"], row.get("subject_id"), row.get("reservoir_id"))
        windows.setdefault(key, []).append((start, end or OPEN_END))
    for spans in windows.values():
        spans.sort()
        for previous, current in zip(spans, spans[1:]):
            if current[0] < previous[1]:
                raise CultureError("Deux plages cibles de la même cible se chevauchent.")


def covering(targets, at):
    """Plages courantes non annulées dont la fenêtre contient la clé de tri `at`."""
    return [target for target in targets if not target.get("cancelled")
            and target["start_sort_at"] <= at < (target.get("end_sort_at") or OPEN_END)]


def resolve_targets(entry, targets):
    """Plage applicable à une mesure, à la date de cette mesure, ou `None`.

    Priorité stricte, sans fusion : cibles directes de l'entrée, puis sujets alimentés par
    la solution à cette date, puis réservoir de l'entrée. Aucune rétroactivité : c'est la
    fenêtre qui contient `sort_at` qui décide, jamais la plage courante du jour. Un lot
    déplacé d'un espace à l'autre change donc de contexte à l'instant de son occupation,
    parce que `fed_subjects` est reconstruit sur les occupations réelles.
    """
    at = entry.get("sort_at")
    if not isinstance(at, str) or not at:
        return None
    applicable = covering(targets, at)
    direct = [subject for subject in (entry.get("targets") or []) if isinstance(subject, str)]
    fed = [subject for subject in (entry.get("fed_subjects") or []) if isinstance(subject, str) and subject not in direct]
    reservoir = entry.get("reservoir_id")
    for source, candidates in (
            ("subject", [t for t in applicable if t["scope"] == "subject" and t.get("subject_id") in direct]),
            ("fed_subject", [t for t in applicable if t["scope"] == "subject" and t.get("subject_id") in fed]),
            ("reservoir", [t for t in applicable if t["scope"] == "reservoir" and reservoir and t.get("reservoir_id") == reservoir])):
        if not candidates:
            continue
        # Un arrosage commun peut viser deux mères ayant chacune leur plage : les fenêtres
        # n'interdisent le chevauchement que pour une même cible. On retient alors la plage
        # commencée le plus tard, et l'ambiguïté est signalée plutôt que silencieusement fusionnée.
        chosen = max(candidates, key=lambda t: (t["start_sort_at"], t.get("id") or ""))
        return {**{key: chosen.get(key) for key in BOUNDS}, "source": source,
                "source_label": SOURCES[source], "id": chosen.get("id"),
                "label": chosen.get("label") or "", "stage": chosen.get("stage"),
                "subject_id": chosen.get("subject_id"), "reservoir_id": chosen.get("reservoir_id"),
                "start_sort_at": chosen["start_sort_at"], "end_sort_at": chosen.get("end_sort_at"),
                "multiple": len(candidates) > 1}
    return None


def target_text(resolved, metric):
    """Plage d'un relevé rendue lisible pour un export ; une absence de cible reste vide.

    Aucune borne n'est complétée : une cible « pH seul » ne fabrique pas de cible EC.
    """
    if not resolved or metric not in ("ph", "ec"):
        return ""
    low, high = resolved.get(metric + "_min"), resolved.get(metric + "_max")
    if low is None and high is None:
        return ""
    if low is None:
        return f"≤ {high}"
    if high is None:
        return f"≥ {low}"
    return f"{low} à {high}"


def target_bands(points):
    """Bandes de référence des courbes : segments consécutifs partageant la même plage.

    Les bandes sont **dérivées** des plages réellement résolues point par point ; aucune
    bande n'est prolongée sur une période sans cible, et aucune bande par défaut n'existe.
    """
    bands = []
    for point in points:
        resolved = point.get("target")
        identifier = resolved.get("id") if resolved else None
        if bands and bands[-1]["id"] == identifier and identifier is not None:
            bands[-1]["end"] = point["at"]
            continue
        if identifier is None:
            bands.append({"id": None, "start": point["at"], "end": point["at"]})
            continue
        bands.append({"id": identifier, "start": point["at"], "end": point["at"],
                      "source": resolved["source"], "label": resolved["label"],
                      **{key: resolved[key] for key in BOUNDS}})
    return [band for band in bands if band["id"] is not None]
