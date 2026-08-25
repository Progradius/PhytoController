#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploiement PhytoController — a lancer DEPUIS le Raspberry Pi de prod.
#
#   ./scripts/deploy.sh                 # pull sur la branche courante + restart
#   ./scripts/deploy.sh master          # bascule sur master, pull, restart
#   ./scripts/deploy.sh --config-git    # prend aussi le param.json du depot
#   ./scripts/deploy.sh --sans-restart  # met a jour le code sans toucher au service
#
# Garanties :
#   - la config vivante (param/param.json, sensor_stats.json) est sauvegardee
#     puis restauree : un deploiement ne perd jamais les reglages de la serre ;
#   - le code est verifie (compileall) AVANT de couper le service ;
#   - si le service ne repond pas apres redemarrage, rollback automatique sur
#     le commit precedent et redemarrage.
# ---------------------------------------------------------------------------
set -Eeuo pipefail

# --- Re-exec depuis /tmp -----------------------------------------------------
# Le git pull reecrit ce fichier pendant qu'il tourne ; bash relit le script a
# l'offset courant et executerait n'importe quoi. On travaille sur une copie.
if [[ "${PHYTO_DEPLOY_REEXEC:-0}" != "1" ]]; then
    PHYTO_APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
    _copie="$(mktemp /tmp/phyto-deploy.XXXXXX.sh)"
    cp "$(readlink -f "$0")" "$_copie"
    chmod +x "$_copie"
    trap 'rm -f "$_copie"' EXIT
    PHYTO_DEPLOY_REEXEC=1 PHYTO_APP_DIR="$PHYTO_APP_DIR" "$_copie" "$@"
    exit $?
fi

APP_DIR="${PHYTO_APP_DIR:?}"                       # .../PhytoController/RPi Version
REPO_DIR="$(git -C "$APP_DIR" rev-parse --show-toplevel)"
SERVICE="phyto"
PORT="8123"
VENV_PY="$APP_DIR/venv/bin/python3"
SAUVEGARDES="$HOME/phyto-backups"
FICHIERS_CONFIG=("param/param.json" "param/sensor_stats.json")
DELAI_SANTE=45                                     # secondes avant de declarer l'echec

BRANCHE=""
CONFIG_DEPUIS_GIT=0
AVEC_RESTART=1

# --- Sortie console ----------------------------------------------------------
if [[ -t 1 ]]; then C_B="\033[36m"; C_V="\033[32m"; C_J="\033[33m"; C_R="\033[31m"; C_0="\033[0m"
else C_B=""; C_V=""; C_J=""; C_R=""; C_0=""; fi
info()    { printf "${C_B}==>${C_0} %s\n" "$*"; }
ok()      { printf "${C_V} ok ${C_0} %s\n" "$*"; }
attn()    { printf "${C_J} !! ${C_0} %s\n" "$*"; }
echec()   { printf "${C_R}!!!${C_0} %s\n" "$*" >&2; }
mourir()  { echec "$*"; exit 1; }

trap 'echec "Echec ligne $LINENO — deploiement interrompu."' ERR

# --- Arguments ---------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --config-git)    CONFIG_DEPUIS_GIT=1 ;;
        --sans-restart)  AVEC_RESTART=0 ;;
        -h|--help)       sed -n '2,14p' "$0"; exit 0 ;;
        -*)              mourir "Option inconnue : $arg" ;;
        *)               BRANCHE="$arg" ;;
    esac
done

# --- Verifications prealables ------------------------------------------------
[[ $EUID -ne 0 ]] || mourir "Ne pas lancer en root : le service tourne sous $(id -un 1000 2>/dev/null || echo progradius)."
[[ -x "$VENV_PY" ]] || mourir "venv introuvable : $VENV_PY"
sudo -n true 2>/dev/null || mourir "sudo sans mot de passe requis (systemctl restart $SERVICE)."

cd "$REPO_DIR"

