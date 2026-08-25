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
./scripts/deploy.sh
./scripts/deploy.sh master
./scripts/deploy.sh --sans-restart
./scripts/deploy.sh --config-git
```

`--config-git` remplace volontairement la configuration vivante par celle du dépôt. Cette option est sensible et ne doit être utilisée qu'après comparaison du schéma et sauvegarde explicite.

## Déroulement

1. Copie du script sous `/tmp` afin qu'un pull ne modifie pas le programme en cours d'exécution.
2. Sauvegarde de `param/param.json` et `param/sensor_stats.json` sous `~/phyto-backups/<horodatage>`.
3. Conservation des vingt derniers répertoires de sauvegarde.
4. Mise de côté des modifications suivies restantes.
5. Fetch et merge fast-forward uniquement.
6. Restauration de la configuration vivante, sauf `--config-git`.
7. Mise à jour des dépendances si nécessaire.
8. `compileall` avant interruption du service.
9. Redémarrage systemd.
10. Attente jusqu'à 45 secondes de `systemctl active` et d'une réponse `/status`.
11. Rollback sur le commit précédent si le contrôle échoue.

## Contrôle post-déploiement

Le contrôle actuel de `deploy.sh` vérifie la disponibilité, pas le contenu du JSON. Compléter manuellement :

```bash
curl -fsS http://127.0.0.1:8123/status | jq -e '.healthy == true'
systemctl show phyto.service -p NRestarts -p ActiveState -p SubState -p StatusText
journalctl -u phyto -n 50 --no-pager -o cat
```

Vérifier également les équipements physiquement actifs et les prochaines échéances.

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
