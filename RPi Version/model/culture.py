"""Règles du carnet : aucune dépendance au matériel, au disque ou à l'horloge système."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


STAGES = {"germination": "Germination", "enracinement": "Enracinement",
          "vegetatif": "Végétatif", "floraison": "Floraison", "sechage": "Séchage",
          "maintien": "Maintien"}
KINDS = {"create": "Origine", "stage": "Stade", "move": "Déplacement",
         "loss": "Perte", "note": "Note", "harvest": "Récolte",
         "finish": "Fin du séchage", "release": "Libération", "archive": "Archivage",
         "identity": "Identité"}
SPACES = {"space_1": "Espace 1", "space_2": "Espace 2"}


class CultureError(ValueError):
    """Erreur métier présentable sans contenu de l'utilisateur.

    `field` porte l'attribut `name` du contrôle fautif, `index` son rang 0-based parmi
    les contrôles de même nom (origines, produits). L'interface peut ainsi rattacher le
    message au champ sans le deviner ; une erreur non rattachable reste sans champ, ce
    qui est une information et non un défaut.
    """

    def __init__(self, message, field=None, index=None):
        super().__init__(message)
        self.field = field
        self.index = index


class CultureConflict(CultureError):
    pass


def text_value(value, label, maximum=120, required=True, *, field=None, index=None):
    if not isinstance(value, str) or len(value.strip()) > maximum:
        raise CultureError(f"{label} : texte invalide ou trop long (maximum {maximum}).", field, index)
    value = value.strip()
    if required and not value:
        raise CultureError(f"{label} obligatoire.", field, index)
    return value


def integer(value, minimum=1, maximum=10000, *, field=None, index=None):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise CultureError(f"Effectif entier attendu, de {minimum} à {maximum}.", field, index)
    return value


def stamp(value, precision, zone, now, *, field=None, index=None):
    """Une date seule reste une date ; sa clé de tri n'est pas une heure déclarée."""
    if precision not in ("date", "approximative", "instant") or not isinstance(value, str):
        raise CultureError("Date ou précision invalide.", field, index)
    try:
        tz = ZoneInfo(zone)
        if precision == "instant":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError()
            if parsed > now:
                raise CultureError("Une date effective ne peut pas être future.", field, index)
            key = parsed.astimezone(timezone.utc).isoformat()
            local = parsed.astimezone(tz).date()
            return key, local.isoformat()
        local = date.fromisoformat(value)
        if local.isoformat() != value:
            raise ValueError()
        if local > now.astimezone(tz).date():
            raise CultureError("Une date effective ne peut pas être future.", field, index)
        key = datetime.combine(local, datetime.min.time(), tz).astimezone(timezone.utc).isoformat()
        return key, local.isoformat()
    except (ValueError, TypeError, OverflowError) as exc:
        if isinstance(exc, CultureError):
            raise
        raise CultureError("Date invalide ; utiliser une date ISO ou un instant avec fuseau.", field, index) from None


