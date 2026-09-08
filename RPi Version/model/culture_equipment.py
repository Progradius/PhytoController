"""Affectations d'équipements datées (lot G) : règles pures, sans disque ni matériel.

Le catalogue `param/equipment_metadata.json` reste la source de vérité des identifiants et
des noms **actuels** ; il n'est ni lu ni écrit ici. Le carnet n'ajoute que l'association
métier historique : quel équipement servait à quoi, et entre quelles dates.

Trois règles gouvernent tout le lot :

* `display_name` est une **copie du libellé connu à la saisie**. Renommer un équipement
  plus tard ne réécrit aucun libellé enregistré.
* la résolution d'un contexte à une date suit une cascade stricte — affectation datée,
  puis copie du catalogue portée par la saisie, puis « inconnue ». Il n'y a **jamais** de
  repli sur le catalogue courant : un nom d'aujourd'hui n'est pas une association d'hier.
* un équipement n'a qu'une seule affectation courante à un instant donné.
"""

from __future__ import annotations

from model.culture import CultureError, SPACES, text_value
from model.culture_solution import RESERVOIRS
from param.equipment_metadata import EQUIPMENT_IDS

EQUIPMENT_SCOPES = {"space": "Espace", "reservoir": "Réservoir", "greenhouse": "Serre entière"}
EQUIPMENT_SOURCES = {"operator": "Déclaration de l'exploitant",
                     "catalog_snapshot": "Reprise déclarée du catalogue"}
PRECISIONS = ("date", "approximative", "instant")
USAGE_MAXIMUM = 32
# Propositions d'usage, jamais un vocabulaire fermé : `cyclic_2` porte deux rôles
# possibles selon l'espace, et l'exploitant doit pouvoir en nommer d'autres.
USAGE_SUGGESTIONS = ("éclairage", "irrigation", "brumisation", "extraction", "brassage",
                     "chauffage", "pompe de bouturage", "oxygénation")
PROVENANCES = {"link": "affectation datée du carnet",
               "snapshot": "copie du catalogue connue à la saisie",
               "unknown": "association inconnue à cette date"}


def equipment_value(value):
    """Identifiant validé en Python contre le catalogue : le schéma ne fige rien."""
    if not isinstance(value, str) or value not in EQUIPMENT_IDS:
        raise CultureError("Équipement inconnu du catalogue.")
    return value


def usage_value(value):
    return text_value(value, "Usage de l'équipement", USAGE_MAXIMUM)


def scope_target(scope, space, reservoir_id):
    """Portée et cible cohérentes : un espace, un réservoir, ou la serre entière."""
    if not isinstance(scope, str) or scope not in EQUIPMENT_SCOPES:
        raise CultureError("Portée attendue : espace, réservoir ou serre entière.")
    space = space or None
    reservoir_id = reservoir_id or None
    if scope == "space":
        if not isinstance(space, str) or space not in SPACES or reservoir_id:
            raise CultureError("Choisir l'espace desservi par cet équipement.")
        return scope, space, None
    if scope == "reservoir":
        if not isinstance(reservoir_id, str) or reservoir_id not in RESERVOIRS or space:
            raise CultureError("Choisir le réservoir desservi par cet équipement.")
        return scope, None, reservoir_id
    if space or reservoir_id:
        raise CultureError("Une affectation à la serre entière ne vise ni espace ni réservoir.")
    return scope, None, None


def source_value(value):
    if value in (None, ""):
        return "operator"
    if not isinstance(value, str) or value not in EQUIPMENT_SOURCES:
        raise CultureError("Origine attendue : déclaration ou reprise du catalogue.")
    return value


def scope_label(row):
    scope = row.get("scope")
    if scope == "space":
        return SPACES.get(row.get("space"), row.get("space") or "")
    if scope == "reservoir":
        return RESERVOIRS.get(row.get("reservoir_id"), (row.get("reservoir_id") or "",))[0]
    return EQUIPMENT_SCOPES.get(scope, scope or "")


def covers(row, at):
    """Fenêtre semi-ouverte [début ; fin[ : une fin de validité n'est plus une couverture."""
    end = row.get("end_sort_at")
    return row["start_sort_at"] <= at and (end is None or at < end)


def link_item(row):
    return {"equipment_id": row["equipment_id"], "display_name": row.get("display_name") or "",
            "usage": row.get("usage") or "", "scope": row.get("scope"),
            "scope_label": scope_label(row), "space": row.get("space"),
            "reservoir_id": row.get("reservoir_id"), "link_id": row.get("id"),
            "revision": row.get("revision"), "recorded_at": row.get("recorded_at"),
            "start_at": row.get("start_at"), "end_at": row.get("end_at"),
            "source": row.get("source", "operator")}


