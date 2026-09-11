# Migration des données vivantes hors du répertoire de travail Git

## Pourquoi

Le 08/09/2026 à 17:48:25, un `git checkout master` lancé à la main sur le Pi a écrasé
`param/param.json`. Le reflog et le contenu le prouvent : le fichier sauvegardé par
`scripts/deploy.sh` à 17:48:45 est identique octet pour octet à celui du commit `e93644a`.

Le mécanisme est celui de Git, pas une défaillance du contrôleur :

- la branche déployée (`47784dc`) ne suivait pas `param.json` — le fichier vivait hors de Git ;
- `master` local (`ac10ba3`) le suivait encore, `param.json` n'ayant été détraqué que le
  03/09 par `5cddf2f` ;
- passer d'une révision où le fichier est ignoré à une révision où il est suivi fait que Git
  **matérialise le fichier du commit par-dessus la configuration vivante**, sans avertissement.

Coût réel : 26 h 21 min sans Éclairage 2 ni sortie cyclique 2, 6 h d'Éclairage 1 perdues, et un
chauffage réactivé à tort qui a chauffé 22 min.

La sauvegarde de `deploy.sh` a bien fonctionné, mais elle est arrivée **après** l'écrasement :
elle a photographié une configuration déjà perdue. Et la garde d'étape 0, qui refuse une cible
suivant la configuration, ne protège que ce qui passe par le script. Tous les commits antérieurs
à `5cddf2f` suivent encore `param.json` : n'importe quel checkout vers l'un d'eux reproduit
l'incident à l'identique.

La seule réponse solide est structurelle : **ce qui n'est pas dans l'arbre de travail ne peut
être ni écrasé, ni supprimé, ni restauré par un checkout, un merge, un reset ou un
`git clean -xdf`.**

## Ce que le code fait désormais

`utils/runtime_paths.py` résout un répertoire unique pour toutes les données écrites à
l'exécution : `PHYTO_DATA_DIR` si elle est définie et non vide, sinon le `param/` du dépôt.
Le défaut préserve exactement le comportement historique — développement, tests et image Docker
sont inchangés.

Huit ancrages y passent : `param.json` (et son `.bak`), `runtime_state.json`,
`sensor_stats.json`, `equipment_metadata.json`, `.csrf_token`, `operator_history.sqlite3`,
`cultures.sqlite3` et, dérivé du chemin de cette base, le répertoire `culture_media/`.

`main.py` appelle `ensure_data_dir()` au démarrage, avant le verrou d'instance et avant tout
accès fichier. Si `PHYTO_DATA_DIR` est posée mais inutilisable, le processus **s'arrête en
clair** : aucune broche n'a encore été touchée. Ne jamais ajouter de repli silencieux vers
`param/` — le processus se remettrait à écrire dans le dépôt sans que personne ne le voie.

`scripts/deploy.sh` lit `PHYTO_DATA_DIR` **dans l'unité systemd** (`systemctl show`), pas dans
son propre environnement : la variable appartient au service, et un `${PHYTO_DATA_DIR:-…}` du
shell retomberait silencieusement sur `param/` après la migration, faisant sauvegarder au script
un répertoire que le service n'utilise plus.

## Procédure sur le Pi

Les deux bases sont en mode WAL. Les déplacer à chaud perdrait les transactions encore dans le
`-wal` : le service doit être arrêté d'abord.

```bash
cd "$HOME/PhytoController/RPi Version"

# 1. Copie de sûreté horodatée AVANT toute manipulation
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/phyto-backups/$HORODATAGE-avant-migration"
cp -a param/param.json param/param.json.bak param/runtime_state.json \
      param/sensor_stats.json param/equipment_metadata.json param/.csrf_token \
      "$HOME/phyto-backups/$HORODATAGE-avant-migration/" 2>/dev/null

# 2. Arrêt propre : GPIO remis à l'état sûr, WAL replié
sudo systemctl stop phyto

# 3. Contrôle : plus aucun -wal/-shm résiduel
ls param/*.sqlite3-wal param/*.sqlite3-shm 2>/dev/null && echo "ATTENDRE : WAL encore présent"

# 4. Déplacement
mkdir -m 700 -p "$HOME/phyto-data"
mv param/param.json param/param.json.bak param/runtime_state.json \
   param/sensor_stats.json param/equipment_metadata.json param/.csrf_token \
   param/operator_history.sqlite3* param/cultures.sqlite3* param/culture_media \
   "$HOME/phyto-data/"

# 5. Unité systemd porteuse de PHYTO_DATA_DIR
sudo cp deploy/phyto.service /etc/systemd/system/phyto.service
sudo systemctl daemon-reload
sudo systemctl start phyto
```

L'étape 4 tolère qu'un fichier manque (`.csrf_token` sur une installation neuve, par exemple) :
adapter la liste plutôt que de forcer.

## Contrôles de sortie

```bash
curl -s http://127.0.0.1:8123/health/ready          # {"ready": true, "unhealthy": []}
ls "$HOME/phyto-data"                               # les 8 entrées vivantes
git -C "$HOME/PhytoController" status --short        # param/ propre, rien de vivant
```

Puis, dans l'interface : le tableau de bord affiche bien les états, `/history` remonte
l'historique opérateur, `/cultures` ouvre le carnet et une photo déjà enregistrée s'affiche.
Vérifier enfin dans le journal que la configuration chargée est la bonne (horaires des minuteurs,
état du chauffage) — c'est le seul contrôle qui prouve que le bon `param.json` a été lu.

## Preuve de non-régression

Le scénario d'origine — un `git checkout` sur une révision qui suit encore `param.json` — ne doit
plus rien casser. Il se rejoue **dans un clone jetable**, jamais dans le checkout servi par le
service : c'est précisément le geste proscrit plus bas, et le faire ici rendrait la preuve
dangereuse au lieu de rassurante.

```bash
COPIE="$(mktemp -d)"
git clone --no-local "$HOME/PhytoController" "$COPIE/depot"
AVANT="$(stat -c '%s %Y' "$HOME/phyto-data/param.json") $(sha256sum < "$HOME/phyto-data/param.json")"
git -C "$COPIE/depot" checkout e93644a   # une révision qui suit encore param.json
APRES="$(stat -c '%s %Y' "$HOME/phyto-data/param.json") $(sha256sum < "$HOME/phyto-data/param.json")"
[ "$AVANT" = "$APRES" ] && echo "param.json intact" || echo "ÉCART : param.json modifié"
rm -rf "$COPIE"
```

Le clone prouve ce qui compte : cette révision **matérialise** encore
`RPi Version/param/param.json` (`git ls-tree e93644a "RPi Version/param/"`), et elle l'écrit dans
sa propre copie de travail sans jamais atteindre `~/phyto-data`. Le checkout de production, lui,
n'est pas touché : il reste détaché sur la révision déployée.

La preuve compare taille, date de modification et empreinte SHA-256 : elle n'imprime aucune valeur
du fichier, qui contient des secrets. Ne jamais l'afficher avec `cat`, `less` ou
`jq` pour « vérifier » — la sortie d'un terminal finit dans un historique, une capture ou un ticket.

## Consigne d'exploitation

**Sur le Pi, jamais de `git checkout <branche>` ni de `git pull`.** Toujours
`scripts/deploy.sh`, qui laisse HEAD détaché sur la cible et refuse une révision suivant la
configuration. La migration rend l'écrasement impossible pour les données ; le checkout de
branche reste malgré tout à proscrire, il fait diverger le Pi du modèle « checkout de lecture »
sur lequel repose tout le script.
