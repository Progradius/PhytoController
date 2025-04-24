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
import os
import signal
import sys

from ui.pretty_console         import success, warning, error, action, info
from network.web.pages         import main_page, conf_page, monitor_page
from model.SensorStats         import SensorStats
from param.config              import AppConfig
from controllers.SensorController import SensorController
from network.web               import influx_handler


class Server:
    """ Routes : GET / | GET,POST /conf | GET /monitor | GET /status """

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
        # --- Request line ---
        req_line = await reader.readline()
        try:
            method, path, _ = req_line.decode("ascii").split()
        except ValueError:
            error("Requête malformée détectée")
            writer.close(); return

        # --- Headers ---
        headers: dict[str,str] = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            key, val = line.decode("ascii").split(":",1)
            headers[key.lower().strip()] = val.strip()

        action(f"{method} {path}")

        # --- POST body parsing ---
        posted: dict[str,list[str]] = {}
        if method == "POST":
            length = int(headers.get("content-length", "0"))
            raw = await reader.readexactly(length) if length else b""
            posted = urllib.parse.parse_qs(raw.decode(), keep_blank_values=True)

        # --- Routing ---
        if method == "GET" and path in ("/", "/index.html"):
            body, ctype, status = (
                main_page(self.controller_status).encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK"
            )

        elif path == "/conf":
            if method == "POST":
                self._apply_conf_changes(posted)
            body, ctype, status = (
                conf_page(self.config).encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK"
            )

        elif method == "GET" and path.startswith("/monitor"):
            # parse query-string
            parts = urllib.parse.urlparse(path)
            query = urllib.parse.parse_qs(parts.query, keep_blank_values=True)

            # resets
            for param in query:
                if param.startswith("reset_"):
                    sensor_key = "DS18B#3" if param == "reset_DS18B3" else param.split("reset_",1)[1]
                    self.stats.clear_key(sensor_key)
                    val = self.sensor_handler.get_sensor_value(sensor_key)
                    if val is not None:
                        self.stats.update(sensor_key, float(val))
                    success(f"Statistique {sensor_key} réinitialisée")

            # reboot?
            if query.get("reboot", ["0"])[0] == "1":
                info("Reboot demandé via l’interface web")
                # envoi d’un SIGTERM pour que les handlers aient le temps de fermer proprement
                os.system("sudo reboot")

            # shutdown?
            if query.get("poweroff", ["0"])[0] == "1":
                info("Extinction demandée via l’interface web")
                os.system("sudo poweroff")

            body, ctype, status = (
                monitor_page(
                    self.sensor_handler,
                    self.stats,
                    self.config,
                    self.controller_status
                ).encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK"
            )

        elif method == "GET" and path.startswith("/status"):
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

        else:
            body, ctype, status = b"Not found", "text/plain", "404 Not Found"

        # --- Response ---
        writer.write(
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
            .encode("utf-8") + body
        )
        await writer.drain()
        writer.close()

    # ---------------------------------------------------------
    #  Mise à jour partielle de la configuration via POST
    # ---------------------------------------------------------
    def _apply_conf_changes(self, posted: dict[str, list[str]]) -> None:
        if not posted:
            return

        alias2field = {
            fi.alias: name
            for name, fi in self.config.model_fields.items()
            if fi.alias
        }

        for alias, values in posted.items():
            raw_val = values[0]

            # imbriqué
            if "." in alias:
                top_alias, nested_key = alias.split(".", 1)
                if top_alias not in alias2field:
                    warning(f"Ignoré : alias inconnu «{top_alias}»")
                    continue
                model_name   = alias2field[top_alias]
                nested_model = getattr(self.config, model_name)
                fld_info     = nested_model.__class__.model_fields.get(nested_key)
                if not fld_info:
                    warning(f"Ignoré : champ imbriqué inconnu «{nested_key}»")
                    continue
                ann = fld_info.annotation
                if ann is bool:
                    val = raw_val.lower() in ("1","true","enabled","yes")
                elif ann is int:
                    val = int(raw_val)
                elif ann is float:
                    val = float(raw_val)
                else:
                    val = raw_val
                setattr(nested_model, nested_key, val)
                success(f"{alias} ← {raw_val}")

            # top-level
            else:
                if alias not in alias2field:
                    warning(f"Ignoré : alias inconnu «{alias}»")
                    continue
                field_name = alias2field[alias]
                fld_info   = self.config.model_fields[field_name]
                ann        = fld_info.annotation
                if ann is bool:
                    val = raw_val.lower() in ("1","true","enabled","yes")
                elif ann is int:
                    val = int(raw_val)
                elif ann is float:
                    val = float(raw_val)
                else:
                    val = raw_val
                setattr(self.config, field_name, val)
                success(f"{alias} ← {raw_val}")

        # sauvegarde et ré-inits
        self.config.save()
        info("Configuration sauvegardée")

        self.sensor_handler = SensorController(self.config)
        setattr(self.sensor_handler, "stats", self.stats)
        self.sensor_handler.sensor_dict = getattr(self.sensor_handler, "_build_sensor_dict")()
        influx_handler.reload_sensor_handler(self.config)
        success("Nouvelle configuration appliquée")
