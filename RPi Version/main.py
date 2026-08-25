# main.py
# Author : Progradius
# License: AGPL-3.0

import asyncio
import signal
import sys
import atexit
import os

import RPi.GPIO as GPIO
from utils import pretty_console as ui
from utils.pretty_console import (
    title, action, success, warning, error, exception, clock,
)
from utils.log_stream import console_stream
from utils.single_instance import ensure_single_instance
from utils import watchdog
from function import motor_all_pin_down_at_boot, set_ntp_time, check_ram_usage
from network.network_handler import do_connect, is_host_connected

from model.Component import Component
from model.DailyTimer import DailyTimer
from model.CyclicTimer import CyclicTimer
from components.MotorHandler import MotorHandler

from controllers.SensorController import SensorController
from controllers.SystemStatus import SystemStatus
from controllers.PuppetMaster import PuppetMaster

from param.config import AppConfig

# =============================================================
#                  VARIABLES GLOBALES SÉCURITÉ
# =============================================================

LOGGER_NAME = "main"

# =============================================================
#          VERROU D'INSTANCE (avant toute action GPIO)
# =============================================================
# Deux instances vivantes se battent pour les mêmes broches : chacune force les
# génériques à HIGH (coupant ce que l'autre tenait ON) et remet le moteur à 0,
# en boucle. Le verrou est pris ici, avant l'enregistrement des handlers de
# signaux et d'`atexit`, pour qu'une instance surnuméraire sorte sans jamais
# toucher une broche.
ensure_single_instance()

# mode de run (pour désactiver certaines fonctions en service)
RUN_AS_SERVICE = os.getenv("PHYTO_RUN_MODE", "").lower() == "service"

# Pins non-moteur qu'on peut forcer à HIGH sans danger
GENERIC_SAFE_PINS = []          # on remplira après chargement config
MOTOR_PINS = []                 # on remplira après chargement config
# `cleanup_gpio()` est atteignable par trois chemins (handler de signal,
# `atexit`, `finally` de la boucle principale) : on ne rejoue pas la séquence.
gpio_safe_state_done = False


# =============================================================
#                  FONCTIONS DE SÉCURITÉ
# =============================================================

def cleanup_gpio():
    """
    Sécurité de sortie — l'état sûr est TERMINAL :
      - pour TOUT ce qui n'est PAS le moteur → HIGH (OFF relai)
      - pour les pins moteur → on les met comme au boot (LOW chez toi)

    On n'appelle **jamais** `GPIO.cleanup()` ici (audit C3) : cette fonction
    remet chaque broche en entrée avec son pull par défaut, ce qui *défait*
    l'état sûr qu'on vient de poser — GPIO 18/22/23/27 retombent au pull-down
    (niveau BAS = commande active pour les Component actifs-BAS, chauffage
    compris) et les broches moteur remontent au pull-up. Les sorties doivent
    rester **pilotées** jusqu'à la coupure d'alimentation.

    Relâcher les broches ne redeviendra acceptable que si des résistances
    externes garantissent l'état sûr (pull-up sur les entrées actives-BAS,
    pull-down sur les entrées moteur) — c'est une dépendance MATÉRIELLE, pas
    une option logicielle.
    """
    global gpio_safe_state_done
    if gpio_safe_state_done:
        return
    gpio_safe_state_done = True

    action("Mise à l'état sûr des GPIO avant extinction…", name=LOGGER_NAME)
    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
    except Exception as e:
        error(f"Impossible de remettre le mode GPIO : {e}", name=LOGGER_NAME)

    # 1) Pins non moteur → HIGH
    for pin in GENERIC_SAFE_PINS:
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH)
        except Exception as e:
            error(f"Erreur GPIO (générique) {pin} : {e}", name=LOGGER_NAME)

    # 2) Pins moteur → état sécurisé (LOW chez toi)
    for pin in MOTOR_PINS:
        try:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)
        except Exception as e:
            error(f"Erreur GPIO (moteur) {pin} : {e}", name=LOGGER_NAME)

    # 3) PAS de GPIO.cleanup() : voir le docstring. Les broches restent des
    #    sorties pilotées à leur état sûr jusqu'à la coupure d'alimentation.
    success("Broches maintenues à l'état sûr (sorties pilotées)", name=LOGGER_NAME)


def handle_exit_signal(signum, frame):
    warning(f"Signal {signum} reçu → arrêt sécurisé", name=LOGGER_NAME)
    watchdog.close_hw_watchdog()
    cleanup_gpio()
    sys.exit(0)


# Interception des signaux système (on enregistre AVANT de lancer l'appli)
for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, handle_exit_signal)

