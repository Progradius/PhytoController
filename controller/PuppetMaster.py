# Author: Progradius
# License: AGPL 3.0

import asyncio

# Custom modules (doivent eux aussi être compatibles Raspberry Pi)
from controller.web.influx_handler import write_sensor_values
from controller.components.dailytimer_handler import timer_daily
from controller.components import cyclic_timer_handler
from controller.components.MotorHandler import temp_control
from controller.web.server_test import Server


class PuppetMaster:
    """
    Classe d’orchestration asynchrone.
    Elle lance tous les composants du système de façon non bloquante.
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

    def set_global_exception(self):
        """
        Définit un gestionnaire global d’exception pour les erreurs asyncio.
        """
        def handle_exception(loop, context):
            import traceback
            print("Exception dans le loop asyncio :", context.get("exception"))
            traceback.print_exception(type(context["exception"]), context["exception"], context["exception"].__traceback__)
            loop.stop()

        loop = asyncio.get_event_loop()
        loop.set_exception_handler(handle_exception)

    async def main_loop(self):
        """
        Lance toutes les tâches asynchrones du système.
        """
        self.set_global_exception()
        loop = asyncio.get_event_loop()

        # Dailytimers
        loop.create_task(timer_daily(dailytimer=self.dailytimer1, sampling_time=60))
        loop.create_task(timer_daily(dailytimer=self.dailytimer2, sampling_time=60))

        # Cyclic timers
        loop.create_task(cyclic_timer_handler.timer_cylic(cyclic_timer=self.cyclic_timer1))
        loop.create_task(cyclic_timer_handler.timer_cylic(cyclic_timer=self.cyclic_timer2))

        # Contrôle moteur par température
        loop.create_task(temp_control(motor_handler=self.motor_handler, parameters=self.parameters, sampling_time=15))

        # Envoi vers InfluxDB si la machine distante est active
        if self.parameters.get_host_machine_state() == "online":
            loop.create_task(write_sensor_values())

        # Serveur Web local
        loop.create_task(Server(controller_status=self.controller_status).run())

        # Boucle infinie
        await asyncio.Event().wait()
