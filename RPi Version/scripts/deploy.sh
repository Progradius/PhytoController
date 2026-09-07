#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploiement PhytoController — a lancer DEPUIS le Raspberry Pi de prod.
#
#   ./scripts/deploy.sh                      # redeploie la derniere cible utilisee
#   ./scripts/deploy.sh master               # deploie origin/master
#   ./scripts/deploy.sh feature/ma-branche   # deploie origin/feature/ma-branche
#   ./scripts/deploy.sh v1.2.0               # deploie un tag, ou un SHA
#   ./scripts/deploy.sh --sans-restart       # met a jour le code sans toucher au service
#
# Le Pi est un checkout de LECTURE : HEAD est toujours detache sur la cible
# (origin/<branche>, tag ou SHA). Aucune branche locale n'est creee ni deplacee,
# donc pas d'echec "fast-forward impossible" quand la branche de test est
# reecrite (rebase, force-push), et un rollback qui ne detruit aucun historique.
# La cible est memorisee dans `git config phyto.deployRef` et reprise telle
# quelle quand deploy.sh est relance sans argument.
#
# Garanties :
#   - un verrou exclusif interdit deux deploiements concurrents ;
#   - les fichiers vivants sont ignores par Git : aucun checkout ne peut les
#     remplacer, meme momentanement, et ils sont sauvegardes avant la bascule ;
#   - le code est verifie (compileall) AVANT de couper le service ;
#   - si la santé complète ne reste pas stable après redémarrage, rollback
#     automatique sur le commit précédent et qualification identique.
# ---------------------------------------------------------------------------
set -Eeuo pipefail

# --- Re-exec depuis /tmp -----------------------------------------------------
# Le git pull reecrit ce fichier pendant qu'il tourne ; bash relit le script a
# l'offset courant et executerait n'importe quoi. On travaille sur une copie.
if [[ "${PHYTO_DEPLOY_REEXEC:-0}" != "1" ]]; then
    PHYTO_APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
    _copie="$(mktemp /tmp/phyto-deploy.XXXXXX.sh)"
    _validateur="$(mktemp /tmp/phyto-deployment-health.XXXXXX.py)"
    cp "$(readlink -f "$0")" "$_copie"
    cp "$PHYTO_APP_DIR/utils/deployment_health.py" "$_validateur"
    chmod +x "$_copie"
    trap 'rm -f "$_copie" "$_validateur"' EXIT
    PHYTO_DEPLOY_REEXEC=1 PHYTO_APP_DIR="$PHYTO_APP_DIR" \
        PHYTO_DEPLOY_HEALTH_VALIDATOR="$_validateur" "$_copie" "$@"
    exit $?
fi

APP_DIR="${PHYTO_APP_DIR:?}"                       # .../PhytoController/RPi Version
REPO_DIR="$(git -C "$APP_DIR" rev-parse --show-toplevel)"
SERVICE="phyto"
PORT="8123"
VENV_PY="$APP_DIR/venv/bin/python3"
VALIDATEUR_SANTE="${PHYTO_DEPLOY_HEALTH_VALIDATOR:?}"
SAUVEGARDES="$HOME/phyto-backups"
FICHIERS_CONFIG=(
    "param/param.json"
    "param/equipment_metadata.json"
    "param/sensor_stats.json"
)
FICHIERS_CONFIG_REPO=(
    "RPi Version/param/param.json"
    "RPi Version/param/equipment_metadata.json"
    "RPi Version/param/sensor_stats.json"
)
DELAI_SANTE=45                                     # délai total après le redémarrage
STABILITE_SANTE=15                                 # secondes saines sans interruption

CIBLE=""
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
trap 'echec "Deploiement interrompu par un signal."; exit 130' HUP INT TERM

# --- Arguments ---------------------------------------------------------------
for arg in "$@"; do
    case "$arg" in
        --config-git)    mourir "--config-git a ete supprime : la configuration locale ne peut plus etre remplacee par un deploiement." ;;
        --sans-restart)  AVEC_RESTART=0 ;;
        -h|--help)       sed -n '2,24p' "$0"; exit 0 ;;
        -*)              mourir "Option inconnue : $arg" ;;
        *)               [[ -z "$CIBLE" ]] || mourir "Une seule cible a la fois (recu : $CIBLE puis $arg)."
                         CIBLE="$arg" ;;
    esac
done

