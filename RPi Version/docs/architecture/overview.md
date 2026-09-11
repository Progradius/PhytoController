# Vue d'ensemble de l'architecture

**Public** : développement, exploitation avancée et audit.
**Référence** : commit `e29bf96`.
**Dernière vérification** : 11 septembre 2026, lecture du code (séquence de boot, travaux supervisés, flux de configuration).

## Responsabilité du système

PhytoController est un processus Python unique chargé de piloter une serre. Il combine :

- des sorties planifiées ;
- une régulation de ventilation à quatre vitesses ;
- une régulation de chauffage ;
- des capteurs I²C, 1-Wire ou GPIO ;
- un export InfluxDB ;
- une interface HTTP locale ;
- une supervision interne et un watchdog systemd ou matériel.

Le programme n'utilise pas de framework applicatif. `main.py` exécute la séquence de boot au niveau du module, construit les objets et confie les boucles longues à `PuppetMaster`.

## Séquence de démarrage

```text
Processus Python
  │
  ├─ 0. ensure_data_dir() : répertoire des données vivantes créé et contrôlé,
  │     sortie en erreur si PHYTO_DATA_DIR est posée mais inutilisable
  ├─ 1. verrou d'instance abstrait, avant tout GPIO
  ├─ 2. handlers SIGINT/SIGTERM/SIGHUP et atexit
  ├─ 3. shared_config().current : chargement et validation de param.json
  │     (repli sur param.json.bak, sinon refus de démarrer)
  ├─ 4. historique opérateur et gestionnaire d'alarmes
  ├─ 5. configuration de la journalisation et flux /console
  ├─ 6. moteur forcé à LOW
  ├─ 7. sorties génériques forcées à HIGH
  ├─ 8. tentative Wi-Fi, NTP et test de l'hôte
  ├─ 9. reprise des forçages « arrêt » encore valides
  ├─ 10. construction des composants, timers et capteurs
  ├─ 11. construction de PuppetMaster
  └─ 12. asyncio.run(PuppetMaster.main_loop())
          ├─ enregistrement des tâches
          ├─ démarrage du superviseur
          ├─ démarrage du watchdog
          ├─ sd_notify(READY=1)
          └─ attente du superviseur
```

`ensure_data_dir()` passe en premier : aucun fichier n'est lu ni écrit avant que le répertoire des données vivantes soit résolu (`PHYTO_DATA_DIR` s'il est posé, sinon `param/` du dépôt), et un répertoire inutilisable arrête le processus avant toute broche, sans repli silencieux vers `param/`. Le verrou est volontairement pris avant l'enregistrement des handlers de sortie : un processus surnuméraire doit quitter sans appliquer une séquence d'arrêt qui toucherait les broches du processus légitime.

## Composants principaux

| Couche | Responsabilité | Fichiers principaux |
|---|---|---|
| Boot | Ordre d'initialisation, niveaux sûrs, signaux | `main.py`, `function.py` |
| Données vivantes | Résolution unique du répertoire des fichiers écrits à l'exécution (`PHYTO_DATA_DIR`) | `utils/runtime_paths.py` |
| Configuration | Schéma Pydantic (`AppConfig`, sans écriture) | `param/config.py` |
| Magasin de configuration | Propriétaire et seul écrivain de `param.json` : relecture sur empreinte, sauvegarde `.bak`, écriture atomique, repli au boot | `param/config_store.py`, `utils/atomic_io.py` |
| Modèle GPIO | Polarité et état logique des sorties | `model/Component.py`, `model/Motor.py` |
| Timers | Calcul des horaires et périodes | `model/DailyTimer.py`, `model/CyclicTimer.py` |
| Boucles métier | Timers, moteur, chauffage | `components/*_handler.py` |
| Capteurs | Construction et lecture des périphériques | `controllers/SensorController.py`, `sensor_handlers/` |
| Orchestration | Enregistrement des travaux | `controllers/PuppetMaster.py` |
| Supervision | Relance, back-off, heartbeat, état sûr | `utils/supervisor.py` |
| Watchdog | `sd_notify` ou `/dev/watchdog` | `utils/watchdog.py` |
| HTTP | Routage, pages, configuration, `/status` | `network/web/server.py`, `network/web/pages.py` |
| Export | Protocole InfluxDB v1 | `network/web/influx_handler.py` |
| Carnet de cultures | Magasin SQLite auxiliaire déclaratif, hors event loop | `utils/culture_store.py` et ses mixins, `model/culture*.py`, `network/web/cultures.py` |
| Logs | Façade, rotation, flux SSE | `utils/pretty_console.py`, `utils/log_stream.py` |
| Déploiement | Sauvegarde, mise à jour, contrôle et rollback | `scripts/deploy.sh` |

## Tâches supervisées

`PuppetMaster._register_jobs()` enregistre toujours onze travaux :

