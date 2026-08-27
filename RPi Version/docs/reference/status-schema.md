# Schémas d'état JSON

Deux formats coexistent : `/api/v1/state`, versionné et destiné à l'IHM comme à
l'automatisation, et `/status`, conservé tel quel pour ne pas casser les scripts existants.

## `/api/v1/state` (schéma 2)

Exemple abrégé, sans valeurs de production :

```json
{
  "schema_version": 2,
  "version": "0123456789abcdef0123456789abcdef01234567",
  "generated_at": "2026-08-25T21:14:03.512Z",
  "web": {"https": {"configured": true, "ready": true, "port": 443}},
  "health": {
    "healthy": true,
    "control_healthy": true,
    "heater_alarm": null,
    "tasks": {
      "climate_control": {
        "alive": true, "healthy": true, "silence_s": 4.2, "max_silence_s": 300.0,
        "restarts": 0, "reloads": 1, "stalls": 0, "last_error": null
      }
    }
  },
  "time": {
    "state": "synchronized", "observed_state": "synchronized",
    "daily_timers_suspended": false, "alarm": null
  },
  "day_night": {"source": "dailytimer1", "start": "19:00", "stop": "07:00", "empty": false},
  "equipment": {"daily_1": {"display_name": "Éclairage 1", "dashboard_visible": true}},
  "actuators": {
    "daily_1": {
      "requested": "on", "actual": "on", "reason": "dans la plage [début, fin)",
      "since_seconds": 121.4, "stale": false, "tracking": "ok",
      "next_transition": {"type": "clock", "at": "07:00"}
    }
  },
  "outputs": {
    "daily_timer_1": "on", "daily_timer_2": "off",
    "cyclic_1": "off", "cyclic_2": "off", "heater": "off"
  },
  "motor": {"speed": 2, "percent": 50},
  "climate": {
    "state": "VENTILER",
    "reason": "chauffage : 27.4°C > 25.0°C · ventilation : 27.4°C ≥ 26.0°C → palier 2",
    "heater_on": false, "motor_speed": 2,
    "temperature": 27.4, "humidity": 52.1,
    "vent_threshold": 26.0, "heater_off_threshold": 25.0,
    "renew_minutes_used": 0.0, "renew_minutes_quota": 5.0,
    "humidity_minutes_used": 0.0, "humidity_minutes_quota": 15.0,
    "updated_at": "2026-08-25T21:14:00"
  },
  "timers": [
    {"id": "daily-1", "kind": "daily", "enabled": true, "output": "daily_timer_1",
     "schedule": {"start": "19:00", "stop": "07:00"}},
    {"id": "cyclic-1", "kind": "cyclic", "enabled": false, "output": "cyclic_1",
     "schedule": {"mode": "journalier", "period_days": 1, "triggers_per_day": 2,
                  "first_trigger_hour": 8, "action_duration_seconds": 30}}
  ],
  "sensors": [
    {"key": "BME280T", "family": "BME280", "label": "Température de l’air",
     "unit": "°C", "decimals": 1, "enabled": true, "status": "normal",
     "acquisition_status": "ok", "value": 21.4, "observed_value": 21.4,
     "raw_value": 21.2, "control_usable": true, "would_block_control": false,
     "control_disposition": "trusted", "reason_codes": [],
     "last_attempt_at": "2026-08-25T21:14:01Z", "last_success_at": "2026-08-25T21:14:01Z",
     "last_trusted_at": "2026-08-25T21:14:01Z", "age_s": 2.1,
     "unchanged_for_s": 0.0, "freshness_threshold_s": 20.0,
     "plausible_range": {"min": -20.0, "max": 60.0},
     "calibration": {"offset": 0.2, "calibrated_at": "2026-08-01", "valid_days": 365, "overdue": false},
     "failures": {"consecutive": 0, "since_calibration": 0,
                  "incoherences_since_calibration": 0, "last_at": null},
     "redundancy": {"group": null, "status": "not_configured", "delta": null}}
  ],
  "stats": [
    {"key": "BME280T", "min": 14.2, "min_at": "2026-08-20T05:11:02",
     "max": 31.8, "max_at": "2026-08-23T15:47:40"}
  ]
}
```

| Champ | Sens |
|---|---|
| `schema_version` | Entier ; toute évolution non additive doit l'incrémenter |
| `version` | Commit Git figé au chargement du processus, ou valeur explicite de `PHYTO_VERSION` hors checkout |
| `generated_at` | Instant de génération, UTC ISO 8601 suffixé `Z` |
| `web.https` | Configuration, disponibilité réelle et port du second point d'écoute HTTPS ; aucun chemin de clé ou de certificat n'est publié |
| `health.healthy` | Santé agrégée du superviseur |
| `health.control_healthy` | Santé des seuls timers, climat et acquisition qui gouvernent le watchdog |
| `health.domains` | Santé regroupée par domaine, contrôle et auxiliaires distingués |
| `health.heater_alarm` | `null` ou texte d'alarme thermique persistante (nom historique conservé) |
| `health.tasks` | Snapshot par travail supervisé |
| `outputs` | État **logique** de chaque sortie : `on`, `off` ou `unknown` |
| `time` | Fiabilité de l'heure, suspension bornée des minuteries et alarme éventuelle |
| `day_night` | Source et plage jour/nuit effectivement résolues |
| `equipment` | Métadonnées descriptives, sans effet sur le contrôle |
| `actuators` | Consigne, relecture GPIO instantanée, motif, durée monotone, prochaine transition et suivi demandé/réel |
| `motor.speed` / `motor.percent` | Vitesse logique 0–4 et son pourcentage |
| `climate.state` | État de l'arbitre : `DESACTIVE`, `CHAUFFER`, `NEUTRE`, `VENTILER`, `RENOUVELER`, `DESHUMIDIFIER`, `SECURITE_HAUTE`, `PLANCHER_THERMIQUE`, `REPLI_CAPTEUR`, `MANUEL` |
| `climate.reason` | Motif lisible de la décision, chauffage puis ventilation |
| `climate.vent_threshold` | Seuil de ventilation **effectif** (relevé si la consigne haute ne laissait pas de zone morte) |
| `climate.heater_off_threshold` | Seuil d'extinction du chauffage |
| `climate.*_minutes_used` / `_quota` | Budgets hiver consommés et alloués sur la fenêtre d'une heure en cours |
| `climate.updated_at` | Horodatage local du dernier tick de régulation ; `null` avant le premier |
| `timers` | Planification effective, telle que la lira la boucle |
| `sensors` | Uniquement les mesures **activées**, dans l'ordre du catalogue |
| `stats` | Min/max suivis et leurs horodatages locaux |