# `git branch -a` affiche "remotes/origin/feature/x" : on accepte ce copier-coller
# comme "feature/x". Le prefixe est retire, jamais le nom de branche lui-meme.
CIBLE="${CIBLE#remotes/}"
CIBLE="${CIBLE#origin/}"

# Le verrou est pris avant toute lecture ou sauvegarde de la configuration.
# Le descripteur reste ouvert pendant toute la vie du script et est libere par
# le noyau sur toute sortie, y compris un signal non rattrapable.
VERROU_DEPLOIEMENT="$HOME/.phyto-deploy.lock"
umask 077
command -v flock >/dev/null 2>&1 \
    || mourir "La commande flock est requise pour garantir un deploiement exclusif."
exec 9>"$VERROU_DEPLOIEMENT"
chmod 600 "$VERROU_DEPLOIEMENT"
if ! flock -n 9; then
    mourir "Un autre deploiement est deja en cours (verrou : $VERROU_DEPLOIEMENT)."
fi

# --- Verifications prealables ------------------------------------------------
[[ $EUID -ne 0 ]] || mourir "Ne pas lancer en root : le service tourne sous $(id -un 1000 2>/dev/null || echo progradius)."
[[ -x "$VENV_PY" ]] || mourir "venv introuvable : $VENV_PY"
sudo -n true 2>/dev/null || mourir "sudo sans mot de passe requis (systemctl restart $SERVICE)."
[[ -f "$APP_DIR/param/param.json" ]] \
    || mourir "Configuration vivante absente : $APP_DIR/param/param.json"

# Refuser avant le fetch et avant tout changement de code une configuration
# locale qui ne redemarrerait deja pas avec la version courante. La sortie est
# masquee : une ValidationError Pydantic ne doit jamais recopier une valeur
# sensible de Network_Settings dans la console de deploiement.
if ! (
    cd "$APP_DIR"
    "$VENV_PY" -c \
        'import json; from pathlib import Path; from param.config import AppConfig; AppConfig.model_validate(json.loads(Path("param/param.json").read_text(encoding="utf-8")))'
) >/dev/null 2>&1; then
    mourir "param/param.json est illisible ou invalide : deploiement refuse avant toute mutation."
fi
ok "Configuration locale valide"

cd "$REPO_DIR"

# Cible : l'argument, sinon la derniere cible deployee (memorisee ici meme),
# sinon la branche suivie par HEAD, sinon la branche par defaut du depot distant.
# Le nom local peut differer du nom distant (un clone nomme "main" en face d'un
# depot dont la branche est "master") : c'est le nom cote origin qui compte.
cible_par_defaut() {
    local memo amont tete courante
    memo="$(git config --local --get phyto.deployRef 2>/dev/null || true)"
    if [[ -n "$memo" ]]; then
        printf '%s\n' "$memo"
        return
    fi
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
    # HEAD deja detache sans memo : on ne peut pas deviner, master est la
    # branche de production de ce depot.
    courante="$(git rev-parse --abbrev-ref HEAD)"
    [[ "$courante" == "HEAD" ]] && courante="master"
    printf '%s\n' "$courante"
}
CIBLE="${CIBLE:-$(cible_par_defaut)}"
SHA_AVANT="$(git rev-parse HEAD)"
info "Depot   : $REPO_DIR"
info "Cible   : $CIBLE"
info "Commit  : $(git log -1 --oneline)"

# --- 1. Sauvegarde de la config vivante --------------------------------------
HORODATAGE="$(date +%Y%m%d-%H%M%S)"
DOSSIER_SAUVEGARDE="$SAUVEGARDES/$HORODATAGE"
mkdir -p "$DOSSIER_SAUVEGARDE"
for f in "${FICHIERS_CONFIG[@]}"; do
    if [[ -f "$APP_DIR/$f" ]]; then
        cp -p "$APP_DIR/$f" "$DOSSIER_SAUVEGARDE/$(basename "$f")"
        chmod 600 "$DOSSIER_SAUVEGARDE/$(basename "$f")"
    fi
