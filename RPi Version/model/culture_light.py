"""Repères d'éclairage (lot F) : règles pures, sans matériel, disque ni horloge implicite.

Un repère est une **information d'exploitation** : il ne commande rien, ne modifie aucun
horaire et n'est jamais appliqué à la configuration. Le rapprochement avec les horaires
réellement configurés est un écart affiché, calculé ici sans lire ni écrire quoi que ce soit.
"""

from __future__ import annotations

from model.culture import SPACES, STAGES, CultureError

DAY_MINUTES = 1440
LIGHT_SCOPES = {"global": "Toutes les cultures", "space": "Un espace", "subject": "Une culture"}
# Rangs de résolution : le plus précis gagne. Sujet > espace > global.
SCOPE_RANK = {"global": 1, "space": 2, "subject": 3}
# Préremplissages proposés par le formulaire, jamais des données existantes ni un
# repère implicite : rien n'est résolu tant qu'un repère n'a pas été saisi.
LIGHT_PRESETS = {"vegetatif": (1080, 360), "floraison": (720, 720)}
MAX_LIGHT_ROWS = 200


def light_minutes(on_minutes, off_minutes):
    """Cycle journalier strict : deux entiers dont la somme fait exactement 24 h."""
    for value in (on_minutes, off_minutes):
        if type(value) is not int or not 0 <= value <= DAY_MINUTES:
            raise CultureError("Durées d'éclairage : entiers de 0 à 1440 minutes.")
    if on_minutes + off_minutes != DAY_MINUTES:
        raise CultureError("Le repère doit couvrir 24 h : éclairage + obscurité = 1440 minutes.")
    return on_minutes, off_minutes


def duration_label(minutes):
    """Durée lisible ; les minutes restent visibles quand elles ne sont pas rondes."""
    if minutes is None:
        return "—"
    hours, rest = divmod(int(minutes), 60)
    return f"{hours} h" if not rest else f"{hours} h {rest:02d}"


def light_label(on_minutes, off_minutes):
    return f"{duration_label(on_minutes)} / {duration_label(off_minutes)}"


def gap_label(minutes):
    """Écart signé, présenté comme une information et jamais comme un défaut."""
    if minutes is None:
        return "—"
    if minutes == 0:
        return "aucun écart"
    sign = "+" if minutes > 0 else "−"
    return f"{sign}{duration_label(abs(minutes))} d’éclairage configuré"


def schedule_on_minutes(schedule):
    """Minutes d'éclairage d'une minuterie quotidienne, minuit traversé compris.

    Convention identique à `utils/schedule.minute_in_range` : la plage est semi-ouverte
    et une plage dont les deux bornes sont égales est **vide**, jamais 24 h.
    """
    try:
        start = int(schedule["start_hour"]) * 60 + int(schedule["start_minute"])
        stop = int(schedule["stop_hour"]) * 60 + int(schedule["stop_minute"])
    except (KeyError, TypeError, ValueError):
        raise CultureError("Horaires de minuterie illisibles.") from None
    if not 0 <= start < DAY_MINUTES or not 0 <= stop < DAY_MINUTES:
        raise CultureError("Horaires de minuterie hors de la journée.")
    if start == stop:
        return 0
    return (stop - start) % DAY_MINUTES


def compare_light(reference, schedule):
    """Écart informatif entre un repère et les horaires configurés d'une minuterie.

    Aucun repère résolu ⇒ aucun écart : `None`, jamais un écart contre une valeur
    standard implicite. L'écart est signé du point de vue de la configuration.
    """
    if reference is None or schedule is None:
        return None
    configured = schedule_on_minutes(schedule)
    expected = int(reference["on_minutes"])
    difference = configured - expected
    return {
        "reference_on_minutes": expected,
        "reference_off_minutes": int(reference["off_minutes"]),
        "configured_on_minutes": configured,
        "configured_off_minutes": DAY_MINUTES - configured,
        "difference_minutes": difference,
        "matches": difference == 0,
        "empty": configured == 0,
        "crosses_midnight": schedule_crosses_midnight(schedule),
        "reference_label": light_label(expected, int(reference["off_minutes"])),
        "configured_label": light_label(configured, DAY_MINUTES - configured),
        "gap_label": gap_label(difference),
    }


