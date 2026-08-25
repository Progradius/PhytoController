# Runbook d'incident

**Public** : exploitant du Raspberry Pi et mainteneur de la serre.
**Référence** : commit `61ad3df`.
**Dernière vérification documentaire** : 25 août 2026.
**Statut** : procédures dérivées du code et des vérifications historiques ; elles doivent être exercées sur le Pi lors du lot d'exploitation reproductible.

## Règle prioritaire

En présence d'un risque physique — chauffage incontrôlé, eau qui coule, plusieurs vitesses moteur actives, fumée, odeur, température anormale — ne pas commencer par redémarrer le logiciel.

1. Mettre les personnes en sécurité.
2. Couper et consigner l'alimentation de la charge concernée ou de la carte relais.
3. Ne toucher au câblage qu'après vérification d'absence de tension.
4. Préserver les logs et l'état du système si cela ne retarde pas la mise en sécurité.

Le Raspberry Pi et le réseau ne constituent pas un dispositif d'arrêt d'urgence.

## Diagnostic initial commun

Les commandes suivantes sont en lecture seule :

```bash
systemctl status phyto --no-pager
journalctl -u phyto -n 100 --no-pager -o cat
curl -fsS http://127.0.0.1:8123/status | jq .
ps -eo pid,ppid,stat,etime,pcpu,pmem,cmd | grep '[p]ython3 main.py'
df -h /
free -h
timedatectl status
```

À relever avant toute action si possible :

- date et heure réelles ;
- commit déployé (`git rev-parse HEAD`) ;
- état systemd et nombre de redémarrages ;
- valeur de `healthy` ;
- contenu de `tasks` sans aucune donnée sensible ;
- `heater_alarm` ;
- température et humidité observées ;
- équipements physiquement actifs ;
- dernière modification de configuration ou dernier déploiement.

Ne jamais joindre `param/param.json` à un ticket : il contient des secrets.

## `/status` répond avec `healthy=false`

### Risque

Une ou plusieurs préoccupations de contrôle sont mortes, silencieuses ou en relance. Le serveur HTTP peut continuer à répondre `200`, donc une simple sonde HTTP ne suffit pas.

### Diagnostic

```bash
curl -fsS http://127.0.0.1:8123/status | jq '{healthy, heater_alarm, tasks}'
journalctl -u phyto --since '30 minutes ago' --no-pager -o cat
```

Examiner pour chaque tâche :

- `alive` et `healthy` ;
- `silence_s` ;
- `restarts` ;
- `stalls` ;
- `last_error`.

### Action

- Vérifier physiquement l'état de la charge associée.
- Si une sortie dangereuse n'est pas dans son état sûr, couper sa puissance.
- Laisser le superviseur effectuer une première relance si la charge est sûre.
- Si les compteurs augmentent ou si la tâche reste malsaine, sauvegarder les logs puis effectuer un redémarrage contrôlé du service.

```bash
sudo systemctl restart phyto
```

### Clôture

- `healthy=true` ;
- tâches attendues vivantes ;
- compteurs stabilisés ;
- sorties physiquement cohérentes ;
- cause identifiée ou incident enregistré comme non expliqué.

## Alarme chauffage

### Symptômes

`heater_alarm` n'est pas `null`, ou les logs signalent des lectures invalides, une chauffe maximale atteinte ou un refroidissement forcé.

### Action immédiate

1. Vérifier la température avec un instrument indépendant.
2. Vérifier physiquement si le chauffage est alimenté.
3. En cas de température excessive ou de relais collé, couper la puissance du chauffage.
4. Ne pas effacer l'alarme par un redémarrage avant d'avoir relevé sa cause.

### Diagnostic

```bash
curl -fsS http://127.0.0.1:8123/status | jq '{heater_alarm, healthy, tasks: .tasks.climate_control}'
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '.climate'
journalctl -u phyto --since '2 hours ago' --no-pager -o cat
```

Contrôler :

- présence et cohérence du BME280 ;
- câblage et alimentation du capteur ;
- erreurs I²C ;
- niveau GPIO du chauffage ;
- durée de chauffe ;
- état mécanique du relais.

### Clôture

L'alarme ne peut être considérée résolue que si le capteur fournit des valeurs plausibles, le GPIO et le relais reviennent à OFF et la température réelle est stable. Un redémarrage qui efface un état mémoire ne prouve pas la réparation.

## Chauffage potentiellement collé ON

### Action immédiate

Couper l'alimentation de puissance du chauffage. Ne pas se fier uniquement à l'IHM ou à `get_state()` : ils lisent la broche, pas le contact mécanique ni le courant réel.

Après consignation :

- comparer la consigne logique, le niveau GPIO, la LED de la carte relais et la présence de tension en sortie ;
- remplacer le relais ou contacteur s'il reste fermé lorsque la commande est OFF ;
- vérifier le thermostat/fusible thermique indépendant ;
- ne remettre en service qu'après un essai contrôlé.

## Plusieurs relais moteur actifs

### Risque

Plusieurs prises de vitesse peuvent être alimentées simultanément. Le code actuel journalise l'état dangereux puis renvoie une vitesse logique 0, sans couper immédiatement les sorties.

