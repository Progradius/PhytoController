# controller/api.py
# Author : Progradius (adapted)
# License: AGPL-3.0
"""
Mini-REST API HTTP (très simple GET) pour modifier certains paramètres à
la volée et fournir des données JSON aux pages web / à une appli externe.

‣ /temperature   → JSON températures (BME + 1-Wire)
‣ /hygrometry    → JSON hygrométrie
‣ /pressure      → JSON pression
‣ /status        → état global du contrôleur
‣ Configuration DailyTimer et CyclicTimer via requêtes GET
   (paramètres query-string)

Le module se contente de parser la *première ligne* de la requête reçue
(par le serveur HTTP) ; il n''implémente **ni** gestion POST
**ni** authentification - à compléter selon vos besoins.
"""

from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import parse_qs, urlparse

from controllers import parameter_handler
from controllers.SensorController import SensorController
from ui.pretty_console import info, warning, error


class API:
    """
    Chaque connexion HTTP instancie un objet **API** chargé de :
      ‣ parser l''URL reçue,
      ‣ éventuellement mettre à jour la configuration,
      ‣ retourner la réponse adéquate (HTML déjà construit par le serveur
        ou JSON généré ici).
    """

    # ------------------------------------------------------------------
    def __init__(self,
                 writer: asyncio.StreamWriter,
                 request_line: str,
                 controller_status,
                 parameters):
        self._writer           = writer
        self._request_line     = request_line      # ex : "GET /status HTTP/1.1"
        self._controller_state = controller_status
        self._params           = parameters
        self._sensors          = SensorController(parameters)

    # ------------------------------------------------------------------
    async def handle(self):
        """
        Route la requête et écrit la réponse HTTP sur `self._writer`.
        """
        try:
            method, raw_path, _ = self._request_line.split()
        except ValueError:
            await self._http_error(400, "Bad request")
            return

        if method != "GET":
            await self._http_error(405, "Method not allowed")
            return

        parsed = urlparse(raw_path)
        path   = parsed.path
        q      = parse_qs(parsed.query)

        # ─────── Config via query-string ──────────────────────
        if "dt1start" in q and "dt1stop" in q:
            self._configure_dailytimer(q)
        if "period" in q and "duration" in q:
            self._configure_cyclic(q)

        # ─────── End-points JSON ──────────────────────────────
        if path == "/temperature":
            await self._send_json(self._temperature_json())

        elif path == "/hygrometry":
            await self._send_json(self._hygrometry_json())

        elif path == "/pressure":
            await self._send_json(self._pressure_json())

        elif path == "/status":
            await self._send_json(self._system_state_json())

        else:                      # route inconnue → 404
            await self._http_error(404, "Not found")

    # ==================================================================
    #                         CONFIGURATION
    # ==================================================================
    def _configure_dailytimer(self, qdict):
        """Met à jour l''heure de début / fin du DailyTimer #1."""
        try:
            sh, sm = self._split_hhmm(qdict["dt1start"][0])
            eh, em = self._split_hhmm(qdict["dt1stop"][0])

            self._params.set_dailytimer1_start_hour(sh)
            self._params.set_dailytimer1_start_minute(sm)
            self._params.set_dailytimer1_stop_hour(eh)
            self._params.set_dailytimer1_stop_minute(em)

            parameter_handler.write_current_parameters_to_json(self._params)
            info(f"DailyTimer mis à jour : {sh:02d}:{sm:02d} → {eh:02d}:{em:02d}")
        except Exception as exc:
            warning(f"DailyTimer: format invalide ({exc})")

    # ------------------------------------------------------------------
    def _configure_cyclic(self, qdict):
        """Met à jour la période et la durée du CyclicTimer #1."""
        try:
            period   = int(qdict["period"][0])
            duration = int(qdict["duration"][0])

            self._params.set_cyclic1_period_minutes(period)
            self._params.set_cyclic1_action_duration_seconds(duration)
            parameter_handler.write_current_parameters_to_json(self._params)

            info(f"CyclicTimer mis à jour : période {period} min - action {duration} s")
        except Exception as exc:
            warning(f"CyclicTimer : paramètres invalides ({exc})")

    # ------------------------------------------------------------------
    @staticmethod
    def _split_hhmm(txt: str) -> tuple[int, int]:
        """
        Convertit 'hh:mm' (ou 'hh%3Amm') en tuple (h, m) ints - lève ValueError si fail.
        """
        txt = txt.replace("%3A", ":")
        m = re.fullmatch(r"(\d{1,2}):(\d{1,2})", txt)
        if not m:
            raise ValueError("HH:MM attendu")
        h, m_ = map(int, m.groups())
        if not (0 <= h < 24 and 0 <= m_ < 60):
            raise ValueError("plage horaire invalide")
        return h, m_

    # ==================================================================
    #                           JSON
    # ==================================================================
    def _temperature_json(self) -> dict:
        data = {}
        if self._sensors.bme:
            data["BME280"] = self._sensors.bme.get_bme_temp()
        if self._sensors.ds18:
            for idx in (1, 2, 3):
                data[f"DS18#{idx}"] = self._sensors.ds18.get_ds18_temp(idx)
        return data

    def _hygrometry_json(self) -> dict:
        return {"BME280H": self._sensors.bme.get_bme_hygro()} if self._sensors.bme else {}

    def _pressure_json(self) -> dict:
        return {"BME280P": self._sensors.bme.get_bme_pressure()} if self._sensors.bme else {}

    def _system_state_json(self) -> dict:
        st = self._controller_state
        return {
            "component_state": st.get_component_state(),
            "motor_speed":     st.get_motor_speed(),
            "dailytimer1": {
                "start": st.get_dailytimer_current_start_time(),
                "stop":  st.get_dailytimer_current_stop_time(),
            },
            "cyclic": {
                "period":   st.get_cyclic_period(),
                "duration": st.get_cyclic_duration(),
            }
        }

    # ==================================================================
    #                      OUTBOUND / HTTP helpers
    # ==================================================================
    async def _send_json(self, payload: dict | None):
        body = json.dumps(payload or {}).encode("utf-8")
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8")
        self._writer.write(headers + body)
        await self._writer.drain()

    # ------------------------------------------------------------------
    async def _http_error(self, code: int, msg: str):
        body = f"{code} {msg}".encode()
        hdr  = f"HTTP/1.1 {code} {msg}\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        self._writer.write(hdr + body)
        await self._writer.drain()
        error(f"API → {code} {msg}")
