# controller/sensor/SensorController.py
# Author : Progradius
# License : AGPL-3.0
# --------------------------------------------------------------------
#  Gestion unifiée de tous les capteurs matériels pour Raspberry Pi
#  (refactoré pour utiliser AppConfig au lieu de Parameter)
# --------------------------------------------------------------------

import asyncio
import copy
import smbus2
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from time import monotonic
from typing import Dict, List

# Handlers spécialisés
from sensor_handlers.BME280Handler   import BME280Handler
from sensor_handlers.DS18Handler     import DS18Handler
from sensor_handlers.VEML6075Handler import VEMLHandler
from sensor_handlers.VL53L0XHandler  import VL53L0XHandler
from sensor_handlers.MLX90614Handler import MLX90614Handler
from sensor_handlers.TSL2591Handler  import TSL2591Handler
from sensor_handlers.HCSR04Handler   import HCSR04Handler

# Affichage « Pretty »
from utils.pretty_console import debug, info, warning, error
from utils.log_dedup import StateLogger

LOGGER_NAME = "sensors"

# Votre modèle de config
from param.config import AppConfig
from controllers.sensor_catalog import SENSOR_CATALOG, SENSORS_BY_KEY, enabled_definitions


class SensorController:
    """
    Regroupe tous les capteurs sous des measurements « métier » :
      • air          : BME280 + MLX90614 ambiant
      • surface_temp : MLX90614 objet
      • water        : DS18B#3 (température d'eau)
      • distance     : VL53L0X + HC-SR04
      • lux          : TSL2591
    """

    def __init__(self, config: AppConfig, stats=None):
        self.config = config
        self.stats = stats
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="phyto-sensors")
        self._snapshot_lock = threading.Lock()
        self._snapshot: dict[str, dict] = {}
        self._closed = False

        # Échecs de lecture : une ligne à l'entrée en panne, une au rétablissement
        self._read_states: Dict[str, StateLogger] = {}
        self._stats_state = StateLogger("Mise à jour des min/max capteurs",
                                        name=LOGGER_NAME, level="warning")
        self.i2c = None
        self.bme = self.ds18 = self.veml = self.vl53 = None
        self.mlx = self.tsl = self.hcsr = None
        self.__init_handlers()

    def __init_handlers(self) -> None:
        """Construit les handlers activés sur l'unique propriétaire matériel."""
        # ── Bus I2C (/dev/i2c-1) ───────────────────────────────────────
        try:
            self.i2c = smbus2.SMBus(1)
            info("Bus I²C /dev/i2c-1 ouvert", name=LOGGER_NAME)
        except (FileNotFoundError, PermissionError, OSError) as e:
            error(f"Impossible d'ouvrir /dev/i2c-1 → {e.__class__.__name__} : {e}",
                  name=LOGGER_NAME)
            self.i2c = None

        # ── Activation selon AppConfig.sensors ─────────────────────────
        s = self.config.sensors
        self.bme_enabled  = s.bme280_state
        self.ds18_enabled = s.ds18b20_state
        self.veml_enabled = s.veml6075_state
        self.vl53_enabled = s.vl53L0x_state
        self.mlx_enabled  = s.mlx90614_state
        self.tsl_enabled  = s.tsl2591_state
        self.hcsr_enabled = s.hcsr04_state

        # Instanciation conditionnelle
        i2c_users = (self.bme_enabled or self.veml_enabled
                     or self.mlx_enabled or self.tsl_enabled)
        if self.i2c is None and i2c_users:
            warning("Bus I²C indisponible → capteurs I²C en mode dégradé (lectures None)",
                    name=LOGGER_NAME)

        self.bme  = BME280Handler(i2c=self.i2c)   if self.bme_enabled else None
        self.ds18 = DS18Handler()                 if self.ds18_enabled else None
        self.veml = VEMLHandler(i2c=self.i2c)     if self.veml_enabled else None
        self.vl53 = VL53L0XHandler(self.config)   if self.vl53_enabled else None
        self.mlx  = MLX90614Handler(i2c=self.i2c) if self.mlx_enabled else None
        self.tsl  = TSL2591Handler(i2c=self.i2c)  if self.tsl_enabled else None
        self.hcsr = HCSR04Handler(
            trigger_pin=self.config.gpio.hcsr_trigger_pin,
            echo_pin=self.config.gpio.hcsr_echo_pin
        ) if self.hcsr_enabled else None

        # ── Dictionnaire de mesures pour Influx / Web ─────────────────
        self.sensor_dict = self._build_sensor_dict()

        # État des capteurs journalisé UNE fois, à l'init (et non en boucle)
        etats = {
            "BME280": self.bme_enabled, "DS18B20": self.ds18_enabled,
            "VEML6075": self.veml_enabled, "VL53L0X": self.vl53_enabled,
            "MLX90614": self.mlx_enabled, "TSL2591": self.tsl_enabled,
            "HC-SR04": self.hcsr_enabled,
        }
        actifs   = [n for n, on in etats.items() if on] or ["aucun"]
        inactifs = [n for n, on in etats.items() if not on] or ["aucun"]
        info(f"Capteurs actifs : {', '.join(actifs)}", name=LOGGER_NAME)
        info(f"Capteurs désactivés : {', '.join(inactifs)}", name=LOGGER_NAME)
        debug(f"Mesures exportées : {self.sensor_dict}", name=LOGGER_NAME)

    def _close_devices(self) -> None:
        """Ferme les bus sans jamais libérer les GPIO vers un état flottant."""
        if self.vl53 and hasattr(self.vl53, "close"):
            self.vl53.close()
        if self.hcsr and getattr(self.hcsr, "sensor", None):
            try:
                import RPi.GPIO as GPIO
                GPIO.output(self.hcsr.sensor.trigger_pin, GPIO.LOW)
            except Exception as exc:
                warning(
                    f"HC-SR04 : maintien du trigger LOW impossible ({exc.__class__.__name__})",
                    name=LOGGER_NAME,
                )
        if self.i2c is not None:
            try:
                self.i2c.close()
            except Exception as exc:
                debug(f"Fermeture I²C ignorée : {exc.__class__.__name__}", name=LOGGER_NAME)
        self.i2c = None
        self.bme = self.ds18 = self.veml = self.vl53 = None
        self.mlx = self.tsl = self.hcsr = None

    def _is_sensor_enabled(self, sensor_name: str) -> bool:
        definition = SENSORS_BY_KEY.get(sensor_name)
        return bool(
            definition
            and getattr(self.config.sensors, definition.enabled_field, False)
        )

    def _build_sensor_dict(self) -> Dict[str, List[str]]:
        """
        Construit le dictionnaire des capteurs activés, utilisé pour l'export.
        """
        sensor_dict: Dict[str, List[str]] = {}
        for definition in enabled_definitions(self.config):
            sensor_dict.setdefault(definition.measurement, []).append(definition.key)

        return sensor_dict

    def get_sensor_value(self, sensor_key: str):
        """
        Retourne la mesure demandée (float ou int) ou None si désactivé/erreur.
        """
        try:
            result = None

            if sensor_key.startswith("DS18B#") and self.ds18:
                idx = int(sensor_key.split("#")[1])
                result = self.ds18.get_ds18_temp(idx)

            elif sensor_key.startswith("BME280") and self.bme:
                result = {
                    "BME280T": self.bme.get_bme_temp,
                    "BME280H": self.bme.get_bme_hygro,
                    "BME280P": self.bme.get_bme_pressure
                }[sensor_key]()

            elif sensor_key.startswith("TSL-") and self.tsl:
                result = {
                    "TSL-LUX": self.tsl.calculate_lux,
                    "TSL-IR": self.tsl.get_ir
                }[sensor_key]()

            elif sensor_key.startswith("VEML-") and self.veml:
                result = {
                    "VEML-UVA": self.veml.get_veml_uva,
                    "VEML-UVB": self.veml.get_veml_uvb,
                    "VEML-UVINDEX": self.veml.get_veml_uv_index
                }[sensor_key]()

            elif sensor_key in ("MLX-AMB", "MLX-OBJ") and self.mlx:
                result = {
                    "MLX-AMB": self.mlx.get_ambient_temp,
                    "MLX-OBJ": self.mlx.get_object_temp
                }[sensor_key]()

            elif sensor_key == "VL53L0X" and self.vl53:
                result = self.vl53.get_vl53_reading()

            elif sensor_key == "HCSR04" and self.hcsr:
                result = self.hcsr.get_distance_cm()

        except Exception as e:
            self._state_for(sensor_key).fail(f"{e.__class__.__name__} : {e}")
            self._record_snapshot(sensor_key, None, error=f"{e.__class__.__name__}")
            return None

        if result is None:
            if not self._is_sensor_enabled(sensor_key):
                # Capteur volontairement désactivé : ce n'est pas une anomalie
                debug(f"{sensor_key} désactivé", name=LOGGER_NAME)
            else:
                self._state_for(sensor_key).fail("lecture vide")
            self._record_snapshot(sensor_key, None, error="lecture vide")
            return None

        self._state_for(sensor_key).ok()
        self._record_snapshot(sensor_key, result)

        stats = getattr(self, "stats", None)
        if stats and sensor_key in stats.KEYS:
            try:
                stats.update(sensor_key, float(result))
                self._stats_state.ok()
            except Exception as e:
                self._stats_state.fail(f"{sensor_key} → {e.__class__.__name__} : {e}")

        return result

    async def read(self, sensor_key: str):
        """Lit une mesure dans l'unique exécuteur matériel sérialisé."""
        if self._closed:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, self.get_sensor_value, sensor_key)

    async def refresh_active(self) -> None:
        """Rafraîchit toutes les mesures actives, sans bloquer l'event loop."""
        for definition in enabled_definitions(self.config):
            await self.read(definition.key)

    def cached_value(self, sensor_key: str, max_age: float = 20.0):
        """Valeur de contrôle seulement si la dernière tentative est fraîche et réussie."""
        with self._snapshot_lock:
            record = self._snapshot.get(sensor_key)
            if not record or record.get("status") != "ok":
                return None
            if monotonic() - record["attempt_monotonic"] > max_age:
                return None
            return record.get("value")

    async def fresh_value(self, sensor_key: str, max_age: float = 20.0):
        value = self.cached_value(sensor_key, max_age=max_age)
        if value is not None:
            return value
        return await self.read(sensor_key)

    def snapshot(self) -> dict[str, dict]:
        """Copie sérialisable du dernier état connu, sans aucune lecture."""
        now = monotonic()
        result: dict[str, dict] = {}
        with self._snapshot_lock:
            records = copy.deepcopy(self._snapshot)
        for definition in SENSOR_CATALOG:
            record = records.get(definition.key)
            enabled = self._is_sensor_enabled(definition.key)
            if not enabled:
                status = "disabled"
            elif record is None:
                status = "never"
            elif record.get("status") != "ok":
                status = "error"
            elif now - record["attempt_monotonic"] > 30.0:
                status = "stale"
            else:
                status = "ok"
            result[definition.key] = {
                "key": definition.key,
                "label": definition.label,
                "unit": definition.unit,
                "decimals": definition.decimals,
                "enabled": enabled,
                "status": status,
                "value": record.get("last_good_value") if record else None,
                "last_attempt_at": record.get("last_attempt_at") if record else None,
                "last_success_at": record.get("last_success_at") if record else None,
                "age_s": round(now - record["success_monotonic"], 1)
                if record and record.get("success_monotonic") is not None else None,
            }
        return result

    async def reconfigure(self, config: AppConfig) -> None:
        """Reconstruit les handlers sur le même propriétaire, de façon sérialisée."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._reconfigure_sync, config)

    def _reconfigure_sync(self, config: AppConfig) -> None:
        self._close_devices()
        self.config = config
        self.__init_handlers()
        self.sensor_dict = self._build_sensor_dict()
        with self._snapshot_lock:
            for key in list(self._snapshot):
                if not self._is_sensor_enabled(key):
                    self._snapshot.pop(key, None)
        info("Pile capteurs reconfigurée sans nouvelle instance", name=LOGGER_NAME)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._executor, self._close_devices)
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _record_snapshot(self, sensor_key: str, value, error: str | None = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        now_mono = monotonic()
        with self._snapshot_lock:
            previous = self._snapshot.get(sensor_key, {})
            record = {
                "status": "ok" if error is None else "error",
                "value": value,
                "last_attempt_at": now_iso,
                "attempt_monotonic": now_mono,
                "last_good_value": previous.get("last_good_value"),
                "last_success_at": previous.get("last_success_at"),
                "success_monotonic": previous.get("success_monotonic"),
            }
            if error is None:
                record["last_good_value"] = value
                record["last_success_at"] = now_iso
                record["success_monotonic"] = now_mono
            self._snapshot[sensor_key] = record

    def _state_for(self, sensor_key: str) -> StateLogger:
        """StateLogger dédié à un capteur (créé à la volée)."""
        state = self._read_states.get(sensor_key)
        if state is None:
            state = StateLogger(f"Lecture {sensor_key}", name=LOGGER_NAME, level="warning")
            self._read_states[sensor_key] = state
        return state