| Nom `/status` | Responsabilité | Domaine | Garde le watchdog | Silence max | État sûr avant relance |
|---|---|---|---|---|---|
| `daily_timer_1` | Première sortie journalière | `timers` | oui | 300 s | Sortie OFF, GPIO HIGH |
| `daily_timer_2` | Deuxième sortie journalière | `timers` | oui | 300 s | Sortie OFF, GPIO HIGH |
| `cyclic_timer_1` | Première sortie cyclique | `timers` | oui | 300 s | Sortie OFF, GPIO HIGH |
| `cyclic_timer_2` | Deuxième sortie cyclique | `timers` | oui | 300 s | Sortie OFF, GPIO HIGH |
| `climate_control` | Arbitre thermique : chauffage **et** ventilation | `climate` | oui | 300 s | Chauffage OFF (GPIO HIGH) puis quatre relais moteur LOW |
| `sensor_snapshot` | Acquisition partagée des capteurs | `sensors` | oui | 300 s | Aucun GPIO |
| `influx_push` | Export des mesures, actif ou suspendu à chaud selon l'hôte | `telemetry` | non | aucun | Aucun GPIO |
| `culture_service` | Agrégats climatiques horaires du carnet de cultures | `cultures` | non | 300 s | Aucun GPIO |
| `http_server` | Interface sur le port 8123 (et HTTPS optionnel) | `http` | non | aucun | Aucun GPIO |
| `time_monitor` | Surveillance de la fiabilité de l'heure | `time` | non | 120 s | Aucun GPIO |
| `operator_service` | Couche opérateur : alarmes, historique SQLite, sonde réseau | `operations` | non | 120 s | Aucun GPIO |

Chaque travail long est fourni sous forme de fabrique de coroutine afin de pouvoir être recréé après une panne. Les boucles métier battent leur cœur et utilisent le sommeil du superviseur. Le serveur HTTP et l'export InfluxDB sont exemptés de contrôle de silence : attendre une connexion, ou rester suspendu tant que l'hôte est absent, est leur fonctionnement normal. Seuls les six travaux marqués « oui » entrent dans `control_healthy()` ; une panne des cinq autres dégrade `healthy` et `/health/ready`, jamais les caresses du watchdog.

## Santé et watchdog

Le superviseur expose pour chaque travail :

- présence et état de la tâche ;
- santé calculée ;
- silence depuis le dernier heartbeat ;
- nombre de relances ;
- nombre de blocages détectés ;
- dernière erreur.

Le watchdog n'est caressé que si `TaskSupervisor.control_healthy()` est vrai, c'est-à-dire si les six travaux `gates_watchdog=True` sont vivants et récents. `is_healthy()`, qui couvre les onze travaux, alimente `healthy` et `/health/ready`. Deux voies sont possibles :

1. systemd si `NOTIFY_SOCKET` et `WATCHDOG_USEC` sont fournis ;
2. `/dev/watchdog` dans les autres cas, sauf `PHYTO_HW_WATCHDOG=0`.

La période de caresse systemd est plafonnée à 30 secondes dans le code courant. `WatchdogSec=600` a été vérifié sur le Pi le 25 août 2026. Il doit rester supérieur au silence maximal de 300 secondes afin que le superviseur tente la récupération avant le redémarrage systemd.

## Flux de configuration

`param/config_store.py` (`ConfigStore`, singleton `shared_config()`) est le **seul propriétaire et le seul écrivain** de `param.json`, situé dans le répertoire des données vivantes :

- `main.py` prend `shared_config().current` au boot et distribue cette **unique** instance à tous les consommateurs ; elle n'est jamais remplacée, seulement mutée en place (`replace_from()`) ;
- les boucles `timer_daily`, `timer_cyclic` et `climate_control` appellent `shared_config().refresh()` à chaque itération : aucune I/O tant que l'empreinte `(mtime_ns, taille)` du fichier est inchangée, jamais d'exception, et un fichier illisible garde la configuration courante ;
- `POST /conf/{section}` construit un `AppConfig` candidat **complet**, le valide intégralement, puis le magasin copie l'ancien contenu en `.bak` et écrit atomiquement ; un rejet ne laisse ni fichier ni mémoire modifiés ;
- les travaux concernés sont ensuite relancés par `supervisor.request_reload()`, **sans** réappliquer l'état sûr (la tâche était saine : couper la charge à chaque enregistrement ferait clignoter le relais), de sorte que moteur, chauffage et minuteries repartent sur la nouvelle consigne sans redémarrage ;
- le `SensorController` est unique et **reconfiguré en place** : le bus I²C n'est jamais rouvert.

Reste ouvert : la séparation des secrets (chantier « configuration »).

## Arbitre thermique

Chauffage et ventilation régulent la même température : ils sont pilotés par un **unique** travail supervisé, `climate_control`.

