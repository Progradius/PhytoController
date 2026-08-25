# Registre vivant des risques

**Public** : pilotage, exploitation, développement et audit.
**Référence initiale** : audit du 25 août 2026, recalé sur le commit `61ad3df`.
**Dernière mise à jour** : 25 août 2026.

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
| R-SAFE-04 | Critique | Chauffage et extraction peuvent fonctionner simultanément | Deux tâches indépendantes | Arbitre thermique unique et zone morte validée | Tests de décision et essai sur plages limites |
| R-SAFE-05 | Critique | Mode hiver : humidité et vitesse minimale peuvent contourner le quota | Ouvert | Fonction de décision pure, quota unique et plancher T | Table de scénarios froid/humide et compteurs persistants |
| R-SAFE-06 | Élevé | Plusieurs relais moteur actifs sont signalés mais pas coupés | `get_motor_speed()` renvoie 0 sans agir | Coupure immédiate, verrouillage dégradé et interlock | Injection d'état multi-HIGH et vérification all-OFF |
| R-CONF-01 | Critique | `/conf` affecte des champs sans revalidation complète | Écriture atomique mais mutations directes | `ConfigStore`, copie candidate puis `model_validate` | Cas invalides refusés sans modifier disque ni contrôle actif |
| R-CONF-02 | Critique | Secrets Wi-Fi/Influx versionnés et affichés | Toujours présents dans `param.json` | Variables/fichier d'environnement, masquage UI, rotation, nettoyage historique décidé | Scan Git, UI et logs sans secret ; nouveaux identifiants actifs |
| R-CONF-03 | Élevé | Hot reload hétérogène, anciens et nouveaux contrôleurs capteurs coexistent | POST reconstruit le contrôleur du serveur, tâches existantes gardent l'ancien | Instance unique avec `reconfigure()`, verrou et `close()` | Test de bascule capteur montrant la même instance pour UI, contrôle et Influx |
| R-WEB-01 | Critique | Traversée de chemin sous `/static/` | Chemin joint sans confinement | Résolution et appartenance, ou serveur statique aiohttp | Tests `..`, encodages et liens symboliques refusés |
| R-WEB-02 | Élevé | IHM sans authentification et validation `Host` absente | Choix LAN-only ; contrôle `Origin` partiel sur `/monitor` | Documenter filtrage réseau, valider `Host`, réévaluer auth | Tests de DNS rebinding et règles réseau vérifiées |
| R-WEB-03 | Élevé | Pas de limites HTTP suffisantes : slowloris, body, connexions | Serveur artisanal | Migration aiohttp ou limites/timeouts explicites | Tests de requêtes lentes et surdimensionnées sans impact contrôle |
| R-WEB-04 | Élevé | `/status` répond 200 lorsque `healthy=false` | Disponibilité et readiness confondues | `/health/live` et `/health/ready`, ou 503 de readiness | Déploiement refuse une tâche malsaine tout en distinguant serveur vivant |
| R-ASYNC-01 | Élevé | I/O bloquantes dans l'event loop | `requests`, capteurs et commandes système concernés | Executor dédié ou clients async, timeouts bornés | Mesure de latence event loop sous panne I/O |
| R-TIME-01 | Élevé | Heure fausse au boot hors réseau | NTP tenté, pas de RTC ni garde `time_synced` | RTC, vérification NTP et politique dégradée | Reboot hors réseau sans commutation à contretemps |
| R-NET-01 | Élevé | Pas de reconnexion Wi-Fi supervisée | Tentative au boot seulement | Tâche réseau supervisée | Coupure/restauration AP avec reconnexion automatique |
| R-OPS-01 | Élevé | Unité systemd et drop-ins non reproductibles | Capturés le 25/08/2026 et recopiés sous `deploy/`, mais installation vierge non exercée et capacités larges | Revoir capacités puis exercer l'installation | Reconstruction d'un Pi avec diff nul par rapport à la référence |
| R-OPS-02 | Élevé | Sonde de déploiement ne valide pas `healthy` | `curl -f /status` seulement | Lire le JSON ou utiliser readiness | Injection d'une tâche malsaine provoquant rollback/refus |
| R-OPS-03 | Moyen | Rotation quotidienne des logs pas encore clôturée en conditions réelles | Au relevé du 25/08 avant minuit, `phyto.log` faisait 45 Kio sans archive quotidienne | Vérifier archive, fichier courant et journal après minuit | Capture datée d'une rotation réelle sans erreur |
| R-HW-01 | Élevé | Collisions GPIO possibles dans la configuration | BCM 27 et 22 ont plusieurs rôles déclarés | PinRegistry et validation d'unicité | Config conflictuelle refusée avant accès GPIO |
| R-HW-02 | Élevé | DS18B20/1-Wire et autres capteurs peuvent être déclarés sans câblage fiable | DS18 désactivé dans la config versionnée actuelle | Inventaire matériel et procédure de mise en service | Mesures stables ou capteur explicitement absent |
| R-MAINT-01 | Moyen | Dépendances non verrouillées et environnement non reproductible | Bornes minimales dans `requirements.txt` | Lock compatible Pi, politique de mise à jour | Installation répétée produisant les mêmes versions validées |
| R-MAINT-02 | Moyen | Docker ne reflète pas clairement la production | Image privilégiée, sudo et services système implicites | Décider support, corriger ou marquer expérimental | Procédure testée ou retrait documenté |
| R-MAINT-03 | Moyen | Pas de suite de vérification permanente | Harnais jetables et observation | Ajouter validations minimales après décision de périmètre | Contrôles reproductibles exécutés avant déploiement |
| R-LEGAL-01 | Moyen | AGPL-3.0 déclarée sans fichier `LICENSE` | Ouvert | Ajouter le texte de licence approprié | Fichier versionné et README cohérent |

