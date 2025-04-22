# controller/network_handler.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import os
import subprocess
import sys
import time
from controller.parameter_handler import read_parameters_from_json

parameters = read_parameters_from_json()

def do_connect():
    """
    Connexion au Wi-Fi via nmcli.
    Vous devez lancer ce script avec sudo (root) pour que nmcli 
    puisse piloter la radio et les connexions.
    """
    ssid     = parameters["Network_Settings"]["wifi_ssid"]
    password = parameters["Network_Settings"]["wifi_password"]

    print(f"Tentative de connexion au Wi-Fi SSID : {ssid}")

    if os.geteuid() != 0:
        print("⚠️  Vous n'êtes pas en root : exécutez 'sudo python3 main.py'")
        return

    try:
        # Active la radio Wi-Fi
        subprocess.run(["nmcli", "radio", "wifi", "on"], check=True)

        # Connexion au réseau
        subprocess.run([
            "nmcli", "device", "wifi",
            "connect", ssid, "password", password
        ], check=True)

        print("✅ Connexion Wi-Fi réussie.")

    except subprocess.CalledProcessError as e:
        print("❌ Erreur de connexion Wi-Fi :", e)


def is_host_connected():
    """
    Vérifie si le host est joignable en pingant une fois avec timeout 1 s.
    """
    host = parameters["Network_Settings"]["host_machine_address"]
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if result.returncode == 0:
            print("Host activé (ping OK).")
            return "online"
        else:
            print("Host désactivé (ping KO).")
            return "offline"
    except Exception as e:
        print("❌ Erreur lors du ping :", e)
        return "offline"