- `components/climate_policy.py` porte toute la décision sous forme d'une fonction **pure** `decide(settings, inputs, memory)`. Aucun GPIO, aucun disque, aucune horloge implicite : la régulation est rejouable à la main.
- `components/climate_control.py` ne fait qu'appliquer : une lecture T/RH par tick, resynchronisation sur l'état réel des sorties, écriture vérifiée, persistance des budgets.
- La **zone morte** est garantie par construction : le seuil de ventilation ne descend jamais sous `target_temp_min + hysteresis_offset + vent_deadband`. Aucune température ne peut donc voir chauffage et extracteur actifs ensemble. Quand la consigne haute est trop basse pour tenir cette contrainte, le seuil est relevé, journalisé et publié dans `/api/v1/state` plutôt que de refuser la configuration — une configuration refusée est un boot mort.
- Les paliers de ventilation ont une **hystérésis à état** (seuil d'engagement, seuil de relâchement distinct) et un **temps de maintien minimal** : plus de battement de relais au seuil.
- En mode hiver, deux budgets horaires **bornés et distincts** gouvernent l'air neuf : renouvellement et déshumidification. L'humidité ne peut plus court-circuiter le quota. Sous le **plancher absolu**, aucune ventilation n'est autorisée, budget restant ou non.
- États publiés : `DESACTIVE`, `CHAUFFER`, `NEUTRE`, `VENTILER`, `RENOUVELER`, `DESHUMIDIFIER`, `SECURITE_HAUTE`, `PLANCHER_THERMIQUE`, `REPLI_CAPTEUR`, `MANUEL`.

## État reporté d'un démarrage à l'autre

`utils/state_store.py` persiste dans `runtime_state.json`, dans le répertoire des données vivantes (écriture atomique, throttlée à une par minute) ce qui ne doit pas repartir de zéro :

- les budgets hiver de l'arbitre thermique — sinon chaque relance réaccorde une fenêtre complète de ventilation ;
- la phase séquentielle des minuteurs cycliques — sinon chaque relance rejoue une phase ON complète.

Un enregistrement absent, illisible ou échu est ignoré : la reprise ne peut que raccourcir un cycle, jamais en inventer un.

## Flux HTTP

Le serveur est un `aiohttp` à routes explicites, sans analyse manuelle de requête :

- `/` rend le tableau de bord, rafraîchi côté navigateur toutes les 5 s par `/api/v1/state` ;
- `/conf` rend le formulaire, `POST /conf/{section}` enregistre une section à la fois ;
- `/console/stream` diffuse les logs par SSE ;
- `/api/v1/state` expose l'état versionné, `/status` l'ancien format, `/health/live` et `/health/ready` les sondes ;
- les actions destructrices sont des routes POST dédiées ;
- `/monitor` n'est plus qu'une redirection de compatibilité ;
- les pages du carnet de cultures (`/cultures`, `/cultures/solutions`, `/cultures/cycles`,
  `/cultures/targets`, `/cultures/light`, `/cultures/equipment`, `/cultures/journal`) et leurs API
  `/api/v1/cultures/…` sont **auxiliaires** : elles délèguent tout accès SQLite à un thread dédié,
  n'écrivent ni configuration ni GPIO, et leur panne ne dégrade ni `control_healthy()` ni le
  watchdog — voir le [guide du carnet](../operations/cultures.md) et son
  [contrat API](../reference/cultures-api.md).

Trois intergiciels encadrent chaque requête : en-têtes de sécurité et `no-store`, validation du `Host` (contre le DNS rebinding), puis jeton CSRF et contrôle d'`Origin` sur toute méthode mutante. Les assets statiques sont servis par une liste blanche exacte de chemins, ce qui supprime la question du confinement de répertoire. Le corps est plafonné à 64 Kio.

L'interface reste sans authentification par décision actuelle et supposée accessible uniquement sur un LAN de confiance. Cette hypothèse est une contrainte d'exploitation, pas une barrière de sécurité fournie par le programme.

Aucune requête HTTP ne déclenche de lecture matérielle : le job supervisé `sensor_snapshot` publie un instantané toutes les 10 s, que l'IHM et l'export InfluxDB consomment.

## Limites architecturales connues

- des I/O bloquantes subsistent hors capteurs et export : commandes système et Wi-Fi ;
- `/status` répond `200` même lorsque `healthy` est faux — utiliser `/health/ready`, dont le code passe à `503` ;
- sans RTC, une heure inconnue ne suspend les minuteries journalières que 15 minutes (`UNKNOWN_SUSPENSION_SECONDS`), après quoi elles reprennent sur l'heure « plausible » ; climat et séquentiels restent en paramètres de nuit tant que l'heure n'est pas prouvée synchronisée ;
- l'unité versionnée `deploy/phyto.service` et ses drop-ins doivent encore être recopiés à la main dans `/etc/systemd/system/` : `deploy.sh` ne les installe pas ;
- la configuration et les secrets ne sont pas séparés.

Ces limites sont suivies dans le [registre des risques](../risk-register.md) et ordonnées dans la [roadmap](../roadmap.md).
