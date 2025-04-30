# main.py
# Author : Progradius
# License: AGPL-3.0

import asyncio
import traceback
import signal
import sys
import atexit
import threading
import os
import time

import RPi.GPIO as GPIO
from ui.pretty_console        import title, action, success, warning, error, clock
from function                import motor_all_pin_down_at_boot, set_ntp_time, check_ram_usage
from network.network_handler import do_connect, is_host_connected

from model.Component          import Component
from model.DailyTimer         import DailyTimer
from model.CyclicTimer        import CyclicTimer
from components.MotorHandler  import MotorHandler

from controllers.SensorController import SensorController
from controllers.SystemStatus     import SystemStatus
from controllers.PuppetMaster     import PuppetMaster

from param.config import AppConfig

# =============================================================
#                  GESTION SÉCURISÉE À LA SORTIE
# =============================================================

SAFE_PINS = [1, 7, 8, 17, 18, 22, 23, 25, 27]
watchdog_thread = None
watchdog_active = False
watchdog_stop = threading.Event()

def cleanup_gpio():
    """Force tous les GPIO utilisés à HIGH et nettoie."""
    print("🧹 Cleanup GPIO avant extinction…")
    GPIO.setmode(GPIO.BCM)
    for pin in SAFE_PINS:
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
        except Exception as e:
            print(f"⚠️ Erreur GPIO {pin} : {e}")
    GPIO.cleanup()

def disable_watchdog():
    """Désactive /dev/watchdog si possible"""
    global watchdog_active
    if not watchdog_active:
        return
    try:
        with open("/dev/watchdog", "w") as f:
            f.write("V")  # signal au driver watchdog pour désactivation
        print("🛡️  Watchdog matériel désactivé proprement")
    except Exception as e:
        print(f"⚠️ Impossible de désactiver le watchdog : {e}")

def handle_exit_signal(signum, frame):
    print(f"\n🛑 Signal {signum} reçu → arrêt sécurisé.")
    disable_watchdog()
    cleanup_gpio()
    sys.exit(0)

# Interception des signaux système
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, handle_exit_signal)

atexit.register(disable_watchdog)
atexit.register(cleanup_gpio)

def watchdog_worker():
    """Thread d'écriture régulière sur /dev/watchdog"""
    global watchdog_active
    try:
        with open("/dev/watchdog", "w") as f:
            watchdog_active = True
            print("🛡️  Watchdog matériel activé")
            while not watchdog_stop.is_set():
                f.write("\n")
                f.flush()
                time.sleep(10)
    except Exception as e:
        warning(f"Watchdog matériel non disponible : {e}")
        watchdog_active = False

# =============================================================
#                    INITIALISATION SYSTÈME
# =============================================================
title("Phyto-Controller - Boot")

# (1) Chargement de la configuration
config = AppConfig.load()
success("Configuration chargée")

# (2) Sécurité : broches moteur → LOW
motor_all_pin_down_at_boot(config)

# (3) Initialisation globale des broches GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
all_pins = [
    config.gpio.dailytimer1_pin,
    config.gpio.dailytimer2_pin,
    config.gpio.cyclic1_pin,
    config.gpio.cyclic2_pin,
    config.gpio.heater_pin,
    config.gpio.motor_pin1,
    config.gpio.motor_pin2,
    config.gpio.motor_pin3,
    config.gpio.motor_pin4,
]
for pin in all_pins:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)
success("Toutes les broches GPIO configurées en OUTPUT (HIGH)")

# Wi-Fi
try:
    action("Connexion Wi-Fi…")
    do_connect()
    success("Interface Wi-Fi prête")
except Exception:
    error("Connexion Wi-Fi échouée")
    traceback.print_exc()

# NTP
try:
    action("Synchronisation NTP…")
    set_ntp_time()
except Exception:
    warning("NTP indisponible → heure non synchronisée")

# (6) Vérification de la reachabilité de l'hôte
if is_host_connected() == "offline":
    warning("Machine hôte hors-ligne → mode dégradé")

# (7) Initialisation des composants physiques
light1      = Component(pin=config.gpio.dailytimer1_pin)
light2      = Component(pin=config.gpio.dailytimer2_pin)
cyclic_out1 = Component(pin=config.gpio.cyclic1_pin)
cyclic_out2 = Component(pin=config.gpio.cyclic2_pin)
heater      = Component(pin=config.gpio.heater_pin)
motor_handler = MotorHandler(config)
success("Composants physiques initialisés")

# (8) Timers
dailytimer1    = DailyTimer(light1,      timer_id="1", config=config)
dailytimer2    = DailyTimer(light2,      timer_id="2", config=config)
cyclic_timer1  = CyclicTimer(cyclic_out1, timer_id="1", config=config)
cyclic_timer2  = CyclicTimer(cyclic_out2, timer_id="2", config=config)

# (9) Capteurs
sensor_handler = SensorController(config)
success("Bus capteurs prêt")

# (10) Statut système
controller_status = SystemStatus(
    config=config,
    component=light1,
    motor=motor_handler.motor
)

# (11) Orchestrateur principal
puppet_master = PuppetMaster(
    config             = config,
    controller_status  = controller_status,
    sensor_handler     = sensor_handler,
    dailytimer1        = dailytimer1,
    dailytimer2        = dailytimer2,
    cyclic_timer1      = cyclic_timer1,
    cyclic_timer2      = cyclic_timer2,
    motor_handler      = motor_handler,
    heater_component   = heater,
)

# (12) Info mémoire
check_ram_usage()
print()

# Lancement du watchdog dans un thread
watchdog_thread = threading.Thread(target=watchdog_worker, daemon=True)
watchdog_thread.start()

# =============================================================
#                   BOUCLE PRINCIPALE ASYNCIO
# =============================================================
try:
    clock("Démarrage boucle principale… (Ctrl-C pour quitter)")
    asyncio.run(puppet_master.main_loop())
except KeyboardInterrupt:
    warning("Arrêt demandé par l'utilisateur (Ctrl-C)")
except Exception as e:
    error(f"Crash : {e}")
    traceback.print_exc()
finally:
    watchdog_stop.set()
    if watchdog_thread.is_alive():
        watchdog_thread.join()
    success("Programme terminé (watchdog & GPIO nettoyés)")
