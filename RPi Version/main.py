# main.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Point d'entrée : orchestre l'initialisation puis démarre
#  la boucle d'exécution asynchrone.
# -------------------------------------------------------------
import asyncio
import traceback

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
#                    INITIALISATION SYSTÈME
# =============================================================
title("Phyto-Controller - Boot")

# (1) Chargement de la configuration
config = AppConfig.load()
success("Configuration chargée")

# (2) Sécurité : broches moteur → LOW
motor_all_pin_down_at_boot(config)

# (3) Wi-Fi
try:
    action("Connexion Wi-Fi…")
    do_connect()
    success("Interface Wi-Fi prête")
except Exception:
    error("Connexion Wi-Fi échouée")
    traceback.print_exc()

# (4) NTP
try:
    action("Synchronisation NTP…")
    set_ntp_time()
except Exception:
    warning("NTP indisponible → heure non synchronisée")



# (5) Vérification de la reachabilité de l'hôte
if is_host_connected() == "offline":
    warning("Machine hôte hors-ligne → mode dégradé")

# (6) Initialisation des composants GPIO
light1      = Component(pin=config.gpio.dailytimer1_pin)
light2      = Component(pin=config.gpio.dailytimer2_pin)
cyclic_out1 = Component(pin=config.gpio.cyclic1_pin)
cyclic_out2 = Component(pin=config.gpio.cyclic2_pin)
heater      = Component(pin=config.gpio.heater_pin)
motor_handler = MotorHandler(config)
success("Composants physiques initialisés")

# (7) Timers
dailytimer1 = DailyTimer(light1, timer_id="1", config=config)
dailytimer2 = DailyTimer(light2, timer_id="2", config=config)
cyclic_timer1 = CyclicTimer(cyclic_out1, timer_id="1", config=config)
cyclic_timer2 = CyclicTimer(cyclic_out2, timer_id="2", config=config)

# (8) Capteurs
sensor_handler = SensorController(config)
success("Bus capteurs prêt")

# (9) Statut système
controller_status = SystemStatus(
    config=config,
    component=light1,
    motor=motor_handler.motor
)

# (10) Orchestrateur principal
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

# (11) Info mémoire
check_ram_usage()
print()  # blanc

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
    success("Programme terminé")