def snapshot_items(recorded_context):
    """Copie de catalogue portée par une saisie ; `{}` reste une absence, jamais un zéro."""
    if not isinstance(recorded_context, dict):
        return []
    items = []
    for key in EQUIPMENT_IDS:
        entry = recorded_context.get(key)
        if not isinstance(entry, dict):
            continue
        items.append({"equipment_id": key, "display_name": str(entry.get("display_name", ""))[:64],
                      "usage": str(entry.get("usage_type", ""))[:USAGE_MAXIMUM],
                      "zone": str(entry.get("zone", ""))[:64],
                      "out_of_service": bool(entry.get("out_of_service", False))})
    return items


def describe(items):
    """Libellé lisible d'un contexte résolu, sans date : la date reste à l'affichage."""
    parts = []
    for item in items:
        name = item.get("display_name") or item["equipment_id"]
        usage = item.get("usage") or "usage non renseigné"
        where = item.get("scope_label") or item.get("zone") or ""
        parts.append(f"{name} · {usage}" + (f" · {where}" if where else ""))
    return " ; ".join(parts)


def resolve_equipment(at, links, recorded_context, *, recorded_at=None):
    """Contexte d'équipement d'une saisie **à sa date effective**, avec sa provenance.

    `links` doit être la liste des révisions courantes des affectations ; les révisions
    annulées sont écartées ici. La cascade est stricte et sans repli sur le catalogue
    d'aujourd'hui : une association inconnue reste inconnue, et l'interface le dit.
    """
    matched = [row for row in (links or []) if not row.get("cancelled") and covers(row, at)]
    if matched:
        items = [link_item(row) for row in sorted(matched, key=lambda row: row["equipment_id"])]
        return {"provenance": "link", "at": at, "items": items, "label": describe(items),
                "recorded_at": max(item["recorded_at"] for item in items if item["recorded_at"])
                if any(item["recorded_at"] for item in items) else None}
    items = snapshot_items(recorded_context)
    if items:
        return {"provenance": "snapshot", "at": at, "items": items, "label": describe(items),
                "recorded_at": recorded_at}
    return {"provenance": "unknown", "at": at, "items": [], "label": "", "recorded_at": None}


def validate_equipment_windows(rows):
    """Invariants exportables des affectations : révisions, portées et non-chevauchement."""
    revisions = {}
    current = {}
    for row in rows:
        row = dict(row)
        equipment_value(row.get("equipment_id"))
        usage_value(row.get("usage"))
        scope_target(row.get("scope"), row.get("space"), row.get("reservoir_id"))
        source_value(row.get("source"))
        if type(row.get("revision")) is not int or row["revision"] < 1:
            raise CultureError("Révision d'affectation invalide.")
        if row.get("cancelled") not in (0, 1):
            raise CultureError("Annulation d'affectation incohérente.")
        if row.get("start_precision") not in PRECISIONS:
            raise CultureError("Précision de début d'affectation invalide.")
        if (row.get("end_at") is None) != (row.get("end_sort_at") is None) or (
                row.get("end_at") is None) != (row.get("end_precision") is None):
            raise CultureError("Fin d'affectation incomplète.")
        if row.get("end_precision") is not None and row["end_precision"] not in PRECISIONS:
            raise CultureError("Précision de fin d'affectation invalide.")
        if row.get("end_sort_at") is not None and row["end_sort_at"] <= row["start_sort_at"]:
            raise CultureError("Une affectation se termine après son début.")
        revisions.setdefault(row["id"], []).append(row["revision"])
        if row["revision"] >= current.get(row["id"], {}).get("revision", 0):
            current[row["id"]] = row
    for values in revisions.values():
        if sorted(values) != list(range(1, len(values) + 1)):
            raise CultureError("Révisions d'affectation manquantes ou dupliquées.")
    by_equipment = {}
    for row in current.values():
        if row["cancelled"]:
            continue
        by_equipment.setdefault(row["equipment_id"], []).append(row)
    for windows in by_equipment.values():
        windows.sort(key=lambda row: (row["start_sort_at"], row["id"]))
        for previous, following in zip(windows, windows[1:]):
            if previous["end_sort_at"] is None or following["start_sort_at"] < previous["end_sort_at"]:
                raise CultureError("Deux affectations de ce même équipement se recouvrent : "
                                   "clore la précédente avant d'ouvrir la suivante.")
