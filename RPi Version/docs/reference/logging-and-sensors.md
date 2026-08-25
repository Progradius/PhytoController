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

Les événements sont en français et utilisent `name=` pour obtenir des loggers `phyto.<nom>`. Les boucles doivent journaliser les transitions à INFO et les ticks à DEBUG. `StateLogger` produit une ligne à l'entrée en panne et une ligne au rétablissement.

La rotation est quotidienne, compression gzip, rétention configurable. Au relevé du 25 août 2026 avant minuit, le fichier faisait 45 Kio et journald 141,3 Mio avec un plafond de 200 Mio. La première rotation réelle restait à constater.

## Capteurs

`SensorController` ouvre `/dev/i2c-1` et instancie seulement les handlers activés :

- BME280 : température, humidité, pression ;
- DS18B20 : température 1-Wire ;
- VEML6075 : UV ;
- VL53L0X : distance ;
- MLX90614 : température de surface ;
- TSL2591 : luminosité ;
- HC-SR04 : distance GPIO.

Une lecture échouée renvoie `None`. Tous les consommateurs doivent le traiter explicitement. Le Pi observé avait BME280 actif et les autres familles désactivées dans la configuration versionnée locale ; la configuration vivante ne doit pas être imprimée pour confirmer ce point.

## InfluxDB

L'export utilise le protocole ligne InfluxDB v1 via `requests.post`, avec les identifiants transmis dans `params` et non dans une URL journalisée. Les clés de capteur sont groupées en mesures : `air`, `water`, `distance`, `lux` et `surface_temp`.

Les requêtes sont encore bloquantes dans l'event loop. Les erreurs sont dédupliquées et ne doivent contenir que `host:port/db` et la classe d'exception, jamais le mot de passe.

## Reconfiguration

Après POST `/conf`, un nouveau contrôleur est affecté au serveur et à InfluxDB, mais les tâches moteur et chauffage gardent leur référence initiale. Jusqu'à la refonte, toute activation/désactivation de capteur doit être vérifiée séparément dans l'IHM, l'export et les boucles de contrôle.
