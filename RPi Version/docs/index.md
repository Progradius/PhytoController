# Documentation de PhytoController

**Public** : exploitation, maintenance, développement et audit.
**Portée** : arborescence `RPi Version/`.
**Référence initiale** : commit `61ad3df`, 25 août 2026.
**État au 11 septembre 2026** : archivage des relevés et plans clos (`docs/archive/`,
`tasks/archive/`), incident du 8 septembre traité par la sortie des données vivantes hors du dépôt,
remédiation web/mobile/PWA livrée dans le dépôt, qualifications opérateur (R4) ouvertes.

**Écart entre le dépôt et la production, au 11 septembre 2026.** Une ligne n'affirme un déploiement
que si un relevé le prouve ; sinon elle dit « à relever sur le Pi ».

| Chantier | Code | Déployé sur le Pi |
|---|---|---|
| Refonte web et acquisition capteurs | `ad39de2` | **Oui**, vérifié le 25 août — [relevé](archive/operations/web-baseline-2026-08-25.md) |
| Arbitre thermique unifié (phase 2) | `a04abbd` | **Oui**, vérifié le 26 août — [relevé](archive/operations/climate-baseline-2026-08-26.md) |
| Magasin de configuration (phase 3) | `f840a91` | **Oui**, ancêtre de `e91b021` déployé le 26 août (vérifié par `git merge-base --is-ancestor`) |
| Correctifs thermiques et jalon 1 de l'expérience opérateur | `e91b021` | **Oui**, observation 48 h acceptée — [relevé](archive/operations/jalon1-watchdog-observation-2026-08-28.md) |
| Alarmes/historique, PWA, santé de déploiement et qualité capteurs | `b26d2b1` | **Oui**, mode `observe` ; HTTPS `:443` actif depuis le 28 août — [relevé](archive/operations/jalon2-observation-operateur-2026-08-30.md), [activation TLS](archive/operations/pwa-tls-activation-2026-08-28.md) |
| Correctif de la politique de figement des capteurs | `985e42d` | **Oui**, déployé le 30 août ; observation corrective 48 h acceptée — [relevé](archive/operations/jalon2-correctif-figement-observation-2026-09-01.md) |
| Observabilité des seuils effectifs de figement | `2ecefb1` (code `1e807b8`) | **Oui**, déployée le 1er septembre à 19:47 UTC |
| Jalon 4 : forçages, console, redémarrage | `a058be3`, `865b789`, `fa63006` | **Oui**, déployés un par un le 2 septembre — [relevé](archive/operations/jalon4-deploiement-2026-09-02.md) |
| Conduite, historique, mobile et PWA du 3 septembre | `47784dc` | **Oui** : branche servie le 8 septembre selon la [migration des données vivantes](operations/migration-donnees-vivantes.md) ; pas de relevé de qualification |
| Carnet de cultures (schémas 1 à 4, lots UI 1 à 4, photos) | `3ac74e5` … `1b31d82` | **En service au plus tard le 10 septembre** (`/cultures` en 200 à la sortie de migration) ; commit exact **à relever sur le Pi** |
| Données vivantes hors du dépôt (`PHYTO_DATA_DIR`) | `fd632bf` | **Oui**, migration exécutée le 10 septembre — [procédure et preuve](operations/migration-donnees-vivantes.md) |
| Remédiation web, mobile et PWA | `6f39986` … `08a4815`, `e29bf96` | **À relever sur le Pi** : aucun relevé de déploiement consigné |

