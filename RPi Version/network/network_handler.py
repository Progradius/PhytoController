# controller/network_handler.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Gestion réseau : connexion Wi-Fi & test reachabilité hôte
# -------------------------------------------------------------

from __future__ import annotations

import os
import subprocess

from param.config_store import shared_config
from utils.pretty_console import debug, success, warning, error, action

LOGGER_NAME = "network"

def get_connected_wifi_device() -> str | None:
    """
    Renvoie le nom de la première interface Wi-Fi déjà connectée (ex. « wlan0 »),
    ou None si aucune ne l'est / si nmcli est indisponible.

    Sert à ne pas rejouer une connexion que NetworkManager a déjà établie tout
    seul au boot (profil en autoconnect) : c'est le cas nominal sous systemd.
    """
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"],
            capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        debug(f"État nmcli illisible : {exc}", name=LOGGER_NAME)
        return None

    for ligne in out.splitlines():
        champs = ligne.split(":")
        # « wifi » strict : « wifi-p2p » n'est pas une interface utilisable
        if len(champs) >= 3 and champs[1] == "wifi" and champs[2] == "connected":
            return champs[0]
    return None


def do_connect() -> None:
    """
    Active la radio Wi-Fi (nmcli) puis tente de se connecter sur SSID/PASS
    définis dans AppConfig.network.

    Si une interface Wi-Fi est déjà connectée (NetworkManager l'a fait au boot),
    on ne touche à rien : root n'est alors pas nécessaire.
    """
    deja = get_connected_wifi_device()
    if deja:
        success(f"Wi-Fi déjà connecté ({deja}) → aucune action", name=LOGGER_NAME)
        return

    # Configuration à jour, servie par le magasin partagé
    config = shared_config().refresh()
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
    # Configuration à jour, servie par le magasin partagé
    config = shared_config().refresh()
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
