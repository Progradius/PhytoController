# Baseline de production — 25 août 2026

**Méthode** : relevé SSH Windows en lecture seule.
**Secrets** : aucune valeur de `param.json`, adresse réseau ou credential reproduit.
**Commit exécuté sur le Pi** : `61a5d7d`.
**Commit du dépôt documentaire local lors du relevé** : `61ad3df`.

## Plateforme

| Élément | Valeur observée |
|---|---|
| OS | Debian GNU/Linux 12 Bookworm |
| Architecture | aarch64 |
| Noyau | 6.12.93+rpt-rpi-v8 |
| Python | 3.11.2 |
| Fuseau | Europe/Paris |
| NTP | Synchronisé |
| Racine | 28 Gio, 34 % utilisés |
| NetworkManager | Actif |

## Dépendances Python

| Paquet | Version |
|---|---:|
| pydantic | 2.11.3 |
| requests | 2.32.3 |
| RPi.GPIO | 0.7.1 |
| smbus2 | 0.5.0 |
| aiohttp | 3.11.18 |
| Jinja2 | 3.1.6 |
| rich | 14.0.0 |

## Interfaces

- `/dev/gpiomem` accessible au groupe `gpio` ;
- `/dev/i2c-1`, `/dev/i2c-20` et `/dev/i2c-21` présents ;
- `/dev/watchdog` et `/dev/watchdog0` réservés à root ;
- `dtparam=i2c_arm=on` ;
- `dtoverlay=w1-gpio` ;
- modules I²C et 1-Wire chargés.

L'utilisateur de service `progradius` appartient notamment à `sudo`, `netdev`, `spi`, `i2c` et `gpio`.

## systemd

| Propriété | Valeur effective |
|---|---|
| État | active/running |
| Type | notify |
| Restart | always |
| RestartSec | 5 s |
| WatchdogSec | 600 s |
| RuntimeWatchdogSec système | 15 s |
| NRestarts | 0 |
| WorkingDirectory | `/home/progradius/PhytoController/RPi Version` |

L'unité et le drop-in recopiés sous `deploy/` ont exactement les mêmes empreintes SHA-256 que les fichiers installés :

```text
fda0f70894fa957186d36b25d82b176b2376cb8fdd6e04a6f49bbfc34acb82a7  phyto.service
d31e83005ead5a1da828743aac040ba854b29517abd4736f5aa9e5b8654a9f07  watchdog.conf
```

## Santé applicative

- `healthy=true` ;
- `heater_alarm=null` ;
- huit tâches vivantes et saines ;
- aucun restart ou stall ;
- export Influx et HTTP présents ;
- moteur observé à la vitesse logique 2 au moment du relevé.

Le répertoire Git du Pi contenait les modifications vivantes attendues de `param/param.json` et `param/sensor_stats.json`, ainsi qu'une sauvegarde locale non suivie de configuration GPIO. Aucun contenu de ces fichiers n'a été lu ou reproduit.

## Journaux

- `logs/phyto.log` : environ 45 Kio avant minuit ;
- journald : 141,3 Mio ;
- `SystemMaxUse=200M` actif ;
- rotation quotidienne applicative encore à vérifier après l'échéance réelle.

## Écarts à traiter

- production en retard de deux commits sur le dépôt documentaire local au moment du relevé ;
- capacités `CAP_SYS_ADMIN` et `CAP_SYS_RAWIO` encore accordées ;
- artefacts systemd capturés mais reconstruction vierge non exercée ;
- rotation quotidienne non encore prouvée en production.
