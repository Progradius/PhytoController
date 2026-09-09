"""Règles pures des vérifications déclaratives (lot D) : contexte historique et conflits.

Rien ici n'accède au matériel, au disque ni à la configuration : une case cochée est une
déclaration datée de l'opérateur, jamais une commande d'équipement.

Le contexte enregistré au moment de la saisie (`space`, `stage`, `stage_at`,
`stage_precision`, `subject_version`) est conservé tel quel et reste **distinct du stade
affiché aujourd'hui**. Le conflit avec une correction rétrospective du parcours est donc
**dérivé à la lecture** : il se recalcule à chaque affichage à partir de la projection
courante, sans colonne d'acquittement et sans réécriture silencieuse. L'opérateur le lève
en créant une révision — correction ou annulation, toujours motivée.
"""

from model.culture import CultureError, text_value
# `local_day` est réexporté ici : le lot des vérifications l'importe depuis ce module
# depuis l'origine, et il n'y a plus qu'une seule fonction pour tout le carnet.
from model.culture_cycle import CHECKLIST, local_day  # noqa: F401  (réexport)

PRECISIONS = ("date", "approximative", "instant")
MAX_REASON = 500


def check_values(raw):
    """Les trois cases exactement, strictement booléennes ; une absence n'est jamais un zéro."""
    if not isinstance(raw, dict) or set(raw) != set(CHECKLIST) or any(type(value) is not bool for value in raw.values()):
        raise CultureError("Renseigner les trois vérifications déclaratives.")
    return {key: int(raw[key]) for key in CHECKLIST}


def reason_value(raw, label):
    """Une correction ou une annulation sans motif ne se relit pas : le motif est obligatoire."""
    return text_value(raw, label, MAX_REASON)


def context_at(subject, day, zone):
    """Stade, début de stade et espace réels d'une culture à un jour local donné.

    Les périodes et occupations viennent de `project()` : le parcours est donc celui
    d'aujourd'hui, corrections comprises. Convention du jour de bascule : la période ou
    l'occupation la plus récente commencée ce jour-là l'emporte, exactement comme la saisie
    qui accepte la date d'un changement de stade horodaté. Un jour antérieur à la première
    période n'a pas de contexte : la fonction renvoie `None` plutôt qu'un contexte inventé.
    """
    period, space = None, None
    for item in subject["periods"]:
        if local_day(item["start"], zone) <= day:
            period = item
    for item in subject["occupations"]:
        if local_day(item["start"], zone) <= day:
            # Un espace libéré avant ce jour ne vaut plus ; libéré le jour même, il vaut encore.
            space = item["space"] if not item["end"] or day <= local_day(item["end"], zone) else None
    if period is None:
        return None
    return {"stage": period["stage"], "stage_at": period["start"],
            "stage_precision": period["precision"], "space": space}


def conflict(row, subject, zone):
    """Verdict `(conflit, contexte inconnu)` d'une vérification face au parcours actuel.

    Une vérification annulée n'affirme plus rien : elle ne peut pas contredire le parcours.
    Une ligne migrée du schéma 3 (`subject_version` nul) n'a pas enregistré son contexte :
    aucun verdict n'est possible, et en inventer un serait pire que de l'admettre.
    """
    if row["cancelled"]:
        return None, False
    if row["subject_version"] is None:
        return None, True
    context = context_at(subject, local_day(row["effective_at"], zone), zone)
    if context is None:
        return None, True
    if context["stage"] == row["stage"] and context["space"] == row["space"]:
        return None, False
    return {"expected_stage": context["stage"], "expected_space": context["space"],
            "recorded_stage": row["stage"], "recorded_space": row["space"]}, False
