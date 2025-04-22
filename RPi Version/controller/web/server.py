# Author: Progradius (adapted)
# License: AGPL‑3.0
# -------------------------------------------------------------
#  Serveur HTTP ultra‑léger basé sur asyncio
# -------------------------------------------------------------

import asyncio, json, urllib.parse

from controller.web.pages import main_page, conf_page, monitor_page
from controller.parameter_handler import (
    write_current_parameters_to_json, update_one_parameter
)

# ── association paramètre GET  →  (section_json, clé_json) ───────────────
_CONF_FIELDS = {
    "dt1start" : ("DailyTimer1_Settings",  ("start_hour",  "start_minute")),  # HH:MM
    "dt1stop"  : ("DailyTimer1_Settings",  ("stop_hour",   "stop_minute")),
    "period"   : ("Cyclic1_Settings",      "period_minutes"),
    "duration" : ("Cyclic1_Settings",      "action_duration_seconds"),
    "stage"    : ("life_period",           "stage"),
    "speed"    : ("Motor_Settings",        "motor_user_speed"),
}

class Server:
    """
    Routes prises en charge :
      • GET /            → page d’accueil
      • GET /conf        → page configuration + prise en compte des champs GET
      • GET /monitor     → page monitoring (valeurs capteurs)
      • GET /status      → JSON de statut pour intégrations externes
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

    # ---------------------------------------------------------
    async def run(self) -> None:
        srv = await asyncio.start_server(self._handle, self.host, self.port)
        print(f"🌐 HTTP en écoute sur {self.host}:{self.port}")
        async with srv:
            await srv.serve_forever()

    # ---------------------------------------------------------
    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:

        # ─── 1) décode la ligne de requête ───────────────────
        req_line = await reader.readline()
        try:
            method, path, _ = req_line.decode("ascii").split()
        except ValueError:          # requête malformée
            writer.close()
            return

        # vide les headers restants
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break

        status, body, ctype = "404 Not Found", b"Not found", "text/plain"

        # ─── 2) ROUTING ──────────────────────────────────────
        if method != "GET":
            status, body = "405 Method Not Allowed", b"Method not allowed"

        else:
            # ----------- / & /index.html ---------------------
            if path in ("/", "/index.html"):
                body   = main_page(self.controller_status).encode("utf‑8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            # ----------- /conf (avec ou sans paramètres GET) -
            elif path.startswith("/conf"):
                self._apply_conf_changes(path)
                body   = conf_page(self.parameters).encode("utf‑8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            # ----------- /monitor ----------------------------
            elif path.startswith("/monitor"):
                body   = monitor_page(self.sensor_handler).encode("utf‑8")
                status = "200 OK"
                ctype  = "text/html; charset=utf-8"

            # ----------- /status  (JSON) ---------------------
            elif path.startswith("/status"):
                payload = {
                    "component_state": self.controller_status.get_component_state(),
                    "motor_speed":     self.controller_status.get_motor_speed(),
                    "dailytimer1": {
                        "start": self.controller_status.get_dailytimer_current_start_time(),
                        "stop":  self.controller_status.get_dailytimer_current_stop_time(),
                    },
                    "cyclic": {
                        "period":   self.controller_status.get_cyclic_period(),
                        "duration": self.controller_status.get_cyclic_duration(),
                    }
                }
                body   = json.dumps(payload).encode("utf‑8")
                status = "200 OK"
                ctype  = "application/json"

        # ─── 3) envoi de la réponse ──────────────────────────
        headers = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers.encode("utf‑8") + body)
        await writer.drain()
        writer.close()

    # ---------------------------------------------------------
    def _apply_conf_changes(self, raw_path: str) -> None:
        """
        Extrait la query‑string éventuelle de `raw_path` et applique les
        changements : instance `Parameter` **+** fichier JSON.
        """
        url_parts = urllib.parse.urlparse(raw_path)
        if not url_parts.query:
            return                                    # aucun champ transmis

        query = urllib.parse.parse_qs(url_parts.query, keep_blank_values=True)

        for key, values in query.items():
            if key not in _CONF_FIELDS:
                continue
            value = values[0]

            section, json_key = _CONF_FIELDS[key]

            # --- champs HH:MM ------------------------------------------
            if isinstance(json_key, tuple):
                try:
                    hh, mm = map(int, value.split(":"))
                except ValueError:
                    print(f"⛔ Format invalide pour {key}: {value}")
                    continue

                k_h, k_m = json_key
                update_one_parameter(section, k_h, hh)
                update_one_parameter(section, k_m, mm)

                # setters in‑memory
                if key == "dt1start":
                    self.parameters.set_dailytimer1_start_hour(hh)
                    self.parameters.set_dailytimer1_start_minute(mm)
                elif key == "dt1stop":
                    self.parameters.set_dailytimer1_stop_hour(hh)
                    self.parameters.set_dailytimer1_stop_minute(mm)

            # --- champs simples ----------------------------------------
            else:
                update_one_parameter(section, json_key, value)

                setter_name = f"set_{json_key}"
                if hasattr(self.parameters, setter_name):
                    getattr(self.parameters, setter_name)(value)

        # ré‑écrit l’ensemble du JSON pour cohérence
        write_current_parameters_to_json(self.parameters)
