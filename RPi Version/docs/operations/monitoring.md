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
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '{health: .health.healthy, alarm: .health.heater_alarm, tasks: .health.tasks}'
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '.climate'
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8123/health/ready
systemctl show phyto.service -p ActiveState -p SubState -p NRestarts -p StatusText
df -h /
timedatectl show -p NTPSynchronized
```

Attendu :

- `healthy=true` et `/health/ready` en **200** — un 503 nomme les travaux fautifs dans `unhealthy` ;
- bloc `climate` cohérent : un seuil de ventilation **relevé** par rapport au maximum configuré est normal (garantie de zone morte, [ADR-0004](../decisions/ADR-0004-unified-climate-arbiter.md)), pas un réglage perdu ;
- état `REPLI_CAPTEUR` : la température n'est plus lisible — vérification physique, ne pas se contenter du redémarrage de la tâche ;
- `heater_alarm=null` ;
- tâches attendues `alive=true` et `healthy=true` ;
- `restarts=0` et `stalls=0` en régime normal ; `reloads` compte les relances **volontaires** après sauvegarde d'une section de configuration et n'est pas un signal de panne ;
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
- vérifier la rotation des logs et journald — l'archive de la veille n'apparaît qu'à la première écriture après minuit, son absence sur un contrôleur silencieux n'est pas une panne ;
- comparer température applicative et thermomètre indépendant ;
- vérifier que les budgets hiver de `param/runtime_state.json` ne sont pas réarmés en boucle par des redémarrages répétés ;
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
- alarme CRITICAL d'écriture GPIO (la sortie ne suit pas la consigne) : couper la puissance, un relais collé ou un pilotage mort est plus probable qu'un défaut logiciel ;
- `stalls > 0` : incident à expliquer même après récupération ;
- relances répétées : intervention, ne pas laisser le back-off masquer la panne ;
- plusieurs relais moteur actifs : couper la puissance ;
- heure fausse : suspendre les décisions planifiées ;
- disque presque plein : traiter avant perte de logs ou impossibilité d'écrire la configuration.

## Limites des sondes HTTP

`/health/live` ne prouve que la présence du serveur HTTP. `/api/v1/state`, `/health/ready` et `/status` ne prouvent pas :

- l'état mécanique d'un relais ;
- le courant réellement consommé ;
- la validité absolue d'un capteur plausible mais figé ;
- la bonne heure réelle ;
- la disponibilité récente d'InfluxDB ;
- la fraîcheur d'une mesure sans lire son `status` et son `age_s` : une valeur affichée avec `status` `stale` est la dernière valeur connue, pas la mesure du moment ;
- la santé du réseau ;
- l'état pendant la fenêtre de boot.

Ces métriques devront être complétées progressivement dans le lot I/O et observabilité.
