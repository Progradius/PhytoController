# Déploiement et rollback

**Source de vérité exécutable** : `scripts/deploy.sh`.
**Statut** : procédure relue dans le code ; exercice complet à consigner.

## Préconditions

- Exécuter depuis le Raspberry Pi de production, pas en root.
- Utiliser le venv attendu sous `RPi Version/venv`.
- Disposer de `sudo` non interactif pour le service.
- Travailler avec un dépôt Git dont la branche distante est accessible.
- Vérifier l'état physique de la serre avant un redémarrage.

## Commandes

```bash
./scripts/deploy.sh                      # redéploie la dernière cible utilisée
./scripts/deploy.sh master               # déploie origin/master
./scripts/deploy.sh feature/ma-branche   # déploie une branche de test
./scripts/deploy.sh v1.2.0               # déploie un tag, ou un SHA
./scripts/deploy.sh --sans-restart
./scripts/deploy.sh --config-git
```

La cible peut être une branche distante, un tag ou un commit. Le préfixe `remotes/` ou `origin/` d'un copier-coller de `git branch -a` est accepté. Le Pi garde **HEAD détaché** sur la cible : aucune branche locale n'est créée ni déplacée, une branche de test rebasée ou force-pushée se redéploie sans divergence, et le rollback ne réécrit aucun historique. La dernière cible est mémorisée dans `git config --local phyto.deployRef` et reprise quand `deploy.sh` est relancé sans argument — vérifier cette valeur avant de conclure qu'un déploiement « sans argument » est parti sur `master`.

`--config-git` remplace volontairement la configuration vivante par celle du dépôt. Cette option est sensible et ne doit être utilisée qu'après comparaison du schéma et sauvegarde explicite.

## Déroulement

1. Copie du script sous `/tmp` afin qu'un pull ne modifie pas le programme en cours d'exécution.
2. Sauvegarde de `param/param.json`, `param/equipment_metadata.json` et `param/sensor_stats.json` sous `~/phyto-backups/<horodatage>`.
3. Conservation des vingt derniers répertoires de sauvegarde.
4. Mise de côté des modifications suivies restantes.
5. Fetch (branches et tags), résolution de la cible, puis `git checkout --detach` dessus.
6. Restauration de la configuration vivante, sauf `--config-git`.
7. Mise à jour des dépendances si nécessaire.
8. `compileall` avant interruption du service.
9. Redémarrage systemd.
10. Attente jusqu'à 45 secondes de `systemctl active` et de cinq réponses saines consécutives de `/health/ready`.
11. Rollback sur le commit précédent si le contrôle échoue.

## Contrôle post-déploiement

Le contrôle actuel de `deploy.sh` vérifie la disponibilité, pas le contenu du JSON. Compléter manuellement :

```bash
curl -fsS http://127.0.0.1:8123/status | jq -e '.healthy == true'
systemctl show phyto.service -p NRestarts -p ActiveState -p SubState -p StatusText
journalctl -u phyto -n 50 --no-pager -o cat
```

Vérifier également les équipements physiquement actifs et les prochaines échéances.

### Fenêtre d'observation du jalon « expérience opérateur »

Le découplage entre santé globale et santé de contrôle modifie la condition de caresse du watchdog. Déployer d'abord avec `PHYTO_HW_WATCHDOG=0` pendant 48 h et neutraliser aussi temporairement `WatchdogSec` si systemd fournit `WATCHDOG_USEC` (`PHYTO_HW_WATCHDOG` ne désactive que l'accès direct à `/dev/watchdog`). Comparer `health.tasks`, `health.domains`, `healthy` et `control_healthy`, puis seulement réarmer le watchdog. Le rollback est déclenché par un écart de régulation, un `control_healthy=false` sans défaut de contrôle réel, ou une absence de heartbeat d'une boucle saine. L'opérateur tranche après conservation du snapshot API, des logs et de l'état GPIO.

#### Dérogation acceptée le 26 août 2026 : observation watchdog armé

Après déploiement et correction du jalon 1, l'opérateur a choisi de conserver le watchdog systemd
armé à 600 s pendant la fenêtre d'observation. Le désarmer rétroactivement aurait retiré le dernier
filet de récupération automatique d'une serre déjà en fonctionnement et imposé un redémarrage
supplémentaire. Cette décision déroge au protocole initial ci-dessus ; elle est acceptée à condition
que tout redémarrage ou faux négatif de `control_healthy` reste explicitement observable.

La preuve est recueillie pendant 48 h par `scripts/observe-jalon1-watchdog.sh`, sans commande GPIO,
mutation de configuration ni redémarrage de service. Le script exige un watchdog armé, fixe comme
références le PID, le compteur systemd `NRestarts`, le `boot_id` et `WatchdogUSec`, puis contrôle toutes
les minutes :

