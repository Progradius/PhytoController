# Documentation de PhytoController

**Public** : exploitation, maintenance, développement et audit.
**Portée** : arborescence `RPi Version/`.
**Référence initiale** : commit `61ad3df`, 25 août 2026.
**Dernière vérification documentaire** : 25 août 2026, après la refonte de l'interface web.

**Écart entre le dépôt et la production, au 26 août 2026 :**

| Chantier | Code | Déployé sur le Pi |
|---|---|---|
| Refonte web et acquisition capteurs | `ad39de2` | **Oui**, vérifié — [relevé](operations/web-baseline-2026-08-25.md) |
| Arbitre thermique unifié (phase 2) | `e93644a` | **Non** — vérifié hors matériel seulement |

Le Pi exécute donc encore le chauffage et la ventilation en deux boucles séparées. Ne pas lire la
documentation de `climate_control` comme une description de la production tant que ce déploiement
n'est pas consigné.

Cette documentation distingue systématiquement quatre niveaux de preuve :

| Statut | Signification |
|---|---|
| **Implémenté** | Présent dans le code versionné cité |
| **Déployé** | Installé sur le Raspberry Pi de production à une date connue |
| **Vérifié matériellement** | Observé sur le Pi ou sur les GPIO réels selon une procédure documentée |
| **Ouvert / reporté** | Non résolu, même si une solution est proposée |

Une fonction implémentée n'est pas automatiquement déployée ; une fonction déployée n'est pas automatiquement une garantie physique.

## Lire selon le besoin

### Comprendre le système

- [Vue d'ensemble de l'architecture](architecture/overview.md)
- [Modèle de sûreté](architecture/safety-model.md)
- [Audit historique du 25 août 2026](../AUDIT-2026-08-25.md)

### Intervenir sur le matériel

- [Matrice GPIO, polarités et collisions](hardware/gpio-matrix.md)
- [Modèle de sûreté](architecture/safety-model.md)
- [Runbook d'incident](operations/incident-runbook.md)

### Exploiter et diagnostiquer

- [Runbook d'incident](operations/incident-runbook.md)
- [Installation Raspberry Pi](operations/install-raspberry-pi.md)
- [systemd et watchdog](operations/systemd.md)
- [Baseline de production du 25 août 2026](operations/production-baseline-2026-08-25.md)
- [Baseline web du 25 août 2026](operations/web-baseline-2026-08-25.md)
- [Déploiement et rollback](operations/deployment-and-rollback.md)
- [Monitoring](operations/monitoring.md)
- [Sauvegarde et restauration](operations/backup-and-restore.md)
- [Registre vivant des risques](risk-register.md)
- [Roadmap consolidée](roadmap.md)

### Faire évoluer le projet

- [AGENTS.md](../AGENTS.md), miroir exact de [CLAUDE.md](../CLAUDE.md)
- [Référence de configuration](reference/configuration.md)
- [Interface HTTP](reference/http-interface.md) et [schémas d'état JSON](reference/status-schema.md)
- [Checklist de changement sûr](development/safe-change-checklist.md)
- [Décisions d'architecture](decisions/README.md)
- [Registre vivant des risques](risk-register.md)
- [Roadmap consolidée](roadmap.md)
- plans historiques dans [`tasks/`](../tasks/)

## Sources de vérité

| Sujet | Source de vérité actuelle |
|---|---|
| Modèle de configuration | `param/config.py` |
| Configuration vivante | `param/param.json` sur le Pi ; contient des secrets |
| Séquence de boot et d'arrêt | `main.py` |
| Orchestration | `controllers/PuppetMaster.py` |
| Supervision | `utils/supervisor.py` |
| Watchdog | `utils/watchdog.py` et configuration systemd installée |
| Polarité des sorties | `model/Component.py` et `model/Motor.py` |
| Routes HTTP et schémas d'état | `network/web/server.py` |
| Catalogue des mesures capteurs | `controllers/sensor_catalog.py` |
| Politique thermique (chauffage et ventilation) | `components/climate_policy.py` |
| État de régulation reporté d'un démarrage à l'autre | `utils/state_store.py` et `param/runtime_state.json` sur le Pi |
| Déploiement | `scripts/deploy.sh` |
| Risques actuels | `docs/risk-register.md` |
| Travaux ordonnés | `docs/roadmap.md` |
| Preuves historiques | `AUDIT-2026-08-25.md` et bilans `tasks/audit_*` |
| Unité systemd observée | `deploy/phyto.service` et son drop-in |

Le code reste prioritaire si un document vivant diverge. Une telle divergence est un défaut documentaire à corriger dans le même changement que le comportement concerné.

## Documents historiques

`AUDIT-2026-08-25.md` et les fichiers `tasks/*.md` conservent le raisonnement, les preuves et les plans ayant conduit aux correctifs. Ils ne décrivent pas tous l'état courant. Ils doivent rester consultables, mais les décisions opérationnelles présentes doivent être prises à partir du registre des risques, de la roadmap et du code actuel.

## Règles de maintenance documentaire

1. Une modification de comportement met à jour la documentation concernée dans le même changement.
2. Toute procédure indique si elle a été seulement relue ou réellement exécutée sur le Pi.
3. Toute valeur de configuration utilisée comme exemple est fictive et non sensible.
4. Les états utilisent les termes « implémenté », « déployé », « vérifié matériellement », « ouvert », « reporté » ou « remplacé ».
5. Les audits datés restent historiques ; leur résultat courant est reporté dans `risk-register.md`.
6. `AGENTS.md` et `CLAUDE.md` restent strictement identiques.
7. Une commande destructrice précise ses préconditions, sa portée et la procédure de récupération.