def event_payload(kind, raw):
    if not isinstance(kind, str) or kind not in KINDS or not isinstance(raw, dict):
        raise CultureError("Type d'événement invalide.")
    fields = {"create": {"origins"}, "stage": {"stage"}, "move": {"space"},
              "loss": {"count", "origin_id", "note"}, "note": {"note"},
              "harvest": {"note", "drying_at", "drying_precision"}, "finish": {"note", "weight_g", "release", "lessons", "origin_weights"},
              "release": set(), "archive": {"note"}, "identity": {"name", "variety"}}
    if set(raw) - fields[kind]:
        raise CultureError("Champ d'événement inconnu.")
    result = {}
    if kind == "create" and "origins" in raw:
        result["origins"] = raw["origins"]
    if "note" in fields[kind]:
        result["note"] = text_value(raw.get("note", ""), "Note", 4000, kind == "note")
    if kind == "identity":
        result["name"] = text_value(raw.get("name"), "Nom")
        result["variety"] = text_value(raw.get("variety", ""), "Variété", required=False)
    if kind == "harvest":
        result["drying_at"] = raw.get("drying_at")
        result["drying_precision"] = raw.get("drying_precision", "date")
    if kind == "stage":
        if not isinstance(raw.get("stage"), str) or raw.get("stage") not in STAGES:
            raise CultureError("Stade inconnu.", "stage")
        result["stage"] = raw["stage"]
    if kind == "move":
        if not isinstance(raw.get("space"), str) or raw.get("space") not in SPACES:
            raise CultureError("Espace inconnu.", "space")
        result["space"] = raw["space"]
    if kind == "loss":
        result["count"] = integer(raw.get("count"), field="count")
        result["origin_id"] = text_value(raw.get("origin_id", ""), "Origine", required=False, field="origin_id")
    if kind == "finish":
        release = raw.get("release", False)
        if not isinstance(release, bool):
            raise CultureError("Libération : booléen attendu.")
        result["release"] = release
        weight = raw.get("weight_g")
        if weight is not None:
            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or not 0 <= weight <= 1000000:
                raise CultureError("Poids sec invalide (grammes).", "weight_g")
        result["weight_g"] = weight
        result["lessons"] = text_value(raw.get("lessons", ""), "Enseignements", 4000, False)
        breakdown = raw.get("origin_weights", [])
        if not isinstance(breakdown, list) or len(breakdown) > 50:
            raise CultureError("Bilan par origine : 50 lignes maximum.")
        seen = set()
        result["origin_weights"] = []
        for position, item in enumerate(breakdown):
            if not isinstance(item, dict) or set(item) != {"origin_id", "weight_g"}:
                raise CultureError("Détail de récolte invalide.")
            origin_id = text_value(item["origin_id"], "Origine")
            value = item["weight_g"]
            if origin_id in seen or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1000000:
                raise CultureError("Poids par origine invalide ou origine dupliquée.", "origin_weight", position)
            seen.add(origin_id)
            result["origin_weights"].append({"origin_id": origin_id, "weight_g": value})
        if weight is not None and sum(item["weight_g"] for item in result["origin_weights"]) > weight + 0.000001:
            raise CultureError("Le détail par origine dépasse le poids total.")
    return result


def stage_path(subject):
    """Ordre des stades d'un lot, déduit de son origine ; un pied mère n'en a pas."""
    if subject["kind"] == "mother":
        return []
    return (["germination"] if subject["origin_type"] == "seed" else ["enracinement"]) + \
        ["vegetatif", "floraison", "sechage"]


def backfill_stages(subject):
    """Stades du parcours antérieurs au stade courant et encore absents de la fiche.

    Le stade courant n'est jamais proposé : une reprise en cours de cycle se complète
    vers le passé, sans toucher au stade affiché ni à la clôture de la fiche.
    """
    path = stage_path(subject)
    if not subject.get("stage") or subject["stage"] not in path:
        return []
    known = {period["stage"] for period in subject["periods"]}
    return [stage for stage in path[:path.index(subject["stage"])] if stage not in known]


# Rangs du parcours utilisés par la liste des stades proposables : germination et
# enracinement sont deux entrées du même rang (une seule des deux existe par lot) et
# `maintien` reste au rang d'entrée, hors parcours des lots.
STAGE_RANKS = {"germination": 0, "enracinement": 0, "vegetatif": 1, "floraison": 2,
               "sechage": 3, "maintien": 0}


def allowed_actions(subject):
    """Opérations proposables sur une fiche, dans l'ordre de `KINDS`.

    Règle unique et testée par équivalence avec le gabarit : une action absente d'ici ne
    doit jamais apparaître dans une page, et réciproquement. Une culture archivée ne garde
    que la note, l'identité et, si son espace est encore occupé, la libération.
    """
    kind, stage, space = subject["kind"], subject.get("stage"), subject.get("space")
    archived = bool(subject.get("archived"))
    actions = []
    for name in KINDS:
        if name == "create":
            continue
        if name in ("note", "identity"):
            allowed = True
        elif not archived and ((kind == "mother" and name == "archive") or (kind == "lot" and (
                (name in ("stage", "move", "loss", "harvest") and stage != "sechage"
                 and not (name == "stage" and stage == "floraison")
                 and not (name == "harvest" and space != "space_2"))
                or (name == "finish" and stage == "sechage")))):
            allowed = True
        else:
            allowed = name == "release" and archived and bool(space)
        if allowed:
            actions.append(name)
    return actions


