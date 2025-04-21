# Author: Progradius
# License: AGPL 3.0

# Standard library
import gc
import asyncio

# Custom modules
from function import set_ntp_time, check_ram_usage
from controller.ControllerStatus import ControllerStatus
from controller.network_handler import do_connect, is_host_connected
from controller.PuppetMaster import PuppetMaster
from controller.parameter_handler import update_one_parameter, update_current_parameters_from_json
from controller.components.MotorHandler import MotorHandler
from model.DailyTimer import DailyTimer
from model.CyclicTimer import CyclicTimer
from model.Parameter import Parameter
from model.Component import Component
from controller.parameter_handler import read_parameters_from_json
from controller.function import motor_all_pin_down_at_boot

# Equivalent de boot.py : désactivation des moteurs
motor_all_pin_down_at_boot()

# Étape 1 : Connexion réseau
do_connect()

# Étape 2 : Synchronisation de l’heure
set_ntp_time()

# Étape 3 : Initialisation des paramètres
gc.collect()
parameters = Parameter()

# Étape 4 : Vérification de l'état du serveur distant
if is_host_connected() == "offline":
    update_one_parameter(section="Network_Settings", key="host_machine_state", value="offline")
update_current_parameters_from_json(parameters=parameters)

# Étape 5 : Déclaration des composants physiques
light1 = Component(pin=parameters.get_dailytimer1_pin())
light2 = Component(pin=parameters.get_dailytimer2_pin())
cyclic_outlet1 = Component(pin=parameters.get_cyclic1_pin())
cyclic_outlet2 = Component(pin=parameters.get_cyclic2_pin())
motor_handler = MotorHandler(parameters=parameters)

# Étape 6 : Déclaration des timers
dailytimer1 = DailyTimer(component=light1, timer_id="1")
dailytimer2 = DailyTimer(component=light2, timer_id="2")
cyclic_timer1 = CyclicTimer(component=cyclic_outlet1, timer_id="1")
cyclic_timer2 = CyclicTimer(component=cyclic_outlet2, timer_id="2")

# Étape 7 : Contrôleur de statut
controller_status = ControllerStatus(parameters=parameters, component=light1)

# Étape 8 : Orchestrateur principal
puppet_master = PuppetMaster(
    parameters=parameters,
    controller_status=controller_status,
    dailytimer1=dailytimer1,
    dailytimer2=dailytimer2,
    cyclic_timer1=cyclic_timer1,
    cyclic_timer2=cyclic_timer2,
    motor_handler=motor_handler
)

# Étape 9 : Infos système
gc.collect()
check_ram_usage()

# Étape 10 : Boucle principale asynchrone
try:
    asyncio.run(puppet_master.main_loop())
except KeyboardInterrupt:
    print("Arrêt du programme.")
finally:
    asyncio.get_event_loop().close()