# Branche cible : l'argument, sinon la branche suivie par HEAD, sinon la branche
# par defaut du depot distant. Le nom local peut differer du nom distant (un
# clone nomme "main" en face d'un depot dont la branche est "master") : c'est le
# nom cote origin qui compte pour le fetch/merge.
branche_par_defaut() {
    local amont tete
    amont="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    if [[ -n "$amont" ]]; then
        printf '%s\n' "${amont#origin/}"
        return
    fi
    tete="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || true)"
    if [[ -n "$tete" ]]; then
        printf '%s\n' "${tete#origin/}"
        return
    fi
    git rev-parse --abbrev-ref HEAD
}
BRANCHE="${BRANCHE:-$(branche_par_defaut)}"
SHA_AVANT="$(git rev-parse HEAD)"
info "Depot   : $REPO_DIR"
info "Branche : $(git rev-parse --abbrev-ref HEAD) -> $BRANCHE"
info "Commit  : $(git log -1 --oneline)"

# --- 1. Sauvegarde de la config vivante --------------------------------------
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
DOSSIER_SAUVEGARDE="$SAUVEGARDES/$HORODATAGE"
mkdir -p "$DOSSIER_SAUVEGARDE"
for f in "${FICHIERS_CONFIG[@]}"; do
    if [[ -f "$APP_DIR/$f" ]]; then
        cp -p "$APP_DIR/$f" "$DOSSIER_SAUVEGARDE/$(basename "$f")"
    fi
