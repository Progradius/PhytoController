# ADR-0001 — Polarités GPIO et état sûr terminal

**Statut** : accepté. **Date** : 25 août 2026. **Commits** : `649eb20`, `61a5d7d`.

## Contexte

Les composants génériques sont actifs-BAS et le moteur actif-HAUT. `GPIO.cleanup()` remettait les broches en entrée et annulait les niveaux sûrs.

## Décision

- Génériques OFF = HIGH ; moteur OFF = LOW.
- L'arrêt maintient les broches comme sorties pilotées.
- `GPIO.cleanup()` est interdit.
- Toute séquence ON/attente/OFF utilise `Component.energized()`.

## Conséquences

L'arrêt contrôlé est déterministe. Les arrêts brutaux et la fenêtre de boot exigent toujours des protections matérielles. Toute refonte GPIO doit préserver les deux polarités.

## Réexamen

Possible seulement si des résistances externes et interlocks garantissent matériellement l'état sûr et si une vérification complète du boot à l'arrêt est fournie.