- `/health/ready`, `healthy` et `control_healthy` ;
- présence d'au moins une tâche `gates_watchdog` ;
- vie, santé, restart, stall et dernière erreur de toutes les tâches ;
- fraîcheur et suivi demandé/réel des actionneurs ;
- état des capteurs et fiabilité temporelle ;
- absence de changement de PID, boot, compteur systemd et configuration watchdog.

Lancer depuis `RPi Version/` après le dernier déploiement du jalon 1 :

```bash
nohup bash ./scripts/observe-jalon1-watchdog.sh \
  > /tmp/phyto-jalon1-observation.log 2>&1 &
echo $!
```

Suivre sans interrompre l'observateur :

```bash
tail -f /tmp/phyto-jalon1-observation.log
cat ~/phyto-observations/latest-jalon1-watchdog-arme.txt
```

Le répertoire indiqué contient `metadata.txt`, `samples.jsonl` et, au terme des 48 h,
`summary.json`. Le résultat n'est accepté que si `summary.json.status` vaut `accepted`, sans
échantillon en échec. Une interruption, un redémarrage, une tâche relancée/bloquée, une perte de
santé ou une modification du watchdog invalide la fenêtre. Un capteur non `ok` ou une heure non
fiable produit un avertissement à examiner, sans masquer l'état du contrôle. Aucun déploiement ne doit
être lancé pendant cette fenêtre, puisqu'il changerait volontairement le PID et invaliderait la preuve.

### Préparation du jalon 2 — alarmes et historique local

Le jalon 2 ajoute `param/operator_history.sqlite3`, un état propre à la machine, avec ses annexes
SQLite `-wal` et `-shm`. Ces fichiers ainsi que `param/sensor_stats.json` sont ignorés par Git ; le
script de déploiement continue de sauvegarder les statistiques avant changement de version. Une base
historique corrompue est conservée sous le suffixe `.corrupt.<horodatage>`, recréée vide et signalée
par une alarme auxiliaire : elle ne doit ni empêcher le boot, ni arrêter les caresses watchdog.

Après le futur déploiement du jalon 2, contrôler sans manipuler les GPIO :

```bash
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '{health,alarms,history,network}'
curl -fsS 'http://127.0.0.1:8123/api/v1/history?hours=24' | jq '{hours,bucket_seconds,buckets:(.buckets|length)}'
curl -fsS 'http://127.0.0.1:8123/api/v1/alarms?status=active' | jq '{summary,alarms}'
```

La fenêtre d'observation minimale est de 24 h pour confirmer l'échantillonnage à la minute, les trous
non interpolés et l'absence de relance auxiliaire. Le rollback est déclenché par toute régression de
régulation, toute modification inexpliquée des sorties ou tout `control_healthy=false` sans défaut de
contrôle réel. Une indisponibilité de l'historique ou d'InfluxDB seule doit rester une alarme auxiliaire
et ne constitue pas, à elle seule, un motif de reboot automatique. Ne pas déployer ce jalon tant que la
fenêtre d'observation du jalon 1 ci-dessus n'est pas terminée et acceptée.

## Rollback manuel d'urgence

Ne pas improviser un `git reset --hard`. Avant une action manuelle :

1. identifier le dernier commit sain ;
2. sauvegarder la configuration et les statistiques ;
3. conserver les logs de l'échec ;
4. vérifier que le problème vient du code et non du matériel ou de la configuration ;
5. utiliser de préférence le rollback automatique du script.

Si le rollback automatique a restauré le commit mais que le service reste indisponible, suivre le [runbook](incident-runbook.md) : la panne peut venir de la configuration vivante, du venv, des permissions ou du matériel.

## Amélioration prioritaire

Faire pointer le contrôle de déploiement vers une readiness qui renvoie un échec lorsque `healthy=false`. Une réponse HTTP du serveur ne doit pas certifier la régulation.

## Dépendances retirées de `requirements.txt`

`scripts/deploy.sh` rejoue `pip install -r requirements.txt` quand le fichier a changé, ce qui
installe et met à jour, mais **ne désinstalle jamais** une dépendance qu'on en a retirée. Le
paquet reste donc dans le venv du Pi, inutilisé.

Ce n'est pas dangereux, mais c'est une divergence entre le fichier et l'environnement réel, et
elle grandit à chaque nettoyage. Retirer explicitement le paquet après le déploiement :

```bash
"RPi Version/venv/bin/pip" uninstall -y <paquet>
```

Fait pour `requests` le 26 août 2026, après le passage de l'export InfluxDB à aiohttp.
