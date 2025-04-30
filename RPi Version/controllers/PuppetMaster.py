# controllers/PuppetMaster.py
# Author: Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Orchestrateur asynchrone du système (tâches, timers, serveur)
# -------------------------------------------------------------

import asyncio

from network.web.influx_handler         import write_sensor_values
from components.dailytimer_handler      import timer_daily
from components.cyclic_timer_handler    import timer_cyclic
from components.MotorHandler            import temp_control
from components.heater_control          import heat_control
from network.web.server                 import Server
from utils.pretty_console                  import info, warning, error
from param.config                       import AppConfig


class PuppetMaster:
    """
    Lance et supervise tous les jobs :
      • Timers (daily & cyclic)
      • Régulation du moteur
      • Régulation du chauffage
      • Push InfluxDB
      • Serveur HTTP (pages + API)
    """

    def __init__(
        self,
        config: AppConfig,
        controller_status,
        sensor_handler,
        dailytimer1,
        dailytimer2,
        cyclic_timer1,
        cyclic_timer2,
        motor_handler,
        heater_component
    ):
        self.config            = config
        self.controller_status = controller_status
        self.sensor_handler    = sensor_handler
        self.dailytimer1       = dailytimer1
        self.dailytimer2       = dailytimer2
        self.cyclic_timer1     = cyclic_timer1
        self.cyclic_timer2     = cyclic_timer2
        self.motor_handler     = motor_handler
        self.heater            = heater_component

        info("PuppetMaster initialisé")

    def _set_global_exception(self) -> None:
        def _handler(loop, context):
            exc = context.get("exception")
            error(f"Exception asyncio non gérée : {exc}")
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
            loop.stop()

        asyncio.get_event_loop().set_exception_handler(_handler)

    async def main_loop(self) -> None:
        self._set_global_exception()
        loop = asyncio.get_event_loop()

        # --- Daily timers ---
        info("Démarrage des DailyTimers")
        loop.create_task(timer_daily(self.dailytimer1, self.config, sampling_time=60))
        loop.create_task(timer_daily(self.dailytimer2, self.config, sampling_time=60))

        # --- Cyclic timers ---
        info("Démarrage des CyclicTimers")
        loop.create_task(timer_cyclic(self.cyclic_timer1))
        loop.create_task(timer_cyclic(self.cyclic_timer2))

        # --- Contrôle moteur ---
        info("Démarrage du contrôle moteur")
        loop.create_task(
            temp_control(
                self.motor_handler,
                self.config,
                sampling_time=15,
            )
        )

        # --- Contrôle chauffage ---
        info("Démarrage du contrôle chauffage")
        loop.create_task(
            heat_control(
                heater_component=self.heater,
                sensor_handler=self.sensor_handler,
                config=self.config,
                sampling_time=30,
            )
        )

        # --- InfluxDB push ---
        if self.config.network.host_machine_state.lower() == "online":
            info("InfluxDB : envoi périodique activé (delay 60 s)")
            loop.create_task(write_sensor_values(period=60))
        else:
            warning("InfluxDB : hôte hors-ligne - export désactivé")

        # --- Serveur HTTP ---
        info("Démarrage du serveur HTTP")
        loop.create_task(
            Server(
                controller_status=self.controller_status,
                sensor_handler=self.sensor_handler,
                config=self.config,
            ).run()
        )

        info("Toutes les tâches asynchrones sont démarrées ✔")
        # Bloque indéfiniment (Ctrl-C pour quitter)
        await asyncio.Event().wait()
