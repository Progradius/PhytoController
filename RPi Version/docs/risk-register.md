# Registre vivant des risques

**Public** : pilotage, exploitation, développement et audit.
**Référence initiale** : audit du 25 août 2026, recalé sur le commit `61ad3df`.
**Dernière mise à jour** : 25 août 2026, après la refonte de l'interface web.

Les réductions apportées par la refonte web sont **implémentées, déployées et vérifiées** sur le
Pi le 25 août 2026 (commit `ad39de2`, service démarré à 23:36 CEST). Preuve :
[Baseline web du 25 août 2026](operations/web-baseline-2026-08-25.md). Elles restent en
« réduites, à surveiller » : chacune conserve une limite résiduelle explicite.

Ce document décrit l'état courant. L'audit historique conserve les preuves détaillées et les identifiants d'origine. Un risque n'est fermé que lorsque la correction, le déploiement et la preuve requise sont tous consignés.

## Échelle

- **Critique** : risque de dommage physique important, secret directement exposé ou contrôle essentiel contournable.
- **Élevé** : panne prolongée, récupération incertaine, privilège ou indisponibilité significative.
- **Moyen** : dette augmentant la probabilité d'erreur ou compliquant l'exploitation.

## Risques ouverts

| ID | Sév. | Risque et impact | État actuel | Prochaine action | Preuve de clôture |
|---|---|---|---|---|---|
| R-SAFE-01 | Critique | Fenêtre de boot sans état sûr garanti | Les niveaux sont sûrs après lancement Python seulement ; anciennes lignes `gpio=` incorrectes | PinRegistry, génération correcte du boot et pulls externes | Mesures des GPIO de la mise sous tension à READY, charges déconnectées puis test contrôlé |
| R-SAFE-02 | Critique | GPIO moteur 1/7/8 réservés ou défavorables, plusieurs relais possibles au boot | Non corrigé ; vitesse 4 sur BCM 1 | Migrer les quatre vitesses vers GPIO adaptés et ajouter pull-down 4,7 kΩ | Schéma, configuration, `pinctrl` et essai moteur par vitesse |
| R-SAFE-03 | Critique | Absence de protection thermique matérielle indépendante | Garde-fous logiciels présents uniquement | Thermostat/fusible thermique en série | Schéma électrique, référence matériel et essai de coupure |
| R-SAFE-06 | Élevé | Plusieurs relais moteur actifs sont signalés mais pas coupés | `get_motor_speed()` renvoie 0 sans agir | Coupure immédiate, verrouillage dégradé et interlock | Injection d'état multi-HIGH et vérification all-OFF |
| R-CONF-02 | Critique | Secrets Wi-Fi/Influx versionnés | Toujours en clair dans `param.json` suivi par git ; **plus affichés** par l'IHM depuis la refonte web | Variables/fichier d'environnement, rotation, nettoyage historique décidé | Scan Git, UI et logs sans secret ; nouveaux identifiants actifs |
| R-WEB-02 | Élevé | IHM sans authentification | Choix LAN-only assumé. `Host` désormais validé (DNS rebinding fermé), CSRF et `Origin` sur toute méthode mutante ; **aucune authentification** | Documenter le filtrage réseau, réévaluer l'auth ou un reverse-proxy TLS sur 127.0.0.1 | Règles réseau vérifiées ; décision d'auth consignée |
| R-ASYNC-01 | Moyen | I/O bloquantes dans l'event loop | Capteurs sortis sur un exécuteur dédié à un fil, Influx passé en aiohttp avec délai de garde de 4 s. **Restent bloquants** : `nmcli`/`ping`/`timedatectl` du boot et les commandes système | Sortir les commandes système, borner leurs délais | Mesure de latence event loop sous panne I/O |
| R-TIME-01 | Élevé | Heure fausse au boot hors réseau | NTP tenté, pas de RTC ni garde `time_synced` | RTC, vérification NTP et politique dégradée | Reboot hors réseau sans commutation à contretemps |
| R-NET-01 | Élevé | Pas de reconnexion Wi-Fi supervisée | Tentative au boot seulement | Tâche réseau supervisée | Coupure/restauration AP avec reconnexion automatique |
| R-OPS-01 | Élevé | Unité systemd et drop-ins non reproductibles | Capturés le 25/08/2026 et recopiés sous `deploy/`, mais installation vierge non exercée et capacités larges | Revoir capacités puis exercer l'installation | Reconstruction d'un Pi avec diff nul par rapport à la référence |
| R-OPS-02 | Élevé | Sonde de déploiement ne valide pas `healthy` | `curl -f /status` seulement, alors que `/health/ready` renvoie désormais 503 sur défaut | Basculer `scripts/deploy.sh` sur `/health/ready` | Injection d'une tâche malsaine provoquant rollback/refus |
| R-HW-01 | Élevé | Collisions GPIO possibles dans la configuration | BCM 27 et 22 ont plusieurs rôles déclarés | PinRegistry et validation d'unicité | Config conflictuelle refusée avant accès GPIO |
| R-HW-02 | Élevé | DS18B20/1-Wire et autres capteurs peuvent être déclarés sans câblage fiable | DS18 désactivé dans la config versionnée actuelle | Inventaire matériel et procédure de mise en service | Mesures stables ou capteur explicitement absent |
| R-MAINT-01 | Moyen | Dépendances non verrouillées et environnement non reproductible | Bornes minimales dans `requirements.txt` ; `requests` retiré, `jinja2` et `aiohttp` désormais requis | Lock compatible Pi, politique de mise à jour | Installation répétée produisant les mêmes versions validées |
| R-MAINT-02 | Moyen | Docker ne reflète pas clairement la production | Image privilégiée, sudo et services système implicites | Décider support, corriger ou marquer expérimental | Procédure testée ou retrait documenté |
| R-MAINT-03 | Moyen | Pas de suite de vérification permanente | Harnais jetables et observation | Ajouter validations minimales après décision de périmètre | Contrôles reproductibles exécutés avant déploiement |
| R-LEGAL-01 | Moyen | AGPL-3.0 déclarée sans fichier `LICENSE` | Ouvert | Ajouter le texte de licence approprié | Fichier versionné et README cohérent |

