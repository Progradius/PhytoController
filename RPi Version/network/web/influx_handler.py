# network/web/influx_handler.py

import asyncio
import gc

import requests

from utils.pretty_console import debug, info, warning, error
from utils.log_dedup import StateLogger
from utils.supervisor import beat, sleep as hb_sleep
from param.config import AppConfig
from controllers.SensorController import SensorController

LOGGER_NAME = "influx"

# Variables globales pouvant être mises à jour dynamiquement
_params = None
_sensor_handler = None
_write_url = ""
_write_params: dict[str, str] = {}
_endpoint_label = ""

# Anti-flood : 1 ligne à l'entrée en panne, 1 au rétablissement
_push_state = StateLogger("Push InfluxDB", name=LOGGER_NAME)


def reload_sensor_handler(config: AppConfig, sensor_handler=None) -> None:
    """
    Recharge dynamiquement le SensorController et l'endpoint Influx.

    `sensor_handler` : réutilise une instance existante plutôt que d'en créer
    une seconde — chaque SensorController ouvre son propre /dev/i2c-1 et rien
    ne le referme.

    Les identifiants ne sont JAMAIS placés dans l'URL : ils partent en
    paramètres de requête (`requests` les gère hors de toute chaîne loggable).
    """
    global _params, _sensor_handler, _write_url, _write_params, _endpoint_label
    _params = config
    _sensor_handler = sensor_handler or SensorController(_params)

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


def _send_grouped_point(measurement: str, values: dict[str, float]) -> None:
    if not values:
        debug(f"{measurement} : aucune donnée à envoyer", name=LOGGER_NAME)
        return

    field_parts = [f"{_escape_field_key(k)}={v}" for k, v in values.items() if v is not None]
    if not field_parts:
        debug(f"{measurement} : toutes les valeurs sont None", name=LOGGER_NAME)
        return

    payload = f"{measurement} {','.join(field_parts)}"
    # Les valeurs sont déjà dans Influx : inutile de les dupliquer en INFO
    debug(f"{measurement} → {', '.join(field_parts)}", name=LOGGER_NAME)

    try:
        r = requests.post(_write_url, params=_write_params, data=payload, timeout=4)
    except requests.RequestException as exc:
        # Surtout pas repr(exc) : requests y recopie l'URL complète (identifiants)
        _push_state.fail(f"{_endpoint_label} → {exc.__class__.__name__}")
        return

    if r.status_code != 204:
        _push_state.fail(f"{_endpoint_label} → HTTP {r.status_code}")
        return

    _push_state.ok()


async def write_sensor_values(period: int = 60) -> None:
    info(f"Boucle de collecte démarrée (intervalle : {period} s)", name=LOGGER_NAME)
    while True:
        beat()
        if _sensor_handler is None:
            warning("Handler InfluxDB non initialisé → collecte ignorée", name=LOGGER_NAME)
        else:
            for measurement, sensors in _sensor_handler.sensor_dict.items():
                sensor_values = {}
                for sensor_name in sensors:
                    sensor_values[sensor_name] = _sensor_handler.get_sensor_value(sensor_name)
                _send_grouped_point(measurement, sensor_values)

        gc.collect()
        await hb_sleep(period)
