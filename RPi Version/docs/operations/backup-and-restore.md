# Sauvegarde et restauration

## Répertoire des données vivantes

Toutes les données écrites à l'exécution vivent dans **un seul** répertoire, résolu une fois au
démarrage par `utils/runtime_paths.py` : **`PHYTO_DATA_DIR` s'il est posé et non vide, sinon
`param/` du dépôt**. Le défaut garde le développement, les tests et l'image Docker inchangés ; en
production, l'unité versionnée `deploy/phyto.service` pose `PHYTO_DATA_DIR` hors du répertoire de
travail Git, pour qu'aucun checkout, merge, reset ou `git clean` ne puisse plus écraser la
configuration (incident du 08/09/2026, voir [la migration](migration-donnees-vivantes.md)).

Pour toute commande de production, lire ce répertoire **dans l'unité systemd**, exactement comme le
fait `scripts/deploy.sh` :

```bash
DONNEES="$(systemctl show phyto -p Environment --value | tr ' ' '\n' | sed -n 's/^PHYTO_DATA_DIR=//p' | tail -n 1)"
[ -n "$DONNEES" ] && [ -d "$DONNEES" ] || { echo "ARRÊT : PHYTO_DATA_DIR absente de l'unité ou répertoire introuvable"; return 1 2>/dev/null || exit 1; }
echo "Données vivantes : $DONNEES"
```

Ne rien enchaîner après un « ARRÊT ». Si l'unité ne pose pas la variable (installation non encore
migrée), le service lit bien `param/` du dépôt : poser alors `DONNEES` explicitement, en
connaissance de cause. Ne jamais écrire `${PHYTO_DATA_DIR:-param}` dans un shell : la variable
appartient au service, pas à la session, et ce défaut retomberait silencieusement sur `param/`, un
répertoire que le service n'utilise plus après la migration.

Dans la suite, `$DONNEES/…` désigne un fichier de ce répertoire.

## Carnet de cultures

`$DONNEES/cultures.sqlite3` et ses annexes sont locaux et hors de Git. Le schéma courant est le
**4**. Les données n'ont pas la rétention de 72 h de l'historique technique. Utiliser la sauvegarde
complète ZIP depuis `/cultures/cycles` : elle inclut la copie SQLite cohérente malgré le WAL, les
fichiers `$DONNEES/culture_media/` — photos d'événements **et** d'observations d'espace — et leur
manifeste SHA-256 (`format=phyto-cultures-bundle`, chaque fichier avec sa taille et son SHA-256).
Une sauvegarde SQLite seule ne suffit plus dès qu’une photo est enregistrée.

La restauration se fait **uniquement vers une destination nouvelle**, jamais par écrasement :

```bash
.venv/bin/python scripts/restore-cultures.py --bundle <archive.zip> <dossier-inexistant>
.venv/bin/python scripts/restore-cultures.py <base.sqlite3> <fichier-inexistant>
```

