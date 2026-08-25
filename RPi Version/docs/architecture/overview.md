# Vue d'ensemble de l'architecture

**Public** : développement, exploitation avancée et audit.
**Référence** : commit `61ad3df`.
**Dernière vérification** : 25 août 2026, lecture du code.

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
  ├─ 1. verrou d'instance abstrait, avant tout GPIO
  ├─ 2. handlers SIGINT/SIGTERM/SIGHUP et atexit
  ├─ 3. chargement et validation de param/param.json
  ├─ 4. configuration de la journalisation
  ├─ 5. moteur forcé à LOW
  ├─ 6. sorties génériques forcées à HIGH
  ├─ 7. tentative Wi-Fi, NTP et test de l'hôte
  ├─ 8. construction des composants, timers et capteurs
  ├─ 9. construction de PuppetMaster
  └─ 10. asyncio.run(PuppetMaster.main_loop())
          ├─ enregistrement des tâches
          ├─ démarrage du superviseur
          ├─ démarrage du watchdog
          ├─ sd_notify(READY=1)
          └─ attente du superviseur
```

Le verrou est volontairement pris avant l'enregistrement des handlers de sortie : un processus surnuméraire doit quitter sans appliquer une séquence d'arrêt qui toucherait les broches du processus légitime.

## Composants principaux

| Couche | Responsabilité | Fichiers principaux |
|---|---|---|
| Boot | Ordre d'initialisation, niveaux sûrs, signaux | `main.py`, `function.py` |
| Configuration | Modèles Pydantic, lecture et écriture atomique | `param/config.py`, `utils/atomic_io.py` |
| Modèle GPIO | Polarité et état logique des sorties | `model/Component.py`, `model/Motor.py` |
| Timers | Calcul des horaires et périodes | `model/DailyTimer.py`, `model/CyclicTimer.py` |
| Boucles métier | Timers, moteur, chauffage | `components/*_handler.py` |
| Capteurs | Construction et lecture des périphériques | `controllers/SensorController.py`, `sensor_handlers/` |
| Orchestration | Enregistrement des travaux | `controllers/PuppetMaster.py` |
| Supervision | Relance, back-off, heartbeat, état sûr | `utils/supervisor.py` |
| Watchdog | `sd_notify` ou `/dev/watchdog` | `utils/watchdog.py` |
| HTTP | Routage, pages, configuration, `/status` | `network/web/server.py`, `network/web/pages.py` |
| Export | Protocole InfluxDB v1 | `network/web/influx_handler.py` |
| Logs | Façade, rotation, flux SSE | `utils/pretty_console.py`, `utils/log_stream.py` |
| Déploiement | Sauvegarde, mise à jour, contrôle et rollback | `scripts/deploy.sh` |

## Tâches supervisées

`PuppetMaster` enregistre jusqu'à huit travaux :

| Nom `/status` | Responsabilité | État sûr avant relance |
|---|---|---|
| `daily_timer_1` | Première sortie journalière | Sortie OFF, GPIO HIGH |
| `daily_timer_2` | Deuxième sortie journalière | Sortie OFF, GPIO HIGH |
| `cyclic_timer_1` | Première sortie cyclique | Sortie OFF, GPIO HIGH |
| `cyclic_timer_2` | Deuxième sortie cyclique | Sortie OFF, GPIO HIGH |
| `motor_temp_control` | Régulation moteur | Quatre relais LOW |
| `heat_control` | Régulation chauffage | Chauffage OFF, GPIO HIGH |
| `influx_push` | Export des mesures, si hôte déclaré online | Aucun GPIO |
| `http_server` | Interface sur le port 8123 | Aucun GPIO |

Chaque travail long est fourni sous forme de fabrique de coroutine afin de pouvoir être recréé après une panne. Les boucles métier battent leur cœur et utilisent le sommeil du superviseur. Le serveur HTTP est exempté de contrôle de silence : attendre une connexion est son fonctionnement normal.

## Santé et watchdog

Le superviseur expose pour chaque travail :

- présence et état de la tâche ;
- santé calculée ;
- silence depuis le dernier heartbeat ;
- nombre de relances ;
- nombre de blocages détectés ;
- dernière erreur.

Le watchdog n'est caressé que si `TaskSupervisor.is_healthy()` est vrai. Deux voies sont possibles :

1. systemd si `NOTIFY_SOCKET` et `WATCHDOG_USEC` sont fournis ;
2. `/dev/watchdog` dans les autres cas, sauf `PHYTO_HW_WATCHDOG=0`.

La période de caresse systemd est plafonnée à 30 secondes dans le code courant. `WatchdogSec=600` a été vérifié sur le Pi le 25 août 2026. Il doit rester supérieur au silence maximal de 300 secondes afin que le superviseur tente la récupération avant le redémarrage systemd.

## Flux de configuration

Le système ne possède pas encore de magasin de configuration unique :

- `main.py` charge une instance au boot ;
- les timers cycliques et journaliers relisent le fichier au cours de leurs boucles ;
- les contrôles moteur et chauffage conservent une référence à l'objet de configuration initial, que le serveur peut muter lors d'un POST ;
- un POST `/conf` reconstruit le `SensorController` utilisé par le serveur et InfluxDB ;
- les tâches moteur et chauffage conservent cependant la référence du contrôleur de capteurs fourni lors de leur enregistrement.

Cette hétérogénéité est un risque ouvert. La cible est un `ConfigStore` revalidé intégralement et un `SensorController` unique, reconfigurable en place.

## Flux HTTP

Le serveur utilise `asyncio.start_server` et analyse manuellement la requête :

- `/` rend l'état ;
- `/conf` rend ou modifie la configuration ;
- `/monitor` rend les mesures en GET et exécute certaines actions en POST ;
- `/console/stream` diffuse les logs par SSE ;
- `/status` renvoie un JSON de statut et de santé.

L'interface est sans authentification par décision actuelle et supposée accessible uniquement sur un LAN de confiance. Cette hypothèse est une contrainte d'exploitation, pas une barrière de sécurité fournie par le programme.

## Limites architecturales connues

- chauffage et ventilation ne sont pas arbitrés par une décision thermique unique ;
- des I/O bloquantes s'exécutent encore dans l'event loop ;
- le serveur artisanal n'impose pas encore de limites et timeouts suffisants ;
- la route statique n'est pas confinée ;
- `/status` répond `200` même lorsque `healthy` est faux ;
- l'heure non synchronisée ne bloque pas les décisions jour/nuit ;
- l'unité systemd installée n'est pas encore versionnée dans le dépôt ;
- la configuration et les secrets ne sont pas séparés.

Ces limites sont suivies dans le [registre des risques](../risk-register.md) et ordonnées dans la [roadmap](../roadmap.md).
