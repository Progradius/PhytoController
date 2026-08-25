# utils/watchdog.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Watchdog piloté par la santé applicative (audit E2)
# -------------------------------------------------------------
"""
L'ancien watchdog était **aveugle** : un thread écrivait sur `/dev/watchdog`
toutes les 10 s sans jamais consulter l'état des tâches. Un event loop bloqué
ou six tâches mortes étaient donc parfaitement invisibles — le watchdog
garantissait seulement que le thread tournait, c'est-à-dire rien.

Ici, le coup de patte est **conditionnel** : il n'est donné que si le
superviseur déclare toutes ses tâches vivantes et récentes. Dès qu'un travail
est mort ou muet, on cesse de caresser et le redémarrage arrive tout seul.

Deux mécanismes, jamais les deux à la fois :

  1. **systemd** (`Type=notify` + `WatchdogSec=`) — voie idiomatique.
     `NOTIFY_SOCKET` et `WATCHDOG_USEC` sont posés par systemd ; on renvoie
     `WATCHDOG=1` et un `STATUS=` lisible dans `systemctl status`.
  2. **`/dev/watchdog` en direct** — hors systemd. Le descripteur est ouvert
     **une seule fois** et conservé ici : le « magic close » (`V`) doit être
     écrit sur *ce* descripteur, l'ancienne implémentation rouvrait le
     périphérique et échouait en `EBUSY`.

La boucle de caresse tourne dans l'event loop (et non dans un thread) : un
event loop bloqué doit cesser de caresser, c'est précisément le défaut qu'on
cherche à détecter.

Variable d'environnement `PHYTO_HW_WATCHDOG` : `0` pour désactiver l'accès
direct à `/dev/watchdog`. **Le défaut est maintenant « activé »** (audit E2).
Sur un Pi où systemd tient déjà le périphérique (`RuntimeWatchdogSec=`),
l'ouverture échoue proprement en `EBUSY` : on le journalise et on continue.
"""

from __future__ import annotations

import asyncio
import os
import socket
from typing import Callable

from utils.pretty_console import debug, info, success, warning

LOGGER_NAME = "watchdog"

HW_WATCHDOG_PATH = "/dev/watchdog"
# Période de repli quand systemd n'impose rien (le watchdog matériel du Pi
# expire typiquement à 15 s).
DEFAULT_PET_PERIOD_SECONDS = 10.0

# Plafond de la période de caresse. La convention systemd (`WatchdogSec/2`)
# suppose une caresse **inconditionnelle** : elle ne laisse alors qu'un seul
# raté avant l'expiration. Ici la caresse dépend de la santé applicative, donc
# un unique contrôle malheureux (une tâche momentanément muette que le
# superviseur relance 30 s plus tard) ferait redémarrer le service.
# En caressant bien plus souvent que nécessaire, un défaut doit **persister**
# tout le `WatchdogSec` pour provoquer un redémarrage : le superviseur agit
# d'abord, systemd n'intervient que s'il a lui-même échoué.
MAX_PET_PERIOD_SECONDS = 30.0

_hw_fd: int | None = None
_notify_socket_path: str | None = None


