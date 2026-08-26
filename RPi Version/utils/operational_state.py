"""Registre d'observabilité des décisions des boucles métier.

Ce registre n'est jamais lu par la régulation pour décider. Il ne contient que
les consignes et leur explication ; l'état GPIO réel est relu par le lecteur
HTTP afin de ne jamais servir une photographie matérielle périmée.
"""

from __future__ import annotations

from time import monotonic

_entries: dict[str, dict] = {}


def publish(equipment_id: str, *, stale_after: float, **values) -> None:
    transition = values.get("next_transition")
    if isinstance(transition, dict) and transition.get("in_seconds") is not None:
        transition = dict(transition)
        try:
            transition["deadline_mono"] = monotonic() + max(0.0, float(transition["in_seconds"]))
        except (TypeError, ValueError):
            pass
        values["next_transition"] = transition
    _entries[equipment_id] = {
        **values,
        "published_mono": monotonic(),
        "stale_after_seconds": float(stale_after),
    }


def snapshot() -> dict[str, dict]:
    now = monotonic()
    result = {}
    for equipment_id, source in _entries.items():
        item = dict(source)
        age = max(0.0, now - item.pop("published_mono"))
        stale_after = item.get("stale_after_seconds", 0.0)
        item["age_seconds"] = round(age, 1)
        item["stale"] = age > stale_after
        item["since_seconds"] = (
            round(max(0.0, now - float(item["since_mono"])), 1)
            if item.get("since_mono") is not None else None
        )
        item.pop("since_mono", None)
        transition = item.get("next_transition")
        if isinstance(transition, dict) and transition.get("deadline_mono") is not None:
            transition = dict(transition)
            transition["in_seconds"] = round(
                max(0.0, float(transition.pop("deadline_mono")) - now), 1
            )
            item["next_transition"] = transition
        result[equipment_id] = item
    return result
