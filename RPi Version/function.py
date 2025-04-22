# Author: Progradius
# License: AGPL 3.0

import os
import gc
import time
import datetime
import requests
import RPi.GPIO as GPIO
from controller.parameter_handler import read_parameters_from_json

parameters = read_parameters_from_json()

# Configuration GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# === Fonctions de conversion ===
def convert_time_to_minutes(hour, minute):
    return (int(hour) * 60) + int(minute)

def convert_time_to_seconds(hour, minute, second):
    return (int(hour) * 3600) + (int(minute) * 60) + int(second)

def convert_minute_to_seconds(minutes):
    return int(minutes) * 60

# === Infos disque ===
def check_flash_usage():
    st = os.statvfs('/')
    total_bytes = st.f_frsize * st.f_blocks
    free_bytes = st.f_frsize * st.f_bavail
    return '{0:.2f} MB'.format(free_bytes / 1048576)

# === Infos mémoire RAM ===
def check_ram_usage():
    # Approche simple : lecture de /proc/meminfo
    with open('/proc/meminfo') as f:
        lines = f.readlines()
    meminfo = {}
    for line in lines:
        key, value = line.split(':')
        meminfo[key] = int(value.strip().split()[0])
    total = meminfo.get('MemTotal', 0)
    free = meminfo.get('MemAvailable', 0)
    percent_free = (free / total * 100) if total > 0 else 0
    print(f'Total: {total} kB, Free: {free} kB ({percent_free:.2f}%)')

# === Synchronisation NTP ===
def set_ntp_time():
    try:
        # Utilise ntp.org pour obtenir l'heure en UTC
        import ntplib
        c = ntplib.NTPClient()
        response = c.request('pool.ntp.org', version=3)
        utc_time = datetime.datetime.utcfromtimestamp(response.tx_time)
        # Ajustement fuseau horaire (ex: UTC+2)
        utc_shift = datetime.timedelta(hours=2)
        local_time = utc_time + utc_shift
        os.system(f'date -s "{local_time.strftime("%Y-%m-%d %H:%M:%S")}"')
        print("Heure mise à jour :", local_time)
    except Exception as e:
        print("Impossible de synchroniser l'heure :", e)

# === Mise des broches moteur à l'état bas au démarrage ===
def motor_all_pin_down_at_boot():
    pins = [
        parameters["GPIO_Settings"]["motor_pin1"],
        parameters["GPIO_Settings"]["motor_pin2"],
        parameters["GPIO_Settings"]["motor_pin3"],
        parameters["GPIO_Settings"]["motor_pin4"],
    ]
    for pin in pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
