# function.py
# Author : Progradius (refactorisé)
# License: AGPL-3.0
# ------------------------------------------------------------------
#  Fonctions utilitaires « système »  (temps, stockage, GPIO, …)
# ------------------------------------------------------------------

import shutil
import subprocess

import RPi.GPIO as GPIO

from param.config import AppConfig
from ui.pretty_console import info, success, warning, error

# ───────────────────────────────────────────────────────────────
#  Init GPIO global – BCM & warnings off
# ───────────────────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# ==================================================================
#                       OUTILS DE CONVERSION TEMPS
# ==================================================================
convert_time_to_minutes   = lambda h, m   : int(h)*60   + int(m)
convert_time_to_seconds   = lambda h, m, s: int(h)*3600 + int(m)*60 + int(s)
convert_minute_to_seconds = lambda m      : int(m)*60

# ==================================================================
#                        INFO STOCKAGE / RAM
# ==================================================================
def check_disk_usage(path: str = "/") -> str:
    """
    Retourne l'espace libre sur *path* sous forme 'X.XX GB'.
    """
    total, used, free = shutil.disk_usage(path)
    return f"{free / (1024**3):.2f} GB"

def check_ram_usage() -> None:
    """
    Affiche la RAM totale et disponible.
    Utilise /proc/meminfo (Linux only).
    """
    mem = {}
    with open("/proc/meminfo") as f:
        for line in f:
            key, val = line.split(":")
            mem[key] = int(val.strip().split()[0])   # en kB

    total = mem.get("MemTotal", 0)
    avail = mem.get("MemAvailable", mem.get("MemFree", 0))
    pct   = avail / total * 100 if total else 0

    info(f"RAM Total : {total/1024:.1f} MB | Libre : {avail/1024:.1f} MB ({pct:.1f} %)")

# ==================================================================
#                       SYNCHRONISATION NTP
# ==================================================================
def set_ntp_time() -> None:
    """
    Active (ou vérifie) la synchro NTP via systemd‐timesyncd.
    Nécessite sudo ou des permissions adaptées.
    """
    try:
        subprocess.run(["sudo", "timedatectl", "set-ntp", "true"], check=True)
        status = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized"],
            capture_output=True, text=True, check=True
        )
        success(f"NTP synchronisé : {status.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        error(f"timedatectl a échoué : {e}")
    except Exception as e:
        error(f"Erreur synchro NTP : {e}")

# ==================================================================
#                   SÉCURITÉ MOTEUR AU DÉMARRAGE
# ==================================================================
def motor_all_pin_down_at_boot(config: AppConfig | None = None) -> None:
    """
    Met **toutes** les broches moteur à LOW au boot (sécurité).
    Si `config` n'est pas fourni, on le charge depuis AppConfig.
    """
    if config is None:
        config = AppConfig.load()

    pins = [
        config.gpio.motor_pin1,
        config.gpio.motor_pin2,
        config.gpio.motor_pin3,
        config.gpio.motor_pin4,
    ]
    for pin in pins:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    warning("Broches moteur forcées à LOW au démarrage.")