## Risques réduits, à surveiller

| ID | Ancien risque | Réduction implémentée | Surveillance restante |
|---|---|---|---|
| M-SAFE-01 | Deux instances pilotant les mêmes GPIO | Socket Unix abstrait avant tout GPIO | Toute nouvelle entrée de programme doit acquérir le même verrou |
| M-SAFE-02 | `GPIO.cleanup()` défaisant l'état sûr | Suppression et état terminal idempotent | Vérification à chaque refonte d'arrêt |
| M-SAFE-03 | Sortie cyclique laissée ON après annulation | `Component.energized()` | Interdire toute séquence manuelle équivalente |
| M-SAFE-04 | Chauffage ON indéfiniment sur perte de capteur | Compteur d'échecs, durée max, cooldown, alarme ; repli nommé `REPLI_CAPTEUR` et écriture GPIO vérifiée | Capteur figé plausible et relais collé restent ouverts |
| M-SAFE-07 | Chauffage et extraction simultanés (ancien R-SAFE-04) | Travail unique `climate_control` ; seuil de ventilation ≥ `min + hystérésis + zone morte` **par construction** ; 27 scénarios rejoués sur la fonction pure | Essai sur plages limites avec le matériel réel non encore fait |
| M-SAFE-08 | Mode hiver : humidité et vitesse minimale contournaient le quota (ancien R-SAFE-05) | Budgets renouvellement/déshumidification distincts et bornés, comptés en temps réel et persistés ; plancher thermique absolu ; `clamp_speed` ne remonte plus un arrêt | Comportement sur un vrai épisode froid/humide à observer sur le Pi |
| M-CONF-01 | Fichier JSON tronqué pendant une écriture | Écriture atomique et mode préservé | Validation sémantique complète encore ouverte |
| M-ASYNC-01 | Tâche morte silencieusement | Superviseur, heartbeats, back-off et état sûr | Event loop bloqué couvert seulement par watchdog |
| M-WDOG-01 | Watchdog aveugle | Caresse conditionnelle, même event loop, fd unique | Configuration systemd à versionner et exercer |
| M-OPS-03 | Rotation quotidienne des logs jamais constatée en réel (ancien R-OPS-03) | Vérifiée sur le Pi le 26/08/2026 à 00:18 : `phyto.log.2026-08-25.gz` (4,6 Kio) contient la journée entière, `phyto.log` repart à la ligne 1, aucune erreur | La rotation est **paresseuse** : elle se déclenche à la première écriture après minuit, pas à minuit. Une archive absente sur un contrôleur silencieux n'est pas une panne |
| M-WEB-01 | Reboot/poweroff déclenchables en GET | Routes POST dédiées, jeton CSRF, contrôle `Origin`, confirmation navigateur | Aucune authentification : le LAN reste la seule frontière |
| M-WEB-02 | Traversée de chemin sous `/static/` (ancien R-WEB-01) | Liste blanche exacte de chemins servis ; plus aucune jonction de chemin issue de l'URL | Toute nouvelle ressource doit être ajoutée explicitement à la liste |
| M-WEB-03 | Absence de limites HTTP (ancien R-WEB-03) | aiohttp : corps 64 Kio, ligne et en-têtes 8190 octets, `shutdown_timeout` 5 s, `backlog` 64 | Slowloris et nombre de connexions simultanées non mesurés en conditions réelles |
| M-WEB-04 | Disponibilité et readiness confondues (ancien R-WEB-04) | `/health/live` (200) et `/health/ready` (503 sur défaut, avec `unhealthy`) | `scripts/deploy.sh` interroge encore `/status` — voir R-OPS-02 |
| M-CONF-02 | `/conf` mutait la configuration sans revalidation (ancien R-CONF-01) | Candidat complet revalidé, écriture atomique, puis `replace_from()` ; un rejet ne modifie ni disque ni mémoire | L'arbitrage chauffage/ventilation n'est plus une contrainte de validation : il est garanti par construction dans `climate_policy` |
| M-CONF-03 | Contrôleurs capteurs multiples après reconfiguration (ancien R-CONF-03) | Instance unique, `reconfigure()` en place dans l'exécuteur, `close()` à l'arrêt, instantané partagé | Bascule capteur à confirmer sur le Pi avec le matériel réel |

## Procédure de mise à jour

Pour fermer ou réduire un risque :

1. citer le changement de code, matériel ou exploitation ;
2. indiquer le commit ;
3. indiquer le statut déployé ou non ;
4. joindre une preuve ne contenant aucun secret ;
5. déplacer le risque vers « réduit » seulement si une limite résiduelle subsiste ;
6. mettre à jour la roadmap et les documents concernés.

Une case cochée dans un ancien TODO ne suffit pas à fermer un risque courant.
