# Roadmap consolidée

**Public** : pilotage et développement.
**Référence initiale** : commit `61ad3df`, audit et plans au 25 août 2026.
**Dernière mise à jour** : 26 août 2026, après l'arbitre thermique unifié.

La roadmap privilégie la réduction du risque physique, puis la reproductibilité et enfin la modernisation. Chaque chantier doit rester livrable, réversible et vérifiable indépendamment.

## Définitions de sortie

Un chantier n'est terminé que si :

- le code ou le matériel est réalisé ;
- la configuration et la documentation sont mises à jour ;
- le changement est déployé si son périmètre inclut la production ;
- les critères de preuve sont exécutés ;
- les risques associés sont requalifiés ;
- le rollback ou l'état sûr en cas d'échec est connu.

## Lot 1 — Socle documentaire et sécurité

**État : réalisé dans l'arbre de travail, à relire et versionner.**

- [x] README et avertissement de sécurité
- [x] index et sources de vérité
- [x] vue d'ensemble de l'architecture
- [x] modèle de sûreté
- [x] matrice GPIO et collisions
- [x] runbook d'incident initial
- [x] registre vivant des risques
- [x] roadmap consolidée
- [ ] Relecture par l'exploitant
- [ ] Vérification des commandes du runbook sur le Pi
- [ ] Décider le propriétaire et la fréquence de revue de chaque document

## Lot 2 — Exploitation reproductible

**Objectif : reconstruire et exploiter un Pi sans connaissance implicite.**

- [x] Capturer en lecture seule l'OS, Python, groupes, interfaces et services réels
- [x] Versionner l'unité `phyto.service` et le drop-in watchdog tels qu'observés
- [ ] Revoir et réduire les capacités ambiantes avant de qualifier ces artefacts
- [x] Documenter l'installation Raspberry Pi depuis une image vierge, à exercer
- [x] Documenter I²C, 1-Wire, NetworkManager, NTP et watchdog
- [x] Documenter le déploiement, les préconditions sudo et le rollback
- [x] Écrire la procédure initiale de sauvegarde et de restauration
- [x] Définir les contrôles quotidiens, hebdomadaires et mensuels
- [ ] Fixer et vérifier la rétention journald
- [ ] Exercer le runbook : service mort, config invalide, tâche malsaine, alarme chauffage
- [ ] Faire lire `healthy` au contrôle de déploiement : `/health/ready` est disponible, `scripts/deploy.sh` interroge encore `/status`

**Critère de sortie** : un second Pi peut être installé avec les artefacts du dépôt et des secrets fournis séparément ; sa configuration système est comparable à la référence.

## Lot 3 — Sécurité matérielle et brochage

**Objectif : garantir l'état sûr même avant Python et pendant les pannes brutales.**

- [ ] Valider le schéma électrique réel hors tension
- [ ] Installer les pulls externes adaptés aux deux polarités
- [ ] Installer thermostat ou fusible thermique en série
- [ ] Définir et installer l'interlock des vitesses moteur
- [ ] Migrer la vitesse 4 hors BCM 1
- [ ] Planifier la migration des vitesses hors BCM 7/8
- [ ] Créer le `PinRegistry` avec propriétaire, direction, polarité et niveau sûr
- [ ] Interdire doublons et GPIO réservés avant tout accès matériel
- [ ] Générer la configuration de boot depuis le registre validé
- [ ] Mesurer les GPIO depuis la mise sous tension jusqu'à READY
- [ ] Corriger ou remplacer les lignes dangereuses dans `notes`

**Critère de sortie** : les relais restent inactifs pendant boot, arrêt, reset et perte du processus selon une procédure mesurée ; plusieurs vitesses ne peuvent pas être alimentées simultanément.

## Lot 4 — Thermique unifié et configuration fiable

**Objectif : une décision cohérente et une source de configuration unique.**

### Arbitre thermique

*(Phase 2, commit `a04abbd` : implémenté, **déployé et vérifié sur le Pi** le 26 août 2026 —
[relevé](operations/climate-baseline-2026-08-26.md). Décision consignée dans
[ADR-0004](decisions/ADR-0004-unified-climate-arbiter.md).)*

- [x] Extraire une fonction pure — `components/climate_policy.decide()`, sans GPIO, disque ni horloge implicite
- [x] Garantir l'exclusion chauffage/extraction — travail unique `climate_control`
- [x] Définir une zone morte valide — garantie **par construction** et non par un validateur bloquant, qui aurait rendu le `param.json` déployé illisible
- [x] Définir la priorité humidité/froid avec un plancher absolu — `absolute_floor_temp`
- [x] Nommer deux budgets distincts — renouvellement et déshumidification, bornés et comptés en temps réellement écoulé
- [x] Ajouter une hystérésis à état — seuil de relâchement distinct et `min_dwell_seconds`
- [x] Persister quota hiver et phase cyclique — `utils/state_store.py`
- [x] Définir le comportement sur capteur absent, hors plage ou figé — repli nommé `REPLI_CAPTEUR`
- [x] Vérification en production : huit travaux sains, cohérence décision ↔ `pinctrl`, état persisté,
      rechargement à chaud sans coupure de sortie
