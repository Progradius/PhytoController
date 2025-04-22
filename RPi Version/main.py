# main.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Point d'entrée : orchestre l'initialisation puis démarre
#  la boucle d'exécution asynchrone.
# -------------------------------------------------------------

# ───────────  Std-lib  ───────────────────────────────────────
import asyncio, gc, traceback

# ───────────  Console « jolie »  ─────────────────────────────
from ui.pretty_console import (
    title, info, success, warning, error, action, clock
)

# ───────────  Helpers système  ──────────────────────────────
from function                      import (
    motor_all_pin_down_at_boot, set_ntp_time, check_ram_usage
)
from network.network_handler    import do_connect, is_host_connected

# ───────────  Modèles / Contrôleurs  ─────────────────────────
from model.Parameter               import Parameter
from controller.SensorController      import SensorController
from controller.SystemStatus   import SystemStatus
from controller.PuppetMaster       import PuppetMaster

from model.Component               import Component
from model.DailyTimer              import DailyTimer
from model.CyclicTimer             import CyclicTimer
from controller.components.MotorHandler import MotorHandler

from param.parameter_handler  import (
    update_one_parameter, update_current_parameters_from_json
)

# =============================================================
#                    INITIALISATION SYSTÈME
# =============================================================
title("Phyto-Controller - Boot")

# (1) sécurité : broches moteur => LOW
motor_all_pin_down_at_boot()

# (2) Wi-Fi
try:
    action("Connexion Wi-Fi…")
    do_connect()
    success("Interface Wi-Fi prête")
except Exception:
    error("Connexion Wi-Fi échouée")
    traceback.print_exc()

# (3) NTP
try:
    action("Synchronisation NTP…")
    set_ntp_time()
except Exception:
    warning("NTP indisponible ; heure non synchronisée")

# (4) paramètres (JSON → objet)
parameters = Parameter()
update_current_parameters_from_json(parameters)
success("Paramètres chargés")

# (5) test reachability hôte
if is_host_connected() == "offline":
    update_one_parameter("Network_Settings", "host_machine_state", "offline")
    warning("Machine hôte hors-ligne ➜ mode dégradé")

# (6) instanciation des composants GPIO
light1        = Component(pin=parameters.get_dailytimer1_pin())
light2        = Component(pin=parameters.get_dailytimer2_pin())
cyclic_out1   = Component(pin=parameters.get_cyclic1_pin())
cyclic_out2   = Component(pin=parameters.get_cyclic2_pin())
motor_handler = MotorHandler(parameters)
success("Composants physiques initialisés")

# (7) timers
dailytimer1   = DailyTimer(light1,  timer_id="1")
dailytimer2   = DailyTimer(light2,  timer_id="2")
cyclic_timer1 = CyclicTimer(cyclic_out1, timer_id="1")
cyclic_timer2 = CyclicTimer(cyclic_out2, timer_id="2")

# (8) capteurs
sensor_handler = SensorController(parameters)
success("Bus capteurs prêt")

# (9) statut contrôleur
controller_status = SystemStatus(parameters, component=light1, motor=motor_handler.motor)

# (10) orchestrateur global
PuppetMaster = PuppetMaster(
    parameters        = parameters,
    controller_status = controller_status,
    sensor_handler    = sensor_handler,
    dailytimer1       = dailytimer1,
    dailytimer2       = dailytimer2,
    cyclic_timer1     = cyclic_timer1,
    cyclic_timer2     = cyclic_timer2,
    motor_handler     = motor_handler
)

# (11) infos RAM
check_ram_usage()
print()  # ligne blanche

# =============================================================
#                   BOUCLE PRINCIPALE ASYNCIO
# =============================================================
try:
    clock("Démarrage boucle principale … (Ctrl-C pour quitter)")
    asyncio.run(PuppetMaster.main_loop())
except KeyboardInterrupt:
    warning("Arrêt demandé par l'utilisateur (Ctrl-C)")
except Exception as e:
    error(f"Crash : {e}")
    traceback.print_exc()
finally:
    success("Programme terminé")