done
chmod 700 "$DOSSIER_SAUVEGARDE"
ok "Config sauvegardee dans $DOSSIER_SAUVEGARDE"
# On ne garde que les 20 derniers deploiements.
ls -1dt "$SAUVEGARDES"/*/ 2>/dev/null | tail -n +21 | xargs -r rm -rf

# --- 2. Recuperation de la cible, sans toucher au checkout -------------------
info "git fetch origin"
git fetch --prune --tags origin
git remote set-head origin --auto >/dev/null 2>&1 || true

# Une branche distante d'abord (le cas courant), sinon un tag ou un SHA : la
# meme commande sert a deployer une branche de test et a rejouer un commit precis.
if git rev-parse --verify --quiet "refs/remotes/origin/$CIBLE^{commit}" >/dev/null; then
    CIBLE_REF="origin/$CIBLE"
elif git rev-parse --verify --quiet "$CIBLE^{commit}" >/dev/null; then
    CIBLE_REF="$CIBLE"
else
    echec "Ni la branche origin/$CIBLE, ni un tag/commit '$CIBLE' n'existe. Branches disponibles :"
    git branch --remotes --list 'origin/*' --format='%(refname:short)' \
        | grep -v '^origin/HEAD$' | sed 's/^/     /' >&2
    mourir "Relancer avec le bon nom, p. ex. : $0 master"
fi

# On fige le SHA avant toute mutation de l'arbre. Une branche distante qui
# bougerait ensuite ne peut donc pas changer silencieusement la cible qualifiee.
SHA_CIBLE="$(git rev-parse "$CIBLE_REF^{commit}")"

verifier_config_non_versionnee() {
    local revision=$1 libelle=$2 fichier
    for fichier in "${FICHIERS_CONFIG_REPO[@]}"; do
        if git cat-file -e "$revision:$fichier" 2>/dev/null; then
            mourir "$libelle versionne encore $fichier : deploiement refuse pour proteger la configuration locale."
        fi
    done
}

# `git checkout --force` est aussi utilise au rollback : les deux revisions
# doivent donc respecter le contrat. Cette barriere interdit notamment un
# rollback manuel vers une ancienne version qui suivait encore param.json.
verifier_config_non_versionnee "$SHA_AVANT" "Le commit actuel"
verifier_config_non_versionnee "$SHA_CIBLE" "La cible"

# --- 3. Nettoyage des seules modifications de code suivies -------------------
# Les fichiers vivants sont ignores par Git et n'apparaissent jamais ici. On ne
# lance volontairement aucun `git checkout` sur param/ : le service continue a
# lire exactement la meme configuration pendant toute la preparation.
info "Mise de cote des modifications de code suivies"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
    attn "Modifications locales restantes, mises de cote (git stash) :"
    git status --short --untracked-files=no | sed 's/^/     /'
    git stash push -m "deploy-$HORODATAGE" >/dev/null
    attn "Recuperables avec : git stash list / git stash pop"
fi

# --- 4. Bascule atomique du code ---------------------------------------------

# HEAD detache : on ne cree ni ne deplace aucune branche locale sur le Pi. Une
# branche de test rebasee ou force-pushee se deploie donc sans divergence
# possible, et le rollback (etape 8) ne peut pas reecrire un historique.
info "Bascule sur $CIBLE_REF"
git checkout --detach "$SHA_CIBLE"
SHA_APRES="$(git rev-parse HEAD)"
git config --local phyto.deployRef "$CIBLE"

if [[ "$SHA_AVANT" == "$SHA_APRES" ]]; then
    ok "Deja a jour ($(git log -1 --oneline))"
else
    ok "Mise a jour : $(git log --oneline "$SHA_AVANT..$SHA_APRES" | wc -l) commit(s)"
    git log --oneline "$SHA_AVANT..$SHA_APRES" | sed 's/^/     /'
fi

# La configuration n'a pas a etre restauree : elle n'a jamais quitte son
# emplacement et Git ne la connait plus. Verifier sa presence ici transforme
# toute regression future en echec avant l'arret du service.
for f in "${FICHIERS_CONFIG[@]}"; do
    if [[ "$f" == "param/param.json" && ! -f "$APP_DIR/$f" ]]; then
        mourir "Configuration vivante absente apres la bascule : $APP_DIR/$f"
    fi
done
ok "Configuration locale preservee sans interruption"

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
    git checkout --force --detach "$SHA_AVANT" >/dev/null 2>&1
    exit 1
fi
ok "Code compilable"

if [[ $AVEC_RESTART -eq 0 ]]; then
    attn "--sans-restart : le service tourne toujours sur l'ancien code."
    exit 0
fi

# --- 7. Redemarrage propre ---------------------------------------------------
# main.py pose l'etat sur des GPIO sur SIGTERM (relais OFF) et n'appelle plus
# GPIO.cleanup() : les broches restent des SORTIES PILOTEES pendant toute la
# fenetre stop -> start, au lieu de retomber en entree flottante. La serre reste
# dans un etat connu pendant le redemarrage.
# main.py prend aussi un verrou d'instance : si l'ancien processus n'est pas
# encore mort, le nouveau attend 15 s puis sort en erreur (visible ici) plutot
# que de piloter les memes broches en double.
sonder_sante() {
    local version_attendue=$1 dossier=$2 code_live code_ready code_state
    if ! systemctl is-active --quiet "$SERVICE"; then
        printf '%s\n' "service inactif"
        return 1
    fi

    code_live="$(curl -sS -o "$dossier/live.json" -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:$PORT/health/live" 2>"$dossier/curl.err" || true)"
    if [[ "$code_live" != "200" ]]; then
        printf '%s\n' "/health/live indisponible (HTTP ${code_live:-aucun})"
        return 1
    fi

    code_ready="$(curl -sS -o "$dossier/ready.json" -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:$PORT/health/ready" 2>"$dossier/curl.err" || true)"
    if [[ "$code_ready" != "200" ]]; then
        printf '%s\n' "/health/ready refuse la disponibilité (HTTP ${code_ready:-aucun})"
        return 1
    fi

    code_state="$(curl -sS -o "$dossier/state.json" -w '%{http_code}' --max-time 3 \
        "http://127.0.0.1:$PORT/api/v1/state" 2>"$dossier/curl.err" || true)"
    if [[ "$code_state" != "200" ]]; then
        printf '%s\n' "/api/v1/state indisponible (HTTP ${code_state:-aucun})"
        return 1
    fi

    "$VENV_PY" "$VALIDATEUR_SANTE" "$version_attendue" \
        "$dossier/live.json" "$dossier/ready.json" "$dossier/state.json"
}

nettoyer_sonde() {
    local dossier=$1
    rm -f "$dossier/live.json" "$dossier/ready.json" "$dossier/state.json" "$dossier/curl.err"
    rmdir "$dossier"
}

attendre_sante() {
    local limite=$1 version_attendue=$2 debut=$SECONDS stable_depuis=-1
    local dossier diagnostic dernier_diagnostic=""
    dossier="$(mktemp -d /tmp/phyto-health.XXXXXX)"
    while (( SECONDS - debut < limite )); do
        if diagnostic="$(sonder_sante "$version_attendue" "$dossier")"; then
            if (( stable_depuis < 0 )); then
                stable_depuis=$SECONDS
                dernier_diagnostic=""
                info "Santé complète acquise ; observation pendant ${STABILITE_SANTE}s"
            fi
            if (( SECONDS - stable_depuis >= STABILITE_SANTE )); then
                nettoyer_sonde "$dossier"
                return 0
            fi
        else
            stable_depuis=-1
            if [[ "$diagnostic" != "$dernier_diagnostic" ]]; then
                attn "Contrôle en attente : $diagnostic"
                dernier_diagnostic="$diagnostic"
            fi
        fi
        sleep 1
    done
    nettoyer_sonde "$dossier"
    return 1
}

info "Redemarrage de $SERVICE"
sudo systemctl restart "$SERVICE"

if attendre_sante "$DELAI_SANTE" "$SHA_APRES"; then
    ok "Service actif et santé complète stable ${STABILITE_SANTE}s sur le port $PORT"
    printf "\n"
    systemctl --no-pager --lines=0 status "$SERVICE" | head -5
    printf "\n"
    info "Derniers logs :"
    journalctl -u "$SERVICE" -n 15 --no-pager -o cat | sed 's/^/     /'
    ok "Deploiement termine — $CIBLE_REF @ $(git log -1 --oneline)"
    exit 0
fi

# --- 8. Rollback -------------------------------------------------------------
echec "La santé complète n'est pas stable après ${DELAI_SANTE}s — rollback."
journalctl -u "$SERVICE" -n 30 --no-pager -o cat | sed 's/^/     /' >&2

if [[ "$SHA_AVANT" == "$SHA_APRES" ]]; then
    mourir "Aucun commit n'a ete applique : la panne vient d'ailleurs (materiel, config)."
fi

git checkout --force --detach "$SHA_AVANT" >/dev/null 2>&1
sudo systemctl restart "$SERVICE"

if attendre_sante "$DELAI_SANTE" "$SHA_AVANT"; then
    attn "Rollback reussi : retour sur $(git log -1 --oneline)"
else
    echec "Rollback effectue mais le service ne repond toujours pas. Intervention manuelle requise :"
    echec "  sudo systemctl status $SERVICE ; journalctl -u $SERVICE -n 100"
fi
exit 1