Les schémas 1 à 4 sont acceptés ; l'outil refuse le carnet actif et toute destination existante.
La procédure complète est décrite dans [le guide du carnet](cultures.md#export-et-sauvegarde) et
[l'exercice de restauration](cultures.md#restaurer-une-sauvegarde-complète-sur-copie).

À chaque migration, le carnet écrit lui-même une copie préalable `cultures.sqlite3.before-vN.sqlite3`
(`.before-v2`, `.before-v3`, `.before-v4`, une par version traversée) et refuse d'écraser une copie
déjà présente : voir
[Lever une sauvegarde `.before-v4`](cultures.md#lever-une-sauvegarde-before-v4-après-migration-interrompue).
Ces copies restent **sur le Pi** : elles ne remplacent pas une sauvegarde hors machine. Prévoir
celle-ci avant toute migration du carnet ; le script de déploiement ne la réalise pas
automatiquement.

## Données vivantes

| Fichier | Contenu | Sensibilité |
|---|---|---|
| `$DONNEES/param.json` (et `param.json.bak`) | Configuration, Wi-Fi, InfluxDB, GPIO | Critique : secrets et sécurité physique |
| `$DONNEES/equipment_metadata.json` | Noms et annotations des équipements | Faible à moyenne |
| `$DONNEES/sensor_stats.json` | Minimums et maximums de capteurs | Faible à moyenne |
| `$DONNEES/runtime_state.json` | Budgets hiver, phase des cycliques, forçages « arrêt » | Faible |
| `$DONNEES/.csrf_token` | Jeton CSRF de l'interface | Local, ne pas copier ailleurs |
| `$DONNEES/operator_history.sqlite3` (et `-wal`, `-shm`) | Historique opérateur de 72 h, alarmes résolues | Faible à moyenne |
| `$DONNEES/cultures.sqlite3` (et annexes), `$DONNEES/culture_media/` | Carnet de cultures et photos | Moyenne : texte d'opérateur |
| `logs/phyto.log*` (dans le dépôt) | Diagnostic applicatif | Peut contenir topologie et événements |

Les journaux applicatifs restent sous `logs/` du dépôt : ils ne passent pas par `PHYTO_DATA_DIR`.

Le script de déploiement sauvegarde `param.json`, `equipment_metadata.json` et `sensor_stats.json`
du répertoire de données lu dans l'unité avant toute mise à jour. Aucun de ces fichiers n'est suivi
par Git, et aucune bascule de code ne les retire ni ne les restaure. Ce mécanisme n'est pas une
sauvegarde hors machine : une panne de carte SD peut détruire le dépôt, `$DONNEES` et
`~/phyto-backups` simultanément.

## Contrôle des sauvegardes de déploiement

```bash
find ~/phyto-backups -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort -r
```

Ne pas afficher le contenu de `param.json`. Contrôler permissions, taille raisonnable et validité sur une copie protégée.

## Politique recommandée

- conserver les vingt sauvegardes locales du script ;
- réaliser une sauvegarde chiffrée hors Pi avant chaque migration de schéma ou câblage ;
- conserver séparément les artefacts systemd et la documentation ;
- ne jamais placer les secrets dans un dépôt Git ordinaire ;
- tester périodiquement une restauration sur un environnement sans charges.

## Restauration

Une restauration peut changer les GPIO, consignes et identifiants. Avant de remplacer un fichier :

1. couper ou mettre en sécurité les charges ;
2. arrêter le service ;
3. sauvegarder le fichier actuel sous un nom horodaté et protégé ;
4. identifier explicitement la sauvegarde source ;
5. restaurer en conservant propriétaire et permissions ;
6. valider le fichier restauré sans imprimer les valeurs — commande du
   [runbook](incident-runbook.md#configuration-invalide-ou-boot-impossible) ;
7. comparer les noms de champs et la matrice GPIO ;
8. redémarrer sous surveillance ;
9. vérifier `healthy`, alarmes, logs et sorties physiques.

Les commandes d'écrasement sont volontairement absentes de cette première version afin d'éviter une restauration sur une cible ambiguë. Elles seront ajoutées après exercice sur une copie et avec des chemins validés.

## Critère de réussite

Une sauvegarde n'est qualifiée que si elle peut restaurer configuration, statistiques et unité systemd sur un Pi de remplacement, avec secrets injectés séparément et vérifications matérielles avant raccordement des charges.

## `runtime_state.json`

État de régulation reporté d'un démarrage à l'autre : budgets horaires du mode hiver, phase
séquentielle des minuteurs cycliques et forçages « arrêt » en cours. Propre à la machine, hors de
Git, **non sauvegardé** par `scripts/deploy.sh` — comme `.csrf_token`, il survit aux déploiements
parce que le script ne fait qu'un `git checkout --detach` du code, qui ne touche ni les fichiers
ignorés ni, depuis la migration, un répertoire situé hors de l'arbre de travail.

Sa perte n'est pas dangereuse : les budgets repartent pleins et la phase séquentielle recommence.
La conséquence est celle que ce fichier existe précisément pour éviter — un redémarrage réaccorde
un crédit de ventilation, ou relance une phase ON complète d'arrosage. À surveiller si des
redémarrages se succèdent.

Un fichier corrompu est détecté au chargement et réinitialisé plutôt que de lever : la régulation
démarre toujours.

## `.csrf_token`

Ce fichier contient le jeton CSRF de l'interface web (mode 0600, hors de Git). Il **n'est pas
sauvegardé** par `scripts/deploy.sh` et n'a pas à l'être : un déploiement ne le supprime pas. S'il
disparaît, le serveur en génère un nouveau au démarrage ; la seule conséquence est que les pages
laissées ouvertes devront être rechargées. Ne pas le recopier vers une autre machine.
