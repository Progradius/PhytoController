# Contribuer

## Avant toute modification

1. Lire `AGENTS.md` et le document du domaine concerné.
2. Vérifier `git status` et préserver les changements existants.
3. Identifier les risques liés dans `docs/risk-register.md`.
4. Définir l'état sûr, le rollback et la preuve attendue.
5. Ne jamais lire ou publier les valeurs sensibles de `param/param.json`.

## Style

- Code, commentaires, messages et logs en français.
- `utils.pretty_console` uniquement, jamais de `print` applicatif.
- Transitions à INFO, ticks à DEBUG, échecs répétés via `StateLogger`.
- Une tâche supervisée reçoit une fabrique, un état sûr si elle pilote une sortie et des heartbeats.
- Une attente avec sortie ON utilise `Component.energized()`.
- Les temps de sécurité utilisent `time.monotonic()`.
- Une lecture capteur peut renvoyer `None`.

## Documentation liée

Mettre à jour dans le même changement :

- référence si une interface ou configuration change ;
- runbook si l'exploitation change ;
- matrice GPIO et modèle de sûreté si le matériel change ;
- ADR si une décision structurelle change ;
- registre des risques et roadmap ;
- changelog pour un comportement livré.

`AGENTS.md` et `CLAUDE.md` sont des miroirs exacts : toute modification doit être identique et `diff -u CLAUDE.md AGENTS.md` doit rester vide.

## Périmètre

Cette arborescence est le port Raspberry Pi. Ne pas reporter automatiquement les changements dans la version ESP32. Le code mort apparent doit être confirmé comme non importé avant suppression.
