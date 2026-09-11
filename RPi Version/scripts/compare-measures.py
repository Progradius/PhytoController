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

Deux mesures ne se comparent que si elles suivent le **même protocole** :

* le **carnet** (`carnet` : `vide`, `rempli`, `externe`). `--carnet` choisit la passe
  comparée, `vide` par défaut : c'est le protocole des 36 visites de l'audit, prouvé par le
  rejeu de la baseline (`docs/images/remediation-web-mobile-pwa-2026-09-09/rejeu-baseline-8023123.md`).
  Une entrée sans clé `carnet` (audit, fichiers antérieurs à cette clé) n'en consigne
  aucun : elle est comparée telle quelle, et le rapport le dit ;
* la **fenêtre** (`viewport`) : `height` vaut `scrollHeight`, qui ne descend jamais sous la
  hauteur de la fenêtre. Deux fenêtres consignées et différentes rendent la ligne
  **non comparable**, ce qui compte comme un échec ; une fenêtre non consignée est signalée.

    scripts/compare-measures.py <avant.json> <après.json> [--tolerance 2] [--metric height] [--carnet vide]
    npm run measure:compare -- <avant.json> <après.json>
"""
import argparse
import json
import sys
from pathlib import Path

# Métriques comparables : toutes des entiers positifs issus du même relevé.
METRICS = ("height", "scrollWidth", "dom")
CARNETS = ("vide", "rempli", "externe")


def nominal(entry, carnet="vide"):
    """Vrai pour une entrée de page nominale en thème sombre, sur le carnet demandé.

    Une entrée sans clé `carnet` n'en consigne aucun : elle est retenue quel que soit le
    carnet demandé, faute de quoi le fichier de l'audit ne serait plus lisible.
    """
    if not isinstance(entry, dict) or "route" not in entry or "width" not in entry:
        return False
    if entry.get("skipped"):
        return False
    if entry.get("carnet", carnet) != carnet:
        return False
    return entry.get("state", "page") == "page" and entry.get("theme", "dark") == "dark"


def index(path, carnet="vide"):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} : une liste d'entrées de mesure est attendue.")
    table = {}
    for entry in payload:
        if not nominal(entry, carnet):
            continue
        key = (entry["route"], int(entry["width"]))
        # Une clé vue deux fois signale un fichier hétérogène : le dire plutôt que
        # d'écraser silencieusement la première mesure.
        if key in table:
            raise SystemExit(f"{path} : {key[0]} à {key[1]} px mesurée deux fois en état nominal.")
        table[key] = entry
    if not table:
        raise SystemExit(f"{path} : aucune entrée nominale en thème sombre sur le carnet « {carnet} ».")
    return table


def viewport_text(viewport):
    return f"{viewport['width']}×{viewport['height']}"


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
        # Deux fenêtres consignées et différentes : la hauteur de l'une ne dit rien de l'autre.
        if old.get("viewport") and new.get("viewport") and old["viewport"] != new["viewport"]:
            failures += 1
            rows.append((route, width, old.get(metric), new.get(metric), None,
                         f"NON COMPARABLE : fenêtres {viewport_text(old['viewport'])} "
                         f"et {viewport_text(new['viewport'])}"))
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


def protocol_notes(label, table, carnet):
    """Ce que le fichier consigne — ou non — de son protocole, pour le pied du rapport."""
    entries = list(table.values())
    without_carnet = sum(1 for entry in entries if "carnet" not in entry)
    without_viewport = sum(1 for entry in entries if not entry.get("viewport"))
    notes = []
    if without_carnet:
        notes.append(f"{label} : {without_carnet} entrée(s) sans carnet consigné, comparée(s) "
                     f"sans vérifier qu'elle(s) suive(nt) le carnet « {carnet} » demandé.")
    if without_viewport:
        notes.append(f"{label} : {without_viewport} entrée(s) sans fenêtre consignée, comparée(s) "
                     "sans vérifier la fenêtre.")
    return notes


def render(rows, tolerance, metric, notes=()):
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
    if notes:
        lines.append("")
        lines.extend(f"* {note}" for note in notes)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("before", type=Path, help="measures.json de référence (audit ou lot précédent)")
    parser.add_argument("after", type=Path, help="measures.json produit par npm run measure:ui")
    parser.add_argument("--tolerance", type=float, default=2.0, help="écart accepté en %% (défaut : 2)")
    parser.add_argument("--metric", choices=METRICS, default="height", help="métrique comparée")
    parser.add_argument("--carnet", choices=CARNETS, default="vide",
                        help="passe comparée (défaut : vide, le protocole de l'audit)")
    args = parser.parse_args(argv)

    before = index(args.before, args.carnet)
    after = index(args.after, args.carnet)
    rows, failures = compare(before, after, args.tolerance, args.metric)
    notes = protocol_notes("Avant", before, args.carnet) + protocol_notes("Après", after, args.carnet)
    # Sortie standard volontairement en Markdown : le tableau est collé tel quel dans le
    # rapport de lot, sans reformatage manuel.
    print(render(rows, args.tolerance, args.metric, notes))
    if failures:
        print(f"\n{failures} écart(s) au-delà de ±{args.tolerance:g} %.", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
