# controller/web/server.py
# Author : Progradius (refacto)
# License: AGPL-3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra-léger basé sur asyncio, utilisant AppConfig
# -------------------------------------------------------------

from __future__ import annotations
import asyncio
import json
import urllib.parse
from typing import Tuple

from ui.pretty_console import info, success, warning, error, action
from network.web.pages import main_page, conf_page, monitor_page
from model.SensorStats   import SensorStats
from param.config        import AppConfig

# ── correspondance « champ GET » → (section_attr, clé_attr) ─────────────
# Les section_attr correspondent aux attributs d’AppConfig
_CONF_FIELDS: dict[str, tuple[str, str | tuple[str, str]]] = {
    # DailyTimer #1
    "dt1start": ("daily_timer1", ("start_hour",    "start_minute")),
    "dt1stop":  ("daily_timer1", ("stop_hour",     "stop_minute")),
    # DailyTimer #2
    "dt2start": ("daily_timer2", ("start_hour",    "start_minute")),
    "dt2stop":  ("daily_timer2", ("stop_hour",     "stop_minute")),

    # Cyclic #1
    "period":   ("cyclic1",      "period_minutes"),
    "duration": ("cyclic1",      "action_duration_seconds"),
    # Cyclic #2
    "period2":  ("cyclic2",      "period_minutes"),
    "duration2":("cyclic2",      "action_duration_seconds"),

    # Temperature Settings
    "min_day":           ("temperature", "target_temp_min_day"),
    "max_day":           ("temperature", "target_temp_max_day"),
    "min_night":         ("temperature", "target_temp_min_night"),
    "max_night":         ("temperature", "target_temp_max_night"),
    "hysteresis_offset": ("temperature", "hysteresis_offset"),

    # Heater enable
    "heater_enabled":    ("heater_settings", "enabled"),

    # Network Settings
    "host":        ("network", "host_machine_address"),
    "wifi_ssid":   ("network", "wifi_ssid"),
    "wifi_password":("network","wifi_password"),
    "influx_db":   ("network", "influx_db_name"),
    "influx_port": ("network", "influx_db_port"),
    "influx_user": ("network", "influx_db_user"),
    "influx_pw":   ("network", "influx_db_password"),

    # Growth stage
    "stage":       ("life_period", "stage"),

    # Motor Settings
    "motor_mode":  ("motor",      "motor_mode"),
    "speed":       ("motor",      "motor_user_speed"),
    "target_temp": ("motor",      "target_temp"),
    "hysteresis":  ("motor",      "hysteresis"),
    "min_speed":   ("motor",      "min_speed"),
    "max_speed":   ("motor",      "max_speed"),

    # GPIO Settings
    "dailytimer1_pin": ("gpio", "dailytimer1_pin"),
    "dailytimer2_pin": ("gpio", "dailytimer2_pin"),
    "cyclic1_pin":     ("gpio", "cyclic1_pin"),
    "cyclic2_pin":     ("gpio", "cyclic2_pin"),
    "heater_pin":      ("gpio", "heater_pin"),
    "motor_pin1":      ("gpio", "motor_pin1"),
    "motor_pin2":      ("gpio", "motor_pin2"),
    "motor_pin3":      ("gpio", "motor_pin3"),
    "motor_pin4":      ("gpio", "motor_pin4"),
}


class Server:
    """
    Routes gérées :
      • GET /         → page d’accueil
      • GET /conf     → page configuration (+ prise en compte des champs GET)
      • GET /monitor  → page monitoring (capteurs + stats + GPIO)
      • GET /status   → JSON de statut pour intégration externe
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

        # Min/max stats
        self.stats = SensorStats()
        # Inject same stats into sensor_handler
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
                body   = main_page(self.controller_status).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            # Configuration
            elif path.startswith("/conf"):
                self._apply_conf_changes(path)
                body   = conf_page(self.config).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            # Monitoring + resets
            elif path.startswith("/monitor"):
                parts = urllib.parse.urlparse(path)
                query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)

                # Traite chaque reset_<capteur>
                for param in query:
                    if not param.startswith("reset_"):
                        continue
                    key = param.split("reset_", 1)[1]
                    sensor_key = "DS18B#3" if key == "DS18B3" else key
                    self.stats.clear_key(sensor_key)
                    val = self.sensor_handler.get_sensor_value(sensor_key)
                    if val is not None:
                        self.stats.update(sensor_key, float(val))
                    success(f"Statistique {sensor_key} réinitialisée")

                body   = monitor_page(self.sensor_handler, self.stats, self.config).encode("utf-8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

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

            section_attr, attr_key = _CONF_FIELDS[key]
            model = getattr(self.config, section_attr)
            raw   = values[0]

            # HH:MM fields
            if isinstance(attr_key, tuple):
                try:
                    h, m = map(int, raw.split(":"))
                except ValueError:
                    error(f"Format HH:MM invalide pour {key}={raw}")
                    continue
                setattr(model, attr_key[0], h)
                setattr(model, attr_key[1], m)

            # simple scalar
            else:
                current = getattr(model, attr_key)
                if isinstance(current, bool):
                    cast = raw.lower() in ("1","true","enabled","on","yes")
                elif isinstance(current, int):
                    cast = int(raw)
                elif isinstance(current, float):
                    cast = float(raw)
                else:
                    cast = raw
                setattr(model, attr_key, cast)

            success(f"{key} <- {raw}")

        # finally persist back to param.json
        self.config.save()
