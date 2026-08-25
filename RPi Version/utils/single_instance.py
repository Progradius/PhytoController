# utils/single_instance.py
# Author : Progradius
# License: AGPL-3.0
"""
Verrou d'instance unique (audit C4).

Deux processus PhytoController vivants en même temps se battent pour les mêmes
broches : chacun force les génériques à HIGH (coupant lumières/chauffage que
l'autre tenait ON), remet le moteur à 0 et réécrit les JSON de config. RPi.GPIO
passe par `/dev/gpiomem` (mmap sans notion de propriétaire) : rien au niveau du
noyau n'empêche ce scénario.

Le verrou est un **socket Unix en espace de noms abstrait** (préfixe `\\0`) et
non un fichier :
  • aucun chemin à choisir entre `/run` (root seulement) et `/tmp` (isolé si
    l'unité systemd active `PrivateTmp=yes`) — le service tourne sous
    `progradius`, un lancement manuel sous `root` : les deux doivent se voir ;
  • le noyau le libère à la mort du processus, quelle qu'en soit la cause
    (SIGKILL, OOM, coupure) : pas de verrou périmé à nettoyer ;
  • pas de droits d'accès à gérer, pas de fichier qui traîne sur la carte SD.
"""

from __future__ import annotations

import socket
import sys
import time

from utils.pretty_console import debug, error, success

LOGGER_NAME = "main"

# Le `\0` initial place le nom dans l'espace de noms abstrait (Linux) : il ne
# correspond à aucune entrée du système de fichiers.
LOCK_ADDRESS = "\0phyto-controller"

# Un `systemctl restart` laisse l'ancien processus agoniser quelques secondes
# (fermeture du serveur HTTP, état sûr des GPIO). On lui laisse le temps de
# mourir plutôt que d'échouer immédiatement.
DEFAULT_TIMEOUT_S = 15.0
RETRY_DELAY_S = 0.5

# Référence conservée pour la durée du processus : si le socket est ramassé par
# le GC, le verrou est relâché.
_lock_socket: socket.socket | None = None


def acquire_single_instance(timeout_s: float = DEFAULT_TIMEOUT_S) -> bool:
    """
    Tente de prendre le verrou, avec une attente bornée.

    Retourne True si le verrou est acquis, False si une autre instance le
    détient toujours après `timeout_s`. N'effectue **aucune** action GPIO.
    """
    global _lock_socket

    if _lock_socket is not None:
        return True

    deadline = time.monotonic() + timeout_s
    waited = False

    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.bind(LOCK_ADDRESS)
        except OSError:
            sock.close()
            if time.monotonic() >= deadline:
                return False
            if not waited:
                waited = True
                debug(
                    "Une autre instance détient le verrou → attente de sa sortie…",
                    name=LOGGER_NAME,
                )
            time.sleep(RETRY_DELAY_S)
            continue

        _lock_socket = sock
        return True


def ensure_single_instance(timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
    """
    Garde-fou à appeler tout en haut de `main.py`, avant tout accès GPIO et
    avant l'enregistrement des handlers de signaux / `atexit`.

    En cas d'échec on sort avec un code **non nul** : systemd doit voir une
    panne (et `scripts/deploy.sh` faire échouer son contrôle de santé) plutôt
    qu'un service « exited » silencieux qui laisserait la serre sans
    régulateur.
    """
    if acquire_single_instance(timeout_s):
        debug("Verrou d'instance acquis", name=LOGGER_NAME)
        return

    error(
        "Une autre instance de PhytoController est déjà active → arrêt "
        "immédiat (aucune broche GPIO n'a été touchée)",
        name=LOGGER_NAME,
    )
    sys.exit(1)


def release_single_instance() -> None:
    """Relâche explicitement le verrou (le noyau le fait de toute façon)."""
    global _lock_socket

    if _lock_socket is None:
        return
    try:
        _lock_socket.close()
    except OSError:
        pass
    finally:
        _lock_socket = None
        success("Verrou d'instance relâché", name=LOGGER_NAME)