# ─────────────────────────────────────────────────────────────
#  systemd : sd_notify
# ─────────────────────────────────────────────────────────────
def notify(state: str) -> bool:
    """
    Envoie un message `sd_notify`. Retourne False si le processus ne tourne pas
    sous un systemd `Type=notify` (cas normal en exécution manuelle).
    """
    global _notify_socket_path
    if _notify_socket_path is None:
        _notify_socket_path = os.getenv("NOTIFY_SOCKET", "")
    if not _notify_socket_path:
        return False

    addr = _notify_socket_path
    # Socket abstraite : systemd la note « @/chemin », l'API attend un NUL.
    if addr.startswith("@"):
        addr = "\0" + addr[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(state.encode("utf-8"))
        return True
    except OSError as e:
        debug(f"sd_notify indisponible : {e}", name=LOGGER_NAME)
        return False


def notify_ready() -> bool:
    """À appeler une fois toutes les tâches lancées (`Type=notify`)."""
    if notify("READY=1"):
        success("systemd notifié : service prêt", name=LOGGER_NAME)
        return True
    return False


def systemd_watchdog_period() -> float | None:
    """
    Demi-période imposée par `WatchdogSec=` (systemd attend une caresse **deux
    fois** plus souvent que le délai d'expiration). None si non configuré.
    """
    raw = os.getenv("WATCHDOG_USEC")
    if not raw:
        return None
    pid = os.getenv("WATCHDOG_PID")
    if pid and pid != str(os.getpid()):
        # Le watchdog était destiné au processus parent, pas à nous.
        return None
    try:
        usec = int(raw)
    except ValueError:
        warning(f"WATCHDOG_USEC illisible : {raw!r}", name=LOGGER_NAME)
        return None
    return max(1.0, usec / 2_000_000)


# ─────────────────────────────────────────────────────────────
#  /dev/watchdog en direct
# ─────────────────────────────────────────────────────────────
def open_hw_watchdog() -> bool:
    """
    Ouvre `/dev/watchdog` et conserve le descripteur au niveau module.
    Ouvrir **arme** le watchdog matériel : à partir de là, ne plus écrire
    provoque le redémarrage de la machine.
    """
    global _hw_fd
    if _hw_fd is not None:
        return True
    try:
        _hw_fd = os.open(HW_WATCHDOG_PATH, os.O_WRONLY)
    except OSError as e:
        warning(f"Watchdog matériel non disponible : {e}", name=LOGGER_NAME)
        _hw_fd = None
        return False
    success("Watchdog matériel armé", name=LOGGER_NAME)
    return True


def pet_hw_watchdog() -> None:
    if _hw_fd is None:
        return
    try:
        os.write(_hw_fd, b"\n")
    except OSError as e:
        warning(f"Écriture watchdog impossible : {e}", name=LOGGER_NAME)


def close_hw_watchdog() -> None:
    """
    « Magic close » : écrire `V` **sur le descripteur déjà ouvert** demande au
    pilote de désarmer au lieu de redémarrer. Rouvrir le périphérique pour ça
    (ancien code) échoue en `EBUSY` et laissait donc le watchdog armé.
    """
    global _hw_fd
    if _hw_fd is None:
        return
    try:
        os.write(_hw_fd, b"V")
        success("Watchdog matériel désarmé proprement", name=LOGGER_NAME)
    except OSError as e:
        warning(f"Désarmement du watchdog impossible : {e}", name=LOGGER_NAME)
    finally:
        try:
            os.close(_hw_fd)
        except OSError:
            pass
        _hw_fd = None


def hw_watchdog_enabled() -> bool:
    """Défaut : activé, sauf opt-out explicite `PHYTO_HW_WATCHDOG=0`."""
    return os.getenv("PHYTO_HW_WATCHDOG", "1") != "0"


# ─────────────────────────────────────────────────────────────
#  Boucle de caresse conditionnelle
# ─────────────────────────────────────────────────────────────
async def watchdog_loop(
    is_healthy: Callable[[], bool],
    unhealthy_names: Callable[[], list] | None = None,
) -> None:
    """
    Caresse systemd et/ou `/dev/watchdog`, **uniquement** si `is_healthy()`.

    Cette coroutine est volontairement lancée en tâche nue, hors superviseur :
    si elle meurt, plus personne ne caresse → redémarrage. C'est le bon sens de
    la panne, contrairement à une relance qui masquerait le défaut.
    """
    systemd_period = systemd_watchdog_period()
    use_systemd = systemd_period is not None
    use_hw = False

    if use_systemd:
        info(
            f"Watchdog systemd actif (expiration {systemd_period * 2:.0f} s, "
            f"caresse toutes les {min(systemd_period, MAX_PET_PERIOD_SECONDS):.0f} s, "
            "conditionnée à la santé des tâches)",
            name=LOGGER_NAME,
        )
    elif hw_watchdog_enabled():
        use_hw = open_hw_watchdog()
    else:
        debug("Watchdog matériel désactivé (PHYTO_HW_WATCHDOG=0)", name=LOGGER_NAME)

    if not use_systemd and not use_hw:
        warning(
            "Aucun watchdog actif : une tâche bloquée ne provoquera pas de "
            "redémarrage automatique",
            name=LOGGER_NAME,
        )
        return

    period = (
        min(systemd_period, MAX_PET_PERIOD_SECONDS)
        if use_systemd
        else DEFAULT_PET_PERIOD_SECONDS
    )
    was_healthy = True

    while True:
        await asyncio.sleep(period)

        healthy = False
        try:
            healthy = bool(is_healthy())
        except Exception as e:
            warning(
                f"Contrôle de santé impossible : {e.__class__.__name__} : {e} "
                "→ traité comme une panne",
                name=LOGGER_NAME,
            )

        if healthy:
            if not was_healthy:
                success("Santé rétablie → reprise des caresses au watchdog",
                        name=LOGGER_NAME)
                if use_systemd:
                    notify("STATUS=Toutes les tâches sont saines")
            was_healthy = True
            if use_systemd:
                notify("WATCHDOG=1")
            if use_hw:
                pet_hw_watchdog()
        else:
            names = []
            if unhealthy_names is not None:
                try:
                    names = list(unhealthy_names())
                except Exception:
                    names = []
            detail = ", ".join(names) if names else "cause inconnue"
            if was_healthy:
                warning(
                    f"Tâches en défaut ({detail}) → watchdog NON caressé, "
                    "redémarrage attendu si la situation persiste",
                    name=LOGGER_NAME,
                )
            was_healthy = False
            if use_systemd:
                notify(f"STATUS=Tâches en défaut : {detail}")
