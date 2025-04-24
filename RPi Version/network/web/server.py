# controller/web/server.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra-léger basé sur asyncio, utilisant AppConfig
# -------------------------------------------------------------

from __future__ import annotations
import asyncio
import json
import urllib.parse

from ui.pretty_console         import success, warning, error, action, info
from network.web.pages         import main_page, conf_page, monitor_page
from model.SensorStats         import SensorStats
from param.config              import AppConfig
from controllers.SensorController import SensorController
from network.web import influx_handler  # ✅ Ajout

class Server:
    """
    Routes gérées :
      • GET /         → page d'accueil
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

        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

        status, body, ctype = "404 Not Found", b"Not found", "text/plain"

        if method != "GET":
            status, body = "405 Method Not Allowed", b"Method not allowed"
        else:
            if path in ("/", "/index.html"):
                body, ctype, status = (
                    main_page(self.controller_status).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )
            elif path.startswith("/conf"):
                self._apply_conf_changes(path)
                body, ctype, status = (
                    conf_page(self.config).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )
            elif path.startswith("/monitor"):
                parts = urllib.parse.urlparse(path)
                query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
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

                body, ctype, status = (
                    monitor_page(
                        self.sensor_handler,
                        self.stats,
                        self.config,
                        self.controller_status                # 🆕
                    ).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK"
                )
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
        parts = urllib.parse.urlparse(raw_path)
        if not parts.query:
            return

        q = urllib.parse.parse_qs(parts.query, keep_blank_values=True)
        data = self.config.model_dump(by_alias=True)

        alias2field: dict[str,str] = {
            field_info.alias: name
            for name, field_info in self.config.model_fields.items()
        }

        for alias, values in q.items():
            raw_val = values[0]
            if "." in alias:
                top_alias, nested_key = alias.split(".", 1)
                if top_alias not in alias2field:
                    warning(f"Ignoré : champ inconnu « {alias} »")
                    continue
                field_name   = alias2field[top_alias]
                nested_model = getattr(self.config, field_name)
                nested_fields= nested_model.__class__.model_fields

                if nested_key not in nested_fields:
                    warning(f"Ignoré : champ imbriqué inconnu « {nested_key} »")
                    continue

                ann = nested_fields[nested_key].annotation
                if ann is bool:
                    value = raw_val.lower() in ("1","true","enabled","yes")
                elif ann is int:
                    value = int(raw_val)
                elif ann is float:
                    value = float(raw_val)
                else:
                    value = raw_val

                data[top_alias][nested_key] = value
                success(f"{alias} ← {raw_val}")
            else:
                if alias not in alias2field:
                    warning(f"Ignoré : champ inconnu « {alias} »")
                    continue
                ann = self.config.model_fields[alias2field[alias]].annotation
                if ann is bool:
                    value = raw_val.lower() in ("1","true","enabled","yes")
                elif ann is int:
                    value = int(raw_val)
                elif ann is float:
                    value = float(raw_val)
                else:
                    value = raw_val

                data[alias] = value
                success(f"{alias} ← {raw_val}")

        self.config = AppConfig(**data)
        self.config.save()
        success("Configuration mise à jour")

        self.sensor_handler = SensorController(self.config)
        setattr(self.sensor_handler, "stats", self.stats)
        self.sensor_handler.sensor_dict = self.sensor_handler._build_sensor_dict()
        info(f"Nouvelles mesures actives : {list(self.sensor_handler.sensor_dict.keys())}")
        success("Sensor handler réinitialisé avec la nouvelle configuration")

        # 🔄 Mise à jour du handler global Influx
        influx_handler.reload_sensor_handler(self.config)
