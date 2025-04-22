# controller/network_handler.py
# Author : Progradius (adapted)
# License: AGPL-3.0
# -------------------------------------------------------------
#  Gestion réseau : connexion Wi-Fi & test reachabilité hôte
# -------------------------------------------------------------

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from controller.ui.pretty_console import (
    info, success, warning, error, action
)
from controller.parameter_handler import read_parameters_from_json

# ──────────────────────────────────────────────────────────────
#  Paramètres réseau depuis param.json
# ──────────────────────────────────────────────────────────────
_param = read_parameters_from_json()
_NET   = _param["Network_Settings"]

SSID      = _NET["wifi_ssid"]
PASSWORD  = _NET["wifi_password"]
HOST_ADDR = _NET["host_machine_address"]

# ──────────────────────────────────────────────────────────────
#  Connexion Wi-Fi
# ──────────────────────────────────────────────────────────────
def do_connect() -> None:
    """
    Active la radio Wi-Fi (nmcli) puis tente de se connecter sur SSID/PASS.
    Nécessite les droits root, sinon on avertit l'utilisateur.
    """
    action(f"Tentative de connexion au Wi-Fi SSID : '{SSID}'")

    if os.geteuid() != 0:
        warning("Exécutez le script en root pour activer le Wi-Fi :"
                "  sudo python3 main.py")
        return

    try:
        # Active la radio
        subprocess.run(["nmcli", "radio", "wifi", "on"], check=True)

        # Se connecte
        subprocess.run(
            ["nmcli", "device", "wifi", "connect", SSID, "password", PASSWORD],
            check=True
        )

        success("Connexion Wi-Fi réussie ✅")

    except subprocess.CalledProcessError as exc:
        error(f"Erreur de connexion Wi-Fi : {exc}")

# ──────────────────────────────────────────────────────────────
#  Test de présence du serveur distant
# ──────────────────────────────────────────────────────────────
def is_host_connected() -> str:
    """
    Ping (1 paquet, timeout 1 s) ; renvoie « online/offline ».
    """
    info(f"Ping vers {HOST_ADDR} …")
    try:
        ret = subprocess.run(
            ["ping", "-c", "1", "-W", "1", HOST_ADDR],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode

        if ret == 0:
            success("Hôte joignable 🎯")
            return "online"

        warning("Hôte injoignable")
        return "offline"

    except Exception as exc:
        error(f"Erreur ping : {exc}")
        return "offline"
