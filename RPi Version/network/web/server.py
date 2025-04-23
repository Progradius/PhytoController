# controller/web/server.py
# Author : Progradius (adapted)
# License: AGPL-3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra-léger basé sur asyncio
# -------------------------------------------------------------

from __future__ import annotations

import asyncio
import json
import urllib.parse
from typing import Tuple

from ui.pretty_console            import info, success, warning, error, action
from network.web.pages            import main_page, conf_page, monitor_page
from param.parameter_handler      import (
    write_current_parameters_to_json,
    update_one_parameter
)

# ── correspondance « champ GET » → (section_JSON, clé_JSON) ─────────────
_CONF_FIELDS: dict[str, tuple[str, str | tuple[str, str]]] = {
    # DailyTimer #1
    "dt1start"      : ("DailyTimer1_Settings", ("start_hour",        "start_minute")),
    "dt1stop"       : ("DailyTimer1_Settings", ("stop_hour",         "stop_minute")),
    # DailyTimer #2
    "dt2start"      : ("DailyTimer2_Settings", ("start_hour",        "start_minute")),
    "dt2stop"       : ("DailyTimer2_Settings", ("stop_hour",         "stop_minute")),

    # Cyclic #1
    "period"        : ("Cyclic1_Settings",     "period_minutes"),
    "duration"      : ("Cyclic1_Settings",     "action_duration_seconds"),
    # Cyclic #2
    "period2"       : ("Cyclic2_Settings",     "period_minutes"),
    "duration2"     : ("Cyclic2_Settings",     "action_duration_seconds"),
    
    # Temperature Settings
    "min_day"           : ("Temperature_Settings", "target_temp_min_day"),
    "max_day"           : ("Temperature_Settings", "target_temp_max_day"),
    "min_night"         : ("Temperature_Settings", "target_temp_min_night"),
    "max_night"         : ("Temperature_Settings", "target_temp_max_night"),
    "hysteresis_offset" : ("Temperature_Settings", "hysteresis_offset"),

    # Heater enable / pin
    "heater_enabled"    : ("Heater_Settings",      "enabled"),
    "heater_pin"        : ("GPIO_Settings",        "heater_pin"),

    # Growth stage
    "stage"         : ("life_period",          "stage"),

    # Motor Settings
    "motor_mode"    : ("Motor_Settings",       "motor_mode"),
    "speed"         : ("Motor_Settings",       "motor_user_speed"),
    "target_temp"   : ("Motor_Settings",       "target_temp"),
    "hysteresis"    : ("Motor_Settings",       "hysteresis"),
    "min_speed"     : ("Motor_Settings",       "min_speed"),
    "max_speed"     : ("Motor_Settings",       "max_speed"),

    # Network Settings
    "host"          : ("Network_Settings",     "host_machine_address"),
    "wifi_ssid"     : ("Network_Settings",     "wifi_ssid"),
    "wifi_password" : ("Network_Settings",     "wifi_password"),
    "influx_db"     : ("Network_Settings",     "influx_db_name"),
    "influx_port"   : ("Network_Settings",     "influx_db_port"),
    "influx_user"   : ("Network_Settings",     "influx_db_user"),
    "influx_pw"     : ("Network_Settings",     "influx_db_password"),
}

