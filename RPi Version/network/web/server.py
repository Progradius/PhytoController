# controller/web/server.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra-léger basé sur asyncio, utilisant AppConfig
# -------------------------------------------------------------

from __future__ import annotations
import asyncio, json, urllib.parse

from ui.pretty_console import success, warning, error, action, info
from network.web.pages import main_page, conf_page, monitor_page
from model.SensorStats  import SensorStats
from param.config       import AppConfig
from controllers.SensorController import SensorController
from network.web        import influx_handler

class Server:
    """ Routes : GET /  |  GET/POST /conf  |  GET /monitor  |  GET /status """

    def __init__(self, controller_status, sensor_handler, config: AppConfig,
                 host: str = "0.0.0.0", port: int = 8123):
        self.controller_status = controller_status
        self.sensor_handler    = sensor_handler
        self.config            = config
        self.host, self.port   = host, port
        self.stats = SensorStats()
        setattr(self.sensor_handler, "stats", self.stats)

    # ---------------------------------------------------------
    async def run(self):
        srv = await asyncio.start_server(self._handle, self.host, self.port)
        success(f"HTTP prêt sur {self.host}:{self.port}")
        async with srv: await srv.serve_forever()

    # ---------------------------------------------------------
    async def _handle(self, rd: asyncio.StreamReader, wr: asyncio.StreamWriter):
        # ------- ligne de requête -------
        req_line = await rd.readline()
        try:  method, path, _ = req_line.decode("ascii").split()
        except ValueError:
            error("Requête malformée"); wr.close(); return

        # ------- entêtes -------
        headers = {}
        while True:
            line = await rd.readline()
            if line in (b"\r\n", b"\n", b""): break
            k, v = line.decode("ascii").split(":", 1)
            headers[k.lower().strip()] = v.strip()

        action(f"{method} {path}")

        # ------- body si POST -------
        posted = {}
        if method == "POST":
            length = int(headers.get("content-length", "0"))
            raw = await rd.readexactly(length) if length else b""
            posted = urllib.parse.parse_qs(raw.decode(), keep_blank_values=True)

        # ------- routing -------
        if method == "GET" and path in ("/", "/index.html"):
            body, ctype, status = main_page(self.controller_status).encode(), "text/html; charset=utf-8", "200 OK"

        elif path == "/conf":
            if method == "POST":
                self._apply_conf_changes(posted)
            body, ctype, status = conf_page(self.config).encode(), "text/html; charset=utf-8", "200 OK"

        elif method == "GET" and path.startswith("/monitor"):
            body = monitor_page(self.sensor_handler, self.stats,
                                self.config, self.controller_status).encode()
            ctype, status = "text/html; charset=utf-8", "200 OK"

        elif method == "GET" and path.startswith("/status"):
            payload = {
                "component_state": self.controller_status.get_component_state(),
                "motor_speed":      self.controller_status.get_motor_speed(),
                "dailytimer1": {
                    "start": self.controller_status.get_dailytimer_current_start_time(),
                    "stop":  self.controller_status.get_dailytimer_current_stop_time()},
                "cyclic": {
                    "period":  self.controller_status.get_cyclic_period(),
                    "duration": self.controller_status.get_cyclic_duration()}
            }
            body, ctype, status = json.dumps(payload).encode(), "application/json", "200 OK"

        else:
            body, ctype, status = b"Not found", "text/plain", "404 Not Found"

        # ------- réponse -------
        wr.write(
            f"HTTP/1.1 {status}\r\nContent-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await wr.drain(); wr.close()

    # ---------------------------------------------------------
    #  Mise à jour partielle de la configuration
    # ---------------------------------------------------------
    def _apply_conf_changes(self, posted: dict[str, list[str]]):
        if not posted: return

        alias2field = {fi.alias: name for name, fi in self.config.model_fields.items()}

        for alias, values in posted.items():
            raw_val = values[0]

            # ---- champ imbriqué ----
            if "." in alias:
                top_alias, nested_key = alias.split(".", 1)
                if top_alias not in alias2field: continue
                model_name  = alias2field[top_alias]
                nested_model= getattr(self.config, model_name)
                fld_info    = nested_model.__class__.model_fields.get(nested_key)
                if not fld_info: continue

                ann = fld_info.annotation
                val = (raw_val.lower() in ("1","true","enabled","yes") if ann is bool
                       else int(raw_val)   if ann is int
                       else float(raw_val) if ann is float
                       else raw_val)
                setattr(nested_model, nested_key, val)
                success(f"{alias} ← {raw_val}")

            # ---- champ top-level ----
            else:
                if alias not in alias2field: continue
                field_name = alias2field[alias]
                ann = self.config.model_fields[field_name].annotation
                val = (raw_val.lower() in ("1","true","enabled","yes") if ann is bool
                       else int(raw_val)   if ann is int
                       else float(raw_val) if ann is float
                       else raw_val)
                setattr(self.config, field_name, val)
                success(f"{alias} ← {raw_val}")

        # Sauvegarde & re-initialisations
        self.config.save(); info("Configuration sauvegardée")
        self.sensor_handler = SensorController(self.config)
        setattr(self.sensor_handler, "stats", self.stats)
        self.sensor_handler.sensor_dict = self.sensor_handler._build_sensor_dict()
        influx_handler.reload_sensor_handler(self.config)
