# network/web/server.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
# Serveur HTTP ultra-léger basé sur asyncio, utilisant AppConfig
# + console SSE alimentée par les logs du PROCESSUS COURANT
# -------------------------------------------------------------

from __future__ import annotations
import asyncio
import json
import os
import urllib.parse

from utils import pretty_console as ui
from utils.pretty_console import success, warning, error, debug, info
from utils.log_stream import console_stream
from network.web.pages import (
    main_page,
    conf_page,
    monitor_page,
    console_page,
)
from model.SensorStats import SensorStats
from param.config import AppConfig
from controllers.SensorController import SensorController
from network.web import influx_handler

LOGGER_NAME = "http"


def _sse(line: str) -> bytes:
    """Encode une ligne de log en évènement SSE (multi-ligne découpé)."""
    chunks = "".join(f"data: {part}\n" for part in str(line).splitlines() or [""])
    return (chunks + "\n").encode("utf-8")


class Server:
    """ Routes :
        GET  /                 → System State
        GET,POST /conf         → Configuration
        GET  /monitor          → Monitored Values (rendu seul, sans effet de bord)
        POST /monitor          → Actions : reset de stat, reboot, extinction
        GET  /console          → Console (xterm.js + SSE)
        GET  /console/stream   → Flux SSE des logs du processus (historique + live)
        GET  /status           → JSON status
    """

    def __init__(
        self,
        controller_status,
        sensor_handler,
        config: AppConfig,
        host: str = "0.0.0.0",
        port: int = 8123,
    ):
        self.controller_status = controller_status
        self.sensor_handler = sensor_handler
        self.config = config
        self.host = host
        self.port = port

        # Min/max stats
        self.stats = SensorStats()
        setattr(self.sensor_handler, "stats", self.stats)

        # Les logs diffusés à /console viennent du processus courant
        console_stream.install()

    async def run(self) -> None:
        """
        Démarre le serveur HTTP.
        On tolère le cas où le port est déjà pris (par un autre process).
        """
        try:
            srv = await asyncio.start_server(self._handle, self.host, self.port)
        except OSError as e:
            if e.errno == 98:
                error(
                    f"Impossible d'ouvrir le serveur HTTP sur {self.host}:{self.port} "
                    f"(déjà utilisé). Le reste du système continue.",
                    name=LOGGER_NAME,
                )
                return
            raise

        success(f"HTTP prêt sur {self.host}:{self.port}", name=LOGGER_NAME)
        async with srv:
            await srv.serve_forever()

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        # --- Request line & headers ---
        line = await reader.readline()
        if not line.strip():
            # Connexion ouverte puis abandonnée (pré-connexion navigateur) : non-évènement
            debug("Connexion fermée avant la requête", name=LOGGER_NAME)
            await self._close(writer)
            return
        try:
            method, path, _ = line.decode("ascii").split()
        except (ValueError, UnicodeDecodeError):
            warning(f"Requête malformée ignorée : {line[:60]!r}", name=LOGGER_NAME)
            await self._close(writer)
            return

        headers = {}
        while True:
            h = await reader.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            try:
                k, v = h.decode("ascii").split(":", 1)
            except (ValueError, UnicodeDecodeError):
                debug(f"En-tête HTTP ignoré (malformé) : {h[:60]!r}", name=LOGGER_NAME)
                continue
            headers[k.lower().strip()] = v.strip()

        # Les assets statiques ne méritent pas une ligne de log
        if not path.startswith("/static/"):
            debug(f"{method} {path}", name=LOGGER_NAME)

        # POST parsing
        posted = {}
        if method == "POST":
            try:
                length = int(headers.get("content-length", "0"))
            except ValueError:
                warning("Content-Length invalide → corps ignoré", name=LOGGER_NAME)
                length = 0
            try:
                raw = await reader.readexactly(length) if length else b""
            except asyncio.IncompleteReadError as e:
                warning(
                    f"Corps de requête tronqué ({len(e.partial)}/{length} octets)",
                    name=LOGGER_NAME,
                )
                await self._close(writer)
                return
            posted = urllib.parse.parse_qs(raw.decode(errors="replace"),
                                           keep_blank_values=True)

        # En-têtes de réponse supplémentaires (Location, Allow…)
        headers_out: list = []

        # --- ROUTING ---
        if method == "GET" and path in ("/", "/index.html"):
            body, ctype, status = (
                main_page(
                    self.controller_status,
                    self.sensor_handler,
                    self.stats,
                    self.config,
                ).encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK",
            )

        elif method == "GET" and path.startswith("/static/"):
            filepath = os.path.join(os.path.dirname(__file__), path.lstrip("/"))
            if os.path.isfile(filepath):
                with open(filepath, "rb") as f:
                    body = f.read()
                ext = os.path.splitext(filepath)[1]
                ctype = {
                    ".css": "text/css",
                    ".js": "application/javascript",
                    ".ttf": "font/ttf",
                    ".woff": "font/woff",
                    ".woff2": "font/woff2",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                }.get(ext, "application/octet-stream")
                status = "200 OK"
            else:
                debug(f"Asset statique introuvable : {path}", name=LOGGER_NAME)
                body = b"Not found"
                ctype = "text/plain"
                status = "404 Not Found"

        elif path == "/conf":
            if method == "POST":
                info("POST /conf → application de la configuration", name=LOGGER_NAME)
                self._apply_conf_changes(posted)
            body, ctype, status = (
                conf_page(self.config).encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK",
            )

        elif path.startswith("/monitor"):
            if method == "POST":
                if self._is_cross_origin(headers):
                    warning(
                        "POST /monitor refusé : origine "
                        f"{headers.get('origin')!r} ≠ hôte {headers.get('host')!r}",
                        name=LOGGER_NAME,
                    )
                    body, ctype, status = b"Forbidden", "text/plain", "403 Forbidden"
                else:
                    self._apply_monitor_actions(posted)
                    # Post/Redirect/Get : un F5 après un reset de stat ne
                    # rejoue pas l'action.
                    headers_out.append(("Location", "/monitor"))
                    body, ctype, status = b"", "text/plain", "303 See Other"

            elif method == "GET":
                # Rendu seul : plus AUCUN effet de bord en GET (audit C12).
                body, ctype, status = (
                    monitor_page(
                        self.sensor_handler,
                        self.stats,
                        self.config,
                        self.controller_status,
                    ).encode("utf-8"),
                    "text/html; charset=utf-8",
                    "200 OK",
                )
            else:
                headers_out.append(("Allow", "GET, POST"))
                body, ctype, status = (
                    b"Method not allowed", "text/plain", "405 Method Not Allowed",
                )

        elif method == "GET" and path == "/console":
            body, ctype, status = (
                console_page().encode("utf-8"),
                "text/html; charset=utf-8",
                "200 OK",
            )

        elif method == "GET" and path.startswith("/console/stream"):
            writer.write(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/event-stream\r\n"
                b"Cache-Control: no-cache\r\n"
                b"Connection: keep-alive\r\n\r\n"
            )
            await writer.drain()

            queue = console_stream.subscribe()
            try:
                # Historique rejoué : une ligne = un évènement SSE
                for past in list(console_stream.history):
                    writer.write(_sse(past))
                await writer.drain()

                while True:
                    try:
                        line = await asyncio.wait_for(queue.get(), timeout=15.0)
                        payload = _sse(line)
                    except asyncio.TimeoutError:
                        payload = b": keep-alive\n\n"
                    writer.write(payload)
                    await writer.drain()
            except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                debug("Client SSE déconnecté", name=LOGGER_NAME)
            except Exception as e:
                warning(f"Flux SSE console interrompu : {e.__class__.__name__} : {e}",
                        name=LOGGER_NAME)
            finally:
                console_stream.unsubscribe(queue)
                await self._close(writer)
            return

        elif method == "GET" and path.startswith("/status"):
            cs = self.controller_status
            payload = {
                "component_state": cs.get_component_state(),
                "motor_speed": cs.get_motor_speed(),
                "dailytimer1": {
                    "start": cs.get_dailytimer_current_start_time(),
                    "stop": cs.get_dailytimer_current_stop_time(),
                },
                "cyclic": {
                    "period": getattr(self.config.cyclic1, "period_days", 1),
                    "duration": self.config.cyclic1.action_duration_seconds,
                },
            }
            body, ctype, status = (
                json.dumps(payload).encode("utf-8"),
                "application/json",
                "200 OK",
            )

        else:
            debug(f"404 : {method} {path}", name=LOGGER_NAME)
            body, ctype, status = b"Not found", "text/plain", "404 Not Found"

        extra = "".join(f"{k}: {v}\r\n" for k, v in headers_out)
        writer.write(
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{extra}"
            "Connection: close\r\n\r\n".encode("utf-8")
            + body
        )
        try:
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError):
            debug("Client HTTP parti avant la fin de la réponse", name=LOGGER_NAME)
        await self._close(writer)

    @staticmethod
    async def _close(writer: asyncio.StreamWriter) -> None:
        """Fermeture propre : on attend réellement la fin de la connexion."""
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    @staticmethod
    def _is_cross_origin(headers: dict) -> bool:
        """
        Vrai si la requête vient manifestement d'une autre origine.

        Il n'y a pas d'authentification sur cette IHM (choix assumé : accès LAN
        uniquement). Le passage des actions destructrices en POST bloque déjà
        les déclenchements passifs — préchargement de navigateur, scanner de
        réseau, balise `<img src="http://pi:8123/monitor?reboot=1">`. Reste le
        formulaire POST hébergé sur un site tiers : les navigateurs envoient
        systématiquement `Origin` sur un POST, il suffit de le comparer à
        `Host`. Absence d'`Origin` = appel non navigateur (curl, script) : on
        laisse passer, l'IHM n'a pas vocation à être un pare-feu.
        """
        origin = headers.get("origin")
        if not origin:
            return False
        return urllib.parse.urlsplit(origin).netloc != headers.get("host", "")

    def _apply_monitor_actions(self, posted: dict) -> None:
        """Actions de la page /monitor — POST uniquement (audit C12)."""
        for p in posted:
            if p.startswith("reset_"):
                k = "DS18B#3" if p == "reset_DS18B3" else p.split("reset_", 1)[1]
                self.stats.clear_key(k)
                val = self.sensor_handler.get_sensor_value(k)
                if val is not None:
                    self.stats.update(k, float(val))
                info(f"Stat {k} réinitialisée", name=LOGGER_NAME)

        if posted.get("reboot", ["0"])[0] == "1":
            warning("Redémarrage demandé via l'interface web", name=LOGGER_NAME)
            rc = os.system("sudo reboot")
            if rc != 0:
                error(f"« sudo reboot » a échoué (code {rc})", name=LOGGER_NAME)

        if posted.get("poweroff", ["0"])[0] == "1":
            warning("Extinction demandée via l'interface web", name=LOGGER_NAME)
            rc = os.system("/sbin/shutdown -h now")
            if rc != 0:
                error(f"« shutdown -h now » a échoué (code {rc})", name=LOGGER_NAME)

    def _apply_conf_changes(self, posted: dict[str, list[str]]) -> None:
        """ Mise à jour partielle de la config via POST (clé alias → champ). """
        if not posted:
            return

        alias2field = {
            fi.alias: name
            for name, fi in self.config.model_fields.items()
            if fi.alias
        }
        changes: list[str] = []

        for alias, vals in posted.items():
            if alias.endswith("_switch"):
                continue

            raw = vals[0]

            if "." in alias:
                top, nest = alias.split(".", 1)

                if top not in alias2field:
                    warning(f"Ignoré alias «{top}»", name=LOGGER_NAME)
                    continue

                mdl = getattr(self.config, alias2field[top])

                fld = mdl.__class__.model_fields.get(nest)
                if fld:
                    ok, val = _coerce(raw, fld.annotation)
                    if not ok:
                        warning(f"Valeur invalide pour «{alias}» : {raw!r} → ignorée",
                                name=LOGGER_NAME)
                        continue
                    if getattr(mdl, nest) != val:
                        changes.append(f"{alias} ← {val}")
                    setattr(mdl, nest, val)
                    continue

                if (top.startswith("DailyTimer") or top.startswith("Cyclic")) and nest == "enabled":
                    val = raw.lower() in ("1", "true", "enabled", "yes")
                    if getattr(mdl, "enabled", None) != val:
                        changes.append(f"{alias} ← {val}")
                    setattr(mdl, "enabled", val)
                    continue

                warning(f"Ignoré champ imbriqué «{nest}» sur «{top}»", name=LOGGER_NAME)
                continue

            if alias not in alias2field:
                warning(f"Ignoré alias «{alias}»", name=LOGGER_NAME)
                continue

            field = alias2field[alias]
            fldinfo = self.config.model_fields[field]
            ok, val = _coerce(raw, fldinfo.annotation)
            if not ok:
                warning(f"Valeur invalide pour «{alias}» : {raw!r} → ignorée",
                        name=LOGGER_NAME)
                continue
            if getattr(self.config, field) != val:
                changes.append(f"{alias} ← {val}")
            setattr(self.config, field, val)

        # Le formulaire poste TOUS les champs : on ne journalise que les écarts
        if not changes:
            self.config.save()
            info("Configuration enregistrée sans changement de valeur", name=LOGGER_NAME)
        else:
            self.config.save()
            info(f"Configuration sauvegardée : {', '.join(changes)}", name=LOGGER_NAME)

        # Niveau / rétention de log applicables à chaud
        ui.apply_log_settings(self.config.logs.level, self.config.logs.retention_days)

        self.sensor_handler = SensorController(self.config)
        setattr(self.sensor_handler, "stats", self.stats)
        self.sensor_handler.sensor_dict = self.sensor_handler._build_sensor_dict()
        # Même instance pour l'export Influx : un seul /dev/i2c-1 ouvert
        influx_handler.reload_sensor_handler(self.config, self.sensor_handler)
        info("Nouvelle configuration appliquée", name=LOGGER_NAME)


def _coerce(raw: str, annotation):
    """
    Convertit une valeur POSTée selon l'annotation du champ.
    Retourne (ok, valeur) — jamais d'exception sur une saisie utilisateur.
    """
    try:
        if annotation is bool:
            return True, raw.lower() in ("1", "true", "enabled", "yes")
        if annotation is int:
            return True, int(raw)
        if annotation is float:
            return True, float(raw)
        return True, raw
    except (TypeError, ValueError):
        return False, None
