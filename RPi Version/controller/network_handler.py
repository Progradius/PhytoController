# Author: Progradius
# License: AGPL 3.0

import subprocess
import time
from controller.parameter_handler import read_parameters_from_json

parameters = read_parameters_from_json()

def do_connect():
    """
    Connexion au Wi-Fi via nmcli (NetworkManager).
    Assurez-vous que NetworkManager est installé et gère l'interface Wi-Fi.
    """
    ssid = parameters["Network_Settings"]["wifi_ssid"]
    password = parameters["Network_Settings"]["wifi_password"]
    static_ip = "192.168.1.20/24"
    gateway = "192.168.1.1"

    print(f"Tentative de connexion au Wi-Fi SSID: {ssid}")
    
    try:
        # Active le Wi-Fi
        subprocess.run(["nmcli", "radio", "wifi", "on"], check=True)

        # Connexion au réseau
        subprocess.run([
            "nmcli", "device", "wifi", "connect", ssid, "password", password
        ], check=True)

        print("Connexion réussie.")

        # Si tu veux forcer une IP statique (facultatif)
        # Tu pourrais aussi modifier /etc/dhcpcd.conf pour une conf permanente
        # subprocess.run(["nmcli", "con", "mod", ssid, "ipv4.addresses", static_ip, "ipv4.gateway", gateway, "ipv4.method", "manual"], check=True)
        # subprocess.run(["nmcli", "con", "up", ssid], check=True)

    except subprocess.CalledProcessError as e:
        print("Erreur de connexion Wi-Fi :", e)


def is_host_connected():
    """
    Vérifie si le host est joignable via ping.
    """
    host = parameters["Network_Settings"]["host_machine_address"]
    try:
        result = subprocess.run(
            ["ping", "-c", "4", "-W", "5", host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        if result.returncode == 0:
            print("Host Activated")
            return "online"
        else:
            print("Host Deactivated")
            return "offline"
    except Exception as e:
        print("Erreur lors du ping :", e)
        return "offline"
