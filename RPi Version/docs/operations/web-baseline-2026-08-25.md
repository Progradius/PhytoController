# Baseline web du 25 août 2026

**Nature** : relevé de vérification après déploiement, en lecture seule sauf mention contraire.
**Commit déployé** : `ad39de2`. **Service démarré** : 25 août 2026 à 23:36:07 CEST.
**Méthode** : commandes exécutées sur le Pi via le pont SSH (`scripts/phyto-ssh.sh`).
**Valeurs sensibles** : aucune n'est reproduite ici.

Ce document est daté : il constate un état, il ne décrit pas le comportement courant. La
référence vivante reste [l'interface HTTP](../reference/http-interface.md) et le
[registre des risques](../risk-register.md).

## Service et supervision

`ActiveState=active`, `SubState=running`, `NRestarts=0`. Watchdog systemd : `WatchdogUSec=10min`,
dernière caresse 18 s avant le relevé.

Neuf tâches supervisées, toutes `alive` et `healthy`, `restarts=0`, `stalls=0` :
`daily_timer_1`, `daily_timer_2`, `cyclic_timer_1`, `cyclic_timer_2`, `motor_temp_control`,
`heat_control`, `sensor_snapshot`, `influx_push`, `http_server`.

`sensor_snapshot` est la tâche introduite par la refonte ; `influx_push` est désormais
enregistrée en permanence et pilotée par `host_machine_state`, relevé à `online`.

## Sondes HTTP

| Contrôle | Résultat |
|---|---|
| `GET /health/live` | 200, `{"live": true}` |
| `GET /health/ready` | 200, `{"ready": true, "unhealthy": []}` |
| `GET /api/v1/state` | 200, `schema_version=1`, `healthy=true`, `heater_alarm=null` |
| `GET /`, `/conf`, `/console`, `/status` | 200 |
| `GET /favicon.svg`, `/static/css/style.css`, `/static/js/{dashboard,config,console}.js`, `/static/fonts/visitor1.ttf` | 200, types MIME corrects |
| `GET /monitor` | 303 vers `/#surveillance` |
| `GET /inexistant` | 404 |
| `GET /static/../param/param.json` | 404 |
| `GET /` avec `Host: evil.example.com` | **421**, refus journalisé |
| `POST /conf/logs` sans jeton | **403**, refus journalisé |

En-têtes présents sur `/` : `Content-Security-Policy` sans `unsafe-inline`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Cache-Control: no-store`.

Flux SSE `/console/stream` : lignes reçues immédiatement, historique inclus.

## Écriture de configuration

| Contrôle | Résultat |
|---|---|
| `POST /conf/logs` avec les valeurs courantes | 303 vers `/conf?success=logs#logs` |
| `POST /conf/temperature` avec minimum > maximum | **422** |
| `param.json` après le rejet | **strictement identique** à la copie prise avant |
| `POST /conf/heater` avec la valeur courante | 303, `heat_control` : `reloads=1`, `restarts=0`, `healthy=true` |
| `param.json` en fin de séquence | aucun écart |

Le rechargement volontaire n'a **pas** modifié la sortie : GPIO 23 (chauffage) lu `hi` (OFF)
avant et après. C'est la vérification du correctif « pas d'état sûr sur rechargement volontaire ».

## Jeton CSRF persistant

`param/.csrf_token` : mode **600**, propriétaire `progradius:progradius`, 44 octets, **absent de
`git status`**. Le jeton servi dans `<meta name="csrf-token">` est identique au contenu du
fichier. `utils.csrf.load_or_create_token()` réexécuté sur le Pi rend la même valeur sans
régénérer : le chemin emprunté au démarrage est déterministe.

*Non exercé* : un `systemctl restart` réel, qui aurait fait basculer les sorties allumées. La
relecture ci-dessus couvre le même chemin de code.

## Capteurs

Trois mesures actives, toutes en `status=ok`, âge ≈ 10 s — conforme à la période du job
`sensor_snapshot` : température, humidité et pression BME280. Les statistiques min/max ont été
mises à jour après le démarrage du service, ce qui exerce l'écriture verrouillée de
`SensorStats`.

DS18B20, VEML6075, VL53L0X, MLX90614, TSL2591 et HC-SR04 restent désactivés.

## GPIO relevés

```text
 1: op -- pn | lo      5: op -- pn | lo      7: op -- pn | lo      8: op -- pn | hi
18: op -- pn | lo     22: op -- pn | hi     23: op -- pn | hi     25: op -- pn | lo
27: op -- pn | lo
```

Cohérence avec l'état logique publié par `/api/v1/state` :

| Sortie | Broche | Niveau | Interprétation |
|---|---|---|---|
| Minuterie 1 | 5 | `lo` | ON (actif-BAS) |
| Minuterie 2 | 18 | `lo` | ON |
| Cyclique 1 | 27 | `lo` | ON |
| Cyclique 2 | 22 | `hi` | OFF |
| Chauffage | 23 | `hi` | OFF |
| Moteur | 25/8/7/1 | `lo`/`hi`/`lo`/`lo` | **une seule** broche HIGH → vitesse 2 |

Toutes les broches sont des sorties pilotées (`op`), aucune n'est relâchée en entrée.

## Environnement Python

`aiohttp 3.13.5`, `jinja2 3.1.6`, `pydantic 2.11.3` dans le venv du service : la mise à jour
automatique de `scripts/deploy.sh` sur changement de `requirements.txt` a fonctionné.

`requests 2.32.3` était **resté installé** dans le venv — `pip install -r` ne désinstalle pas ce
qui a été retiré du fichier. Désinstallé le 26 août 2026 à 00:19 (`pip uninstall -y requests`) :
`import requests` échoue désormais, les imports applicatifs et `influx_push` restent sains.

## Journal

Zéro ligne `[ERROR]` ou `[CRITICAL]` depuis le démarrage. Les seuls `[WARNING]` sont les refus
volontairement provoqués par ce relevé (`Host` étranger, CSRF absent) et les lectures DS18B20
antérieures au redéploiement, sur un capteur physiquement absent.

## Exploitation

NTP synchronisé, partition racine à 34 % (18 Gio libres), journald à 141,3 Mio.

## Suites données le 26 août 2026

- **Rotation quotidienne des logs** (`R-OPS-03`) : **constatée** à 00:18.
  `phyto.log.2026-08-25.gz` (4,6 Kio) contient la journée entière, `phyto.log` repart à la
  première ligne, aucune erreur. Elle ne s'est déclenchée qu'à la première écriture après
  minuit — comportement normal de `TimedRotatingFileHandler`, désormais documenté.
- **`requests`** désinstallé du venv du Pi.
- **`param/param.json.bak-gpio17`** supprimé : ancienne copie de configuration contenant les
  identifiants Wi-Fi et InfluxDB en clair, hors de tout suivi git.

## Points restés ouverts après ce relevé

- **Plafond journald** : 141,3 Mio ; vérifier que `SystemMaxUse=200M` est bien appliqué.
- **Collisions GPIO déclarées** (`R-HW-01`) : `i2c_scl` et `cyclic2_pin` valent tous deux 22,
  `hcsr_echo_pin` et `cyclic1_pin` valent tous deux 27. Sans effet tant que HC-SR04 et l'I²C
  logiciel restent inutilisés, mais la configuration reste ambiguë.
- **`motor_pin4` toujours sur BCM 1** (`ID_SC`) — migration prévue vers BCM 16.
- **`scripts/deploy.sh`** interroge encore `/status` et non `/health/ready` (`R-OPS-02`).
