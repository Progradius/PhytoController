# Author: Progradius
# License: AGPL 3.0

import uasyncio as asyncio
# Custom Library
from controller.web.influx_handler import write_sensor_values
from controller.components.dailytimer_handler import timer_daily
from controller.components import cyclic_timer_handler
from controller.components.MotorHandler import temp_control
from controller.web.server_test import Server


class PuppetMaster:
    """
    Asyncio stuff class, responsible of orchestrating asynchronous operation
    """

    def __init__(self, parameters, controller_status, dailytimer1, dailytimer2, cyclic_timer1, cyclic_timer2,
                 motor_handler):
        self.parameters = parameters
        self.controller_status = controller_status
        self.dailytimer1 = dailytimer1
        self.dailytimer2 = dailytimer2
        self.cyclic_timer1 = cyclic_timer1
        self.cyclic_timer2 = cyclic_timer2
        self.motor_handler = motor_handler

    # Debug function
    def set_global_exception(self):
        def handle_exception(loop, context):
            import sys
            sys.print_exception(context["exception"])
            sys.exit()

        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_exception)

    # Main app
    async def main_loop(self):
        self.set_global_exception()
        loop = asyncio.get_event_loop()
        # Dailytimers task
        loop.create_task(timer_daily(dailytimer=self.dailytimer1, sampling_time=60))
        loop.create_task(timer_daily(dailytimer=self.dailytimer2, sampling_time=60))
        # CyclicTimers task
        loop.create_task(cyclic_timer_handler.timer_cylic(cyclic_timer=self.cyclic_timer1))
        loop.create_task(cyclic_timer_handler.timer_cylic(cyclic_timer=self.cyclic_timer2))
        loop.create_task(temp_control(motor_handler=self.motor_handler, parameters=self.parameters, sampling_time=15))
        # Sensors logging Task, only if host machine is online
        if self.parameters.get_host_machine_state() == "online":
            loop.create_task(write_sensor_values())
        loop.create_task(Server(controller_status=self.controller_status).run())

        loop.run_forever()