### Action immédiate

1. Couper la puissance du moteur ou de la carte relais.
2. Ne pas demander une autre vitesse pour « corriger » l'état.
3. Relever les quatre niveaux GPIO et l'état des relais après consignation.

### Diagnostic logiciel

```bash
journalctl -u phyto --since '30 minutes ago' --no-pager -o cat | grep -F 'plusieurs relais moteur actifs'
```

Vérifier le boot, les GPIO réservés 1/7/8, les erreurs d'écriture et le câblage. Un interlock électromécanique est la correction structurelle.

## Sortie cyclique ou électrovanne restée ON

### Action immédiate

- couper l'alimentation de la pompe ou de l'électrovanne si l'eau continue de circuler ;
- contrôler les dégâts et le niveau d'eau avant tout redémarrage.

### Diagnostic

Rechercher l'activation, l'annulation et la coupure :

```bash
journalctl -u phyto --since '2 hours ago' --no-pager -o cat
curl -fsS http://127.0.0.1:8123/status | jq '{healthy, tasks}'
```

Le code courant utilise `Component.energized()` pour les deux modes cycliques. Si la sortie logique est OFF mais la charge reste active, suspecter le relais ou le câblage.

## Service inaccessible

### Diagnostic

```bash
systemctl is-active phyto
systemctl status phyto --no-pager
journalctl -u phyto -b --no-pager -n 150 -o cat
ss -ltnp 'sport = :8123'
```

Causes fréquentes :

- configuration JSON invalide ou incomplète ;
- verrou détenu par une ancienne instance ;
- port 8123 déjà occupé ;
- permission GPIO, I²C, logs ou watchdog ;
- dépendance Python manquante ;
- boucle de redémarrage systemd.

Ne pas lancer une seconde instance manuelle tant que le service existe. Le verrou empêche normalement le double pilotage, mais le bon diagnostic consiste à identifier le propriétaire de l'instance.

## Configuration invalide ou boot impossible

### Précautions

Ne jamais afficher le fichier complet dans un canal enregistré. Valider sans imprimer les valeurs :

```bash
venv/bin/python3 -c 'from param.config import AppConfig; AppConfig.load(); print("configuration valide")'
```

Le script de déploiement conserve des sauvegardes sous `~/phyto-backups/<horodatage>/`. Identifier la sauvegarde voulue en lecture seule :

```bash
find ~/phyto-backups -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort -r
```

La restauration écrase une configuration vivante et doit être effectuée seulement après sélection explicite de la sauvegarde et sauvegarde du fichier défectueux. La procédure exécutable complète sera ajoutée dans le lot « sauvegarde et restauration ».

## Échec après déploiement

`scripts/deploy.sh` tente automatiquement un rollback si le service ne répond pas sous 45 secondes.

Si le rollback échoue :

```bash
systemctl status phyto --no-pager
journalctl -u phyto -n 100 --no-pager -o cat
git log -3 --oneline
```

Vérifier séparément :

- code courant ;
- validité de la configuration restaurée ;
- dépendances du venv ;
- disponibilité du matériel ;
- état du port 8123.

Ne pas enchaîner des `git reset --hard` manuels sans avoir identifié le commit cible et sauvegardé les données vivantes.

## Perte Wi-Fi ou InfluxDB

La régulation locale doit continuer sans InfluxDB. Vérifier :

```bash
nmcli -t -f DEVICE,TYPE,STATE device status
ping -c 1 -W 1 <hote-influx>
journalctl -u phyto --since '1 hour ago' --no-pager -o cat
```

Ne pas placer d'identifiants dans la ligne de commande enregistrée. Les erreurs répétées sont dédupliquées ; rechercher une entrée en panne puis une éventuelle ligne de récupération.

Le code ne possède pas encore de tâche autonome de reconnexion réseau. Une relance du service ne doit être tentée qu'après vérification de l'état sûr des charges.

## Heure non synchronisée

Les timers utilisent l'heure civile et le système ne possède pas encore de RTC ni de blocage strict des décisions jour/nuit lorsque NTP est faux.

```bash
timedatectl status
timedatectl show -p NTPSynchronized
date --iso-8601=seconds
```

Si l'heure est manifestement fausse :

- mettre les sorties planifiées dans un état maîtrisé ;
- restaurer le réseau ou l'heure ;
- vérifier les prochaines échéances avant de reprendre l'automatisme.

## Disque plein ou logs volumineux

```bash
df -h /
du -sh logs 2>/dev/null
journalctl --disk-usage
```

Ne pas supprimer arbitrairement la configuration ou les sauvegardes. La rotation applicative est quotidienne avec rétention configurable ; la rétention journald doit être fixée sur le Pi. Une anomalie de rotation doit être enregistrée avant nettoyage.

## Informations à conserver pour le retour d'expérience

- horodatage et durée ;
- commit et branche ;
- état `/status` filtré ;
- extraits de logs pertinents sans secrets ;
- configuration modifiée : noms des champs uniquement si sensibles ;
- état physique des charges ;
- niveaux GPIO observés ;
- action immédiate et résultat ;
- cause racine ou hypothèses restantes ;
- correction, preuve et condition de non-récurrence.
