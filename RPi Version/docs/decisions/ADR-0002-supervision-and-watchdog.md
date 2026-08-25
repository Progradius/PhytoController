# ADR-0002 — Supervision et watchdog conditionné à la santé

**Statut** : accepté. **Date** : 25 août 2026. **Commit** : `61a5d7d`, cadence ajustée dans `61ad3df`.

## Contexte

Des tâches asyncio pouvaient mourir tandis que le processus et HTTP restaient vivants. Un watchdog aveugle certifiait alors un contrôleur incomplet.

## Décision

- Chaque travail métier long est lancé par une fabrique sous `TaskSupervisor`.
- Une sortie reçoit un état sûr appliqué avant relance.
- Heartbeats et silence maximal détectent les blocages.
- Le watchdog tourne dans l'event loop et n'est caressé que si le superviseur est sain.
- systemd utilise 600 s, supérieur aux 300 s du superviseur ; caresse plafonnée à 30 s.

## Conséquences

Les pannes deviennent visibles et récupérables. Un blocage de l'event loop gèle aussi le superviseur, mais arrête la caresse et laisse systemd redémarrer. Les I/O bloquantes restent à supprimer.
