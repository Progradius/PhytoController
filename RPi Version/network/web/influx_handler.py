# network/web/influx_handler.py

import asyncio
import gc
from time import time
from typing import TYPE_CHECKING

import aiohttp

from utils.pretty_console import debug, info
from utils.log_dedup import StateLogger
from utils.supervisor import beat, sleep as hb_sleep
from param.config import AppConfig

if TYPE_CHECKING:
    from controllers.SensorController import SensorController

LOGGER_NAME = "influx"

# Variables globales pouvant être mises à jour dynamiquement
_params = None
_sensor_handler = None
_write_url = ""
_write_params: dict[str, str] = {}
_endpoint_label = ""
_health = {
    "state": "never",
    "last_success_ts": None,
    "last_failure_ts": None,
    "last_error": None,
}

# Anti-flood : 1 ligne à l'entrée en panne, 1 au rétablissement
_push_state = StateLogger("Push InfluxDB", name=LOGGER_NAME)


def get_health() -> dict:
    """État sûr de l'export, sans endpoint ni identifiant."""
    enabled = bool(
        _params is not None
        and str(_params.network.host_machine_state).lower() == "online"
    )
    return {**_health, "enabled": enabled, "failures": _push_state.failures}


def reload_sensor_handler(config: AppConfig, sensor_handler: "SensorController | None" = None) -> None:
    """
    Recharge dynamiquement le SensorController et l'endpoint Influx.

    `sensor_handler` : réutilise une instance existante plutôt que d'en créer
    une seconde — chaque SensorController ouvre son propre /dev/i2c-1 et rien
    ne le referme.

    Les identifiants ne sont JAMAIS placés dans l'URL : ils partent en
    paramètres de requête (hors de toute chaîne loggable).
    """
    global _params, _sensor_handler, _write_url, _write_params, _endpoint_label
    _params = config
    if sensor_handler is None:
        raise ValueError("Un SensorController partagé est requis")
    _sensor_handler = sensor_handler

    net = _params.network
    _write_url = f"http://{net.host_machine_address}:{net.influx_db_port}/write"
    _write_params = {
        "db": net.influx_db_name,
        "u": net.influx_db_user,
        "p": net.influx_db_password,
    }
    # Label sûr pour les messages : hôte, port et base, jamais les identifiants
    _endpoint_label = f"{net.host_machine_address}:{net.influx_db_port}/{net.influx_db_name}"

    info(
        f"Handler rechargé, mesures : {', '.join(_sensor_handler.sensor_dict.keys())}",
        name=LOGGER_NAME,
    )


# Pas d'initialisation à l'import : elle ouvrirait un second bus I²C et ferait
# dépendre l'import de PuppetMaster de la validité de param.json.
# PuppetMaster appelle reload_sensor_handler() au démarrage des tâches.


def _escape_field_key(key: str) -> str:
    return key.replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")


def _escape_tag(value: str) -> str:
    return _escape_field_key(value)


def _escape_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _send_quality_point(session, sensor: dict) -> tuple[bool | None, str | None]:
    fields = [
        f'status="{_escape_string(str(sensor.get("status", "absent")))}"',
        f'control_usable={str(bool(sensor.get("control_usable"))).lower()}',
        f'consecutive_failures={int(sensor.get("failures", {}).get("consecutive", 0))}i',
        f'unchanged_seconds={float(sensor.get("unchanged_for_s", 0.0))}',
    ]
    if sensor.get("raw_value") is not None:
        fields.append(f'raw_value={float(sensor["raw_value"])}')
    if sensor.get("observed_value") is not None:
        fields.append(f'observed_value={float(sensor["observed_value"])}')
    payload = f'sensor_quality,sensor={_escape_tag(sensor["key"])} {",".join(fields)}'
    try:
        async with session.post(_write_url, params=_write_params, data=payload) as response:
            status = response.status
            await response.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return False, exc.__class__.__name__
    return (True, None) if status == 204 else (False, f"HTTP {status}")


async def _send_grouped_point(
    session: aiohttp.ClientSession,
    measurement: str,
    values: dict[str, float],
) -> tuple[bool | None, str | None]:
    if not values:
        debug(f"{measurement} : aucune donnée à envoyer", name=LOGGER_NAME)
        return None, None

    field_parts = [f"{_escape_field_key(k)}={v}" for k, v in values.items() if v is not None]
    if not field_parts:
        debug(f"{measurement} : toutes les valeurs sont None", name=LOGGER_NAME)
        return None, None

    payload = f"{measurement} {','.join(field_parts)}"
    # Les valeurs sont déjà dans Influx : inutile de les dupliquer en INFO
    debug(f"{measurement} → {', '.join(field_parts)}", name=LOGGER_NAME)

    try:
        async with session.post(_write_url, params=_write_params, data=payload) as response:
            status = response.status
            await response.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        # Surtout pas repr(exc) : certains clients recopient l'URL complète.
        return False, exc.__class__.__name__

    if status != 204:
        return False, f"HTTP {status}"

    return True, None


async def write_sensor_values(period: int = 60) -> None:
    info(f"Boucle de collecte démarrée (intervalle : {period} s)", name=LOGGER_NAME)
    timeout = aiohttp.ClientTimeout(total=4)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        while True:
            beat()
            if _sensor_handler is None:
                _push_state.fail("handler non initialisé")
                _health.update(
                    state="error", last_failure_ts=time(),
                    last_error="handler non initialisé",
                )
            elif str(_params.network.host_machine_state).lower() != "online":
                debug("Export InfluxDB désactivé", name=LOGGER_NAME)
                _push_state.ok("export désactivé")
                _health.update(state="disabled", last_error=None)
            else:
                snapshot = _sensor_handler.snapshot()
                attempted = False
                failures = []
                for measurement, sensors in _sensor_handler.sensor_dict.items():
                    sensor_values = {
                        sensor_name: snapshot[sensor_name]["value"]
                        for sensor_name in sensors
                        if snapshot.get(sensor_name, {}).get("status") in {"normal", "degraded", "ok"}
                        and snapshot.get(sensor_name, {}).get("value") is not None
                    }
                    outcome, detail = await _send_grouped_point(session, measurement, sensor_values)
                    if outcome is not None:
                        attempted = True
                    if outcome is False:
                        failures.append(detail or "échec")
                for sensor in snapshot.values():
                    if not sensor.get("enabled"):
                        continue
                    attempted = True
                    outcome, detail = await _send_quality_point(session, sensor)
                    if outcome is False:
                        failures.append(detail or "échec qualité")
                if failures:
                    safe_detail = failures[0]
                    _push_state.fail(f"{_endpoint_label} → {safe_detail}")
                    _health.update(
                        state="error", last_failure_ts=time(), last_error=safe_detail,
                    )
                elif attempted:
                    _push_state.ok()
                    _health.update(
                        state="ok", last_success_ts=time(), last_error=None,
                    )
                else:
                    _push_state.ok("aucune mesure valide à exporter")
                    _health.update(state="idle", last_error=None)

            gc.collect()
            await hb_sleep(period)