def stage_options(subject, current=None):
    """Stades proposables, dans l'ordre de `STAGES`.

    Un stade déjà saisi (`current`, mode correction) rouvre la liste entière du parcours :
    corriger une saisie n'est pas progresser, et interdire le retour en arrière rendrait
    une erreur de stade irréparable. Le séchage n'est jamais proposé ici — il commence par
    une récolte — et l'entrée du parcours non retenue par l'origine reste exclue.
    """
    kind, stage = subject["kind"], subject.get("stage")
    excluded = "germination" if subject.get("origin_type") == "cutting" else "enracinement"
    options = []
    for key in STAGES:
        if kind == "mother":
            if key == "maintien":
                options.append(key)
        elif kind == "lot" and key not in ("maintien", "sechage") and key != excluded and (
                current or STAGE_RANKS[key] > STAGE_RANKS.get(stage, -1)):
            options.append(key)
    return options


def first_stage(kind, origin_type):
    """Premier stade du parcours : `maintien` pour un pied mère, sinon semis ou bouture."""
    if kind == "mother":
        return "maintien"
    return "enracinement" if origin_type == "cutting" else "germination"


def creation_stages(kind, origin_type):
    """Stades acceptés à la création d'une fiche.

    Plus large que `stage_options` d'un cran : une reprise peut déclarer une culture déjà
    en séchage, ce que le parcours autorise et que refuser rendrait insaisissable.
    """
    if kind == "mother":
        return ["maintien"]
    return [first_stage(kind, origin_type), "vegetatif", "floraison", "sechage"]


def fiche_actions(subject):
    """Triade d'en-tête de la fiche et repli des autres opérations.

    `reading` et `observation` ne sont pas des types d'événement : le premier est un lien
    vers la saisie de relevé, le second réunit la note et sa photo. Au plus une action
    contextuelle les rejoint — celle que l'état du parcours rend évidente — et `other`
    reçoit tout le reste, sans jamais répéter la note ni l'action promue.
    """
    allowed = allowed_actions(subject)
    stage, space = subject.get("stage"), subject.get("space")
    promoted = None
    if subject.get("archived"):
        promoted = "release" if space else None
    elif subject["kind"] == "mother":
        promoted = "archive"
    elif stage in ("germination", "enracinement", "vegetatif"):
        promoted = "stage"
    elif stage == "floraison":
        promoted = "harvest" if space == "space_2" else "move"
    elif stage == "sechage":
        promoted = "finish"
    if promoted not in allowed:
        promoted = None
    return {"primary": ["reading", "observation"] + ([promoted] if promoted else []),
            "other": [name for name in allowed if name != "note" and name != promoted]}


