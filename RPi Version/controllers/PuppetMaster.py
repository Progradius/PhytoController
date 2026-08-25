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
from components.climate_control import climate_control
from network.web.server import Server
from utils.pretty_console import debug, info, warning, error
from utils.supervisor import TaskSupervisor
from utils.supervisor import beat, sleep as hb_sleep
from utils import watchdog
from param.config import AppConfig

LOGGER_NAME = "puppetmaster"

# Silence toléré avant de considérer une tâche bloquée. Chaque boucle bat le
# cœur à chaque tour **et** pendant ses attentes (`utils.supervisor.sleep`) :
# un silence de plusieurs minutes n'est donc jamais un fonctionnement normal.
MAX_SILENCE_SECONDS = 300.0


async def refresh_sensor_snapshot(sensor_handler, period: int = 10) -> None:
    """Acquisition centrale : l'HTTP ne déclenche jamais de lecture matérielle."""
    while True:
        beat()
        await sensor_handler.refresh_active()
        await hb_sleep(period)


class PuppetMaster:
    """
    Lance et supervise tous les jobs :
      • Timers (daily & cyclic)
      • Régulation du moteur
      • Régulation du chauffage
      • Push InfluxDB
      • Serveur HTTP (pages + API)

    Chaque job est confié au `TaskSupervisor` : il est relancé après remise à
    l'état sûr, son battement de cœur est surveillé, et sa santé conditionne le
    coup de patte au watchdog. Une régulation ne peut plus s'arrêter en silence.
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

        self.supervisor = TaskSupervisor()

        info("PuppetMaster initialisé", name=LOGGER_NAME)

    def _set_global_exception(self) -> None:
        """
        Filet de dernier recours : le superviseur attrape déjà tout ce qui vient
        des tâches métier. Ce qui remonte ici (callbacks, tâches nues) est
        journalisé sans arrêter la boucle — une serre ne s'éteint pas sur une
        exception isolée.
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

    # ──────────────────────────────────────────────────────────
    #  États sûrs, appliqués AVANT chaque relance de tâche
    # ──────────────────────────────────────────────────────────
    @staticmethod
    def _component_off(component):
        """Coupe une sortie active-BAS (`set_state(0)` → GPIO HIGH)."""
        def _safe():
            component.set_state(0)
        return _safe

    def _motor_off(self) -> None:
        """État sûr moteur : les 4 relais actifs-HAUT à LOW."""
        self.motor_handler.all_off()

    def _climate_off(self) -> None:
        """
        État sûr de l'arbitre thermique : les **deux** organes coupés.

        L'ordre compte : le chauffage d'abord (c'est lui qui peut brûler une
        culture), la ventilation ensuite. Une exception sur le premier ne doit
        pas empêcher le second — le superviseur journalise et poursuit.
        """
        try:
            self.heater.set_state(0)
        finally:
            self.motor_handler.all_off()

    # ──────────────────────────────────────────────────────────
    def _register_jobs(self) -> None:
        sup = self.supervisor

        # --- Daily timers ---
        sup.register(
            "daily_timer_1",
            lambda: timer_daily(self.dailytimer1, sampling_time=60),
            safe_state=self._component_off(self.dailytimer1.component),
            max_silence=MAX_SILENCE_SECONDS,
        )
        sup.register(
            "daily_timer_2",
            lambda: timer_daily(self.dailytimer2, sampling_time=60),
            safe_state=self._component_off(self.dailytimer2.component),
            max_silence=MAX_SILENCE_SECONDS,
        )

        # --- Cyclic timers ---
        sup.register(
            "cyclic_timer_1",
            lambda: timer_cyclic(self.cyclic_timer1),
            safe_state=self._component_off(self.cyclic_timer1.component),
            max_silence=MAX_SILENCE_SECONDS,
        )
        sup.register(
            "cyclic_timer_2",
            lambda: timer_cyclic(self.cyclic_timer2),
            safe_state=self._component_off(self.cyclic_timer2.component),
            max_silence=MAX_SILENCE_SECONDS,
        )

        # --- Arbitre thermique (chauffage + ventilation) ---
        # Un seul travail pour les deux organes : ils régulent la même
        # température et se contredisaient tant qu'ils étaient supervisés
        # séparément (audit C9).
        sup.register(
            "climate_control",
            lambda: climate_control(
                heater_component=self.heater,
                motor_handler=self.motor_handler,
                sensor_handler=self.sensor_handler,
                sampling_time=30,
            ),
            safe_state=self._climate_off,
            max_silence=MAX_SILENCE_SECONDS,
        )

        # --- Snapshot capteurs partagé ---
        sup.register(
            "sensor_snapshot",
            lambda: refresh_sensor_snapshot(self.sensor_handler, period=10),
            max_silence=MAX_SILENCE_SECONDS,
        )

        # --- InfluxDB push ---
        # On partage le SensorController déjà construit : une seule ouverture
        # de /dev/i2c-1 pour tout le processus.
        try:
            influx_handler.reload_sensor_handler(self.config, self.sensor_handler)
        except Exception as exc:
            error(f"Initialisation InfluxDB impossible : {exc.__class__.__name__} : {exc}",
                  name=LOGGER_NAME)

        # Le job reste vivant : `host_machine_state` l'active ou le suspend à
        # chaud, sans devoir modifier le registre du superviseur.
        sup.register(
            "influx_push",
            lambda: write_sensor_values(period=60),
            max_silence=MAX_SILENCE_SECONDS,
        )

        # --- Serveur HTTP ---
        # `max_silence=None` : rester en attente de connexion **est** son
        # fonctionnement normal, un silence n'y prouve rien.
        # Instance unique : `run()` referme sa socket en sortant (`async with`),
        # donc une relance rouvre proprement le port sans recréer les stats.
        server = Server(
            controller_status=self.controller_status,
            sensor_handler=self.sensor_handler,
            config=self.config,
            supervisor=self.supervisor,
            dailytimer1=self.dailytimer1,
            dailytimer2=self.dailytimer2,
            cyclic_timer1=self.cyclic_timer1,
            cyclic_timer2=self.cyclic_timer2,
            heater_component=self.heater,
        )
        sup.register("http_server", server.run, max_silence=None)

    # ──────────────────────────────────────────────────────────
    async def main_loop(self) -> None:
        self._set_global_exception()
        loop = asyncio.get_event_loop()

        self._register_jobs()
        self.supervisor.start()

        # Watchdog : tâche nue et volontairement non supervisée — si elle meurt,
        # plus personne ne caresse et le redémarrage survient. C'est le bon sens
        # de la panne (audit E2).
        loop.create_task(
            watchdog.watchdog_loop(
                self.supervisor.is_healthy,
                self.supervisor.unhealthy_names,
            ),
            name="watchdog",
        )

        # systemd `Type=notify` : le service n'est déclaré prêt qu'une fois les
        # tâches de régulation lancées, pas au démarrage du processus.
        watchdog.notify_ready()

        debug("Boucle principale : attente des tâches supervisées", name=LOGGER_NAME)
        try:
            await self.supervisor.wait()
        finally:
            await self.sensor_handler.close()