Pour un capteur, `status` vaut :

- `normal` : mesure fraîche, plausible et cohérente ;
- `degraded` : mesure encore qualifiée mais assortie d'une réserve, par exemple calibration expirée ou redondance indisponible ;
- `absent` : aucune mesure fraîche et exploitable, après erreurs de lecture ou expiration du seuil de fraîcheur ;
- `inconsistent` : valeur acquise mais hors plage, figée ou en désaccord avec son groupe redondant ;
- `disabled` : capteur désactivé dans `Sensor_State` (absent de `sensors`).

`raw_value` est la lecture matérielle, `observed_value` cette lecture après offset, et `value`
uniquement la valeur **qualifiée**. Une valeur incohérente reste visible dans `observed_value` pour
le diagnostic, mais `value` vaut `null`. `control_usable` est l'autorité explicite pour le contrôle :
en mode `observe`, un figement ou un désaccord redondant peut être publié comme
`shadow_accepted`; en mode `enforce`, la même décision devient immédiatement `blocked` sans
attendre une nouvelle lecture. Une valeur hors plage, absente ou périmée est toujours bloquée.

`reason_codes` explique la décision (`frozen`, `out_of_range`, `stale`,
`redundancy_mismatch`, `calibration_overdue`, etc.). `age_s` porte l'âge de la dernière valeur
qualifiée, tandis que `attempt_age_s` porte l'âge de la dernière tentative.

Aucune lecture matérielle n'est déclenchée par une requête HTTP : le job supervisé
`sensor_snapshot` rafraîchit l'instantané toutes les 10 s, l'IHM et InfluxDB le consomment.

## `/api/v1/alarms/active` (schéma 1)

Ce snapshot contient `schema_version`, `generated_at`, le résumé d'alarmes et les occurrences actives
déjà tenues en mémoire par `AlarmManager`. Il ne consulte ni SQLite, ni GPIO, ni capteur. La PWA
l'interroge toutes les cinq secondes lorsqu'elle est exécutée ; une occurrence conserve le même UUID
tant qu'elle reste active, ce qui permet la déduplication locale des notifications.

Pour une tâche :

- `alive` : runner présent ;
- `healthy` : vivant et pas au-delà du silence autorisé ;
- `silence_s` : ancienneté du heartbeat ;
- `max_silence_s` : limite, `null` pour HTTP ;
- `restarts` : relances après panne ou fin inattendue ;
- `reloads` : relances **volontaires** après changement de configuration ;
- `stalls` : blocages silencieux détectés ;
- `last_error` : dernière erreur connue.
- `domain` : domaine de santé affiché ;
- `gates_watchdog` : indique si cette tâche participe à `control_healthy`.

Le registre `actuators` ne conserve jamais l'état matériel réel : celui-ci est relu pendant la requête HTTP. Une publication métier plus vieille que deux périodes porte `stale=true`, une consigne `unknown` et un suivi `unknown`. `tracking=known_hardware_fault` signifie que l'écart demandé/relu est couvert par l'annotation `out_of_service`, non qu'il est résolu.

## `/health/live` et `/health/ready`

```json
{"live": true}
{"ready": false, "unhealthy": ["climate_control"]}
```

`/health/live` répond 200 tant que le serveur HTTP tourne : il ne prouve rien sur la
régulation. `/health/ready` répond **503** dès qu'un travail supervisé est en défaut et nomme
les fautifs. C'est la sonde à brancher sur une supervision externe.

## `/status` (ancien format)

```json
{
  "component_state": "Enabled",
  "motor_speed": 2,
  "dailytimer1": {"start": "19:00", "stop": "07:00"},
  "cyclic": {"period": 1, "duration": 30},
  "heater_alarm": null,
  "healthy": true,
  "control_healthy": true,
  "time": {"state": "synchronized"},
  "tasks": {}
}
```

Les champs historiques restent figés ; les ajouts `control_healthy`, `time` et `health_domains`
sont additifs. `cyclic.period` est désormais une période en **jours** (`period_days`) ; le contournement par
`getattr` a disparu en même temps que le champ `period_minutes` inexistant lu par
`SystemStatus.get_cyclic_period()`. Les détails d'actionneurs restent réservés à `/api/v1/state`.

## Interprétation

Une réponse HTTP 200 ne signifie pas `healthy=true` : les outils d'exploitation doivent
analyser le JSON, ou interroger `/health/ready` dont le **code** porte l'information. Un état
logique ne prouve pas l'état mécanique des relais.
