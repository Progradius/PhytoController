# Author: Progradius
# License: AGPL 3.0

# Vanilla Library
import gc
import uasyncio as asyncio
# Custom library
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

# Connecting to WLAN
do_connect()
# Set time to UTC 0
set_ntp_time()
# Get program parameters
gc.collect()
parameters = Parameter()
# Ping host machine to know if it's reachable and set the target parameters
if is_host_connected() == "offline":
    update_one_parameter(section="Network_Settings", key="host_machine_state", value="offline")
    # Write parameters application wide
    update_current_parameters_from_json(parameters=parameters)
# Declaring components
# Outlets reserved for lights
light1 = Component(pin=parameters.get_dailytimer1_pin())
light2 = Component(pin=parameters.get_dailytimer2_pin())
# Outlets reserved for cyclic timers
cyclic_outlet1 = Component(pin=parameters.get_cyclic1_pin())
cyclic_outlet2 = Component(pin=parameters.get_cyclic2_pin())
# Motor handler
motor_handler = MotorHandler(parameters=parameters)

# Dailytimer used to drive the lights
dailytimer1 = DailyTimer(component=light1, timer_id="1")
dailytimer2 = DailyTimer(component=light2, timer_id="2")

# CyclicTimer used to drive outlets by cycle
cyclic_timer1 = CyclicTimer(component=cyclic_outlet1, timer_id="1")
cyclic_timer2 = CyclicTimer(component=cyclic_outlet2, timer_id="2")

# Class used to retrieve and show the different component's states
controller_status = ControllerStatus(parameters=parameters, component=light1)

# Asynchronous orchestrator
puppet_master = PuppetMaster(parameters=parameters,
                             controller_status=controller_status,
                             dailytimer1=dailytimer1,
                             dailytimer2=dailytimer2,
                             cyclic_timer1=cyclic_timer1,
                             cyclic_timer2=cyclic_timer2,
                             motor_handler=motor_handler)
# Running garbage collector and printing system stats for debug
gc.collect()
print(check_ram_usage())
# Entering async loop
try:
    asyncio.run(puppet_master.main_loop())
finally:
    asyncio.new_event_loop()
