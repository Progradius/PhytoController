# controller/web/server.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
# Serveur HTTP ultra-léger basé sur asyncio, utilisant AppConfig
# + PTY pour console ANSI → SSE avec historique & keep-alive
# -------------------------------------------------------------

from __future__ import annotations
import asyncio
import errno
import json
import os
import pty
import subprocess
import urllib.parse
from collections import deque

from ui.pretty_console            import success, warning, error, action, info
from network.web.pages            import (
    main_page,
    conf_page,
    monitor_page,
    console_page
)
from model.SensorStats            import SensorStats
from param.config                 import AppConfig
from controllers.SensorController import SensorController
from network.web                  import influx_handler

# Chemin vers votre script main.py
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MAIN_PY  = os.path.join(BASE_DIR, "main.py")


class Server:
    """ Routes :
        GET  /                 → System State
        GET,POST /conf         → Configuration
        GET  /monitor          → Monitored Values
        GET  /console          → Console (xterm.js + SSE)
        GET  /console/stream   → Flux SSE des logs ANSI (historique + live)
        GET  /status           → JSON status
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

        # pour lister les clients SSE
        self._console_queues: list[asyncio.Queue[str]] = []
        # pour stocker les dernières lignes (taille max configurable)
        self._console_history = deque(maxlen=1000)

    async def run(self) -> None:
        # démarre la tâche PTY → broadcast
        asyncio.create_task(self._spawn_pty_and_broadcast())
        # démarre le serveur HTTP
        srv = await asyncio.start_server(self._handle, self.host, self.port)
        success(f"HTTP prêt sur {self.host}:{self.port}")
        async with srv:
            await srv.serve_forever()

    async def _spawn_pty_and_broadcast(self) -> None:
        """Ouvre un PTY, lance main.py et diffuse chaque ligne ANSI."""
        master_fd, slave_fd = pty.openpty()
        proc = subprocess.Popen(
            ["python3", "-u", MAIN_PY],
            cwd=BASE_DIR,
            stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
            close_fds=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        os.close(slave_fd)

        loop   = asyncio.get_event_loop()
        reader = os.fdopen(master_fd, 'rb', buffering=0)
        buf    = b""
        try:
            while True:
                chunk = await loop.run_in_executor(None, reader.read, 1024)
                if not chunk:
                    break  # EOF
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    text = line.decode("utf-8", errors="ignore")
                    # on stocke dans l'historique
                    self._console_history.append(text)
                    # on broadcast à tous les clients
                    for q in list(self._console_queues):
                        await q.put(text)
        except OSError as e:
            if e.errno == errno.EIO:
                info("PTY EOF détecté, arrêt du broadcast console")
            else:
                error(f"PTY broadcast erreur inattendue: {e!r}")
        except Exception as e:
            error(f"PTY broadcast erreur: {e!r}")
        finally:
            reader.close()
            proc.terminate()
            proc.wait()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ) -> None:
        # --- Request line & headers ---
        line = await reader.readline()
        try:
            method, path, _ = line.decode("ascii").split()
        except ValueError:
            error("Requête malformée détectée"); writer.close(); return

        headers = {}
        while True:
            h = await reader.readline()
            if h in (b"\r\n", b"\n", b""): break
            k, v = h.decode("ascii").split(":",1)
            headers[k.lower().strip()] = v.strip()

        action(f"{method} {path}")

        # POST parsing
        posted = {}
        if method == "POST":
            l = int(headers.get("content-length","0"))
            raw = await reader.readexactly(l) if l else b""
            posted = urllib.parse.parse_qs(raw.decode(), keep_blank_values=True)

        # --- ROUTING ---
        if method=="GET" and path in ("/","/index.html"):
            body, ctype, status = (
                main_page(self.controller_status, self.sensor_handler, self.stats, self.config)
                    .encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK"
            )

        elif path=="/conf":
            if method=="POST":
                self._apply_conf_changes(posted)
            body,ctype,status = (
                conf_page(self.config).encode("utf-8"),
                "text/html; charset=utf-8","200 OK"
            )

        elif method=="GET" and path.startswith("/monitor"):
            # resets
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(path).query, keep_blank_values=True)
            for p in qs:
                if p.startswith("reset_"):
                    k = "DS18B#3" if p=="reset_DS18B3" else p.split("reset_",1)[1]
                    self.stats.clear_key(k)
                    val = self.sensor_handler.get_sensor_value(k)
                    if val is not None: self.stats.update(k,float(val))
                    success(f"Stat {k} réinitialisée")
            if qs.get("reboot",["0"])[0]=="1":
                info("Reboot via web"); os.system("sudo reboot")
            if qs.get("poweroff",["0"])[0]=="1":
                info("Poweroff via web"); os.system("sudo poweroff")

            body,ctype,status = (
                monitor_page(
                    self.sensor_handler,
                    self.stats,
                    self.config,
                    self.controller_status
                ).encode("utf-8"),
                "text/html; charset=utf-8","200 OK"
            )

        elif method=="GET" and path=="/console":
            body,ctype,status = (
                console_page().encode("utf-8"),
                "text/html; charset=utf-8","200 OK"
            )

        elif method=="GET" and path.startswith("/console/stream"):
            # SSE headers
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/event-stream\r\n"
                b"Cache-Control: no-cache\r\n"
                b"Connection: keep-alive\r\n\r\n"
            )
            await writer.drain()

            # nouveau client
            queue = asyncio.Queue()
            self._console_queues.append(queue)
            # on lui envoie en backlog tout l'historique
            for past in self._console_history:
                writer.write(f"data: {past}\n\n".encode("utf-8"))
            await writer.drain()

            try:
                while True:
                    try:
                        line = await asyncio.wait_for(queue.get(), timeout=15.0)
                        msg  = f"data: {line}\n\n"
                    except asyncio.TimeoutError:
                        # keep-alive comment
                        msg = ": keep-alive\n\n"
                    writer.write(msg.encode("utf-8"))
                    await writer.drain()
            except Exception as e:
                error(f"SSE console erreur: {e!r}")
            finally:
                self._console_queues.remove(queue)
                writer.close()
            return

        elif method=="GET" and path.startswith("/status"):
            cs = self.controller_status
            payload = {
                "component_state": cs.get_component_state(),
                "motor_speed"   : cs.get_motor_speed(),
                "dailytimer1"   : {
                    "start": cs.get_dailytimer_current_start_time(),
                    "stop" : cs.get_dailytimer_current_stop_time(),
                },
                "cyclic": {
                    "period"  : cs.get_cyclic_period(),
                    "duration": cs.get_cyclic_duration(),
                }
            }
            body,ctype,status = (
                json.dumps(payload).encode("utf-8"),
                "application/json","200 OK"
            )

        else:
            body,ctype,status = b"Not found","text/plain","404 Not Found"

        # réponse standard
        writer.write(
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
            .encode("utf-8") + body
        )
        await writer.drain()
        writer.close()

    def _apply_conf_changes(self, posted: dict[str, list[str]]) -> None:
        """ Mise à jour partielle de la config via POST (clé alias → champ). """
        if not posted:
            return

        alias2field = {
            fi.alias: name
            for name, fi in self.config.model_fields.items()
            if fi.alias
        }

        for alias, vals in posted.items():
            raw = vals[0]
            if "." in alias:
                top,nest = alias.split(".",1)
                if top not in alias2field:
                    warning(f"Ignoré alias «{top}»"); continue
                mdl = getattr(self.config, alias2field[top])
                fld = mdl.__class__.model_fields.get(nest)
                if not fld:
                    warning(f"Ignoré champ imbriqué «{nest}»"); continue
                ann = fld.annotation
                val = (
                    raw.lower() in ("1","true","enabled","yes") if ann is bool else
                    int(raw)   if ann is int   else
                    float(raw) if ann is float else
                    raw
                )
                setattr(mdl, nest, val)
                success(f"{alias} ← {raw}")
            else:
                if alias not in alias2field:
                    warning(f"Ignoré alias «{alias}»"); continue
                fldinfo = self.config.model_fields[alias2field[alias]]
                ann     = fldinfo.annotation
                val = (
                    raw.lower() in ("1","true","enabled","yes") if ann is bool else
                    int(raw)   if ann is int   else
                    float(raw) if ann is float else
                    raw
                )
                setattr(self.config, alias2field[alias], val)
                success(f"{alias} ← {raw}")

        # sauve + ré-init
        self.config.save(); info("Configuration sauvegardée")
        self.sensor_handler = SensorController(self.config)
        setattr(self.sensor_handler, "stats", self.stats)
        self.sensor_handler.sensor_dict = self.sensor_handler._build_sensor_dict()
        influx_handler.reload_sensor_handler(self.config)
        success("Nouvelle configuration appliquée")