## Risques réduits, à surveiller

| ID | Ancien risque | Réduction implémentée | Surveillance restante |
|---|---|---|---|
| M-SAFE-01 | Deux instances pilotant les mêmes GPIO | Socket Unix abstrait avant tout GPIO | Toute nouvelle entrée de programme doit acquérir le même verrou |
| M-SAFE-02 | `GPIO.cleanup()` défaisant l'état sûr | Suppression et état terminal idempotent | Vérification à chaque refonte d'arrêt |
| M-SAFE-03 | Sortie cyclique laissée ON après annulation | `Component.energized()` | Interdire toute séquence manuelle équivalente |
| M-SAFE-04 | Chauffage ON indéfiniment sur perte de capteur | Compteur d'échecs, durée max, cooldown, alarme | Capteur figé plausible et relais collé restent ouverts |
| M-CONF-01 | Fichier JSON tronqué pendant une écriture | Écriture atomique et mode préservé | Validation sémantique complète encore ouverte |
| M-ASYNC-01 | Tâche morte silencieusement | Superviseur, heartbeats, back-off et état sûr | Event loop bloqué couvert seulement par watchdog |
| M-WDOG-01 | Watchdog aveugle | Caresse conditionnelle, même event loop, fd unique | Configuration systemd à versionner et exercer |
| M-WEB-01 | Reboot/poweroff déclenchables en GET | POST, PRG, contrôle Origin partiel | Auth, Host et LAN restent ouverts |

## Procédure de mise à jour

Pour fermer ou réduire un risque :

1. citer le changement de code, matériel ou exploitation ;
2. indiquer le commit ;
3. indiquer le statut déployé ou non ;
4. joindre une preuve ne contenant aucun secret ;
5. déplacer le risque vers « réduit » seulement si une limite résiduelle subsiste ;
6. mettre à jour la roadmap et les documents concernés.

Une case cochée dans un ancien TODO ne suffit pas à fermer un risque courant.
