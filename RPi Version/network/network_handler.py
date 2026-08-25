# controller/network_handler.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Gestion réseau : connexion Wi-Fi & test reachabilité hôte
# -------------------------------------------------------------

from __future__ import annotations

import os
import subprocess

from utils.pretty_console import debug, success, warning, error, action

LOGGER_NAME = "network"
from param.config       import AppConfig

def do_connect() -> None:
    """
    Active la radio Wi-Fi (nmcli) puis tente de se connecter sur SSID/PASS
    définis dans AppConfig.network. Nécessite les droits root.
    """
    # Recharge la config à jour
    config = AppConfig.load()
    ssid     = config.network.wifi_ssid
    password = config.network.wifi_password

    action(f"Tentative de connexion au Wi-Fi SSID : '{ssid}'", name=LOGGER_NAME)

    if os.geteuid() != 0:
        warning(
            "Exécutez le script en root pour activer le Wi-Fi : sudo python3 main.py",
            name=LOGGER_NAME,
        )
        return

    try:
        # Active la radio Wi-Fi
        subprocess.run(["nmcli", "radio", "wifi", "on"], check=True)
        # Se connecte
        subprocess.run(
            ["nmcli", "device", "wifi", "connect", ssid, "password", password],
            check=True
        )
        success("Connexion Wi-Fi réussie", name=LOGGER_NAME)

    except subprocess.CalledProcessError as exc:
        error(f"Erreur de connexion Wi-Fi : {exc}", name=LOGGER_NAME)


def is_host_connected() -> str:
    """
    Ping l'hôte configuré dans AppConfig.network.host_machine_address
    (1 paquet, timeout 1 s) ; renvoie « online » ou « offline ».
    """
    # Recharge la config à jour
    config = AppConfig.load()
    host = config.network.host_machine_address

    debug(f"Ping vers {host} …", name=LOGGER_NAME)
    try:
        ret = subprocess.run(
            ["ping", "-c", "1", "-W", "1", host],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode

        if ret == 0:
            success("Hôte joignable", name=LOGGER_NAME)
            return "online"

        warning("Hôte injoignable", name=LOGGER_NAME)
        return "offline"

    except Exception as exc:
        error(f"Erreur ping : {exc}", name=LOGGER_NAME)
        return "offline"