Le Pi exécute le chauffage et la ventilation sous un arbitre unique, le lot opérateur, la PWA et la
qualité capteurs en mode `observe` (non armée). Les observations de 48 h des jalons 1 et 2 sont closes
et archivées. Depuis le 10 septembre, toutes les données écrites à l'exécution vivent sous
`~/phyto-data`, hors du répertoire de travail Git : un checkout ne peut plus écraser la configuration.

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
- [Décisions d'architecture](decisions/README.md)

### Intervenir sur le matériel

- [Matrice GPIO, polarités et collisions](hardware/gpio-matrix.md)
- [Validation matérielle des sorties](development/hardware-validation.md)
- [Modèle de sûreté](architecture/safety-model.md)
- [Runbook d'incident](operations/incident-runbook.md)

### Exploiter et diagnostiquer

- [Runbook d'incident](operations/incident-runbook.md)
- [Installation Raspberry Pi](operations/install-raspberry-pi.md)
- [systemd et watchdog](operations/systemd.md)
- [Déploiement, rollback et processus de release](operations/deployment-and-rollback.md)
- [Migration des données vivantes hors du dépôt (`PHYTO_DATA_DIR`)](operations/migration-donnees-vivantes.md)
- [Sauvegarde et restauration](operations/backup-and-restore.md)
- [Monitoring](operations/monitoring.md)
- [PWA locale et autorité TLS privée](operations/pwa-local-tls.md)
- [Carnet de cultures : mères, lots, stades, solutions, cycles, journal et sauvegarde](operations/cultures.md)
- [Registre vivant des risques](risk-register.md)
- [Roadmap consolidée](roadmap.md)

### Référence

- [Configuration](reference/configuration.md)
- [Variables d'environnement](reference/environment-variables.md)
- [Interface HTTP](reference/http-interface.md) et [schémas d'état JSON](reference/status-schema.md)
- [Journalisation, capteurs et InfluxDB](reference/logging-and-sensors.md)
- [Contrat API du carnet de cultures](reference/cultures-api.md)

### Faire évoluer le projet

- [AGENTS.md](../AGENTS.md), miroir exact de [CLAUDE.md](../CLAUDE.md)
- [Contribuer : validation, style, mesures web et composants partagés](development/contributing.md)
- [Cadre agents, chaîne de preuves et design system : état des lieux et plan proposé](development/harness-et-design-system-reference.md) — référence du 11 septembre 2026, implémentation future
- [Checklist de changement sûr](development/safe-change-checklist.md)
- [Stratégie de vérification](development/verification.md)
- [Validation matérielle des sorties](development/hardware-validation.md)
- [Audit web, mobile et PWA du 9 septembre 2026](development/audit-web-mobile-pwa-2026-09-09.md)
- [Plan de remédiation web, mobile et PWA, état d'avancement](development/remediation-web-mobile-pwa-2026-09-09.md)
- [Qualification mobile et PWA sur appareils réels (R4.1)](development/qualification-mobile-pwa.md)
- [Baseline de performance web du 10 septembre 2026 (R4.2)](development/web-perf-baseline-2026-09-10.md)
- [Protocole de validation produit (R4.3)](development/validation-produit-protocole.md)
- [Suivi des cases ouvertes](../tasks/todo.md) et [leçons](../tasks/lessons.md)
- [Plan de résilience Wi-Fi (R-NET-01)](../tasks/wifi_resilience_plan.md) et
  [plan de dette technique](../tasks/plan_dette_technique.md)

## Archives

Documents clos, conservés comme preuves et **plus mis à jour** ; chacun porte une ligne d'archive en
tête. Les décisions courantes se prennent à partir du registre des risques, de la roadmap et du code.

- [`archive/`](archive/) : [audit historique du 25 août 2026](archive/AUDIT-2026-08-25.md) ;
- [`archive/operations/`](archive/operations/) : baselines de production et web du 25 août, relevé de
  l'arbitre thermique du 26 août, activation TLS du 28 août, clôtures d'observation des 28 et
  30 août et du 1er septembre, déploiement du jalon 4 du 2 septembre,
  [procédures d'observation des jalons 1 et 2](archive/operations/procedures-observation-jalons-1-2.md) ;
- [`archive/development/`](archive/development/) : audit UI/UX du carnet du 8 septembre, bilans des
  lots UI 1 à 4, plans de remédiation des lots 2-3 et 4, passe « photos », bilan du lot F ;
- [`archive/images/`](archive/images/) : captures et mesures de ces bilans ;
- [`../tasks/archive/`](../tasks/archive/) : bilans des phases 0 à 3 de l'audit, plan d'expérience
  opérateur, plans du carnet de cultures et
  [sections closes de `tasks/todo.md`](../tasks/archive/todo-sections-closes-2026-09-11.md).

Supprimés le 11 septembre 2026, récupérables dans l'historique Git : le fichier racine `notes`
(bloc `gpio=` dangereux), `tasks/logging_refonte_plan.md`, `scripts/observe-jalon1-watchdog.sh`,
`docs/development/release-process.md` (fusionné dans le déploiement) et des captures non référencées.

## Sources de vérité

| Sujet | Source de vérité actuelle |
|---|---|
| Modèle de configuration | `param/config.py` |
| Configuration vivante | `param.json` dans le répertoire des données vivantes (`PHYTO_DATA_DIR`, `~/phyto-data` sur le Pi) ; contient des secrets |
| Emplacement des données écrites à l'exécution | `utils/runtime_paths.py` et `deploy/phyto.service` |
| Séquence de boot et d'arrêt | `main.py` |
| Orchestration | `controllers/PuppetMaster.py` |
| Supervision | `utils/supervisor.py` |
| Watchdog | `utils/watchdog.py` et configuration systemd installée |
| Polarité des sorties | `model/Component.py` et `model/Motor.py` |
| Routes HTTP et schémas d'état | `network/web/server.py` |
| Carnet de cultures (schéma SQLite 4) | `utils/culture_store.py` et ses mixins ; `cultures.sqlite3` dans le répertoire des données vivantes |
| Catalogue des mesures capteurs | `controllers/sensor_catalog.py` |
| Politique thermique (chauffage et ventilation) | `components/climate_policy.py` |
| État de régulation reporté d'un démarrage à l'autre | `utils/state_store.py` et `runtime_state.json` dans le répertoire des données vivantes |
| Déploiement | `scripts/deploy.sh` |
| Risques actuels | `docs/risk-register.md` |
| Travaux ordonnés | `docs/roadmap.md` et, pour le détail des cases ouvertes, `tasks/todo.md` |
| Preuves historiques | `docs/archive/` et `tasks/archive/` |
| Unité systemd observée | `deploy/phyto.service` et ses drop-ins |

Le code reste prioritaire si un document vivant diverge. Une telle divergence est un défaut documentaire à corriger dans le même changement que le comportement concerné.

## Règles de maintenance documentaire

1. Une modification de comportement met à jour la documentation concernée dans le même changement.
2. Toute procédure indique si elle a été seulement relue ou réellement exécutée sur le Pi.
3. Toute valeur de configuration utilisée comme exemple est fictive et non sensible.
4. Les états utilisent les termes « implémenté », « déployé », « vérifié matériellement », « ouvert », « reporté » ou « remplacé ».
5. Les audits datés restent historiques ; leur résultat courant est reporté dans `risk-register.md`.
6. `AGENTS.md` et `CLAUDE.md` restent strictement identiques.
7. Une commande destructrice précise ses préconditions, sa portée et la procédure de récupération.
8. Un document clos part dans `docs/archive/` ou `tasks/archive/` avec une ligne d'archive en tête, et
   ses liens entrants sont mis à jour dans le même changement.
