# controller/web/server.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra-léger basé sur asyncio
# -------------------------------------------------------------

from __future__ import annotations
import asyncio
import urllib.parse
from typing import Tuple

from ui.pretty_console           import info, success, warning, error, action
from network.web.pages           import main_page, conf_page, monitor_page
from model.SensorStats           import SensorStats
from param.config                import AppConfig

# ── correspondance « champ GET » → (section_attr, clé_attr) ─────────────
# section_attr doit correspondre au nom du champ AppConfig.<section_attr>
_CONF_FIELDS: dict[str, tuple[str, str | tuple[str, str]]] = {
    # DailyTimer #1
    "dt1start"      : ("daily_timer1_settings", ("start_hour",    "start_minute")),
    "dt1stop"       : ("daily_timer1_settings", ("stop_hour",     "stop_minute")),
    # DailyTimer #2
    "dt2start"      : ("daily_timer2_settings", ("start_hour",    "start_minute")),
    "dt2stop"       : ("daily_timer2_settings", ("stop_hour",     "stop_minute")),

    # Cyclic #1
    "period"        : ("cyclic1_settings",     "period_minutes"),
    "duration"      : ("cyclic1_settings",     "action_duration_seconds"),
    # Cyclic #2
    "period2"       : ("cyclic2_settings",     "period_minutes"),
    "duration2"     : ("cyclic2_settings",     "action_duration_seconds"),

    # Temperature Settings
    "min_day"           : ("temperature_settings", "target_temp_min_day"),
    "max_day"           : ("temperature_settings", "target_temp_max_day"),
    "min_night"         : ("temperature_settings", "target_temp_min_night"),
    "max_night"         : ("temperature_settings", "target_temp_max_night"),
    "hysteresis_offset" : ("temperature_settings", "hysteresis_offset"),

    # Heater enable
    "heater_enabled"    : ("heater_settings",      "enabled"),

    # Network Settings
    "host"              : ("network_settings",     "host_machine_address"),
    "wifi_ssid"         : ("network_settings",     "wifi_ssid"),
    "wifi_password"     : ("network_settings",     "wifi_password"),
    "influx_db"         : ("network_settings",     "influx_db_name"),
    "influx_port"       : ("network_settings",     "influx_db_port"),
    "influx_user"       : ("network_settings",     "influx_db_user"),
    "influx_pw"         : ("network_settings",     "influx_db_password"),

    # Growth stage
    "stage"             : ("life_period",          "stage"),

    # Motor Settings
    "motor_mode"        : ("motor_settings",       "motor_mode"),
    "speed"             : ("motor_settings",       "motor_user_speed"),
    "target_temp"       : ("motor_settings",       "target_temp"),
    "hysteresis"        : ("motor_settings",       "hysteresis"),
    "min_speed"         : ("motor_settings",       "min_speed"),
    "max_speed"         : ("motor_settings",       "max_speed"),

    # GPIO Settings
    "dailytimer1_pin"   : ("gpio_settings",        "dailytimer1_pin"),
    "dailytimer2_pin"   : ("gpio_settings",        "dailytimer2_pin"),
    "cyclic1_pin"       : ("gpio_settings",        "cyclic1_pin"),
    "cyclic2_pin"       : ("gpio_settings",        "cyclic2_pin"),
    "heater_pin"        : ("gpio_settings",        "heater_pin"),
    "motor_pin1"        : ("gpio_settings",        "motor_pin1"),
    "motor_pin2"        : ("gpio_settings",        "motor_pin2"),
    "motor_pin3"        : ("gpio_settings",        "motor_pin3"),
    "motor_pin4"        : ("gpio_settings",        "motor_pin4"),
}

class Server:
    """
    Routes gérées :
      • GET /            → page d’accueil
      • GET /conf        → page configuration (+ prise en compte des champs GET)
      • GET /monitor     → page monitoring (valeurs capteurs + stats + GPIO)
      • GET /status      → JSON de statut pour intégration externe
    """

    def __init__(
        self,
        controller_status,
        sensor_handler,
        config: AppConfig,
        host: str = "0.0.0.0",
        port: int = 8123
    ):
        self.controller_status = controller_status
        self.sensor_handler    = sensor_handler
        self.config            = config
        self.host              = host
        self.port              = port

        # min/max stats
        self.stats = SensorStats()
        # inject same stats into the handler
        setattr(self.sensor_handler, "stats", self.stats)

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
        # 1) Request line
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

        # 2) Skip headers
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

        status, body, ctype = "404 Not Found", b"Not found", "text/plain"

        # 3) Routing
        if method != "GET":
            status, body = "405 Method Not Allowed", b"Method not allowed"

        else:
            # Accueil
            if path in ("/", "/index.html"):
                body, ctype, status = (
                    main_page(self.controller_status).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )

            # Configuration
            elif path.startswith("/conf"):
                self._apply_conf_changes(path)
                body, ctype, status = (
                    conf_page(self.config).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )

            # Monitoring + resets
            elif path.startswith("/monitor"):
                parts = urllib.parse.urlparse(path)
                query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)

                # reset_<capteur>
                for param in query:
                    if not param.startswith("reset_"):
                        continue
                    key = param.split("reset_",1)[1]
                    sensor_key = "DS18B#3" if key == "DS18B3" else key
                    self.stats.clear_key(sensor_key)
                    val = self.sensor_handler.get_sensor_value(sensor_key)
                    if val is not None:
                        self.stats.update(sensor_key, float(val))
                    success(f"Statistique {sensor_key} réinitialisée")

                # Génère la page
                body, ctype, status = (
                    monitor_page(self.sensor_handler, self.stats, self.config).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )

            # Status JSON
            elif path.startswith("/status"):
                payload = {
                    "component_state": self.controller_status.get_component_state(),
                    "motor_speed"    : self.controller_status.get_motor_speed(),
                    "dailytimer1"    : {
                        "start": self.controller_status.get_dailytimer_current_start_time(),
                        "stop" : self.controller_status.get_dailytimer_current_stop_time(),
                    },
                    "cyclic"         : {
                        "period"  : self.controller_status.get_cyclic_period(),
                        "duration": self.controller_status.get_cyclic_duration(),
                    }
                }
                body, ctype, status = (
                    json.dumps(payload).encode("utf-8"),
                    "application/json",
                    "200 OK"
                )

        # 4) Envoi réponse
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
        Applique chaque paramètre GET sur self.config, puis sauvegarde le JSON.
        """
        parts = urllib.parse.urlparse(raw_path)
        if not parts.query:
            return

        query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        for key, values in query.items():
            if key not in _CONF_FIELDS:
                warning(f"Champ GET inconnu : {key}")
                continue

            section_attr, j_k = _CONF_FIELDS[key]
            model = getattr(self.config, section_attr)

            value = values[0]
            # HH:MM fields
            if isinstance(j_k, tuple):
                try:
                    hh, mm = map(int, value.split(":"))
                except ValueError:
                    error(f"Format HH:MM invalide pour {key}={value}")
                    continue
                setattr(model, j_k[0], hh)
                setattr(model, j_k[1], mm)

            # simple scalar fields
            else:
                # conversion booléenne pour heater_enabled
                if key == "heater_enabled":
                    cast = value.lower() in ("1","true","enabled","on","yes")
                else:
                    # int ou float selon votre modèle AppConfig
                    cast = (int(value) if isinstance(getattr(model, j_k), int)
                            else float(value)
                            if isinstance(getattr(model, j_k), float)
                            else value)
                setattr(model, j_k, cast)

            success(f"{key} <- {value}")

        # enfin on écrit tout d’un coup dans le JSON
        self.config.save()
