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

### Amorçage du validateur de santé renforcé

Le premier déploiement qui introduit le commit `21879ac` doit se faire en deux passes. Le script se
recopie sous `/tmp` avant le fetch : un lancement depuis une version antérieure continue donc
volontairement avec l'ancienne logique jusqu'à sa fin et ne peut pas utiliser le nouveau
`utils/deployment_health.py` qu'il vient seulement de récupérer.

Après avoir poussé la branche cible, exécuter sur le Pi :

```bash
./scripts/deploy.sh feature/qol-operator-experience --sans-restart
./scripts/deploy.sh feature/qol-operator-experience
```

La première passe met à jour et compile le checkout sans toucher au processus en cours. La seconde
part du nouveau script, redémarre le service et impose réellement le commit attendu,
`control_healthy=true`, zéro alarme critique et 15 s de stabilité continue. Ne pas lancer directement
une seule passe pour qualifier ce lot : le service pourrait être déployé correctement, mais la preuve
du nouveau contrat de déploiement manquerait.

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
10. Attente jusqu'à 45 secondes de la qualification complète, maintenue 15 secondes sans interruption.
11. Rollback sur le commit précédent si le contrôle échoue.

## Contrôle post-déploiement

`deploy.sh` ne conclut au succès que si, pendant au moins 15 secondes continues :

- le service systemd reste actif ;
- `/health/live` répond 200 avec `live=true` ;
- `/health/ready` répond 200 avec `ready=true` ;
- `/api/v1/state` publie `health.control_healthy=true` ;
- le commit annoncé par le processus correspond exactement au commit ciblé ;
- `alarms.critical_count` vaut zéro.

Toute rupture remet la fenêtre de stabilité à zéro. Les mêmes critères qualifient le commit précédent
après un rollback automatique. Pour compléter le diagnostic opérateur après le déploiement :

```bash
curl -fsS http://127.0.0.1:8123/health/live | jq '{live,version}'
curl -fsS http://127.0.0.1:8123/health/ready | jq .
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '{version,control_healthy:.health.control_healthy,critical_alarms:.alarms.critical_count}'
systemctl show phyto.service -p NRestarts -p ActiveState -p SubState -p StatusText
journalctl -u phyto -n 50 --no-pager -o cat
```

Si le HTTPS PWA est configuré, ajouter le contrôle auxiliaire décrit dans
[PWA locale et TLS](pwa-local-tls.md). Le déploiement continue délibérément de qualifier la régulation
sur HTTP loopback : une panne de certificat ne doit pas provoquer un rollback ou un reboot de la
serre. Elle doit en revanche laisser `web.https.ready=false` et bloquer la qualification PWA.

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

**Clôture du 28 août 2026** : la fenêtre a produit `status=accepted` après 172 800 s et 2 868
échantillons, sans échec ni avertissement. La preuve complète et sa limite thermique sont consignées
dans le [relevé de clôture](jalon1-watchdog-observation-2026-08-28.md). Le prérequis de passage au
jalon 2 est donc satisfait.

### Observation du lot opérateur, PWA et qualité capteurs

Le jalon 2 ajoute `param/operator_history.sqlite3`, un état propre à la machine, avec ses annexes
SQLite `-wal` et `-shm`. Ces fichiers ainsi que `param/sensor_stats.json` sont ignorés par Git ; le
script de déploiement continue de sauvegarder les statistiques avant changement de version. Une base
historique corrompue est conservée sous le suffixe `.corrupt.<horodatage>`, recréée vide et signalée
par une alarme auxiliaire : elle ne doit ni empêcher le boot, ni arrêter les caresses watchdog.

Le même lot ajoute la PWA auxiliaire et la qualification/calibration des capteurs. Le premier
déploiement doit impérativement conserver `Sensor_Quality.mode=observe` : un diagnostic de figement ou
de redondance y reste visible sans acquérir l'autorité de bloquer la régulation. L'armement
`enforce` appartient à une intervention ultérieure et exige la confirmation explicite `ARMER`.

Après le déploiement, contrôler sans manipuler les GPIO :

```bash
curl -fsS http://127.0.0.1:8123/api/v1/state | jq '{health,alarms,history,network}'
curl -fsS 'http://127.0.0.1:8123/api/v1/history?hours=24' | jq '{hours,bucket_seconds,buckets:(.buckets|length)}'
curl -fsS 'http://127.0.0.1:8123/api/v1/alarms?status=active' | jq '{summary,alarms}'
```

Lancer ensuite l'observateur borné de 48 h, sur le même format que la preuve jalon 1 :

```bash
nohup bash ./scripts/observe-jalon2-operator-quality.sh \
  > /tmp/phyto-jalon2-observation.log 2>&1 &
echo $!
```

Suivre sans interrompre l'observateur :

```bash
tail -f /tmp/phyto-jalon2-observation.log
cat ~/phyto-observations/latest-jalon2-operateur-qualite.txt
```

Le script fixe comme références le commit, le PID, le compteur `NRestarts`, le `boot_id` et le
watchdog. Toutes les minutes, il contrôle le schéma API 2, la santé et les domaines du superviseur,
les dix tâches attendues dont `operator_service`, les alarmes, la fraîcheur et le suivi des sorties,
le contrat qualité détaillé de chaque capteur et le maintien du mode `observe`. Toutes les dix minutes,
il qualifie également la croissance de l'historique 24 h et les routes manifeste, service worker et
repli PWA. Il interroge aussi directement le measurement Influx `sensor_quality` sur les cinq dernières
minutes, sans journaliser l'hôte ni aucun identifiant, afin de confirmer un point récent pour chaque
capteur actif.

Le répertoire de preuve contient `metadata.txt`, `samples.jsonl`, les derniers snapshots état/alarmes/
historique et le `summary.json` final. La qualification automatique complète exige
`summary.json.status=accepted`. `accepted_with_warnings` demande une analyse : une indisponibilité de
l'historique, d'InfluxDB, du réseau ou du TLS reste auxiliaire et ne constitue pas à elle seule un motif
de reboot ou de rollback, mais elle empêche de déclarer la fonctionnalité concernée qualifiée.

Le rollback est déclenché par toute régression de régulation, toute modification inexpliquée des
sorties, toute alarme critique, tout `control_healthy=false`, tout restart/stall ou un passage inattendu
de la qualité capteurs hors du mode `observe`. La PWA sur Chrome Android, les coupures/reconnexions,
les notifications, la calibration par instrument de référence et l'armement `enforce` restent des
qualifications manuelles distinctes suivies dans `tasks/todo.md`.

## Rollback manuel d'urgence

Ne pas improviser un `git reset --hard`. Avant une action manuelle :

1. identifier le dernier commit sain ;
2. sauvegarder la configuration et les statistiques ;
3. conserver les logs de l'échec ;
4. vérifier que le problème vient du code et non du matériel ou de la configuration ;
5. utiliser de préférence le rollback automatique du script.

Un retour vers un commit antérieur à la PWA supprime le point d'écoute `:443` mais conserve HTTP
`:8123`. Une application déjà installée peut alors rester sur sa coque locale en affichant hors ligne ;
la désinstaller ou effacer les données du site Chrome. Les fichiers TLS sous `/etc/phyto/tls` ne sont
pas gérés par `deploy.sh` et restent disponibles pour un redéploiement.

Si le rollback automatique a restauré le commit mais que le service reste indisponible, suivre le [runbook](incident-runbook.md) : la panne peut venir de la configuration vivante, du venv, des permissions ou du matériel.

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
