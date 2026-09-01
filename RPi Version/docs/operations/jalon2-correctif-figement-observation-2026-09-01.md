# Observation du correctif de figement — clôture du 1er septembre 2026

**Objet** : clôturer la nouvelle fenêtre de 172 800 s lancée après le déploiement du correctif de
figement `985e42d`. **Décision** : observation acceptée sans anomalie ; le correctif de figement est
qualifié en mode `observe`.

## Résumé final

Le `summary.json` produit le 1er septembre 2026 à 19:09:11 UTC sous
`~/phyto-observations/jalon2-operateur-qualite-20260830T190911Z/` porte `status=accepted` :

| Preuve | Résultat final |
|---|---:|
| Durée demandée / réelle | 172 800 s / **172 800 s** |
| Échantillons | **2 864** |
| Échantillons en échec | **0** |
| Échantillons avec avertissement | **0** |
| Écart maximal entre deux sondes | 61 s |
| Sondes auxiliaires historique / Influx | 287 / 287 |
| BME280T / BME280H / BME280P `normal` | **2 864 / 2 864 chacune** |

La sonde Influx finale est conforme pour les trois mesures et l'historique final couvre 720 buckets
de 120 s, sans événement. Les listes `failure_types` et `warning_types` sont vides.

## Relevé intermédiaire ayant précédé la clôture

Au moment de la collecte, le Raspberry Pi était le 1er septembre 2026 à 07:02 UTC. La fenêtre avait
donc parcouru 129 200 s sur les 172 800 s demandées, soit 35 h 53 min 20 s. Il restait 43 600 s
(12 h 6 min 40 s). Les processus de référence étaient toujours présents : observateur `722191`,
service `721771`, sans redémarrage systemd.

Cette attente a été respectée : aucun redéploiement ni redémarrage du service n'a interrompu la
fenêtre avant la production du résumé final.

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

## Conclusion

Le défaut observé les 28–30 août n'est pas réapparu pendant la fenêtre complète, notamment pendant
les deux tranches nocturnes examinées. Le correctif ancré et l'epsilon nul se comportent comme attendu
sur une acquisition vivante. Les trois critères d'acceptation sont satisfaits : durée réelle d'au
moins 172 800 s, zéro échantillon en échec et aucun avertissement à expliquer.

Cette clôture qualifie uniquement la correction du faux positif de figement sur les BME280 actifs.
Le mode `Sensor_Quality.mode=observe` doit rester inchangé ; calibration par instrument de référence,
redondance, repli matériel et armement `enforce` restent hors du périmètre et ouverts dans la TODO.
