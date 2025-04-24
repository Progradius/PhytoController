# controller/api.py
# Author : Progradius
# License: AGPL-3.0
"""
Mini-REST API HTTP (GET only) pour exposer des données et modifier à la volée
certains paramètres via AppConfig (Pydantic + JSON centralisé).
"""

from __future__ import annotations
import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse

from param.config                 import AppConfig
from controllers.SensorController import SensorController
from ui.pretty_console            import info, warning, error


class API:
    """
    Chaque connexion HTTP instancie un objet API chargé de :
      • parser l’URL reçue,
      • mettre à jour AppConfig si besoin,
      • retourner JSON ou erreur HTTP.
    """

    def __init__(
        self,
        writer: asyncio.StreamWriter,
        request_line: str,
        controller_status,
        config: AppConfig
    ):
        self._writer           = writer
        self._request_line     = request_line      # ex : "GET /status HTTP/1.1"
        self._controller_state = controller_status
        self._config           = config
        # capteurs mettent à jour automatiquement les stats via injection
        self._sensors          = SensorController(config)

    async def handle(self):
        """Route la requête et écrit la réponse HTTP."""
        try:
            method, raw_path, _ = self._request_line.split()
        except ValueError:
            await self._http_error(400, "Bad Request")
            return

        if method != "GET":
            await self._http_error(405, "Method Not Allowed")
            return

        parsed = urlparse(raw_path)
        path   = parsed.path
        q      = parse_qs(parsed.query, keep_blank_values=True)

        # ─── Configuration via query-string ─────────────────────
        if "dt1start" in q and "dt1stop" in q:
            self._configure_dailytimer(q)
        if "period_days" in q and "action_duration_seconds" in q:
            self._configure_cyclic(q)

        # ─── Endpoints JSON ───────────────────────────────────
        if path == "/temperature":
            await self._send_json(self._temperature_json())

        elif path == "/hygrometry":
            await self._send_json(self._hygrometry_json())

        elif path == "/pressure":
            await self._send_json(self._pressure_json())

        elif path == "/status":
            await self._send_json(self._system_state_json())

        else:
            await self._http_error(404, "Not Found")

    # ──────────────────────────────────────────────────────────
    # CONFIGURATION
    # ──────────────────────────────────────────────────────────
    def _configure_dailytimer(self, q: dict[str, list[str]]):
        """Met à jour début/fin du DailyTimer #1 dans AppConfig puis sauve."""
        try:
            sh, sm = self._split_hhmm(q["dt1start"][0])
            eh, em = self._split_hhmm(q["dt1stop"][0])

            dt1 = self._config.daily_timer1
            dt1.start_hour   = sh
            dt1.start_minute = sm
            dt1.stop_hour    = eh
            dt1.stop_minute  = em

            self._config.save()
            info(f"DailyTimer mis à jour → {sh:02d}:{sm:02d}–{eh:02d}:{em:02d}")

        except Exception as exc:
            warning(f"DailyTimer: format invalide ({exc})")

    def _configure_cyclic(self, q: dict[str, list[str]]):
        """
        Met à jour le CyclicTimer #1 dans AppConfig puis sauve.
        Attend les paramètres :
          • period_days
          • action_duration_seconds
        """
        try:
            days = int(q["period_days"][0])
            dur  = int(q["action_duration_seconds"][0])

            c1 = self._config.cyclic1
            c1.period_days             = days
            c1.action_duration_seconds = dur

            self._config.save()
            info(f"CyclicTimer mis à jour → période {days} j, action {dur} s")

        except Exception as exc:
            warning(f"CyclicTimer: paramètres invalides ({exc})")

    @staticmethod
    def _split_hhmm(txt: str) -> tuple[int, int]:
        """
        Convertit 'hh:mm' ou 'hh%3Amm' en (h, m), lève ValueError sinon.
        """
        txt = txt.replace("%3A", ":")
        m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", txt)
        if not m:
            raise ValueError("HH:MM attendu")
        h, mn = map(int, m.groups())
        if not (0 <= h < 24 and 0 <= mn < 60):
            raise ValueError("plage horaire invalide")
        return h, mn

    # ──────────────────────────────────────────────────────────
    # GÉNÉRATION JSON
    # ──────────────────────────────────────────────────────────
    def _temperature_json(self) -> dict:
        data: dict[str, float] = {}
        if self._sensors.bme:
            data["BME280"] = self._sensors.bme.get_bme_temp()
        if self._sensors.ds18:
            for idx in (1, 2, 3):
                data[f"DS18B#{idx}"] = self._sensors.ds18.get_ds18_temp(idx)
        return data

    def _hygrometry_json(self) -> dict:
        return (
            {"BME280H": self._sensors.bme.get_bme_hygro()}
            if self._sensors.bme else {}
        )

    def _pressure_json(self) -> dict:
        return (
            {"BME280P": self._sensors.bme.get_bme_pressure()}
            if self._sensors.bme else {}
        )

    def _system_state_json(self) -> dict:
        """
        Expose l’état système, y compris les réglages du CyclicTimer refactoré.
        """
        st  = self._controller_state
        cfg = self._config.cyclic1

        # Base du payload pour le cyclic
        cyc: dict[str, int | str] = {
            "mode":                     cfg.mode,
            "period_days":              cfg.period_days,
            "action_duration_seconds":  cfg.action_duration_seconds,
        }
        # Si mode "séquentiel", on ajoute les temps on/off
        if cfg.mode == "séquentiel":
            cyc.update({
                "on_time_day":    cfg.on_time_day,
                "off_time_day":   cfg.off_time_day,
                "on_time_night":  cfg.on_time_night,
                "off_time_night": cfg.off_time_night,
            })

        return {
            "component_state": st.get_component_state(),
            "motor_speed"    : st.get_motor_speed(),
            "dailytimer1"    : {
                "start": st.get_dailytimer_current_start_time(),
                "stop" : st.get_dailytimer_current_stop_time(),
            },
            "cyclic1"        : cyc,
        }

    # ──────────────────────────────────────────────────────────
    # HTTP / JSON HELPERS
    # ──────────────────────────────────────────────────────────
    async def _send_json(self, payload: dict | None):
        body = json.dumps(payload or {}, indent=2).encode("utf-8")
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8")
        self._writer.write(headers + body)
        await self._writer.drain()

    async def _http_error(self, code: int, msg: str):
        body = f"{code} {msg}".encode("utf-8")
        headers = (
            f"HTTP/1.1 {code} {msg}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        ).encode("utf-8")
        self._writer.write(headers + body)
        await self._writer.drain()
        error(f"API → {code} {msg}")
