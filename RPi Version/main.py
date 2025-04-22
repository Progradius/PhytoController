# main.py
# Author: Progradius
# License: AGPL-3.0

# ──────────────  Standard  ───────────────────────────────────
import asyncio
import gc

# ──────────────  Helpers système  ────────────────────────────
from function                 import (motor_all_pin_down_at_boot,
                                       set_ntp_time,
                                       check_ram_usage)
from controller.network_handler import do_connect, is_host_connected

# ──────────────  Modèles / Contrôleurs  ──────────────────────
from model.Parameter           import Parameter
from controller.SensorHandler  import SensorHandler
from controller.ControllerStatus import ControllerStatus
from controller.PuppetMaster   import PuppetMaster

from model.Component           import Component
from model.DailyTimer          import DailyTimer
from model.CyclicTimer         import CyclicTimer
from controller.components.MotorHandler import MotorHandler

from controller.parameter_handler import (read_parameters_from_json,
                                          update_one_parameter,
                                          update_current_parameters_from_json)

# ──────────────────────────────────────────────────────────────
#                      INITIALISATION
# ──────────────────────────────────────────────────────────────

# (1) sécurité : toutes les sorties moteur à l'état bas
motor_all_pin_down_at_boot()

# (2) connexion Wi-Fi (NetworkManager)
try:
    do_connect()
except Exception as e:
    print("⚠️  Connexion Wi-Fi échouée :", e)

# (3) synchronisation NTP (optionnelle)
try:
    set_ntp_time()
except Exception as e:
    print("⚠️  Impossible de régler l'heure :", e)

# (4) paramètres
parameters = Parameter()
gc.collect()

# (5) état du serveur hôte
if is_host_connected() == "offline":
    update_one_parameter("Network_Settings", "host_machine_state", "offline")
update_current_parameters_from_json(parameters)

# (6) composants physiques
light1         = Component(pin=parameters.get_dailytimer1_pin())
light2         = Component(pin=parameters.get_dailytimer2_pin())
cyclic_out1    = Component(pin=parameters.get_cyclic1_pin())
cyclic_out2    = Component(pin=parameters.get_cyclic2_pin())
motor_handler  = MotorHandler(parameters)

# (7) timers
dailytimer1    = DailyTimer(component=light1,  timer_id="1")
dailytimer2    = DailyTimer(component=light2,  timer_id="2")
cyclic_timer1  = CyclicTimer(component=cyclic_out1, timer_id="1")
cyclic_timer2  = CyclicTimer(component=cyclic_out2, timer_id="2")

# (8) bus capteurs
sensor_handler = SensorHandler(parameters=parameters)

# (9) état global du contrôleur
controller_status = ControllerStatus(parameters=parameters,
                                     component =light1)

# (10) orchestrateur
puppet_master = PuppetMaster(
    parameters       = parameters,
    controller_status= controller_status,
    dailytimer1      = dailytimer1,
    dailytimer2      = dailytimer2,
    cyclic_timer1    = cyclic_timer1,
    cyclic_timer2    = cyclic_timer2,
    motor_handler    = motor_handler,
    sensor_handler   = sensor_handler
)

# info RAM au démarrage
check_ram_usage()

# ──────────────────────────────────────────────────────────────
#                     BOUCLE PRINCIPALE
# ──────────────────────────────────────────────────────────────
try:
    asyncio.run(puppet_master.main_loop())
except KeyboardInterrupt:
    print("🛑 Arrêt demandé par l'utilisateur.")
