# Référence de configuration

**Source de vérité** : `param/config.py`.
**Format actuel** : JSON avec sections PascalCase et booléens legacy `enabled`/`disabled`.
**Sécurité** : ne jamais publier le fichier réel, qui contient des secrets.

## Chargement et sauvegarde

`AppConfig.load()` lit `param/param.json` et valide avec Pydantic v2. `save()` sérialise par alias, reconvertit les booléens legacy et écrit atomiquement. Les boucles ne consomment pas encore toutes la configuration de la même façon ; la colonne « application » décrit l'état actuel, pas une garantie idéale.

Tous les modèles héritent de `ValidatedModel` (`validate_assignment=True`, `populate_by_name=True`) : une affectation invalide lève au lieu de corrompre silencieusement la configuration vivante. `AppConfig.replace_from(candidat)` remplace champ par champ la configuration partagée par une candidate déjà validée — c'est ainsi que `POST /conf/{section}` publie un changement sans réinstancier les objets que détiennent le serveur, le moteur et le chauffage.

## Sections

| Section JSON | Modèle | Usage | Application actuelle |
|---|---|---|---|
| `Life_Period` | `LifePeriod` | Stade affiché/métier | Objet partagé, comportement limité |
| `DailyTimer1_Settings` | `DailyTimerSettings` | Sortie journalière 1 | Relue en boucle |
| `DailyTimer2_Settings` | `DailyTimerSettings` | Sortie journalière 2 | Relue en boucle |
| `Day_Night_Settings` | `DayNightSettings` | Référence globale jour/nuit | À chaud ; héritage explicite ou horaires personnalisés |
| `Cyclic1_Settings` | `CyclicSettings` | Sortie cyclique 1 | Relue par itération, parfois tardivement |
| `Cyclic2_Settings` | `CyclicSettings` | Sortie cyclique 2 | Relue par itération, parfois tardivement |
| `Temperature_Settings` | `TemperatureSettings` | Consignes et arbitrage thermique | À chaud : relance de `climate_control` |
| `Heater_Settings` | `HeaterSettings` | Activation chauffage | À chaud : relance de `climate_control` |
| `Network_Settings` | `NetworkSettings` | Wi-Fi et InfluxDB | Influx à chaud ; Wi-Fi au redémarrage ; secrets présents |
| `GPIO_Settings` | `GPIOSettings` | Broches | **Lecture seule dans l'IHM** ; redémarrage et intervention matérielle |
| `Motor_Settings` | `MotorSettings` | Modes et consignes moteur | À chaud : relance de `climate_control` |
| `Sensor_State` | `SensorState` | Capteurs activés | À chaud : `SensorController.reconfigure()` sur l'instance unique, puis rechargement Influx |
| `Sensor_Quality` | `SensorQualitySettings` | Calibration, fraîcheur, plausibilité, figement, identités et redondance | À chaud ; mode observation par défaut, armement explicite du repli qualité |
| `Log_Settings` | `LogSettings` | Niveau et rétention | À chaud |

## Calibration et qualité des capteurs

`Sensor_Quality.mode` vaut `observe` par défaut. Dans ce mode, les diagnostics sont publiés et
alarmés, mais un figement plausible ou un désaccord redondant ne modifie pas encore les sorties.
Le passage à `enforce` exige la confirmation littérale `ARMER` dans l'IHM ; une incohérence déjà
confirmée sur `BME280T` déclenche alors immédiatement `REPLI_CAPTEUR` sans attendre cinq erreurs
d'acquisition. Les valeurs hors plage et périmées ne sont jamais autorisées, quel que soit le mode.

`profiles` est indexé par la clé canonique (`BME280T`, `DS18B#1`, etc.). Chaque profil peut
surcharger l'offset additif, la date et la durée de validité de calibration, le seuil de fraîcheur,
la plage plausible, l'epsilon de variation, la durée et le nombre minimal d'échantillons nécessaires
pour déclarer un figement. `freeze_after_seconds: "disabled"` désactive seulement ce diagnostic.
Les plages configurées doivent rester incluses dans les limites matérielles du catalogue.

`ds18b20_bindings` lie chaque nom métier DS18B à son identifiant 1-Wire stable au format
`28-xxxxxxxxxxxx`. Une sonde activée mais non liée est déclarée absente : l'ordre de découverte
sysfs ne doit jamais déplacer une calibration d'une sonde physique à une autre.

`redundancy_groups` contient des groupes de mesures de même unité, une tolérance et un quorum.
Une mesure ne peut appartenir qu'à un groupe. Avec deux sondes en désaccord, aucune n'est choisie
arbitrairement ; avec trois sondes ou plus, le plus grand groupe cohérent identifie les valeurs
divergentes. Trois comparaisons cohérentes consécutives sont requises pour sortir du diagnostic.

