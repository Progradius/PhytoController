"""Synthèses de culture auxiliaires : lit seulement la copie des acquisitions existantes."""

import asyncio

from controllers.sensor_catalog import SENSOR_CATALOG
from utils.log_dedup import StateLogger
from utils.supervisor import beat, sleep


class CultureService:
    def __init__(self, store, sensors):
        self.store = store
        self.sensors = sensors
        self.logger = StateLogger("Synthèse climatique du carnet", name="cultures")
        self.metadata = {sensor.key: (sensor.label, sensor.unit) for sensor in SENSOR_CATALOG}

    async def sample_once(self):
        return await self.store.call("climate_sample", self.sensors.snapshot(), self.metadata)

    async def run(self):
        while True:
            beat()
            try:
                await self.sample_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Le texte de l'exception ne contient jamais de note/photo opérateur.
                self.logger.fail(f"Synthèse climatique du carnet indisponible ({type(exc).__name__}).")
            else:
                self.logger.ok("Synthèse climatique du carnet disponible.")
            await sleep(60)