done
chmod 700 "$DOSSIER_SAUVEGARDE"
ok "Config sauvegardee dans $DOSSIER_SAUVEGARDE"
# On ne garde que les 20 derniers deploiements.
ls -1dt "$SAUVEGARDES"/*/ 2>/dev/null | tail -n +21 | xargs -r rm -rf

# --- 2. Nettoyage de l'arbre de travail --------------------------------------
# Les logs et la config sont des fichiers suivis modifies en permanence par
# l'appli : on les remet a l'etat du depot pour que le pull passe.
info "Remise a plat de l'arbre de travail"
git checkout -- "RPi Version/logs" 2>/dev/null || true
for f in "${FICHIERS_CONFIG[@]}"; do
    git checkout -- "RPi Version/$f" 2>/dev/null || true
done
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    attn "Modifications locales restantes, mises de cote (git stash) :"
    git status --short --untracked-files=no | sed 's/^/     /'
    git stash push -m "deploy-$HORODATAGE" >/dev/null
    attn "Recuperables avec : git stash list / git stash pop"
fi

# --- 3. Recuperation du code -------------------------------------------------
info "git fetch origin"
git fetch --prune origin
git remote set-head origin --auto >/dev/null 2>&1 || true
if ! git rev-parse --verify "origin/$BRANCHE" >/dev/null 2>&1; then
    echec "La branche origin/$BRANCHE n'existe pas. Branches disponibles :"
    git branch --remotes --list 'origin/*' --format='%(refname:short)' \
        | grep -v '^origin/HEAD$' | sed 's/^/     /' >&2
    mourir "Relancer avec le bon nom, p. ex. : $0 master"
fi

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "$BRANCHE" ]]; then
    git checkout "$BRANCHE"
fi

if ! git merge --ff-only "origin/$BRANCHE"; then
    mourir "Fast-forward impossible : la branche locale a diverge de origin/$BRANCHE."
fi
SHA_APRES="$(git rev-parse HEAD)"

if [[ "$SHA_AVANT" == "$SHA_APRES" ]]; then
    ok "Deja a jour ($(git log -1 --oneline))"
else
    ok "Mise a jour : $(git log --oneline "$SHA_AVANT..$SHA_APRES" | wc -l) commit(s)"
    git log --oneline "$SHA_AVANT..$SHA_APRES" | sed 's/^/     /'
fi

# --- 4. Restauration de la config vivante ------------------------------------
if [[ $CONFIG_DEPUIS_GIT -eq 1 ]]; then
    attn "--config-git : la config du depot remplace celle du Pi."
else
    for f in "${FICHIERS_CONFIG[@]}"; do
        [[ -f "$DOSSIER_SAUVEGARDE/$(basename "$f")" ]] || continue
        cp -p "$DOSSIER_SAUVEGARDE/$(basename "$f")" "$APP_DIR/$f"
    done
    ok "Config du Pi restauree"
    # Si le depot a fait evoluer param.json (nouveau champ, renommage), la config
    # restauree peut etre incomplete : on previent sans afficher les valeurs
    # (identifiants Wi-Fi / InfluxDB en clair dans ce fichier).
    if [[ "$SHA_AVANT" != "$SHA_APRES" ]] \
       && ! git diff --quiet "$SHA_AVANT" "$SHA_APRES" -- "RPi Version/param/param.json"; then
        attn "param.json a change dans le depot : verifier les nouveaux champs"
        attn "  git diff $SHA_AVANT $SHA_APRES -- 'RPi Version/param/param.json'"
    fi
fi

# --- 5. Dependances ----------------------------------------------------------
if [[ "$SHA_AVANT" != "$SHA_APRES" ]] \
   && ! git diff --quiet "$SHA_AVANT" "$SHA_APRES" -- "RPi Version/requirements.txt"; then
    info "requirements.txt a change — mise a jour du venv"
    "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
    ok "Dependances a jour"
fi

# --- 6. Verification syntaxique AVANT de couper le service -------------------
info "Verification du code (compileall)"
if ! "$VENV_PY" -m compileall -q -x '(venv|\.git|__pycache__|lib/sensors)' "$APP_DIR" >/tmp/phyto-compile.log 2>&1; then
    cat /tmp/phyto-compile.log >&2
    echec "Erreur de syntaxe : rollback sur $SHA_AVANT, le service n'a pas ete touche."
    git reset --hard "$SHA_AVANT" >/dev/null
    for f in "${FICHIERS_CONFIG[@]}"; do
        [[ -f "$DOSSIER_SAUVEGARDE/$(basename "$f")" ]] \
            && cp -p "$DOSSIER_SAUVEGARDE/$(basename "$f")" "$APP_DIR/$f"
    done
    exit 1
fi
ok "Code compilable"

if [[ $AVEC_RESTART -eq 0 ]]; then
    attn "--sans-restart : le service tourne toujours sur l'ancien code."
    exit 0
fi

# --- 7. Redemarrage propre ---------------------------------------------------
# main.py restaure les GPIO dans leur etat sur sur SIGTERM (relais OFF) :
# systemctl stop/start laisse donc la serre dans un etat connu.
attendre_sante() {
    local limite=$1 i
    for ((i = 0; i < limite; i++)); do
        if systemctl is-active --quiet "$SERVICE" \
           && curl -fsS -o /dev/null --max-time 3 "http://127.0.0.1:$PORT/status"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

info "Redemarrage de $SERVICE"
sudo systemctl restart "$SERVICE"

if attendre_sante "$DELAI_SANTE"; then
    ok "Service actif, /status repond sur le port $PORT"
    printf "\n"
    systemctl --no-pager --lines=0 status "$SERVICE" | head -5
    printf "\n"
    info "Derniers logs :"
    journalctl -u "$SERVICE" -n 15 --no-pager -o cat | sed 's/^/     /'
    ok "Deploiement termine — $(git log -1 --oneline)"
    exit 0
fi

# --- 8. Rollback -------------------------------------------------------------
echec "Le service ne repond pas apres ${DELAI_SANTE}s — rollback."
journalctl -u "$SERVICE" -n 30 --no-pager -o cat | sed 's/^/     /' >&2

if [[ "$SHA_AVANT" == "$SHA_APRES" ]]; then
    mourir "Aucun commit n'a ete applique : la panne vient d'ailleurs (materiel, config)."
fi

git reset --hard "$SHA_AVANT" >/dev/null
for f in "${FICHIERS_CONFIG[@]}"; do
    [[ -f "$DOSSIER_SAUVEGARDE/$(basename "$f")" ]] \
        && cp -p "$DOSSIER_SAUVEGARDE/$(basename "$f")" "$APP_DIR/$f"
done
sudo systemctl restart "$SERVICE"

if attendre_sante "$DELAI_SANTE"; then
    attn "Rollback reussi : retour sur $(git log -1 --oneline)"
else
    echec "Rollback effectue mais le service ne repond toujours pas. Intervention manuelle requise :"
    echec "  sudo systemctl status $SERVICE ; journalctl -u $SERVICE -n 100"
fi
exit 1
