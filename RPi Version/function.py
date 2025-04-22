# function.py
# Author: Progradius (adapted)
# License: AGPL 3.0

import os
import shutil
import subprocess
import time

import RPi.GPIO as GPIO

from controller.parameter_handler import read_parameters_from_json

# Init global GPIO (BCM mode, warnings off)
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Charge les paramètres JSON
parameters = read_parameters_from_json()


def convert_time_to_minutes(hour, minute):
    return int(hour) * 60 + int(minute)


def convert_time_to_seconds(hour, minute, second):
    return int(hour) * 3600 + int(minute) * 60 + int(second)


def convert_minute_to_seconds(minutes):
    return int(minutes) * 60


def check_disk_usage(path: str = '/') -> str:
    total, used, free = shutil.disk_usage(path)
    return f"{free / (1024**3):.2f} GB"


def check_ram_usage() -> None:
    """
    Affiche les stats RAM (total, disponible, pourcentage de libre)
    sans dépendance externe.
    """
    meminfo = {}
    with open('/proc/meminfo') as f:
        for line in f:
            key, val = line.split(':')
            meminfo[key] = int(val.strip().split()[0])  # en kB

    total_kb = meminfo.get('MemTotal', 0)
    avail_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
    pct_free = avail_kb / total_kb * 100 if total_kb else 0

    print(f"RAM Total: {total_kb/1024:.2f} MB, Disponible: {avail_kb/1024:.2f} MB ({pct_free:.2f}%)")


def set_ntp_time() -> None:
    """
    Active la synchronisation NTP via systemd-timesyncd (timedatectl).
    Nécessite d'être exécuté avec sudo (ou que l'utilisateur ait les droits).
    """
    try:
        # active la synchro NTP
        subprocess.run(['sudo', 'timedatectl', 'set-ntp', 'true'], check=True)
        # optionnel : vérification du statut
        status = subprocess.run(['timedatectl', 'show', '-p', 'NTPSynchronized'], 
                                capture_output=True, text=True)
        print("🕒 NTP synchronization status:", status.stdout.strip())
    except subprocess.CalledProcessError as e:
        print("❌ Échec timedatectl set-ntp :", e)
    except Exception as e:
        print("❌ Erreur lors de la synchronisation NTP :", e)


def motor_all_pin_down_at_boot() -> None:
    """
    Met toutes les broches moteur à LOW au démarrage (sécurité).
    """
    pins = [
        parameters["GPIO_Settings"]["motor_pin1"],
        parameters["GPIO_Settings"]["motor_pin2"],
        parameters["GPIO_Settings"]["motor_pin3"],
        parameters["GPIO_Settings"]["motor_pin4"],
    ]
    for pin in pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.LOW)
    print("🔧 Broches moteur mises à LOW au boot.")
