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
  hauteur de la fenêtre. Deux fenêtres différentes rendent la ligne **non comparable**, et une
  fenêtre connue d'un seul côté aussi : la supposer égale à l'autre est l'erreur même qui a fait
  comparer 320 × 568 à 320 × 844. `--fenetres-audit` suppose explicitement les fenêtres de
  l'audit pour les entrées qui ne consignent pas la leur — c'est ainsi que le fichier de
  l'audit se compare encore, l'hypothèse étant écrite dans le rapport.

    scripts/compare-measures.py <avant.json> <après.json> [--tolerance 2] [--metric height] [--carnet vide] [--fenetres-audit]
    npm run measure:compare -- <avant.json> <après.json>
"""
import argparse
import json
import sys
from pathlib import Path

# Métriques comparables : toutes des entiers positifs issus du même relevé.
METRICS = ("height", "scrollWidth", "dom")
CARNETS = ("vide", "rempli", "externe")
# Fenêtres du protocole de l'audit (`docs/development/audit-web-mobile-pwa-2026-09-09.md`).
# Elles ne sont **supposées** que sur demande explicite (`--fenetres-audit`), pour les entrées
# qui ne consignent pas la leur : c'est une hypothèse, donc elle se déclare.
AUDIT_VIEWPORTS = {320: {"width": 320, "height": 844}, 390: {"width": 390, "height": 844},
                   1440: {"width": 1440, "height": 900}}


def nominal(entry, carnet="vide"):
    """Vrai pour une entrée de page nominale en thème sombre, sur le carnet demandé.

    Une entrée sans clé `carnet` ne consigne pas son protocole. Elle n'est retenue que pour
    `--carnet vide` : c'est le protocole de l'audit et des fichiers antérieurs à cette clé,
    prouvé par le rejeu de la baseline. La retenir pour « rempli » ferait passer un écart de
    protocole pour une régression de page — exactement ce que la règle des fenêtres refuse.
    """
    if not isinstance(entry, dict) or "route" not in entry or "width" not in entry:
        return False
    if entry.get("skipped"):
        return False
    if entry.get("carnet", "vide") != carnet:
        return False
    return entry.get("state", "page") == "page" and entry.get("theme", "dark") == "dark"


def index(path, carnet="vide", fenetres_audit=False):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"{path} : une liste d'entrées de mesure est attendue.")
    table = {}
    sans_carnet = 0
    for entry in payload:
        if isinstance(entry, dict) and "carnet" not in entry and not entry.get("skipped"):
            sans_carnet += 1
        if not nominal(entry, carnet):
            continue
        key = (entry["route"], int(entry["width"]))
        # Une clé vue deux fois signale un fichier hétérogène : le dire plutôt que
        # d'écraser silencieusement la première mesure.
        if key in table:
            raise SystemExit(f"{path} : {key[0]} à {key[1]} px mesurée deux fois en état nominal.")
        # Fenêtre supposée, et **dite** : sans elle, un fichier au format de l'audit ne se
        # compare plus à rien, puisqu'une seule fenêtre connue rend la ligne non comparable.
        if fenetres_audit and not entry.get("viewport") and int(entry["width"]) in AUDIT_VIEWPORTS:
            entry = {**entry, "viewport": AUDIT_VIEWPORTS[int(entry["width"])], "viewport_suppose": True}
        table[key] = entry
    if not table:
        if sans_carnet and carnet != "vide":
            raise SystemExit(
                f"{path} : {sans_carnet} entrée(s) ne consignent pas leur carnet ; elles ne sont "
                f"comparables qu'avec « --carnet vide », le protocole de l'audit. Non comparable "
                f"au carnet « {carnet} » demandé.")
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
        # Fenêtres : `height` vaut `scrollHeight`, qui ne descend jamais sous la hauteur de la
        # fenêtre. Deux fenêtres différentes ne se comparent pas — et **une seule fenêtre
        # connue non plus** : ignorer l'inconnue reviendrait à supposer qu'elle vaut l'autre,
        # ce qui est précisément l'erreur qui a fait comparer 320 × 568 à 320 × 844.
        if bool(old.get("viewport")) != bool(new.get("viewport")):
            failures += 1
            connue = "avant" if old.get("viewport") else "après"
            rows.append((route, width, old.get(metric), new.get(metric), None,
                         f"NON COMPARABLE : fenêtre consignée seulement {connue}"))
            continue
        if old.get("viewport") and old["viewport"] != new["viewport"]:
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
    supposed = sum(1 for entry in entries if entry.get("viewport_suppose"))
    without_viewport = sum(1 for entry in entries if not entry.get("viewport"))
    notes = []
    if without_carnet:
        notes.append(f"{label} : {without_carnet} entrée(s) sans carnet consigné, tenue(s) pour "
                     f"le carnet « {carnet} » (protocole de l'audit).")
    if supposed:
        notes.append(f"{label} : {supposed} entrée(s) sans fenêtre consignée, **supposée(s)** aux "
                     "fenêtres de l'audit (320 × 844, 390 × 844, 1440 × 900) par `--fenetres-audit`.")
    if without_viewport:
        notes.append(f"{label} : {without_viewport} entrée(s) sans fenêtre consignée : chaque ligne "
                     "où l'autre mesure consigne la sienne est déclarée non comparable.")
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
    parser.add_argument("--fenetres-audit", action="store_true",
                        help="suppose les fenêtres de l'audit (320 × 844, 390 × 844, 1440 × 900) "
                             "pour les entrées qui ne consignent pas la leur ; l'hypothèse est "
                             "écrite dans le rapport")
    args = parser.parse_args(argv)

    before = index(args.before, args.carnet, args.fenetres_audit)
    after = index(args.after, args.carnet, args.fenetres_audit)
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
