# Relevé de l'arbitre thermique — 26 août 2026

**Objet** : vérification du déploiement de la phase 2 (arbitre thermique unifié) sur le Pi de
production. **Commit déployé** : `a04abbd` (contient `e93644a`). **Service démarré** :
26 août 2026, 00:48:31 CEST. **Méthode** : lecture seule via le pont SSH Windows, plus une
écriture de configuration à valeur inchangée (procédure identique à la
[baseline web du 25 août](web-baseline-2026-08-25.md)).

Aucun identifiant n'est reproduit ici.

## Contexte de la serre au moment du relevé

Chauffage **désactivé**, moteur en mode **manuel** à la vitesse 2, minuterie journalière 1 active
(19:00 → 07:00), cyclique 1 en phase ON séquentielle, cyclique 2 désactivé. Température ambiante
26,9 °C, humidité 55 %.

## Service et tâches

| Contrôle | Résultat |
|---|---|
| `systemctl is-active phyto` | `active`, `NRestarts=0` |
| Travaux supervisés | 8 : `daily_timer_1/2`, `cyclic_timer_1/2`, **`climate_control`**, `sensor_snapshot`, `influx_push`, `http_server` |
| `heat_control` / `motor_temp_control` | **absents** — remplacés par l'arbitre |
| `restarts` / `stalls` / `last_error` | 0 / 0 / `null` sur les huit travaux |
| `/health/ready` | 200 |
| `healthy` (`/status`) | `true` |

## Cohérence décision ↔ matériel

Le bloc `climate` de `/api/v1/state` annonçait `MANUEL`, chauffage OFF, vitesse 2, seuil de
ventilation 26,0 °C et seuil d'extinction du chauffage 25,0 °C. `pinctrl` :

| Broche | Rôle | Lu | Attendu |
|---|---|---|---|
| 23 | Chauffage (actif-BAS) | `op hi` | OFF ✅ |
| 25 / 8 / 7 / 1 | Moteur (actif-HAUT) | `lo` / **`hi`** / `lo` / `lo` | vitesse 2, une seule broche HIGH ✅ |
| 5 | Minuterie journalière 1 | `op lo` | ON ✅ |
| 18 | Minuterie journalière 2 | `op lo` | ON ✅ |
| 27 | Cyclique 1 | `op lo` | ON (phase séquentielle) ✅ |
| 22 | Cyclique 2 | `op hi` | OFF ✅ |

Aucun écart entre l'état publié et l'état électrique.

## État persisté

`param/runtime_state.json` créé au démarrage, propriétaire `progradius`, contenant les deux
sections attendues :

- `climate` : fenêtre de budgets ouverte à 00:48:31, renouvellement et déshumidification à 0 min
  (mode manuel : aucun budget consommé) ;
- `cyclic_1` : phase `on`, échéance cohérente avec `on_time_day = 9999 s`.

## Rechargement à chaud

| Contrôle | Résultat |
|---|---|
| `POST /conf/heater` avec la valeur courante | 303 |
| `climate_control` après le POST | `reloads=1`, `restarts=0`, `healthy=true`, `last_error=null` |
| GPIO 23 avant / après | `hi` / `hi` — **la sortie n'a pas bougé** |

C'est la vérification du correctif « pas d'état sûr sur rechargement volontaire » pour le nouveau
travail unique : un enregistrement de configuration ne fait pas clignoter le chauffage.

## Migration de `param.json`

Le `param.json` de production **ne contenait pas** les sept nouveaux champs après le déploiement :
`scripts/deploy.sh` préserve la configuration locale, et le dépôt n'écrase pas la production.
Pydantic appliquait donc ses valeurs par défaut, ce que confirmait `/api/v1/state`
(seuil 26,0 °C, budgets 5 et 15 min/h).

Le premier enregistrement d'une section les a matérialisés dans le fichier, exactement ceux
attendus, sans autre écart :

