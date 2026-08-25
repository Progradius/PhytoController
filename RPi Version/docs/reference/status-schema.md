# Schémas d'état JSON

Deux formats coexistent : `/api/v1/state`, versionné et destiné à l'IHM comme à
l'automatisation, et `/status`, conservé tel quel pour ne pas casser les scripts existants.

## `/api/v1/state` (schéma 1)

Exemple abrégé, sans valeurs de production :

```json
{
  "schema_version": 1,
  "generated_at": "2026-08-25T21:14:03.512Z",
  "health": {
    "healthy": true,
    "heater_alarm": null,
    "tasks": {
      "climate_control": {
        "alive": true, "healthy": true, "silence_s": 4.2, "max_silence_s": 300.0,
        "restarts": 0, "reloads": 1, "stalls": 0, "last_error": null
      }
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
    {"key": "BME280T", "label": "Température de l’air", "unit": "°C", "decimals": 1,
     "enabled": true, "status": "ok", "value": 21.4,
     "last_attempt_at": "2026-08-25T21:14:01Z", "last_success_at": "2026-08-25T21:14:01Z",
     "age_s": 2.1}
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
| `generated_at` | Instant de génération, UTC ISO 8601 suffixé `Z` |
| `health.healthy` | Santé agrégée du superviseur |
| `health.heater_alarm` | `null` ou texte d'alarme thermique persistante (nom historique conservé) |
| `health.tasks` | Snapshot par travail supervisé |
| `outputs` | État **logique** de chaque sortie : `on`, `off` ou `unknown` |
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

- `ok` : dernière tentative réussie et datant de moins de 30 s ;
- `stale` : dernière réussite trop ancienne — `value` est la **dernière valeur connue** ;
- `error` : dernière tentative en échec ;
- `never` : aucune tentative depuis le démarrage ;
- `disabled` : capteur désactivé dans `Sensor_State` (absent de `sensors`).

`value` est toujours la dernière valeur **valide** connue, jamais une valeur inventée ; `age_s`
donne son ancienneté. Une valeur affichée avec `status` différent de `ok` ne doit pas être
utilisée comme mesure courante.

Aucune lecture matérielle n'est déclenchée par une requête HTTP : le job supervisé
`sensor_snapshot` rafraîchit l'instantané toutes les 10 s, l'IHM et InfluxDB le consomment.

Pour une tâche :

- `alive` : runner présent ;
- `healthy` : vivant et pas au-delà du silence autorisé ;
- `silence_s` : ancienneté du heartbeat ;
- `max_silence_s` : limite, `null` pour HTTP ;
- `restarts` : relances après panne ou fin inattendue ;
- `reloads` : relances **volontaires** après changement de configuration ;
- `stalls` : blocages silencieux détectés ;
- `last_error` : dernière erreur connue.

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
  "tasks": {}
}
```

`cyclic.period` est désormais une période en **jours** (`period_days`) ; le contournement par
`getattr` a disparu en même temps que le champ `period_minutes` inexistant lu par
`SystemStatus.get_cyclic_period()`. Ce format est figé : toute nouvelle information va dans
`/api/v1/state`.

## Interprétation

Une réponse HTTP 200 ne signifie pas `healthy=true` : les outils d'exploitation doivent
analyser le JSON, ou interroger `/health/ready` dont le **code** porte l'information. Un état
logique ne prouve pas l'état mécanique des relais.
