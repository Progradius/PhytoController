# Référence de configuration

**Source de vérité** : `param/config.py`.
**Format actuel** : JSON avec sections PascalCase et booléens legacy `enabled`/`disabled`.
**Sécurité** : ne jamais publier le fichier réel, qui contient des secrets.

## Chargement et sauvegarde

`AppConfig.load()` lit `param/param.json` et valide avec Pydantic v2. `save()` sérialise par alias, reconvertit les booléens legacy et écrit atomiquement. Les boucles ne consomment pas encore toutes la configuration de la même façon ; la colonne « application » décrit l'état actuel, pas une garantie idéale.

## Sections

| Section JSON | Modèle | Usage | Application actuelle |
|---|---|---|---|
| `Life_Period` | `LifePeriod` | Stade affiché/métier | Objet partagé, comportement limité |
| `DailyTimer1_Settings` | `DailyTimerSettings` | Sortie journalière 1 | Relue en boucle |
| `DailyTimer2_Settings` | `DailyTimerSettings` | Sortie journalière 2 | Relue en boucle |
| `Cyclic1_Settings` | `CyclicSettings` | Sortie cyclique 1 | Relue par itération, parfois tardivement |
| `Cyclic2_Settings` | `CyclicSettings` | Sortie cyclique 2 | Relue par itération, parfois tardivement |
| `Temperature_Settings` | `TemperatureSettings` | Consignes moteur/chauffage | Objet initial muté par `/conf` |
| `Heater_Settings` | `HeaterSettings` | Activation chauffage | Objet initial muté par `/conf` |
| `Network_Settings` | `NetworkSettings` | Wi-Fi et InfluxDB | Partiel ; secrets présents |
| `GPIO_Settings` | `GPIOSettings` | Broches | Redémarrage obligatoire et intervention matérielle |
| `Motor_Settings` | `MotorSettings` | Modes et consignes moteur | Objet initial muté par `/conf` |
| `Sensor_State` | `SensorState` | Capteurs activés | Nouveau contrôleur côté web/Influx, anciennes boucles inchangées |
| `Log_Settings` | `LogSettings` | Niveau et rétention | À chaud |

## Timers journaliers

| Champ | Type | Contraintes actuelles | Unité / remarque |
|---|---|---|---|
| `enabled` | bool legacy | Conversion permissive | `enabled`/`disabled` au disque |
| `start_hour` | int | Pas de borne Pydantic explicite | 0–23 attendu |
| `start_minute` | int | Pas de borne explicite | 0–59 attendu |
| `stop_hour` | int | Pas de borne explicite | 0–23 attendu |
| `stop_minute` | int | Pas de borne explicite | 0–59 attendu |

Les plages traversant minuit sont gérées. Les bornes manquantes doivent être ajoutées avant de considérer l'interface comme sûre face à toute saisie.

## Timers cycliques

| Champ | Type | Contraintes | Signification |
|---|---|---|---|
| `enabled` | bool legacy | Conversion permissive | Activation |
| `mode` | enum | `journalier` ou `séquentiel` | Algorithme |
| `period_days` | int | >= 1 | Période journalière |
| `triggers_per_day` | int | >= 1 | Déclenchements par jour |
| `first_trigger_hour` | int | 0–23 | Première heure |
| `action_duration_seconds` | int | > 0 | Durée ON |
| `on_time_day` | int | Aucune borne | Secondes ON le jour |
| `off_time_day` | int | Aucune borne | Secondes OFF le jour |
| `on_time_night` | int | Aucune borne | Secondes ON la nuit |
| `off_time_night` | int | Aucune borne | Secondes OFF la nuit |

Une désactivation peut être prise en compte tardivement si la boucle dort sur une longue période métier. Le futur ordonnanceur doit recalculer des échéances absolues à intervalle court.

## Température et chauffage

`Temperature_Settings` contient cinq flottants sans contraintes croisées : minimum et maximum jour/nuit, plus `hysteresis_offset`. Il faut actuellement vérifier manuellement que minimum < maximum et que les seuils n'ordonnent pas chauffage et ventilation simultanément.

`Heater_Settings.enabled` active la régulation. Les limites de sécurité -20/60 °C, cinq échecs, 120 minutes ON et 15 minutes OFF sont des constantes de code, pas des champs de configuration.

## Moteur

| Champ | Type / borne | Remarque |
|---|---|---|
| `motor_mode` | `manual`, `auto`, `winter` | Mode principal |
| `motor_user_speed` | int sans borne modèle | 0–4 attendu |
| `target_temp` | float | Consigne auto |
| `hysteresis` | float | Hystérésis auto |
| `min_speed` | int sans borne modèle | 0–4 attendu |
| `max_speed` | int sans borne modèle | 0–4 attendu et >= min |
| `winter_default_speed` | 0–4 | Vitesse hors renouvellement |
| `winter_temp_margin` | >= 0 | Marge froid |
| `winter_refresh_speed` | 0–4 | Vitesse renouvellement |
| `winter_refresh_minutes_per_hour` | 0–60 | Quota |
| `winter_humidity_threshold` | 0–100 | Seuil RH |

Les contraintes croisées et la politique thermique restent ouvertes.

## GPIO

Tous les champs sont des entiers sans validation d'unicité ni liste noire. Une modification GPIO exige arrêt, vérification du câblage et redémarrage. Voir la [matrice GPIO](../hardware/gpio-matrix.md). Ne jamais considérer un POST `/conf` comme une méthode sûre de recâblage à chaud.

## Réseau et secrets

`Network_Settings` contient adresse et état de l'hôte, SSID/mot de passe Wi-Fi et paramètres InfluxDB. `wifi_password` et `influx_db_password` sont des secrets. `wifi_ssid`, hôte, base et utilisateur peuvent aussi révéler la topologie.

La cible est de ne conserver dans le JSON que les paramètres non sensibles et d'injecter les secrets depuis un fichier d'environnement protégé par systemd.

## Logs

- `level` : DEBUG, INFO, WARNING ou ERROR ;
- `retention_days` : entier >= 1 ;
- priorité : `PHYTO_LOG_LEVEL` > fichier > INFO ;
- application immédiate après POST `/conf`.

## Règle de modification

Toute évolution de schéma doit : ajouter les contraintes, préserver le round-trip legacy si nécessaire, fournir une migration de la configuration vivante, mettre à jour ce document et être testée sur une copie sans afficher les secrets.
