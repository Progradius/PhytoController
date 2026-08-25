#!/usr/bin/env bash
#
# setup-ssh-bridge.sh — met en place un acces SSH sans mot de passe vers le
# PhytoController (Raspberry Pi), utilisable depuis WSL.
#
# Pourquoi ce script :
#   WSL2 est derriere un NAT / pare-feu Hyper-V et ne peut pas joindre le LAN
#   192.168.1.0/24 ("No route to host"). On passe donc par le client OpenSSH
#   *de Windows* (ssh.exe), qui lui a un acces direct au reseau local.
#
# Ce script :
#   1. localise ssh.exe et le repertoire .ssh de Windows
#   2. verifie que le Pi repond sur le port 22
#   3. genere une paire de cles si necessaire
#   4. installe la cle publique dans ~/.ssh/authorized_keys du Pi
#      (demande le mot de passe UNE seule fois)
#   5. ajoute/actualise un alias "phyto" dans le ssh_config Windows
#   6. verifie que la connexion par cle fonctionne
#
# Usage :
#   ./scripts/setup-ssh-bridge.sh                       # defauts ci-dessous
#   ./scripts/setup-ssh-bridge.sh 192.168.1.15 progradius phyto
#
set -euo pipefail

HOST_IP="${1:-192.168.1.15}"
SSH_USER="${2:-progradius}"
ALIAS="${3:-phyto}"

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()    { printf '\033[1;32m OK\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m  !\033[0m %s\n' "$*"; }
die()   { printf '\033[1;31mERR\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. environnement -------------------------------------------------------
grep -qi microsoft /proc/version 2>/dev/null || die "Ce script est prevu pour WSL."

SSH_EXE=""
for candidate in \
    /mnt/c/Windows/System32/OpenSSH/ssh.exe \
    /mnt/c/Program*/OpenSSH/ssh.exe ; do
    [ -x "$candidate" ] && { SSH_EXE="$candidate"; break; }
done
[ -n "$SSH_EXE" ] || die "ssh.exe introuvable. Installe le client OpenSSH de Windows
  (Parametres > Applications > Fonctionnalites facultatives > Client OpenSSH)."
KEYGEN_EXE="${SSH_EXE%ssh.exe}ssh-keygen.exe"
ok "client SSH Windows : $SSH_EXE"

WIN_HOME_RAW="$(/mnt/c/Windows/System32/cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r\n')"
[ -n "$WIN_HOME_RAW" ] || die "Impossible de determiner %USERPROFILE%."
WIN_HOME="$(wslpath -u "$WIN_HOME_RAW")"
SSH_DIR="$WIN_HOME/.ssh"
SSH_CONFIG="$SSH_DIR/config"
KEY_PRIV="$SSH_DIR/id_rsa"
KEY_PUB="$KEY_PRIV.pub"
mkdir -p "$SSH_DIR"
ok "repertoire SSH Windows : $SSH_DIR"

# --- 2. joignabilite --------------------------------------------------------
info "Test du port 22 sur $HOST_IP ..."
PS_EXE=/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe
if [ -x "$PS_EXE" ]; then
    reachable="$("$PS_EXE" -NoProfile -Command \
        "(Test-NetConnection -ComputerName $HOST_IP -Port 22 -WarningAction SilentlyContinue).TcpTestSucceeded" \
        2>/dev/null | tr -d '\r\n ')"
    [ "$reachable" = "True" ] \
        || die "$HOST_IP:22 injoignable depuis Windows. Le Pi est-il allume et sur le meme reseau ?"
    ok "$HOST_IP:22 accessible"
else
    warn "powershell.exe introuvable, test de joignabilite ignore"
fi

# --- 3. cle -----------------------------------------------------------------
if [ -f "$KEY_PUB" ]; then
    ok "cle existante reutilisee : $KEY_PUB"
else
    info "Aucune cle trouvee, generation d'une paire ed25519 ..."
    "$KEYGEN_EXE" -t ed25519 -N '' -f "$(wslpath -w "$SSH_DIR")\\id_ed25519" >/dev/null
    KEY_PRIV="$SSH_DIR/id_ed25519"
    KEY_PUB="$KEY_PRIV.pub"
    ok "cle generee : $KEY_PUB"
fi
PUBKEY="$(tr -d '\r\n' < "$KEY_PUB")"
[ -n "$PUBKEY" ] || die "Cle publique vide : $KEY_PUB"

# --- 4. installation de la cle sur le Pi ------------------------------------
info "Verification de l'authentification par cle ..."
if "$SSH_EXE" -o BatchMode=yes -o ConnectTimeout=8 -i "$(wslpath -w "$KEY_PRIV")" \
        "$SSH_USER@$HOST_IP" true 2>/dev/null; then
    ok "la cle est deja autorisee sur le Pi"
else
    info "Installation de la cle publique sur $SSH_USER@$HOST_IP"
    warn "Le mot de passe de '$SSH_USER' va etre demande (une seule fois)."
    # La cle est passee en argument, pas via stdin : stdin reste libre pour
    # que ssh.exe puisse lire le mot de passe au clavier.
    "$SSH_EXE" -o ConnectTimeout=10 "$SSH_USER@$HOST_IP" \
        "set -e
         mkdir -p ~/.ssh && chmod 700 ~/.ssh
         touch ~/.ssh/authorized_keys
         grep -qxF '$PUBKEY' ~/.ssh/authorized_keys || echo '$PUBKEY' >> ~/.ssh/authorized_keys
         chmod 600 ~/.ssh/authorized_keys" \
        || die "Installation de la cle echouee (mot de passe errone, ou PasswordAuthentication desactive sur le Pi)."
    ok "cle publique installee"
fi

# --- 5. alias dans le ssh_config Windows ------------------------------------
info "Mise a jour de l'alias '$ALIAS' dans $SSH_CONFIG"
touch "$SSH_CONFIG"
tmp="$(mktemp)"
# on retire un eventuel bloc "Host <alias>" existant, puis on le reecrit
awk -v alias="$ALIAS" '
    /^[Hh]ost[ \t]/ { in_block = ($2 == alias) }
    !in_block { print }
' "$SSH_CONFIG" > "$tmp"
{
    # une seule ligne vide de separation
    sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' "$tmp"
    printf '\nHost %s\n' "$ALIAS"
    printf '  HostName %s\n' "$HOST_IP"
    printf '  User %s\n' "$SSH_USER"
    printf '  IdentityFile ~/.ssh/%s\n' "$(basename "$KEY_PRIV")"
    printf '  IdentitiesOnly yes\n'
    printf '  ServerAliveInterval 15\n'
    # Wi-Fi domestique : quelques tentatives valent mieux qu'un timeout court
    printf '  ConnectTimeout 15\n'
    printf '  ConnectionAttempts 3\n'
} > "$SSH_CONFIG.new"
# ecriture par copie (pas de rename atomique : casse sur les montages drvfs)
cat "$SSH_CONFIG.new" > "$SSH_CONFIG"
rm -f "$tmp" "$SSH_CONFIG.new"
ok "alias '$ALIAS' configure"

# --- 6. verification finale -------------------------------------------------
info "Verification de bout en bout ..."
remote_id="$("$SSH_EXE" -o BatchMode=yes "$ALIAS" 'echo "$(hostname) | $(uname -srm)"' 2>&1)" \
    || die "La connexion par cle echoue toujours : $remote_id"
ok "connecte : $remote_id"

cat <<EOF

------------------------------------------------------------------
Pont SSH pret.

  Utilisation manuelle :
    $SSH_EXE $ALIAS

  Wrapper fourni (a utiliser depuis WSL, y compris par Claude Code) :
    ./scripts/phyto-ssh.sh 'journalctl -n 200 --no-pager'
    ./scripts/phyto-ssh.sh 'cat ~/PhytoController/param/*.json'
------------------------------------------------------------------
EOF
