# controller/web/influx_handler.py
# Author : Progradius
# License: AGPL-3.0
"""
Envoi périodique des mesures capteurs vers InfluxDB (v1.*) via l’API HTTP.

‣ URL construite dynamiquement à partir de AppConfig
‣ Log soigné (Pretty-Console)
‣ Gestion mémoire explicite (gc.collect) après chaque rafraîchissement
"""

import asyncio
import gc
from urllib.parse import urlencode

import requests

from ui.pretty_console import info, warning, error
from param.config import AppConfig
from controllers.SensorController import SensorController

# ───────────────────────────────────────────────────────────────
#  Initialisation unique depuis AppConfig
# ───────────────────────────────────────────────────────────────
_params = AppConfig.load()
# On passe _params en premier argument (config), pas en keyword 'parameters'
_sensor_handler = SensorController(_params)

_influx_host = f"http://{_params.network.host_machine_address}:{_params.network.influx_db_port}"
_query_base = _influx_host + "/write?" + urlencode({
    "db": _params.network.influx_db_name,
    "u":  _params.network.influx_db_user,
    "p":  _params.network.influx_db_password
})

info(f"InfluxDB → {_query_base}")


# ───────────────────────────────────────────────────────────────
#  Fonctions
# ───────────────────────────────────────────────────────────────
def _send_point(measurement: str, field: str, value):
    """
    Format *ligne protocole* Influx et POSTe la donnée.
    """
    if value is None:
        warning(f"{field}: valeur None ignorée")
        return

    payload = f"{measurement} {field}={value}"
    info(f"[{measurement}] {field} = {value}")

    try:
        r = requests.post(_query_base, data=payload, timeout=4)
        if r.status_code == 204:
            return  # OK (Influx renvoie 204 No Content)
        warning(f"InfluxDB HTTP {r.status_code}: {r.text.strip()}")
    except requests.RequestException as exc:
        error(f"POST InfluxDB : {exc}")


# ----------------------------------------------------------------
async def write_sensor_values(period: int = 60):
    """
    Coroutine principale : boucle infinie toutes les *period* secondes.
    """
    while True:
        for meas, sensors in _sensor_handler.sensor_dict.items():
            for name in sensors:
                val = _sensor_handler.get_sensor_value(name)
                _send_point(meas, name, val)

        gc.collect()
        await asyncio.sleep(period)
