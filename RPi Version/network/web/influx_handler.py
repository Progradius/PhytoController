# network/web/influx_handler.py

import asyncio
import gc
from urllib.parse import urlencode

import requests

from ui.pretty_console import info, warning, error
from param.config import AppConfig
from controllers.SensorController import SensorController

# Variables globales pouvant être mises à jour dynamiquement
_params = None
_sensor_handler = None
_query_base = ""

def reload_sensor_handler(config: AppConfig) -> None:
    """
    Recharge dynamiquement le SensorController et l'endpoint Influx.
    """
    global _params, _sensor_handler, _query_base
    _params = config
    _sensor_handler = SensorController(_params)
    _query_base = f"http://{_params.network.host_machine_address}:{_params.network.influx_db_port}/write?" + urlencode({
        "db": _params.network.influx_db_name,
        "u": _params.network.influx_db_user,
        "p": _params.network.influx_db_password,
    })
    info(f"[Influx] Handler rechargé avec mesures : {_sensor_handler.sensor_dict.keys()}")

# Initialisation
reload_sensor_handler(AppConfig.load())

def _escape_field_key(key: str) -> str:
    return key.replace(" ", r"\ ").replace(",", r"\,").replace("=", r"\=")

def _send_grouped_point(measurement: str, values: dict[str, float]) -> None:
    if not values:
        warning(f"{measurement}: aucune donnée à envoyer")
        return

    field_parts = [f"{_escape_field_key(k)}={v}" for k, v in values.items() if v is not None]
    if not field_parts:
        warning(f"{measurement}: toutes les valeurs sont None")
        return

    payload = f"{measurement} {','.join(field_parts)}"
    info(f"[{measurement}] → {', '.join(field_parts)}")

    try:
        r = requests.post(_query_base, data=payload, timeout=4)
        if r.status_code != 204:
            warning(f"InfluxDB HTTP {r.status_code}: {r.text.strip()}")
    except requests.RequestException as exc:
        error(f"POST InfluxDB : {exc}")

async def write_sensor_values(period: int = 60) -> None:
    info(f"▶️ Boucle de collecte démarrée (intervalle : {period}s)")
    while True:
        for measurement, sensors in _sensor_handler.sensor_dict.items():
            sensor_values = {}
            for sensor_name in sensors:
                val = _sensor_handler.get_sensor_value(sensor_name)
                sensor_values[sensor_name] = val
            _send_grouped_point(measurement, sensor_values)

        gc.collect()
        await asyncio.sleep(period)
