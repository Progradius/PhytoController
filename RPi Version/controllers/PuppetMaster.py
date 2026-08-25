# controllers/PuppetMaster.py
# Author: Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Orchestrateur asynchrone du système (tâches, timers, serveur)
# -------------------------------------------------------------

import asyncio
import traceback

from network.web import influx_handler
from network.web.influx_handler import write_sensor_values
from components.dailytimer_handler import timer_daily
from components.cyclic_timer_handler import timer_cyclic
from components.MotorHandler import temp_control
from components.heater_control import heat_control
from network.web.server import Server
from utils.pretty_console import info, warning, error
from param.config import AppConfig

LOGGER_NAME = "puppetmaster"


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
        self.config             = config
        self.controller_status  = controller_status
        self.sensor_handler     = sensor_handler
        self.dailytimer1        = dailytimer1
        self.dailytimer2        = dailytimer2
        self.cyclic_timer1      = cyclic_timer1
        self.cyclic_timer2      = cyclic_timer2
        self.motor_handler      = motor_handler
        self.heater             = heater_component

        self._tasks: list[asyncio.Task] = []

        info("PuppetMaster initialisé", name=LOGGER_NAME)

    def _set_global_exception(self) -> None:
        """
        Avant : on arrêtait toute la boucle.
        Maintenant : on log seulement.
        """
        def _handler(loop, context):
            exc = context.get("exception")
            task = context.get("task") or context.get("future")
            where = f" [{task.get_name()}]" if hasattr(task, "get_name") else ""
            msg = context.get("message")

            if exc:
                tb = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ).strip()
                error(f"Exception asyncio non gérée{where} : {msg}\n{tb}",
                      name=LOGGER_NAME)
            else:
                error(f"Erreur asyncio{where} : {msg}", name=LOGGER_NAME)

        asyncio.get_event_loop().set_exception_handler(_handler)

    def _spawn(self, loop, coro, name: str) -> asyncio.Task:
        """
        Crée une tâche nommée, en garde la référence (sinon le GC peut la
        collecter) et signale toute terminaison : ces boucles sont infinies,
        leur fin est TOUJOURS une anomalie.
        """
        task = loop.create_task(coro, name=name)
        task.add_done_callback(self._task_finished)
        self._tasks.append(task)
        return task

    @staticmethod
    def _task_finished(task: asyncio.Task) -> None:
        name = task.get_name()
        if task.cancelled():
            warning(f"Tâche « {name} » annulée", name=LOGGER_NAME)
            return

        exc = task.exception()
        if exc is not None:
            tb = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
            error(f"Tâche « {name} » interrompue par une exception :\n{tb}",
                  name=LOGGER_NAME)
        else:
            error(f"Tâche « {name} » terminée alors qu'elle ne devrait jamais s'arrêter",
                  name=LOGGER_NAME)

    async def main_loop(self) -> None:
        self._set_global_exception()
        loop = asyncio.get_event_loop()

        # --- Daily timers ---
        self._spawn(
            loop,
            timer_daily(self.dailytimer1, self.config, sampling_time=60),
            "daily_timer_1",
        )
        self._spawn(
            loop,
            timer_daily(self.dailytimer2, self.config, sampling_time=60),
            "daily_timer_2",
        )

        # --- Cyclic timers ---
        self._spawn(loop, timer_cyclic(self.cyclic_timer1), "cyclic_timer_1")
        self._spawn(loop, timer_cyclic(self.cyclic_timer2), "cyclic_timer_2")

        # --- Contrôle moteur ---
        self._spawn(
            loop,
            temp_control(
                motor_handler=self.motor_handler,
                config=self.config,
                sensor_handler=self.sensor_handler,
                sampling_time=15
            ),
            "motor_temp_control",
        )

        # --- Contrôle chauffage ---
        self._spawn(
            loop,
            heat_control(
                heater_component=self.heater,
                sensor_handler=self.sensor_handler,
                config=self.config,
                sampling_time=30
            ),
            "heat_control",
        )

        # --- InfluxDB push ---
        # On partage le SensorController déjà construit : une seule ouverture
        # de /dev/i2c-1 pour tout le processus.
        try:
            influx_handler.reload_sensor_handler(self.config, self.sensor_handler)
        except Exception as exc:
            error(f"Initialisation InfluxDB impossible : {exc.__class__.__name__} : {exc}",
                  name=LOGGER_NAME)

        if self.config.network.host_machine_state.lower() == "online":
            self._spawn(loop, write_sensor_values(period=60), "influx_push")
        else:
            warning("InfluxDB : hôte hors-ligne → export désactivé", name=LOGGER_NAME)

        # --- Serveur HTTP ---
        self._spawn(
            loop,
            Server(
                controller_status=self.controller_status,
                sensor_handler=self.sensor_handler,
                config=self.config,
            ).run(),
            "http_server",
        )

        info(
            "Tâches démarrées : "
            + ", ".join(t.get_name() for t in self._tasks),
            name=LOGGER_NAME,
        )

        # boucle infinie
        await asyncio.Event().wait()
