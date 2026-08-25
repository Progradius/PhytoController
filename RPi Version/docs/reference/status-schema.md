# Schéma de `/status`

Exemple sans valeurs de production :

```json
{
  "component_state": "Enabled",
  "motor_speed": 2,
  "dailytimer1": {"start": "19:00", "stop": "07:00"},
  "cyclic": {"period": 1, "duration": 30},
  "heater_alarm": null,
  "healthy": true,
  "tasks": {
    "heat_control": {
      "alive": true,
      "healthy": true,
      "silence_s": 4.2,
      "max_silence_s": 300.0,
      "restarts": 0,
      "stalls": 0,
      "last_error": null
    }
  }
}
```

| Champ | Sens |
|---|---|
| `component_state` | État du composant fourni à `SystemStatus`, actuellement la première sortie journalière |
| `motor_speed` | Vitesse logique 0–4 ; un état multi-relais dangereux peut aussi produire 0 |
| `dailytimer1` | Horaires courants de la première sortie |
| `cyclic` | Résumé du premier timer cyclique |
| `heater_alarm` | `null` ou texte d'alarme persistante |
| `healthy` | Santé agrégée du superviseur |
| `tasks` | Snapshot par travail enregistré |

Pour une tâche :

- `alive` : runner présent ;
- `healthy` : vivant et pas au-delà du silence autorisé ;
- `silence_s` : ancienneté du heartbeat ;
- `max_silence_s` : limite, `null` pour HTTP ;
- `restarts` : relances après panne ou fin inattendue ;
- `stalls` : blocages silencieux détectés ;
- `last_error` : dernière erreur connue.

## Interprétation

Une réponse HTTP 200 ne signifie pas que `healthy=true`. Les outils d'exploitation doivent analyser le JSON. Un état logique ne prouve pas l'état mécanique des relais. Le schéma n'est pas encore versionné comme API stable ; toute évolution doit rester additive ou être accompagnée d'une migration des consommateurs.
