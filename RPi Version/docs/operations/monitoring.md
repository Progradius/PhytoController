# Monitoring et contrôles périodiques

## Trois niveaux à distinguer

| Niveau | Question | Preuve actuelle |
|---|---|---|
| Disponibilité | Le processus et HTTP répondent-ils ? | systemd, port 8123, HTTP 200 |
| Santé applicative | Les tâches de contrôle progressent-elles ? | `healthy`, `tasks`, heartbeats |
| Sûreté physique | Les charges sont-elles réellement dans l'état attendu ? | GPIO, relais, courant, température indépendante |

Aucun niveau ne remplace le suivant.

## Contrôle quotidien

```bash
curl -fsS http://127.0.0.1:8123/status | jq '{healthy, heater_alarm, tasks}'
systemctl show phyto.service -p ActiveState -p SubState -p NRestarts -p StatusText
df -h /
timedatectl show -p NTPSynchronized
```

Attendu :

- `healthy=true` ;
- `heater_alarm=null` ;
- tâches attendues `alive=true` et `healthy=true` ;
- `restarts=0` et `stalls=0` en régime normal ;
- aucune croissance inexpliquée de `NRestarts` ;
- espace disque suffisant ;
- heure synchronisée.

État observé le 25 août 2026 : huit tâches saines, aucun restart ou stall, aucune alarme chauffage, NTP synchronisé, journald à 141,3 Mio avec `SystemMaxUse=200M`, partition racine utilisée à 34 %. Le Pi exécutait encore le commit `61a5d7d`, alors que le dépôt de travail local avait avancé jusqu'à `61ad3df`.

L'export InfluxDB peut être absent si `host_machine_state` est configuré offline ; comparer les tâches présentes à la configuration attendue.

## Contrôle hebdomadaire

- rechercher les entrées puis récupérations de `StateLogger` ;
- examiner les relances et blocages ;
- vérifier l'ancienneté du dernier point Influx ;
- vérifier les sauvegardes de déploiement ;
- vérifier la rotation des logs et journald ;
- comparer température applicative et thermomètre indépendant ;
- observer bruits ou claquements anormaux des relais.

## Contrôle mensuel

- tester un arrêt contrôlé et les niveaux sûrs selon une fenêtre autorisée ;
- inspecter connexions, oxydation, échauffement et serrage hors tension ;
- tester le thermostat/fusible et les interlocks lorsqu'ils seront installés ;
- revoir le registre des risques ;
- vérifier mises à jour de sécurité et capacité de rollback avant application.

## Seuils d'escalade

- `healthy=false` : diagnostic immédiat ;
- `heater_alarm` non nul : vérification physique immédiate ;
- `stalls > 0` : incident à expliquer même après récupération ;
- relances répétées : intervention, ne pas laisser le back-off masquer la panne ;
- plusieurs relais moteur actifs : couper la puissance ;
- heure fausse : suspendre les décisions planifiées ;
- disque presque plein : traiter avant perte de logs ou impossibilité d'écrire la configuration.

## Limites de `/status`

`/status` ne prouve pas :

- l'état mécanique d'un relais ;
- le courant réellement consommé ;
- la validité absolue d'un capteur plausible mais figé ;
- la bonne heure réelle ;
- la disponibilité récente d'InfluxDB ;
- la santé du réseau ;
- l'état pendant la fenêtre de boot.

Ces métriques devront être complétées progressivement dans le lot I/O et observabilité.