# Enregistrement automatique à la fin du programme.
# `close_hw_watchdog()` écrit le « magic close » sur le descripteur conservé par
# `utils.watchdog` : il désarme le watchdog au lieu de laisser la machine
# redémarrer après un arrêt volontaire.
atexit.register(watchdog.close_hw_watchdog)
atexit.register(cleanup_gpio)


# =============================================================
#                    INITIALISATION SYSTÈME
# =============================================================
title("Phyto-Controller - Boot", name=LOGGER_NAME)

# (1) Chargement de la configuration
config = AppConfig.load()

# Niveau et rétention de log : env PHYTO_LOG_LEVEL > param.json > INFO
ui.apply_log_settings(config.logs.level, config.logs.retention_days)
# Diffusion des logs du processus courant vers la page /console
console_stream.install()
success(
    f"Configuration chargée (log : {config.logs.level}, "
    f"rétention {config.logs.retention_days} j)",
    name=LOGGER_NAME,
)

# Maintenant qu'on a la config, on sait quelles sont les pins moteur
MOTOR_PINS[:] = [
    config.gpio.motor_pin1,
    config.gpio.motor_pin2,
    config.gpio.motor_pin3,
    config.gpio.motor_pin4,
]

# Et les autres pins qu'on peut mettre HIGH à la fin
GENERIC_SAFE_PINS[:] = [
    config.gpio.dailytimer1_pin,
    config.gpio.dailytimer2_pin,
    config.gpio.cyclic1_pin,
    config.gpio.cyclic2_pin,
    config.gpio.heater_pin,
    # surtout pas les pins moteur ici
]

# (2) Sécurité : broches moteur → LOW (avant toute autre init)
# c'est ton état sûr
motor_all_pin_down_at_boot(config)

# (3) Initialisation globale des broches GPIO
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

# On initialise d'abord les pins "non dangereuses" en HIGH
for pin in GENERIC_SAFE_PINS:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)

# Puis on initialise les pins moteur en LOW explicitement
for pin in MOTOR_PINS:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

success("GPIO initialisés (génériques=HIGH, moteur=LOW)", name=LOGGER_NAME)

# (4) Wi-Fi
try:
    action("Connexion Wi-Fi…", name=LOGGER_NAME)
    do_connect()
    success("Interface Wi-Fi prête", name=LOGGER_NAME)
except Exception:
    exception("Connexion Wi-Fi échouée", name=LOGGER_NAME)

# (5) NTP
try:
    action("Synchronisation NTP…", name=LOGGER_NAME)
    set_ntp_time()
except Exception:
    warning("NTP indisponible → heure non synchronisée", name=LOGGER_NAME)

# (6) Vérification de la reachabilité de l'hôte
if is_host_connected() == "offline":
    warning("Machine hôte hors-ligne → mode dégradé", name=LOGGER_NAME)

# (7) Initialisation des composants physiques
light1       = Component(pin=config.gpio.dailytimer1_pin)
light2       = Component(pin=config.gpio.dailytimer2_pin)
cyclic_out1  = Component(pin=config.gpio.cyclic1_pin)
cyclic_out2  = Component(pin=config.gpio.cyclic2_pin)
heater       = Component(pin=config.gpio.heater_pin)

# ATTENTION : MotorHandler va réutiliser les pins moteur, mais on les a déjà
# mises dans l'état sûr juste au-dessus
motor_handler = MotorHandler(config)
success("Composants physiques initialisés", name=LOGGER_NAME)

# (8) Timers
dailytimer1   = DailyTimer(light1,       timer_id="1", config=config)
dailytimer2   = DailyTimer(light2,       timer_id="2", config=config)
cyclic_timer1 = CyclicTimer(cyclic_out1, timer_id="1", config=config)
cyclic_timer2 = CyclicTimer(cyclic_out2, timer_id="2", config=config)

# (9) Capteurs
sensor_handler = SensorController(config)
success("Bus capteurs prêt", name=LOGGER_NAME)

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

# Le watchdog n'est plus un thread aveugle : il est armé et caressé depuis
# l'event loop par `PuppetMaster`, et **uniquement** si toutes les tâches
# supervisées sont vivantes et récentes (audit E2).

# =============================================================
#                   BOUCLE PRINCIPALE ASYNCIO
# =============================================================
try:
    clock("Démarrage boucle principale… (Ctrl-C pour quitter)", name=LOGGER_NAME)
    asyncio.run(puppet_master.main_loop())
except KeyboardInterrupt:
    warning("Arrêt demandé par l'utilisateur (Ctrl-C)", name=LOGGER_NAME)
except Exception as e:
    exception(f"Crash : {e}", name=LOGGER_NAME)
finally:
    # idempotents : `atexit` et le handler de signal les ont peut-être déjà appelés
    watchdog.close_hw_watchdog()
    cleanup_gpio()
    success("Programme terminé (watchdog désarmé, GPIO à l'état sûr)", name=LOGGER_NAME)
