# Author: Progradius (adapted)
# License: AGPL 3.0
# -------------------------------------------------------------
#  Orchestrateur asynchrone du système
# -------------------------------------------------------------

import asyncio

from controller.web.influx_handler          import write_sensor_values
from controller.components.dailytimer_handler import timer_daily
from controller.components                   import cyclic_timer_handler
from controller.components.MotorHandler      import temp_control
from controller.web.server                   import Server


class PuppetMaster:
    def __init__(
        self,
        parameters,
        controller_status,
        sensor_handler,          # ← on passe l’instance unique
        dailytimer1,
        dailytimer2,
        cyclic_timer1,
        cyclic_timer2,
        motor_handler
    ):
        self.parameters        = parameters
        self.controller_status = controller_status
        self.sensor_handler    = sensor_handler
        self.dailytimer1       = dailytimer1
        self.dailytimer2       = dailytimer2
        self.cyclic_timer1     = cyclic_timer1
        self.cyclic_timer2     = cyclic_timer2
        self.motor_handler     = motor_handler

    # ---------------------------------------------------------
    def _set_global_exception(self) -> None:
        def handler(loop, context):
            import traceback
            exc = context.get("exception")
            print("❌ Exception asyncio :", exc)
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            loop.stop()

        asyncio.get_event_loop().set_exception_handler(handler)

    # ---------------------------------------------------------
    async def main_loop(self) -> None:
        self._set_global_exception()
        loop = asyncio.get_event_loop()

        # Timers
        loop.create_task(timer_daily(self.dailytimer1, sampling_time=60))
        loop.create_task(timer_daily(self.dailytimer2, sampling_time=60))
        loop.create_task(cyclic_timer_handler.timer_cylic(self.cyclic_timer1))
        loop.create_task(cyclic_timer_handler.timer_cylic(self.cyclic_timer2))

        # Contrôle moteur
        loop.create_task(
            temp_control(self.motor_handler, self.parameters, sampling_time=15)
        )

        # InfluxDB
        if self.parameters.get_host_machine_state() == "online":
            loop.create_task(write_sensor_values())

        # Serveur HTTP
        loop.create_task(
            Server(
                controller_status=self.controller_status,
                sensor_handler   =self.sensor_handler,
                parameters       =self.parameters
            ).run()
        )

        # Exécution infinie
        await asyncio.Event().wait()