```
Temperature_Settings : + vent_deadband 1.0, vent_step 1.0, vent_release 0.5,
                         absolute_floor_temp 5.0, min_dwell_seconds 120
Motor_Settings       : + sensor_fallback_speed 0, winter_humidity_minutes_per_hour 15
```

**Conséquence d'exploitation** : après un déploiement, les nouveaux réglages existent et sont
actifs (valeurs par défaut) avant même d'apparaître dans le fichier. Le fichier n'est donc pas la
référence de ce qui s'applique — `/api/v1/state` l'est.

## Interface web

Toutes les routes répondent : `/`, `/conf`, `/console`, `/api/v1/state`, `/health/live`,
`/health/ready`, `/status` en 200, `/monitor` en 303. Les sept nouveaux champs sont rendus dans
`/conf` et la carte « Régulation thermique » est présente sur le tableau de bord.

## Capteurs, export et journal

- BME280 : température, humidité et pression en `ok`, âge 3 s.
- InfluxDB : mesure `air` alimentée toutes les 60 s, dernier point 25 s avant le relevé.
- DS18B20 : toujours sans mesure (`water` vide) — cause matérielle connue, hors périmètre.
- Journal : **65 lignes en trois minutes**, aucune erreur, aucune trace d'exception. La régulation
  n'émet qu'une ligne INFO par changement d'état, conformément à « journaliser les transitions ».
- Rotation quotidienne confirmée : `logs/phyto.log.2026-08-25.gz` présent aux côtés de
  `logs/phyto.log`.

## Deux défauts trouvés par ce relevé

Ils ne sont pas des régressions de comportement dangereuses, mais ils faussaient le réglage et la
lecture ; ils sont corrigés dans le commit suivant et **ne sont pas encore déployés**.

1. **Zone morte appliquée alors que le chauffage est désactivé.** Le seuil de ventilation était
   relevé à 26 °C sur une serre dont le chauffage est coupé : il n'y avait pas deux organes à
   séparer, et la serre montait donc d'un degré de plus que la consigne, sans contrepartie. Le
   seuil vaut désormais la consigne haute telle quelle quand `Heater_Settings.enabled` est faux.
2. **Vocabulaire d'alarme pour un ajustement volontaire.** Le relèvement du seuil passait par
   `StateLogger`, qui écrit « … **en échec** » puis « rétabli après N échec(s) ». Un exploitant y
   lit une panne. Le message est désormais dédupliqué sur la valeur du seuil et formulé comme ce
   qu'il est : une consigne trop basse pour laisser une zone morte, avec le réglage à modifier.

## TODO différé jusqu'à l'activation de la régulation automatique

**Décision opérateur du 28 août 2026** : la qualification thermique dynamique est volontairement
reportée au moment où le chauffage et le mode automatique seront activés. Ce report n'est ni un
défaut observé ni un motif de rollback. L'observation continue menée avec chauffage désactivé et
moteur manuel qualifie la stabilité du service, du superviseur, des capteurs, des minuteries et du
suivi demandé/réel des sorties ; elle ne qualifie pas une régulation qui n'était pas autorisée à agir.

À cette activation, réaliser un essai supervisé et conserver les snapshots API, les journaux et les
états GPIO couvrant au minimum :

- un franchissement réel des seuils de chauffe, avec extinction par hystérésis ;
- la limite de chauffe continue et le repos forcé qui la suit ;
- le passage et le relâchement des paliers de ventilation en mode automatique, avec respect du temps
  minimal de maintien ;
- l'absence d'activation simultanée du chauffage et de l'extraction ;
- un épisode froid et humide en mode hiver, afin de voir les budgets distincts de renouvellement et
  de déshumidification se consommer, se borner puis se réarmer ;
- la concordance entre décision publiée, état logique et niveau électrique réel des GPIO.

Ce TODO est également suivi dans la [roadmap](../roadmap.md#arbitre-thermique) et dans le
[registre des risques](../risk-register.md).
