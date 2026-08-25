#!/usr/bin/env bash
#
# phyto-ssh.sh — execute une commande sur le PhytoController depuis WSL.
#
# WSL2 ne peut pas joindre le LAN directement (NAT / pare-feu Hyper-V), donc on
# delegue au client OpenSSH de Windows, qui utilise l'alias "phyto" defini par
# ./scripts/setup-ssh-bridge.sh.
#
# Usage :
#   ./scripts/phyto-ssh.sh 'journalctl -n 200 --no-pager'
#   ./scripts/phyto-ssh.sh 'cat ~/PhytoController/param/param.json'
#   ./scripts/phyto-ssh.sh                 # session interactive
#
# Variables d'environnement :
#   PHYTO_HOST   alias ou user@ip a utiliser (defaut : phyto)
#
set -euo pipefail

PHYTO_HOST="${PHYTO_HOST:-phyto}"

SSH_EXE=""
for candidate in \
    /mnt/c/Windows/System32/OpenSSH/ssh.exe \
    /mnt/c/Program*/OpenSSH/ssh.exe ; do
    [ -x "$candidate" ] && { SSH_EXE="$candidate"; break; }
done
if [ -z "$SSH_EXE" ]; then
    echo "ssh.exe introuvable — lance d'abord ./scripts/setup-ssh-bridge.sh" >&2
    exit 1
fi

if [ "$#" -eq 0 ]; then
    exec "$SSH_EXE" "$PHYTO_HOST"
fi

# BatchMode : jamais de prompt de mot de passe, on echoue vite si la cle
# n'est pas (ou plus) installee — indispensable pour un appel non interactif.
set +e
out="$("$SSH_EXE" -o BatchMode=yes "$PHYTO_HOST" "$@" 2>&1)"
status=$?
set -e

if [ "$status" -ne 0 ]; then
    printf '%s\n' "$out" >&2
    case "$out" in
        *"Permission denied"*|*"Could not resolve"*|*"No such host"*)
            echo "-> Pont SSH non configure ou casse : ./scripts/setup-ssh-bridge.sh" >&2 ;;
        *"Connection timed out"*|*"refused"*)
            echo "-> Pi injoignable : verifie qu'il est allume et sur le reseau." >&2 ;;
    esac
    exit "$status"
fi
printf '%s\n' "$out"