def project(subject, events, origins, now, zone, reliable):
    """Rejoue le parcours entier après chaque correction, avant validation en base."""
    current = dict(subject)
    current.update(stage=None, stage_at=None, stage_end=None, space=None, archived=False,
                   count=sum(o["count"] for o in origins), origins=origins, periods=[], occupations=[])
    current["initial_count"] = current["count"]
    active = [e for e in events if not e["cancelled"]]
    active.sort(key=lambda e: (e["sort_at"], e["sequence"]))
    created = False
    known_losses = {}
    for event in active:
        kind, data = event["kind"], event["payload"]
        at = event["effective_at"]
        if kind == "create":
            if created:
                raise CultureError("Origine dupliquée.")
            created = True
            current["origin_at"] = at
            current["origin_precision"] = event["precision"]
            continue
        if not created:
            raise CultureError("Un événement précède l'origine de la culture.")
        if current["archived"] and kind not in ("note", "identity", "release"):
            raise CultureError("Ce parcours est terminé ; corriger sa clôture avant de le modifier.")
        if kind == "identity":
            current.update(data)
        if kind in ("stage", "harvest"):
            stage = "sechage" if kind == "harvest" else data["stage"]
            stage_at = data["drying_at"] if kind == "harvest" else at
            stage_precision = data["drying_precision"] if kind == "harvest" else event["precision"]
            if subject["kind"] == "mother":
                if stage != "maintien" or current["stage"]:
                    raise CultureError("Un pied mère possède une seule période de maintien.")
            else:
                path = stage_path(subject)
                if stage not in path or (current["stage"] and path.index(stage) <= path.index(current["stage"])):
                    raise CultureError("Les stades doivent progresser dans l'ordre du parcours.")
                if stage == "sechage" and kind != "harvest":
                    raise CultureError("Utiliser la récolte pour commencer le séchage.")
                if kind == "harvest" and current["space"] != "space_2":
                    raise CultureError("La récolte et le séchage ont lieu dans l'espace 2.")
            if current["periods"]:
                current["periods"][-1]["end"] = at
            current["periods"].append({"stage": stage, "start": stage_at, "end": None, "precision": stage_precision})
            current.update(stage=stage, stage_at=stage_at, stage_precision=stage_precision)
        if kind == "move":
            if current["stage"] == "sechage":
                raise CultureError("Le lot en séchage reste dans l'espace 2.")
            if subject["kind"] == "mother" and data["space"] != "space_1":
                raise CultureError("Les pieds mères restent dans l'espace 1.")
            if current["space"] == data["space"]:
                raise CultureError("La culture occupe déjà cet espace.")
            if current["occupations"] and current["space"]:
                current["occupations"][-1]["end"] = event["sort_at"]
            current["occupations"].append({"space": data["space"], "start": event["sort_at"], "end": None})
            current["space"] = data["space"]
        if kind == "loss":
            if subject["kind"] != "lot" or current["stage"] == "sechage":
                raise CultureError("Une perte concerne un lot avant récolte.")
            current["count"] -= data["count"]
            if current["count"] < 0:
                raise CultureError("La perte dépasse l'effectif restant.")
            origin = data["origin_id"]
            if origin:
                match = next((o for o in origins if o["id"] == origin), None)
                known_losses[origin] = known_losses.get(origin, 0) + data["count"]
                if not match or known_losses[origin] > match["count"]:
                    raise CultureError("Perte incompatible avec cette origine.")
        if kind in ("finish", "archive"):
            if kind == "finish" and (subject["kind"] != "lot" or current["stage"] != "sechage"):
                raise CultureError("Terminer nécessite un lot en séchage.")
            if kind == "finish" and event["sort_at"] < stamp(current["stage_at"], current["stage_precision"], zone, now)[0]:
                raise CultureError("La fin du séchage précède son début.")
            if kind == "archive" and subject["kind"] != "mother":
                raise CultureError("Terminer le séchage pour archiver ce lot.")
            if kind == "finish" and any(item["origin_id"] not in {o["id"] for o in origins} for item in data.get("origin_weights", [])):
                raise CultureError("Origine du bilan inconnue ; corriger la récolte avant de modifier ses origines.")
            current.update(archived=True, stage_end=at, balance=data)
            if current["periods"]:
                current["periods"][-1]["end"] = at
        if kind in ("release", "archive") or (kind == "finish" and data["release"]):
            if kind == "release" and not current["archived"]:
                raise CultureError("Libérer l'espace après la fin du parcours.")
            if current["space"]:
                current["occupations"][-1]["end"] = event["sort_at"]
            current["space"] = None
    if not created:
        raise CultureError("L'origine de la culture ne peut pas être annulée.")
    if not current["periods"] or not current["occupations"]:
        raise CultureError("Conserver au moins un stade et une entrée dans un espace.")
    # Même convention calendaire que les compteurs : une période encore ouverte se compte jusqu'à aujourd'hui.
    for period in current["periods"]:
        period["duration"] = age(period["start"], period["end"], now, zone)
    current["age"] = age(current.get("stage_at"), current.get("stage_end"), now, zone)
    current["origin_age"] = age(current["origin_at"], current.get("stage_end"), now, zone)
    current["clock_reliable"] = reliable
    current["stage_label"] = STAGES.get(current["stage"], "À renseigner")
    return current


def age(start, end, now, zone):
    if not start:
        return None
    def local(value):
        if len(value) == 10:
            return date.fromisoformat(value)
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo(zone)).date()
    days = max(0, ((local(end) if end else now.astimezone(ZoneInfo(zone)).date()) - local(start)).days)
    return {"days": days, "weeks": days // 7, "remaining_days": days % 7, "week": days // 7 + 1}


def validate_spaces(subjects):
    occupied = []
    names = set()
    for subject in subjects:
        if subject["kind"] == "mother":
            name = subject["name"].casefold()
            if name in names:
                raise CultureError("Chaque pied mère doit avoir un nom distinct, archives comprises.")
            names.add(name)
        for period in subject["occupations"]:
            if period["end"] is not None and period["end"] <= period["start"]:
                continue
            if period["space"] == "space_2":
                for other_id, other in occupied:
                    if other_id != subject["id"] and period["start"] < (other["end"] or "9999") and other["start"] < (period["end"] or "9999"):
                        raise CultureError("L'espace 2 est déjà occupé sur cette période.")
                occupied.append((subject["id"], period))