class Server:
    """
    Routes gérées :
      • GET /            → page d’accueil
      • GET /conf        → page configuration (+ prise en compte des champs GET)
      • GET /monitor     → page monitoring (valeurs capteurs live)
      • GET /status      → JSON de statut pour intégration externe
    """

    def __init__(
        self,
        controller_status,
        sensor_handler,
        parameters,
        host: str = "0.0.0.0",
        port: int = 8123
    ):
        self.controller_status = controller_status
        self.sensor_handler    = sensor_handler
        self.parameters        = parameters
        self.host = host
        self.port = port

    async def run(self) -> None:
        srv = await asyncio.start_server(self._handle, self.host, self.port)
        success(f"HTTP prêt sur {self.host}:{self.port}")
        async with srv:
            await srv.serve_forever()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:

        # 1) Lecture de la ligne de requête
        req_line = await reader.readline()
        try:
            method, path, _ = req_line.decode("ascii").split()
        except ValueError:
            raw = req_line.decode("ascii", errors="replace").rstrip("\r\n")
            error("Requête malformée détectée")
            warning(f"Contenu brut : {repr(raw)}")
            writer.close()
            return

        action(f"{method} {path}")

        # 2) Vidage des headers
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

        status, body, ctype = "404 Not Found", b"Not found", "text/plain"

        # 3) Routing
        if method != "GET":
            status, body = "405 Method Not Allowed", b"Method not allowed"
        else:
            if path in ("/", "/index.html"):
                body   = main_page(self.controller_status).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            elif path.startswith("/conf"):
                self._apply_conf_changes(path)
                body   = conf_page(self.parameters).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            elif path.startswith("/monitor"):
                body   = monitor_page(self.sensor_handler).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            elif path.startswith("/status"):
                payload = {
                    "component_state": self.controller_status.get_component_state(),
                    "motor_speed"    : self.controller_status.get_motor_speed(),
                    "dailytimer1"    : {
                        "start": self.controller_status.get_dailytimer_current_start_time(),
                        "stop" : self.controller_status.get_dailytimer_current_stop_time(),
                    },
                    "cyclic"        : {
                        "period"  : self.controller_status.get_cyclic_period(),
                        "duration": self.controller_status.get_cyclic_duration(),
                    }
                }
                body   = json.dumps(payload).encode("utf-8")
                status = "200 OK"
                ctype  = "application/json"

        # 4) Envoi de la réponse
        headers = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers.encode("utf-8") + body)
        await writer.drain()
        writer.close()

    def _apply_conf_changes(self, raw_path: str) -> None:
        """
        Extrait la query-string éventuelle et applique les changements
        → instance Parameter **et** fichier JSON.
        """
        parts = urllib.parse.urlparse(raw_path)
        if not parts.query:
            return

        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        for key, values in query.items():
            if key not in _CONF_FIELDS:
                warning(f"Champ GET inconnu : {key}")
                continue

            value, (section, j_k) = values[0], _CONF_FIELDS[key]

            # HH:MM fields
            if isinstance(j_k, tuple):
                try:
                    hh, mm = map(int, value.split(":"))
                except ValueError:
                    error(f"Format HH:MM invalide pour {key}={value}")
                    continue

                k_h, k_m = j_k
                update_one_parameter(section, k_h, hh)
                update_one_parameter(section, k_m, mm)

                if key == "dt1start":
                    self.parameters.set_dailytimer1_start_hour(hh)
                    self.parameters.set_dailytimer1_start_minute(mm)
                elif key == "dt1stop":
                    self.parameters.set_dailytimer1_stop_hour(hh)
                    self.parameters.set_dailytimer1_stop_minute(mm)
                elif key == "dt2start":
                    self.parameters.set_dailytimer2_start_hour(hh)
                    self.parameters.set_dailytimer2_start_minute(mm)
                elif key == "dt2stop":
                    self.parameters.set_dailytimer2_stop_hour(hh)
                    self.parameters.set_dailytimer2_stop_minute(mm)

                success(f"{key} → {hh:02d}:{mm:02d}")

            # simple fields
            else:
                # Special case pour heater_enabled (garder la chaîne "enabled"/"disabled")
                if key == "heater_enabled":
                    update_one_parameter("Heater_Settings", "enabled", value)
                    self.parameters.set_heater_enabled(value)
                    success(f"{key} = {value}")
                    continue

                update_one_parameter(section, j_k, value)
                setter = getattr(self.parameters, f"set_{j_k}", None)
                if callable(setter):
                    setter(value)
                success(f"{key} = {value}")

        # ré-écrit le JSON complet pour cohérence
        write_current_parameters_to_json(self.parameters)
