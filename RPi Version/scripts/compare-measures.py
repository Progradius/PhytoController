#!/usr/bin/env python3
"""Comparateur de mesures web (acceptation de la fiche R0.1).

Rejoue la comparaison « les hauteurs sont reproduites à ±2 % » entre deux fichiers
`measures.json` : celui de l'audit du 9 septembre 2026 et celui produit par
`npm run measure:ui`. La comparaison porte sur l'**état nominal** (`state` absent ou
`page`) en **thème sombre** (`theme` absent ou `dark`) — le fichier de l'audit ne porte
ni `state` ni `theme`, son absence vaut donc « page » et « dark ».

Le code de retour est non nul dès qu'un écart dépasse la tolérance, ou dès qu'une route
mesurée avant a disparu après : une page qui n'est plus mesurée n'est pas une page
conforme.

    scripts/compare-measures.py <avant.json> <après.json> [--tolerance 2] [--metric height]
    npm run measure:compare -- <avant.json> <après.json>
"""
import argparse
import json
import sys
from pathlib import Path

# Métriques comparables : toutes des entiers positifs issus du même relevé.
METRICS = ("height", "scrollWidth", "dom")


def nominal(entry):
    """Vrai pour une entrée de page nominale en thème sombre."""
    if not isinstance(entry, dict) or "route" not in entry or "width" not in entry:
        return False
    if entry.get("skipped"):
        return False
    return entry.get("state", "page") == "page" and entry.get("theme", "dark") == "dark"


def index(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} : une liste d'entrées de mesure est attendue.")
    table = {}
    for entry in payload:
        if not nominal(entry):
            continue
        key = (entry["route"], int(entry["width"]))
        # Une clé vue deux fois signale un fichier hétérogène : le dire plutôt que
        # d'écraser silencieusement la première mesure.
        if key in table:
            raise SystemExit(f"{path} : {key[0]} à {key[1]} px mesurée deux fois en état nominal.")
        table[key] = entry
    if not table:
        raise SystemExit(f"{path} : aucune entrée nominale en thème sombre.")
    return table


def compare(before, after, tolerance, metric):
    rows = []
    failures = 0
    for key in sorted(set(before) | set(after)):
        route, width = key
        old = before.get(key)
        new = after.get(key)
        if old is None:
            rows.append((route, width, None, new.get(metric), None, "nouvelle route"))
            continue
        if new is None:
            failures += 1
            rows.append((route, width, old.get(metric), None, None, "ABSENTE APRÈS"))
            continue
        previous = old.get(metric)
        current = new.get(metric)
        if not isinstance(previous, (int, float)) or not isinstance(current, (int, float)):
            failures += 1
            rows.append((route, width, previous, current, None, f"{metric} non mesuré"))
            continue
        if previous == 0:
            drift = 0.0 if current == 0 else float("inf")
        else:
            drift = (current - previous) / previous * 100
        over = abs(drift) > tolerance
        failures += 1 if over else 0
        rows.append((route, width, previous, current, drift, "HORS TOLÉRANCE" if over else "ok"))
    return rows, failures


def render(rows, tolerance, metric):
    lines = [
        f"| Route | Largeur | {metric} avant | {metric} après | Écart | Verdict |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for route, width, previous, current, drift, verdict in rows:
        drift_text = "—" if drift is None else f"{drift:+.2f} %"
        lines.append(
            f"| `{route}` | {width} | {previous if previous is not None else '—'} "
            f"| {current if current is not None else '—'} | {drift_text} | {verdict} |"
        )
    lines.append("")
    lines.append(f"Tolérance appliquée : ±{tolerance:g} % sur `{metric}`.")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before", type=Path, help="measures.json de référence (audit ou lot précédent)")
    parser.add_argument("after", type=Path, help="measures.json produit par npm run measure:ui")
    parser.add_argument("--tolerance", type=float, default=2.0, help="écart accepté en %% (défaut : 2)")
    parser.add_argument("--metric", choices=METRICS, default="height", help="métrique comparée")
    args = parser.parse_args(argv)

    rows, failures = compare(index(args.before), index(args.after), args.tolerance, args.metric)
    # Sortie standard volontairement en Markdown : le tableau est collé tel quel dans le
    # rapport de lot, sans reformatage manuel.
    print(render(rows, args.tolerance, args.metric))
    if failures:
        print(f"\n{failures} écart(s) au-delà de ±{args.tolerance:g} %.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