Modifier l'offset ou la date de calibration réinitialise les compteurs qualité et les min/max de la
mesure concernée. L'état de figement et les compteurs sont conservés dans
`param/runtime_state.json`; les instants monotones ne sont volontairement pas restaurés.

## Timers journaliers

| Champ | Type | Contraintes actuelles | Unité / remarque |
|---|---|---|---|
| `enabled` | bool legacy | Conversion permissive | `enabled`/`disabled` au disque |
| `start_hour` | int | 0–23 | Borné dans le modèle |
| `start_minute` | int | 0–59 | Borné dans le modèle |
| `stop_hour` | int | 0–23 | Borné dans le modèle |
| `stop_minute` | int | 0–59 | Borné dans le modèle |

Les plages traversant minuit sont gérées avec une sémantique unique `[début, fin)` : la borne de fin est exclue et `début == fin` décrit une plage vide. L'IHM poste `start_time`/`stop_time` au format `HH:MM` (les secondes éventuelles d'un navigateur sont ignorées) ; une valeur hors bornes est refusée en 422 sans toucher au fichier.

## Référence jour/nuit

`Day_Night_Settings.source` vaut `dailytimer1` ou `custom`. Avec `dailytimer1`, le climat et les cycles séquentiels suivent en continu les horaires de la minuterie 1 ; les quatre horaires personnalisés restent mémorisés sans être utilisés. Avec `custom`, ils définissent la plage jour selon la même règle `[début, fin)`. Avant une preuve NTP, le climat et les cycles séquentiels utilisent toujours les paramètres nuit.

## Timers cycliques

| Champ | Type | Contraintes | Signification |
|---|---|---|---|
| `enabled` | bool legacy | Conversion permissive | Activation |
| `mode` | enum | `journalier` ou `séquentiel` | Algorithme |
| `period_days` | int | >= 1 | Période journalière |
| `triggers_per_day` | int | >= 1 | Déclenchements par jour |
| `first_trigger_hour` | int | 0–23 | Première heure |
| `action_duration_seconds` | int | > 0 | Durée ON |
| `on_time_day` | int | >= 0 | Secondes ON le jour |
| `off_time_day` | int | >= 0 | Secondes OFF le jour |
| `on_time_night` | int | >= 0 | Secondes ON la nuit |
| `off_time_night` | int | >= 0 | Secondes OFF la nuit |

Le mode journalier recalcule une échéance strictement future toutes les 30 secondes : aucune impulsion passée n'est rattrapée. Les longues attentes restent donc réactives à un hand-edit de configuration. Le mode séquentiel conserve sa phase persistée et utilise les paramètres nuit tant que l'heure n'est pas synchronisée.

## Métadonnées d'équipements

`param/equipment_metadata.json` est volontairement séparé de `param.json` et écrit atomiquement. Il indexe `daily_1`, `daily_2`, `cyclic_1`, `cyclic_2`, `motor` et `heater`. Les champs descriptifs (`display_name`, `usage_type`, `zone`, `icon`, `wiring_note`, `dashboard_visible`, `out_of_service`) n'ont aucun effet sur le contrôle. Les booléens sont des booléens JSON natifs. Un fichier absent ou illisible rend le catalogue par défaut sans empêcher le démarrage.

## Température et chauffage

`Temperature_Settings` porte les consignes jour/nuit **et** l'arbitrage entre chauffage et ventilation.

| Champ | Type / borne | Rôle |
|---|---|---|
| `target_temp_min_day` / `_night` | -20 à 60 °C | Seuil d'allumage du chauffage |
| `target_temp_max_day` / `_night` | -20 à 60 °C | Consigne haute, base du seuil de ventilation |
| `hysteresis_offset` | 0 à 20 °C | Bande morte du **chauffage** seul : extinction à `min + hysteresis_offset` |
| `vent_deadband` | 0 à 20 °C | Écart minimal entre extinction du chauffage et démarrage de la ventilation |
| `vent_step` | > 0 à 20 °C | Largeur d'un palier de vitesse |
| `vent_release` | 0 à 20 °C | Seuil de relâchement d'un palier (hystérésis à état) |
| `absolute_floor_temp` | -20 à 60 °C | Plancher absolu : aucune ventilation au-dessous |
| `min_dwell_seconds` | 0 à 3600 s | Temps de maintien minimal entre deux changements de vitesse |

