"""Validation pure des réponses utilisées pour qualifier un déploiement."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def validation_error(expected: str, live: dict, ready: dict, state: dict) -> str | None:
    critical_count = state.get("alarms", {}).get("critical_count")
    checks = (
        (live.get("live") is True, "/health/live ne confirme pas live=true"),
        (ready.get("ready") is True, "/health/ready ne confirme pas ready=true"),
        (
            state.get("health", {}).get("control_healthy") is True,
            "control_healthy n'est pas vrai",
        ),
        (
            live.get("version") == expected,
            f"version active {live.get('version')!r}, attendue {expected}",
        ),
        (
            state.get("version") == expected,
            f"version d'état {state.get('version')!r}, attendue {expected}",
        ),
        (
            type(critical_count) is int and critical_count == 0,
            f"{critical_count!r} alarme(s) critique(s)",
        ),
    )
    return next((message for valid, message in checks if not valid), None)


def _load(path: str) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError("la réponse JSON n'est pas un objet")
    return payload


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        print("usage : deployment_health.py VERSION LIVE READY STATE")
        return 2
    try:
        error = validation_error(argv[1], _load(argv[2]), _load(argv[3]), _load(argv[4]))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"réponse de santé illisible ({exc.__class__.__name__})")
        return 1
    if error:
        print(error)
        return 1
    print("santé complète confirmée")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
