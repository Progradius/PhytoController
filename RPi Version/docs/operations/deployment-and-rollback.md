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
```

La cible peut être une branche distante, un tag ou un commit. Le préfixe `remotes/` ou `origin/` d'un copier-coller de `git branch -a` est accepté. Le Pi garde **HEAD détaché** sur la cible : aucune branche locale n'est créée ni déplacée, une branche de test rebasée ou force-pushée se redéploie sans divergence, et le rollback ne réécrit aucun historique. La dernière cible est mémorisée dans `git config --local phyto.deployRef` et reprise quand `deploy.sh` est relancé sans argument — vérifier cette valeur avant de conclure qu'un déploiement « sans argument » est parti sur `master`.

`--config-git` a été supprimée et est explicitement refusée. Une mise à jour de schéma se prépare à
partir de `param/param.example.json`, puis s’applique à la configuration locale par l’interface ou par
une migration dédiée et validée ; elle ne passe jamais par un checkout.

Un verrou non bloquant sur `~/.phyto-deploy.lock` couvre toute l’exécution. Un second lancement échoue
avant la sauvegarde, le fetch ou toute mutation Git. Le descripteur étant détenu par le processus, le
noyau libère également le verrou après une interruption ou un arrêt brutal.

Les fichiers vivants `param.json`, `equipment_metadata.json` et `sensor_stats.json` résident dans le
répertoire des données vivantes : `PHYTO_DATA_DIR` s'il est posé, sinon `param/` du dépôt (voir
[Répertoire des données vivantes](backup-and-restore.md#répertoire-des-données-vivantes)). Le script
lit ce répertoire **dans l'unité systemd** (`systemctl show phyto -p Environment`), jamais dans son
propre environnement, et ne retombe sur `param/` du dépôt que si l'unité ne pose pas la variable.
Aucun de ces fichiers n'est suivi par Git : le script refuse le commit courant ou la cible si
`RPi Version/param/param.json`, `RPi Version/param/equipment_metadata.json` ou
`RPi Version/param/sensor_stats.json` y est encore versionné. Cette barrière s’applique aussi aux
checkouts forcés de rollback : une ancienne révision dangereuse doit être migrée vers ce contrat avant
de pouvoir être déployée.

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

1. Copie du script et du validateur de santé sous `/tmp` afin qu'un pull ne modifie pas le programme en cours d'exécution.
2. Lecture du répertoire des données vivantes dans l'unité systemd.
3. Prise du verrou exclusif avant toute lecture de configuration.
4. Validation Pydantic de `param.json` du répertoire de données, sortie masquée : une configuration qui ne redémarrerait déjà pas est refusée avant toute mutation.
5. Sauvegarde de `param.json`, `equipment_metadata.json` et `sensor_stats.json` du répertoire de données sous `~/phyto-backups/<horodatage>` avec un `umask` privé.
6. Conservation des vingt derniers répertoires de sauvegarde.
7. Fetch des branches et tags sans toucher au checkout, puis résolution de la cible en SHA immuable.
8. Refus si le commit courant ou la cible versionne un fichier vivant.
9. Mise de côté des seules modifications de code suivies, puis `git checkout --detach` du SHA.
10. Vérification que `param.json` est toujours présent dans le répertoire de données ; aucune restauration n’est normalement nécessaire puisqu’il n’a jamais bougé.
11. Mise à jour des dépendances si nécessaire.
12. `compileall` avant interruption du service.
13. Redémarrage systemd.
14. Attente jusqu'à 45 secondes de la qualification complète, maintenue 15 secondes sans interruption.
15. Rollback sur le commit précédent si le contrôle échoue.

Le premier déploiement du commit qui introduit cette séparation est une migration particulière :
l’ancienne copie de `deploy.sh`, déjà recopiée sous `/tmp`, sauvegarde puis restaure encore le fichier
pendant cette unique bascule. Avant de la lancer, vérifier qu’aucun autre déploiement n’est actif et
conserver une copie hors dépôt de `param.json`. Une fois le commit installé, tous les déploiements
suivants appliquent le nouveau contrat et ne touchent plus jamais à la configuration.

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

Les procédures d'observation de 48 h des jalons 1 et 2, closes, sont archivées telles quelles dans
[Procédures d'observation des jalons 1 et 2](../archive/operations/procedures-observation-jalons-1-2.md).

### Déploiement qui modifie un profil qualité

Après un déploiement qui modifie un profil qualité, deux points méritent d'être vérifiés
explicitement : les diagnostics latchés doivent disparaître d'eux-mêmes, parce que le changement de
signature de profil réinitialise la mémoire qualité ; et l'absence d'alarme dans les minutes qui
suivent ne prouve rien, la mémoire repartant de zéro. La preuve d'un correctif de figement est la
période calme suivante, pas l'instantané d'après redémarrage.

### Critères de rollback et qualifications manuelles

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
