# Changelog

Ce changelog commence avec la consolidation documentaire du 25 août 2026. L'historique antérieur reste disponible dans Git et dans `AUDIT-2026-08-25.md`.

Les mentions **code**, **déployé** et **vérifié matériellement** sont distinctes.

## Non publié

### Documentation

- Porte d'entrée, architecture, modèle de sûreté et matrice GPIO.
- Runbook d'incident, monitoring, installation, systemd, déploiement et sauvegarde.
- Références configuration, environnement, HTTP, `/status`, logs, capteurs et InfluxDB.
- Registre vivant des risques, roadmap, checklists, releases et ADR initiaux.
- Capture en lecture seule de la production et versionnement des artefacts systemd observés.

## 2026-08-25 — Supervision et watchdog

**Code `61a5d7d` ; déployé et observé sur le Pi.**

- Superviseur de tâches, heartbeats, back-off et états sûrs.
- `Component.energized()` pour les sorties cycliques.
- Watchdog conditionné à la santé, notification systemd et statut enrichi.
- Huit tâches saines, aucun restart/stall lors du relevé live.

Cadence de caresse plafonnée à 30 secondes dans `61ad3df`, présent dans le dépôt local mais pas encore dans le commit de production relevé (`61a5d7d`).

## 2026-08-25 — Garde-fous immédiats

**Code `649eb20` ; déployé et vérifié matériellement.**

- Verrou d'instance avant tout accès GPIO.
- Écritures atomiques de configuration et statistiques.
- État sûr terminal sans `GPIO.cleanup()`.
- Repli chauffage et alarme persistante.
- Actions `/monitor` déplacées de GET vers POST avec contrôle Origin partiel.

## 2026-08-25 — Journalisation

**Code `fb26cd2` et correctifs suivants ; déployé.**

- Façade unique, niveaux configurables, rotation quotidienne et déduplication.
- Console SSE du processus courant, sans second `main.py`.
- Partage du contrôleur de capteurs au boot et logs des seuls écarts de configuration.
