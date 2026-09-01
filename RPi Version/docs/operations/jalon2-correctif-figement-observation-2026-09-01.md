# Observation du correctif de figement — relevé intermédiaire du 1er septembre 2026

**Objet** : examiner la nouvelle fenêtre de 172 800 s lancée après le déploiement du correctif de
figement `985e42d`. **Statut de ce document** : relevé intermédiaire en lecture seule, pas clôture de
la fenêtre. L'observateur reste actif et son `summary.json` ne sera produit qu'après le
1er septembre 2026 à 19:09:11 UTC.

## Écart de calendrier constaté

Au moment de la collecte, le Raspberry Pi était le 1er septembre 2026 à 07:02 UTC. La fenêtre avait
donc parcouru 129 200 s sur les 172 800 s demandées, soit 35 h 53 min 20 s. Il restait 43 600 s
(12 h 6 min 40 s). Les processus de référence étaient toujours présents : observateur `722191`,
service `721771`, sans redémarrage systemd.

La fenêtre ne doit pas être marquée `accepted` avant la présence et la lecture du `summary.json`.
Interrompre l'observateur, redéployer ou modifier le service avant son terme invaliderait la preuve
de continuité.

## État intermédiaire

Analyse des preuves sous
`~/phyto-observations/jalon2-operateur-qualite-20260830T190911Z/samples.jsonl` :

| Preuve | Résultat à 07:02:31 UTC |
|---|---:|
| Échantillons | 2 142 |
| Durée réellement couverte | 129 200 s |
| Écart maximal entre deux sondes | 61 s |
| Échantillons en échec | **0** |
| Échantillons avec avertissement | **0** |
| Sondes auxiliaires historique / Influx | 215 / 215 |
| Maximum d'alarmes actives / contrôle / critiques | **0 / 0 / 0** |

Les 2 142 échantillons publient `healthy=true`, `control_healthy=true`, un service
`active/running`, le même PID, le même `boot_id`, `NRestarts=0`, un watchdog à 10 minutes et des
actionneurs avec `tracking=ok`. Aucun `failure_type` ni `warning_type` n'est présent.

## Capteurs BME280

| Mesure | Statut `normal` | Raisons qualité | Plateau strict maximal | Minimum Influx | Maximum Influx |
|---|---:|---:|---:|---:|---:|
| BME280T | 2 142 / 2 142 | aucune | 50,2 s | 21,939 °C | 28,533 °C |
| BME280H | 2 142 / 2 142 | aucune | 20,1 s | 48,567 % | 58,289 % |
| BME280P | 2 142 / 2 142 | aucune | 30,1 s | 944,656 hPa | 949,594 hPa |

La tranche nocturne de contrôle, définie ici par 20:00–06:00 UTC pour rendre le calcul
reproductible, contient 1 193 échantillons. Les trois mesures y sont `normal` à 100 %, sans
`reason_codes`. Le plateau nocturne maximal vaut 40,2 s pour la température, 10,1 s pour l'humidité
et 30,1 s pour la pression, très loin des seuils respectifs de 1 800, 1 800 et 3 600 s.

InfluxDB contient, au moment de la seconde sonde, 2 153 points `sensor_quality` par mesure depuis le
début de la fenêtre et aucun point dont `status != normal`. Cette interrogation n'a publié ni
identifiant ni secret.

## Conclusion provisoire

Le défaut observé les 28–30 août n'est pas réapparu pendant deux tranches nocturnes : le correctif
ancré et l'epsilon nul se comportent comme attendu sur une acquisition vivante. Ce relevé constitue
une preuve intermédiaire forte contre le faux positif de figement, mais pas encore la qualification
formelle de 48 h.

La décision à la clôture reste binaire : accepter seulement si le résumé final couvre au moins
172 800 s, contient zéro échantillon en échec et si tout avertissement éventuel est examiné. Le mode
`Sensor_Quality.mode=observe` doit rester inchangé ; calibration par instrument de référence,
redondance, repli matériel et armement `enforce` restent hors du périmètre de cette observation.