Un validateur de modèle refuse un minimum supérieur au maximum, de jour comme de nuit. **La cohérence chauffage/ventilation n'est plus à la charge de l'exploitant** : le seuil de ventilation effectif vaut `max(target_temp_max, target_temp_min + hysteresis_offset + vent_deadband)`. Si la consigne haute est trop basse, le seuil est relevé, un WARNING dédupliqué le signale et `/api/v1/state` publie la valeur effective — la configuration n'est jamais refusée pour autant.

**Exception** : `Heater_Settings.enabled` à faux, le seuil de ventilation vaut `target_temp_max` sans relèvement. Il n'y a alors pas deux organes à séparer, et décaler la ventilation ne ferait que laisser monter la serre.

**Le fichier n'est pas la référence de ce qui s'applique.** Un champ absent de `param.json` prend sa valeur par défaut et régule immédiatement ; il n'apparaît dans le fichier qu'au premier enregistrement d'une section depuis `/conf`. C'est ce qui s'est produit au déploiement de la phase 2 sur le Pi : les sept nouveaux champs étaient actifs avant d'être écrits. Pour savoir ce qui s'applique réellement, lire `/api/v1/state`, pas le fichier.

`Heater_Settings.enabled` active la régulation. Les limites de sécurité -20/60 °C, cinq échecs, 120 minutes ON et 15 minutes OFF sont des constantes de code (`components/climate_policy.py`), pas des champs de configuration.

## Moteur

| Champ | Type / borne | Remarque |
|---|---|---|
| `motor_mode` | `manual`, `auto`, `winter` | Mode principal |
| `motor_user_speed` | 0–4 | Vitesse manuelle |
| `target_temp` | -20 à 60 °C | Consigne auto |
| `hysteresis` | 0 à 20 °C | Hystérésis auto |
| `min_speed` | 0–4 | Borné dans le modèle ; ne remonte **jamais** un ordre d'arrêt |
| `sensor_fallback_speed` | 0–4 | Vitesse en état `REPLI_CAPTEUR` (défaut 0) |
| `max_speed` | 0–4 | Borné, et `min_speed <= max_speed` vérifié par validateur de modèle |
| `winter_default_speed` | 0–4 | Vitesse hors renouvellement |
| `winter_temp_margin` | >= 0 | Marge froid |
| `winter_refresh_speed` | 0–4 | Vitesse renouvellement |
| `winter_refresh_minutes_per_hour` | 0–60 | Budget horaire de renouvellement d'air |
| `winter_humidity_threshold` | 0–100 | Seuil RH déclenchant la déshumidification |
| `winter_humidity_minutes_per_hour` | 0–60 | Budget horaire de déshumidification, **distinct** du précédent (0 = désactivée) |

`target_temp` et `hysteresis` ne sont pas exposés par l'IHM et ne sont plus lus par la régulation : celle-ci utilise `Temperature_Settings`. Les deux budgets hiver sont comptés en minutes **réellement écoulées** sur une fenêtre glissante d'une heure, et persistés dans `param/runtime_state.json` : un redémarrage ne réaccorde plus une fenêtre complète.

## GPIO

Tous les champs sont des entiers sans validation d'unicité ni liste noire. L'IHM les affiche en **lecture seule** et aucune section `/conf/{section}` n'y donne accès : une modification passe par l'édition du fichier. Elle exige arrêt, vérification du câblage et redémarrage. Voir la [matrice GPIO](../hardware/gpio-matrix.md). Ne jamais considérer un POST `/conf` comme une méthode sûre de recâblage à chaud.

## Réseau et secrets

`Network_Settings` contient adresse et état de l'hôte, SSID/mot de passe Wi-Fi et paramètres InfluxDB. `host_machine_state` est restreint à `online`/`offline` et `influx_db_port` doit être un entier de 1 à 65535. `wifi_password` et `influx_db_password` sont des secrets. `wifi_ssid`, hôte, base et utilisateur peuvent aussi révéler la topologie.

L'IHM n'affiche plus aucune valeur secrète : `wifi_password`, `influx_db_user` et `influx_db_password` sont rendus vides, avec la seule indication qu'une valeur est ou non enregistrée. Un champ laissé vide conserve la valeur existante ; il n'est donc pas possible d'effacer un secret depuis le web.

La cible est de ne conserver dans le JSON que les paramètres non sensibles et d'injecter les secrets depuis un fichier d'environnement protégé par systemd.

## Logs

- `level` : DEBUG, INFO, WARNING ou ERROR ;
- `retention_days` : entier >= 1 ;
- priorité : `PHYTO_LOG_LEVEL` > fichier > INFO ;
- application immédiate après POST `/conf`.

## Règle de modification

Toute évolution de schéma doit : ajouter les contraintes, préserver le round-trip legacy si nécessaire, fournir une migration de la configuration vivante, mettre à jour ce document et être testée sur une copie sans afficher les secrets.
