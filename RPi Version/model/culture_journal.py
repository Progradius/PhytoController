"""Règles pures du journal transversal et des observations d'espace (lot H).

Aucune dépendance au disque, au matériel ni à l'horloge système : les bornes de période
reçoivent leur fuseau en argument, comme `stamp`. Le journal lui-même est une **vue**
SQLite (`culture_journal`) : ce module ne décrit que ce qui peut être vérifié sans base —
la forme d'une observation d'espace, la forme d'un filtre, et les invariants rejoués à la
restauration.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from model.culture import KINDS, SPACES, CultureError, text_value
from model.culture_solution import RESERVOIRS, SOLUTION_KINDS

# Une observation d'espace vise l'espace lui-même, jamais une fausse plante créée pour
# porter la note : les trois genres décrivent ce qui arrive au lieu, pas à une culture.
SPACE_EVENT_KINDS = {"observation": "Observation", "maintenance": "Maintenance",
                     "incident": "Incident"}
JOURNAL_SOURCES = {"event": "Culture", "solution": "Solution", "space_event": "Espace"}
# Le filtre « type » désigne une source et un genre : deux catalogues distincts partagent
# des noms (une note de culture n'est pas une observation d'espace), le préfixe les sépare.
JOURNAL_TYPES = {f"event:{key}": f"Culture · {label}" for key, label in KINDS.items()}
JOURNAL_TYPES.update({f"solution:{key}": f"Solution · {label}" for key, label in SOLUTION_KINDS.items()})
JOURNAL_TYPES.update({f"space_event:{key}": f"Espace · {label}" for key, label in SPACE_EVENT_KINDS.items()})
JOURNAL_FILTERS = ("start", "end", "target", "type")
JOURNAL_PAGE = 40
# Bloc « Aujourd'hui » de l'accueil : un rappel des toutes dernières opérations, pas une
# seconde page de journal. Au-delà, l'accueil renvoie au journal complet plutôt que de
# grossir une page dont le rôle est de montrer la prochaine action.
TODAY_JOURNAL = 5
# Quatre photos par observation, comme pour un événement de culture : le lot H réutilise
# les plafonds existants au lieu d'en inventer de nouveaux.
MAX_SPACE_PHOTOS = 4


def space_event_payload(kind, raw):
    """Contenu d'une observation d'espace : une note bornée, rien d'autre.

    Les refus nomment le contrôle de `culture_journal.html` qui les porte : `kind` pour
    le genre observé, `note` pour l'observation elle-même (le formulaire de correction
    l'appelle « Observation corrigée », sous le même `name`). Un contenu hors forme, lui,
    ne vient d'aucun champ : c'est la commande qui est malformée.
    """
    if not isinstance(kind, str) or kind not in SPACE_EVENT_KINDS:
        raise CultureError("Genre d'observation inconnu.", "kind")
    if not isinstance(raw, dict) or set(raw) - {"note"}:
        raise CultureError("Contenu d'observation invalide.")
    return {"note": text_value(raw.get("note"), "Note d'observation", 4000, field="note")}


def journal_filters(filters):
    """Filtres acceptés du journal, sans contact avec la base.

    L'existence de la cible dépend du carnet et reste vérifiée par le magasin ; ici seule
    la forme est jugée, pour qu'un filtre malformé n'atteigne jamais une requête SQL.
    """
    filters = filters or {}
    if not isinstance(filters, dict) or set(filters) - set(JOURNAL_FILTERS):
        raise CultureError("Filtre de journal inconnu.")
    clean = {}
    for key in JOURNAL_FILTERS:
        value = filters.get(key, "")
        if value in (None, ""):
            continue
        clean[key] = text_value(value, "Filtre du journal", 100)
    if clean.get("type") and clean["type"] not in JOURNAL_TYPES:
        raise CultureError("Type de journal inconnu.")
    return clean


def journal_window(filters, zone):
    """Bornes UTC `[début ; fin + 1 jour[` d'un filtre de période.

    La borne haute est **exclusive et calendaire** : une entrée horodatée du dernier jour
    du filtre reste incluse, ce qu'une comparaison sur la seule date effective raterait
    pour les saisies « date et heure connues ».
    """
    start, end = filters.get("start", ""), filters.get("end", "")
    if start and end and start > end:
        raise CultureError("La fin de la période précède son début.")

    def key(value, days=0):
        try:
            local = date.fromisoformat(value)
            if local.isoformat() != value or not 2000 <= local.year <= 2100:
                raise ValueError()
        except (ValueError, TypeError):
            raise CultureError("Période du journal : dates ISO de 2000 à 2100 attendues.") from None
        moment = datetime.combine(local + timedelta(days=days), time.min, ZoneInfo(zone))
        return moment.astimezone(timezone.utc).isoformat()

    return (key(start) if start else "", key(end, 1) if end else "")


def journal_target_kind(target, subject_ids):
    """Nature d'une cible de filtre : sujet, espace ou réservoir, jamais un texte libre."""
    if target in subject_ids:
        return "subject"
    if target in SPACES:
        return "space"
    if target in RESERVOIRS:
        return "reservoir"
    raise CultureError("Cible de filtre inconnue.")


def validate_space_events(rows):
    """Invariants rejoués à la restauration : révisions 1..n sans trou, contenu conforme.

    Une observation entièrement annulée reste légitime : la trace d'une saisie erronée ne
    doit pas disparaître d'une sauvegarde vérifiée.
    """
    revisions = {}
    for row in rows:
        item = dict(row)
        if item["space"] not in SPACES or item["kind"] not in SPACE_EVENT_KINDS:
            raise CultureError("Observation d'espace : espace ou genre inconnu.")
        if item["cancelled"] not in (0, 1) or item["clock_reliable"] not in (0, 1):
            raise CultureError("Observation d'espace incohérente.")
        if item["precision"] not in ("date", "approximative", "instant"):
            raise CultureError("Précision d'observation inconnue.")
        try:
            payload = json.loads(item["payload"])
        except (ValueError, TypeError):
            raise CultureError("Observation d'espace : contenu illisible.") from None
        space_event_payload(item["kind"], payload)
        revisions.setdefault(item["id"], []).append(item["revision"])
    for values in revisions.values():
        if sorted(values) != list(range(1, len(values) + 1)):
            raise CultureError("Révisions d'observation manquantes ou dupliquées.")