def schedule_crosses_midnight(schedule):
    start = int(schedule["start_hour"]) * 60 + int(schedule["start_minute"])
    stop = int(schedule["stop_hour"]) * 60 + int(schedule["stop_minute"])
    return start > stop


def light_target(row):
    """Cible d'un repère : couple (portée, identifiant visé) servant à l'unicité."""
    scope = row["scope"]
    if scope == "subject":
        return ("subject", row["subject_id"])
    if scope == "space":
        return ("space", row["space"])
    return ("global", None)


def resolve_light(at, stage, subject_id, space, rows):
    """Repère applicable à une date : sujet > espace > global, stade prioritaire.

    `rows` sont les révisions courantes non annulées. Un repère dont le `stage` est
    renseigné ne s'applique qu'à ce stade déclaré ; aucun repère résolu ⇒ `None`.
    """
    best = None
    for row in rows:
        if row.get("cancelled"):
            continue
        if row["start_sort_at"] > at or (row["end_sort_at"] is not None and row["end_sort_at"] <= at):
            continue
        scope = row["scope"]
        if scope == "subject" and row["subject_id"] != subject_id:
            continue
        if scope == "space" and row["space"] != space:
            continue
        if row["stage"] and row["stage"] != stage:
            continue
        key = (SCOPE_RANK[scope], 1 if row["stage"] else 0, row["start_sort_at"], row["revision"])
        if best is None or key > best[0]:
            best = (key, row)
    return dict(best[1]) if best else None


def validate_light_windows(rows):
    """Invariants exportables : révisions sans trou, cycle de 24 h, fenêtres disjointes.

    Le chevauchement est refusé par `(portée, cible, stade)` : un repère de stade et un
    repère sans stade peuvent couvrir la même période, ils ne désignent pas la même chose.
    """
    revisions = {}
    for row in rows:
        row = dict(row)
        if row["scope"] not in LIGHT_SCOPES:
            raise CultureError("Portée de repère d'éclairage inconnue.")
        if (row["scope"] == "subject") != (row["subject_id"] is not None):
            raise CultureError("Repère d'éclairage : cible de culture incohérente.")
        if (row["scope"] == "space") != (row["space"] is not None):
            raise CultureError("Repère d'éclairage : espace incohérent.")
        if row["space"] is not None and row["space"] not in SPACES:
            raise CultureError("Espace de repère d'éclairage inconnu.")
        if row["stage"] is not None and row["stage"] not in STAGES:
            raise CultureError("Stade de repère d'éclairage inconnu.")
        light_minutes(row["on_minutes"], row["off_minutes"])
        if (row["end_at"] is None) != (row["end_sort_at"] is None):
            raise CultureError("Fin de repère d'éclairage incomplète.")
        if row["end_sort_at"] is not None and row["end_sort_at"] <= row["start_sort_at"]:
            raise CultureError("Une fenêtre de repère se termine avant de commencer.")
        if type(row["revision"]) is not int or row["revision"] < 1:
            raise CultureError("Révision de repère d'éclairage invalide.")
        revisions.setdefault(row["id"], []).append(row)
    current = []
    for versions in revisions.values():
        numbers = sorted(version["revision"] for version in versions)
        if numbers != list(range(1, len(numbers) + 1)):
            raise CultureError("Révisions de repère d'éclairage manquantes ou dupliquées.")
        latest = max(versions, key=lambda version: version["revision"])
        if not latest["cancelled"]:
            current.append(latest)
    groups = {}
    for row in current:
        groups.setdefault((light_target(row), row["stage"]), []).append(row)
    for windows in groups.values():
        windows.sort(key=lambda row: row["start_sort_at"])
        for previous, following in zip(windows, windows[1:]):
            if previous["end_sort_at"] is None or previous["end_sort_at"] > following["start_sort_at"]:
                raise CultureError("Deux repères d'éclairage se chevauchent pour la même cible et le même stade.")
    return current