- [ ] Essai sur plages limites avec le matériel réel : la serre est en chauffage désactivé et moteur
      manuel, donc ni les seuils de chauffe, ni les paliers de ventilation, ni les budgets hiver
      n'ont encore été exercés en conditions réelles

### Configuration

*(Refonte web : implémenté dans l'arbre de travail, non encore déployé.)*

- [ ] Créer un `ConfigStore` unique
- [x] Charger une copie candidate et la revalider intégralement
- [x] Activer `validate_assignment` sur tous les modèles
- [x] Ajouter les contraintes de bornes et les contraintes croisées température/vitesses
- [ ] Ajouter les contraintes GPIO (unicité, broches réservées)
- [ ] Définir migrations et sauvegarde `.bak`
- [ ] Retirer les lectures disque des chemins de contrôle
- [x] Distinguer champs à chaud et champs nécessitant redémarrage
- [x] Créer un `SensorController.reconfigure()` unique avec sérialisation et fermeture
- [ ] Sortir les secrets vers un environnement protégé
- [x] Masquer les secrets dans `/conf`
- [ ] Faire tourner les identifiants et décider du nettoyage de l'historique Git

**Critère de sortie** : aucune configuration invalide n'atteint le disque ou les boucles, toutes les préoccupations observent la même version, et chauffage/ventilation proviennent d'une décision unique testable.

## Lot 5 — Frontière I/O, maintenance et gouvernance

**Objectif : réduire les blocages, l'exposition LAN et la dérive future.**

### I/O et HTTP

*(Refonte web : implémenté dans l'arbre de travail, non encore déployé.)*

- [x] Migrer vers aiohttp
- [x] Ajouter timeouts, limites de body et en-têtes de sécurité
- [x] Confiner les fichiers statiques — liste blanche exacte de chemins
- [x] Valider `Host` et documenter le filtrage réseau
- [x] Séparer `/health/live` et `/health/ready`
- [x] Déplacer l'export Influx et les lectures capteurs hors event loop
- [ ] Sortir les commandes système (`nmcli`, `ping`, `timedatectl`, reboot) de l'event loop
- [ ] Ajouter disjoncteur et métrique d'ancienneté InfluxDB
- [ ] Ajouter reconnexion Wi-Fi supervisée
- [ ] Ajouter RTC et politique `time_synced`

### Projet et gouvernance

- [ ] Ajouter `LICENSE` AGPL-3.0
- [x] Ajouter `SECURITY.md` sans exposer de secret ni de topologie sensible
- [x] Ajouter `CHANGELOG.md`
- [x] Écrire les ADR initiaux
- [x] Écrire la checklist de changement sûr
- [x] Définir le processus de release et de retour arrière
- [ ] Verrouiller les dépendances compatibles Raspberry Pi
- [ ] Décider si Docker est supporté, expérimental ou retiré
- [x] Supprimer le code mort de la couche web (`api_handler.py`, `monitor.html`, `get_cyclic_period()` cassé)
- [ ] Supprimer le reste du code mort après vérification des usages
- [ ] Mettre en place des validations automatisées minimales et reproductibles
- [ ] Archiver les TODO remplacés après transfert de leurs informations

**Critère de sortie** : une panne I/O ne bloque pas la régulation, l'interface résiste aux requêtes hostiles du LAN, les releases sont reproductibles et les décisions structurelles sont traçables.

## Ordre et dépendances

```text
Lot 1 Documentation
  └─ Lot 2 Exploitation reproductible
       ├─ Lot 3 Matériel et GPIO
       └─ Lot 4 Thermique et configuration
            └─ Lot 5 I/O et gouvernance finale
```

Le travail documentaire du lot 5 peut commencer plus tôt, mais les références exhaustives de configuration et d'HTTP ne doivent être déclarées stables qu'après les refontes correspondantes.

## Prochaines actions immédiates

1. Relire et versionner le lot 1.
2. Vérifier le runbook sur le Pi sans déclencher d'action destructive.
3. Capturer l'unité systemd et ses drop-ins en masquant toute donnée sensible.
4. Clôturer ou documenter la rotation réelle des logs.
5. Préparer le schéma et la fenêtre d'intervention matérielle du lot 3.
6. Ouvrir une décision d'architecture pour l'arbitre thermique avant son implémentation.

## Relation avec les anciens plans

- `AUDIT-2026-08-25.md` reste la preuve historique détaillée.
- `tasks/audit_phase0_todo.md` et `tasks/audit_phase1_todo.md` restent les bilans des phases réalisées et reportées.
- `tasks/logging_refonte_plan.md` conserve le plan initial de logging.
- `tasks/todo.md` conserve des actions ponctuelles historiques.

Quand tous leurs éléments utiles auront été transférés et reliés à une preuve, ces fichiers pourront être marqués « remplacés par la roadmap et le registre des risques », sans supprimer l'historique.
