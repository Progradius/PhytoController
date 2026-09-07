# Journalisation, capteurs et InfluxDB

## Journalisation

`utils.pretty_console` est l'unique façade. Les logs vont vers la console, `logs/phyto.log` et le flux SSE du processus courant.

| Fonction | Niveau |
|---|---|
| `debug`, `action`, `clock` | DEBUG |
| `info`, `success` | INFO |
| `warning` | WARNING |
| `error`, `exception` | ERROR |
| `critical` | CRITICAL |

Les événements sont en français et utilisent `name=` pour obtenir des loggers `phyto.<nom>` :
`phyto.climate` pour l'arbitre thermique, `phyto.state` pour la persistance de régulation,
`phyto.http`, `phyto.sensors`, `phyto.influx`, `phyto.supervisor`, `phyto.timer.daily`,
`phyto.timer.cyclic`. Les boucles doivent journaliser les transitions à INFO et les ticks à DEBUG. `StateLogger` produit une ligne à l'entrée en panne et une ligne au rétablissement.

La rotation est quotidienne, compression gzip, rétention configurable.

Elle est **paresseuse**, et c'est le comportement normal de `TimedRotatingFileHandler` : le basculement est déclenché par la première écriture *après* minuit, jamais par une minuterie. Sur un contrôleur en régime calme — les boucles journalisent leurs ticks en DEBUG, donc rien n'est écrit tant qu'aucun évènement ne survient — l'archive du jour précédent peut n'apparaître qu'avec plusieurs dizaines de minutes de retard. **Ne pas conclure à une panne de rotation sur la seule absence d'archive juste après minuit** : provoquer une ligne de log et vérifier à nouveau.

Constatée en conditions réelles le 26 août 2026 à 00:18 : `logs/phyto.log.2026-08-25.gz` (4,6 Kio) contient l'intégralité de la journée, `logs/phyto.log` repart à la première ligne, aucune erreur de rotation dans le fichier ni dans `journalctl -u phyto`.

## Capteurs

`controllers/sensor_catalog.py` est la **table canonique** des mesures : clé interne, famille matérielle, champ d'activation dans `Sensor_State`, measurement InfluxDB, libellé, unité, limites plausibles, fraîcheur et paramètres de figement par défaut. Toute nouvelle mesure s'ajoute là et nulle part ailleurs.

`SensorController` est l'unique propriétaire du matériel. Il ouvre `/dev/i2c-1` une fois et instancie seulement les handlers activés :

- BME280 : température, humidité, pression ;
- DS18B20 : température 1-Wire ;
- VEML6075 : UV ;
- VL53L0X : distance ;
- MLX90614 : température de surface ;
- TSL2591 : luminosité ;
- HC-SR04 : distance GPIO.

Toutes les lectures passent par un **exécuteur à un seul fil** : elles ne gèlent jamais l'event loop et ne s'exécutent jamais en parallèle sur le même bus. Une lecture échouée renvoie `None`. Tous les consommateurs doivent le traiter explicitement.

Le job supervisé `sensor_snapshot` rafraîchit les mesures actives toutes les 10 s et publie un instantané horodaté. Ce sont HTTP et InfluxDB qui le **consomment** : une requête web ne déclenche plus aucune lecture matérielle. Les boucles moteur et chauffage utilisent `fresh_value(clé, max_age=20)`, qui réutilise l'instantané s'il est frais et ne relit le capteur que sinon.

`controllers/sensor_quality.py` qualifie chaque tentative sans I/O : offset, plage plausible,
fraîcheur, compteur d'échecs, calibration échue, figement par durée **et** nombre d'échantillons,
puis comparaison redondante éventuelle. Les états publiés sont `normal`, `degraded`, `absent` et
`inconsistent`. Trois mesures réellement variables réarment un figement ; une simple oscillation
unique suivie d'une nouvelle constante ne suffit pas.

Le snapshot sépare `raw_value`, `observed_value` et `value` qualifiée. Le tableau de bord montre une
valeur suspecte comme telle au lieu de la transformer en donnée valide. Les compteurs et diagnostics
sont persistés atomiquement ; la date de calibration n'est déclarée échue que si l'horloge civile est
fiable. Les DS18B20 sont lus par identité 1-Wire configurée, jamais par position dans un glob sysfs.

## InfluxDB

L'export utilise le protocole ligne InfluxDB v1 via une session **aiohttp** partagée, avec un délai de garde total de 4 s et les identifiants transmis en paramètres de requête, jamais dans une URL journalisée. Les clés de capteur sont groupées en mesures selon le catalogue : `air`, `water`, `distance`, `lux`, `surface_temp` et `uv`.

Plus aucun appel bloquant ne subsiste dans l'event loop pour cet export. Il ne lit rien lui-même : les
measurements métier ne reçoivent que `value` qualifiée. Un point séparé
`sensor_quality,sensor=<clé>` exporte le statut, l'autorité de contrôle, les échecs, la durée sans
variation et les valeurs brute/observée éventuelles. Une valeur suspecte reste donc analysable sans
polluer la série de confiance.

Le job `influx_push` reste enregistré même hors ligne : `host_machine_state` le suspend ou le réactive à chaud, sans passer par le registre du superviseur ni par un redémarrage.

Les erreurs sont dédupliquées et ne doivent contenir que `host:port/db` et la classe d'exception, jamais le mot de passe.

## Reconfiguration

`POST /conf/sensors` appelle `SensorController.reconfigure()` : les périphériques sont fermés puis reconstruits **dans le même exécuteur et sur la même instance**, sans nouvelle ouverture de `/dev/i2c-1`, et les mesures désormais désactivées sortent de l'instantané. L'export Influx est rechargé dans la foulée.

Comme moteur, chauffage, IHM et export lisent tous le même instantané, une activation ou désactivation prend effet partout à la fois ; il n'y a plus de vérification séparée à faire par consommateur.
