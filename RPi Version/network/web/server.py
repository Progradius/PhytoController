"""Serveur HTTP aiohttp de l'interface locale PhytoController."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
import socket
import ssl
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from pydantic import ValidationError

from components.climate_control import get_climate_alarm, get_climate_snapshot
from controllers.sensor_catalog import SENSOR_CATALOG, SENSORS_BY_KEY
from network.web import influx_handler
from network.web.pages import (
    ASSET_VERSIONS,
    PWA_CACHE_VERSION,
    alarms_page,
    conf_page,
    console_page,
    error_page,
    main_page,
    offline_page,
)
from param.config_store import shared_config
from param.equipment_metadata import (
    EQUIPMENT_IDS, EquipmentMetadata, EquipmentMetadataStore,
)
from utils import pretty_console as ui
from utils.csrf import load_or_create_token
from utils.deployment_info import DEPLOYED_VERSION
from utils.log_stream import console_stream
from utils.pretty_console import debug, error, info, success, warning
from utils.operational_state import snapshot as operational_snapshot
from utils.schedule import day_night_times
from utils.time_reliability import time_reliability


LOGGER_NAME = "http"
WEB_DIR = Path(__file__).parent
STATIC_DIR = WEB_DIR / "static"
MAX_BODY_SIZE = 64 * 1024

HTTP_ERROR_TITLES = {
    400: "Requête invalide",
    403: "Action refusée",
    404: "Page introuvable",
    405: "Méthode non autorisée",
    413: "Requête trop volumineuse",
    421: "Hôte non autorisé",
    422: "Valeurs refusées",
    429: "Trop de requêtes",
    500: "Erreur interne",
    503: "Service indisponible",
}

SENSITIVE_FIELDS = {
    "wifi_password",
    "influx_db_user",
    "influx_db_password",
}

SECTION_FIELDS: dict[str, dict[str, tuple[str, str] | str]] = {
    "life": {"stage": ("Life_Period", "stage")},
    "daily-timer-1": {
        "enabled": ("DailyTimer1_Settings", "enabled"),
        "start_time": "daily_start",
        "stop_time": "daily_stop",
    },
    "daily-timer-2": {
        "enabled": ("DailyTimer2_Settings", "enabled"),
        "start_time": "daily_start",
        "stop_time": "daily_stop",
    },
    "day-night": {
        "source": ("Day_Night_Settings", "source"),
        "start_time": "day_night_start",
        "stop_time": "day_night_stop",
    },
    "cyclic-1": {
        name: ("Cyclic1_Settings", name)
        for name in (
            "enabled", "mode", "period_days", "triggers_per_day",
            "first_trigger_hour", "action_duration_seconds", "on_time_day",
            "off_time_day", "on_time_night", "off_time_night",
        )
    },
    "cyclic-2": {
        name: ("Cyclic2_Settings", name)
        for name in (
            "enabled", "mode", "period_days", "triggers_per_day",
            "first_trigger_hour", "action_duration_seconds", "on_time_day",
            "off_time_day", "on_time_night", "off_time_night",
        )
    },
    "temperature": {
        name: ("Temperature_Settings", name)
        for name in (
            "target_temp_min_day", "target_temp_max_day",
            "target_temp_min_night", "target_temp_max_night", "hysteresis_offset",
            "vent_deadband", "vent_step", "vent_release", "absolute_floor_temp",
            "min_dwell_seconds",
        )
    },
    "heater": {"enabled": ("Heater_Settings", "enabled")},
    "motor": {
        name: ("Motor_Settings", name)
        for name in (
            "motor_mode", "motor_user_speed", "min_speed", "max_speed",
            "sensor_fallback_speed",
            "winter_default_speed", "winter_temp_margin", "winter_refresh_speed",
            "winter_refresh_minutes_per_hour", "winter_humidity_threshold",
            "winter_humidity_minutes_per_hour",
        )
    },
    "sensors": {},
    "sensor-quality": {},
    "wifi": {
        "wifi_ssid": ("Network_Settings", "wifi_ssid"),
        "wifi_password": ("Network_Settings", "wifi_password"),
    },
    "influx": {
        name: ("Network_Settings", name)
        for name in (
            "host_machine_state", "host_machine_address", "influx_db_port",
            "influx_db_name", "influx_db_user", "influx_db_password",
        )
    },
    "logs": {
        "level": ("Log_Settings", "level"),
        "retention_days": ("Log_Settings", "retention_days"),
    },
    "equipment": {
        f"{equipment_id}__{field}": "equipment_metadata"
        for equipment_id in EQUIPMENT_IDS
        for field in (
            "display_name", "usage_type", "zone", "icon", "wiring_note",
            "dashboard_visible", "out_of_service",
        )
    },
}

for _sensor_field in (
    "bme280_state", "ds18b20_state", "veml6075_state", "vl53L0x_state",
    "mlx90614_state", "tsl2591_state", "hcsr04_state",
):
    SECTION_FIELDS["sensors"][_sensor_field] = ("Sensor_State", _sensor_field)

RELOAD_JOBS = {
    "daily-timer-1": ("daily_timer_1",),
    "daily-timer-2": ("daily_timer_2",),
    "cyclic-1": ("cyclic_timer_1",),
    "cyclic-2": ("cyclic_timer_2",),
    "temperature": ("climate_control",),
    "heater": ("climate_control",),
    "motor": ("climate_control",),
    "day-night": ("cyclic_timer_1", "cyclic_timer_2", "climate_control"),
    "sensors": ("climate_control",),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _host_without_port(authority: str) -> str:
    authority = authority.strip()
    if authority.startswith("["):
        end = authority.find("]")
        return authority[1:end].lower() if end > 0 else ""
    if authority.count(":") == 1:
        return authority.rsplit(":", 1)[0].lower()
    return authority.lower()


class Server:
    def __init__(
        self,
        controller_status,
        sensor_handler,
        config,
        host: str = "0.0.0.0",
        port: int = 8123,
        supervisor=None,
        dailytimer1=None,
        dailytimer2=None,
        cyclic_timer1=None,
        cyclic_timer2=None,
        heater_component=None,
        operator_service=None,
        equipment_store=None,
    ):
        self.controller_status = controller_status
        self.sensor_handler = sensor_handler
        self.config_store = shared_config()
        # Même instance que celle du magasin : elle est mutée en place, jamais
        # remplacée, donc cette référence reste à jour indéfiniment.
        self.config = config
        self.host = host
        self.port = port
        self.supervisor = supervisor
        self.dailytimer1 = dailytimer1
        self.dailytimer2 = dailytimer2
        self.cyclic_timer1 = cyclic_timer1
        self.cyclic_timer2 = cyclic_timer2
        self.heater_component = heater_component
        self.operator_service = operator_service
        self.stats = sensor_handler.stats
        self.equipment_store = equipment_store or EquipmentMetadataStore()
        # Jeton persistant : un redémarrage du service ne doit pas invalider
        # les pages laissées ouvertes (voir utils/csrf.py).
        self.csrf_token = load_or_create_token()
        self._runner: web.AppRunner | None = None
        self._history_query_running = False
        self._allowed_names = self._build_allowed_names()
        self._https_port, self._https_config_error = self._load_https_port()
        self._tls_cert_file = os.getenv("PHYTO_TLS_CERT_FILE", "").strip()
        self._tls_key_file = os.getenv("PHYTO_TLS_KEY_FILE", "").strip()
        self._https_configured = bool(
            self._https_port
            or self._https_config_error
            or self._tls_cert_file
            or self._tls_key_file
        )
        self._https_ready = False
        console_stream.install()

    @staticmethod
    def _load_https_port() -> tuple[int, str | None]:
        raw = os.getenv("PHYTO_HTTPS_PORT", "0").strip()
        try:
            port = int(raw)
        except ValueError:
            return 0, "port HTTPS invalide"
        if not 0 <= port <= 65535:
            return 0, "port HTTPS hors limites"
        return port, None

    def _build_allowed_names(self) -> set[str]:
        hostname = socket.gethostname().lower()
        allowed = {"localhost", hostname, f"{hostname}.local"}
        allowed.update(
            item.strip().lower()
            for item in os.getenv("PHYTO_ALLOWED_HOSTS", "").split(",")
            if item.strip()
        )
        return allowed

    def create_app(self) -> web.Application:
        app = web.Application(
            client_max_size=MAX_BODY_SIZE,
            middlewares=[self._security_middleware, self._host_middleware, self._csrf_middleware],
            handler_args={"max_line_size": 8190, "max_field_size": 8190},
        )
        app.add_routes([
            web.get("/", self._dashboard),
            web.get("/index.html", self._dashboard),
            web.get("/monitor", self._monitor_redirect),
            web.post("/monitor", self._legacy_monitor_action),
            web.get("/conf", self._configuration),
            web.post("/conf/{section}", self._configuration_post),
            web.get("/console", self._console),
            web.get("/console/stream", self._console_stream),
            web.get("/alarms", self._alarms),
            web.get("/api/v1/state", self._api_state),
            web.get("/api/v1/alarms", self._api_alarms),
            web.get("/api/v1/alarms/active", self._api_active_alarms),
            web.get("/api/v1/history", self._api_history),
            web.post("/actions/alarms/ack", self._acknowledge_alarm),
            web.post("/actions/stats/reset", self._reset_stats),
            web.post("/actions/sensors/reset-quality", self._reset_sensor_quality),
            web.post("/actions/system/reboot", self._reboot),
            web.post("/actions/system/poweroff", self._poweroff),
            web.get("/status", self._legacy_status),
            web.get("/health/live", self._health_live),
            web.get("/health/ready", self._health_ready),
            web.get("/favicon.ico", self._favicon_redirect),
            web.get("/favicon.svg", self._favicon),
            web.get("/app.webmanifest", self._manifest),
            web.get("/service-worker.js", self._service_worker),
            web.get("/offline", self._offline),
            web.get("/static/css/style.css", self._style),
            web.get("/static/js/pwa.js", self._pwa_js),
            web.get("/static/js/dashboard.js", self._dashboard_js),
            web.get("/static/js/config.js", self._config_js),
            web.get("/static/js/console.js", self._console_js),
            web.get("/static/js/alarms.js", self._alarms_js),
            web.get("/static/js/history.js", self._history_js),
            web.get("/static/fonts/visitor1.ttf", self._font),
            web.get("/static/equipment-icons.svg", self._equipment_icons),
            web.get("/static/icons/pwa-192.png", self._pwa_icon_192),
            web.get("/static/icons/pwa-512.png", self._pwa_icon_512),
            web.get("/static/icons/pwa-maskable-512.png", self._pwa_icon_maskable),
        ])
        return app

    async def run(self) -> None:
        self._https_ready = False
        app = self.create_app()
        self._runner = web.AppRunner(app, access_log=None, shutdown_timeout=5.0)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port, backlog=64)
        try:
            await site.start()
        except OSError as exc:
            await self._runner.cleanup()
            self._runner = None
            if exc.errno == 98:
                error(
                    f"Impossible d'ouvrir le serveur HTTP sur {self.host}:{self.port} "
                    "(déjà utilisé).",
                    name=LOGGER_NAME,
                )
                return
            raise
        success(f"HTTP aiohttp prêt sur {self.host}:{self.port}", name=LOGGER_NAME)
        await self._start_https()
        try:
            await asyncio.Event().wait()
        finally:
            if self._runner is not None:
                await self._runner.cleanup()
                self._runner = None

    async def _start_https(self) -> None:
        if not self._https_configured:
            debug("HTTPS PWA désactivé", name=LOGGER_NAME)
            return
        if self._https_config_error:
            error(f"HTTPS PWA indisponible : {self._https_config_error}", name=LOGGER_NAME)
            return
        if not self._https_port or not self._tls_cert_file or not self._tls_key_file:
            error(
                "HTTPS PWA indisponible : port, certificat et clé doivent être configurés ensemble",
                name=LOGGER_NAME,
            )
            return
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(self._tls_cert_file, self._tls_key_file)
            site = web.TCPSite(
                self._runner,
                self.host,
                self._https_port,
                backlog=64,
                ssl_context=context,
            )
            await site.start()
        except (OSError, ssl.SSLError, ValueError) as exc:
            error(
                f"HTTPS PWA indisponible ({exc.__class__.__name__}) ; HTTP reste actif",
                name=LOGGER_NAME,
            )
            return
        self._https_ready = True
        success(f"HTTPS PWA prêt sur {self.host}:{self._https_port}", name=LOGGER_NAME)

    @web.middleware
    async def _security_middleware(self, request: web.Request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = self._error_response(request, exc)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # `same-origin` et non `no-referrer` : Firefox applique la referrer
        # policy à l'en-tête `Origin` des POST de formulaire, y compris
        # same-origin. Avec `no-referrer` il envoie `Origin: null`, que le
        # contrôle d'origine du middleware CSRF refuse — tout POST devenait un
        # 403 sur ce navigateur. `same-origin` ne fuite toujours aucun referrer
        # vers l'extérieur (et l'UI n'a aucun lien sortant).
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
            "worker-src 'self'; manifest-src 'self'; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )
        response.headers.setdefault("Cache-Control", "no-store")
        if request.path.startswith("/static/") or response.content_type == "application/json":
            response.enable_compression()
        return response

    @web.middleware
    async def _host_middleware(self, request: web.Request, handler):
        raw_host = request.headers.get("Host", "")
        host = _host_without_port(raw_host)
        allowed = host in self._allowed_names
        if not allowed:
            try:
                address = ipaddress.ip_address(host)
                allowed = address.is_private or address.is_loopback or address.is_link_local
            except ValueError:
                allowed = False
        if not allowed:
            warning(f"Host HTTP refusé : {raw_host!r}", name=LOGGER_NAME)
            raise web.HTTPMisdirectedRequest(text="Hôte non autorisé")
        return await handler(request)

    @web.middleware
    async def _csrf_middleware(self, request: web.Request, handler):
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await handler(request)
        form = await request.post()
        request["form_data"] = form
        supplied = request.headers.get("X-CSRF-Token") or form.get("csrf_token", "")
        if not hmac.compare_digest(str(supplied), self.csrf_token):
            warning(f"CSRF refusé sur {request.path}", name=LOGGER_NAME)
            raise web.HTTPForbidden(text="Jeton de formulaire invalide")
        origin = request.headers.get("Origin")
        if origin:
            # Le refus doit être diagnostiquable : sans les deux valeurs, le log
            # ne dit pas si c'est un `Origin: null` (iframe/webview) ou une
            # adresse d'accès différente du `Host` reçu.
            received = urllib.parse.urlsplit(origin).netloc.lower()
            expected = request.host.lower()
            if received != expected:
                warning(
                    f"Origine refusée sur {request.path} : "
                    f"Origin={origin!r} (netloc {received!r}) ≠ Host attendu {expected!r}",
                    name=LOGGER_NAME,
                )
                raise web.HTTPForbidden(text="Origine non autorisée")
        return await handler(request)

    @staticmethod
    def _error_response(request: web.Request, exc: web.HTTPException) -> web.Response:
        """Rend les erreurs en HTML pour un navigateur, en texte pour le reste.

        Les redirections (3xx) sont aussi des `HTTPException` : elles doivent
        traverser sans être transformées en page d'erreur.
        """
        if exc.status < 400 or "text/html" not in request.headers.get("Accept", ""):
            return exc
        title = HTTP_ERROR_TITLES.get(exc.status, "Requête refusée")
        response = web.Response(
            text=error_page(exc.status, title, exc.text or title),
            status=exc.status,
            content_type="text/html",
            charset="utf-8",
        )
        # `Allow` porte l'information utile d'un 405 : la recopier explicitement
        # plutôt que l'ensemble des en-têtes (Content-Type/Length de l'exception).
        if "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response

    @staticmethod
    def _html(body: str, status: int = 200) -> web.Response:
        return web.Response(text=body, status=status, content_type="text/html", charset="utf-8")

    async def _dashboard(self, request: web.Request) -> web.Response:
        return self._html(main_page(self._state_payload(), self.csrf_token))

    def _operator_snapshot(self) -> dict:
        if self.operator_service is None:
            return {
                "alarms": {"active_count": 0, "unacknowledged_count": 0,
                           "critical_count": 0, "control_count": 0,
                           "auxiliary_count": 0, "highest_severity": None},
                "history": {"available": False},
                "network": {"status": "unknown"},
            }
        return self.operator_service.snapshot()

    async def _monitor_redirect(self, request: web.Request) -> web.Response:
        raise web.HTTPSeeOther(location="/#surveillance")

    async def _configuration(self, request: web.Request) -> web.Response:
        success_section = request.query.get("success")
        if success_section not in SECTION_FIELDS:
            success_section = None
        return self._html(conf_page(
            self.config,
            self.csrf_token,
            alarm_summary=self._operator_snapshot()["alarms"],
            equipment=self.equipment_store.current,
            success=success_section,
            active_section=success_section,
            sensor_snapshot=self.sensor_handler.snapshot(),
            discovered_ds18=getattr(self.sensor_handler, "discovered_ds18_ids", lambda: [])(),
        ))

    async def _configuration_post(self, request: web.Request) -> web.Response:
        section = request.match_info["section"]
        if section not in SECTION_FIELDS:
            raise web.HTTPNotFound(text="Section inconnue")
        form = request["form_data"]
        if section == "sensor-quality":
            return await self._sensor_quality_configuration_post(form)
        errors = self._validate_form_shape(section, form)
        if errors:
            return self._html(conf_page(
                self.config, self.csrf_token, equipment=self.equipment_store.current,
                alarm_summary=self._operator_snapshot()["alarms"],
                errors=errors, active_section=section,
            ), status=422)

        if section == "equipment":
            return await self._equipment_configuration_post(form)

        payload = self.config.model_dump(by_alias=True)
        changed_fields: list[str] = []
        try:
            self._apply_section_to_payload(section, form, payload, changed_fields)
            candidate = self.config.__class__.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            errors = self._format_validation_errors(exc)
            return self._html(conf_page(
                self.config, self.csrf_token, equipment=self.equipment_store.current,
                alarm_summary=self._operator_snapshot()["alarms"],
                errors=errors, active_section=section,
            ), status=422)

        try:
            # Le magasin revalide, sauvegarde l'ancien contenu en `.bak`, écrit
            # atomiquement puis adopte la candidate dans l'instance partagée —
            # celle que tient déjà `self.config` (audit C5, M4).
            self.config_store.save(candidate)
        except OSError:
            return self._html(conf_page(
                self.config,
                self.csrf_token,
                alarm_summary=self._operator_snapshot()["alarms"],
                equipment=self.equipment_store.current,
                errors={"__all__": "Écriture impossible : la configuration active est inchangée."},
                active_section=section,
            ), status=500)
        await self._apply_runtime_changes(section)
        if changed_fields:
            safe_names = [f"{name} modifié" if name in SENSITIVE_FIELDS else name for name in changed_fields]
            info(f"Configuration « {section} » sauvegardée : {', '.join(safe_names)}", name=LOGGER_NAME)
        else:
            info(f"Configuration « {section} » enregistrée sans écart", name=LOGGER_NAME)
        raise web.HTTPSeeOther(location=f"/conf?success={section}#{section}")

    def _validate_form_shape(self, section: str, form) -> dict[str, str]:
        allowed = set(SECTION_FIELDS[section]) | {"csrf_token"}
        errors = {}
        for key in form:
            if key not in allowed:
                errors[key] = "Champ inattendu."
            elif len(form.getall(key)) != 1:
                errors[key] = "Le champ est présent plusieurs fois."
        return errors

    def _apply_section_to_payload(self, section: str, form, payload: dict, changed: list[str]) -> None:
        section_fields = SECTION_FIELDS[section]
        for field_name, target in section_fields.items():
            if field_name not in form:
                continue
            raw = str(form[field_name])
            if field_name in SENSITIVE_FIELDS and raw == "":
                continue
            if target in {"daily_start", "daily_stop", "day_night_start", "day_night_stop"}:
                # `<input type="time">` renvoie « HH:MM », mais certains
                # navigateurs ajoutent les secondes : elles sont ignorées.
                try:
                    parts = raw.split(":")
                    hour, minute = int(parts[0]), int(parts[1])
                except (IndexError, ValueError, TypeError):
                    raise ValueError(f"Horaire invalide pour {field_name}")
                if target.startswith("day_night"):
                    top = "Day_Night_Settings"
                    prefix = "start" if target.endswith("start") else "stop"
                else:
                    top = "DailyTimer1_Settings" if section.endswith("1") else "DailyTimer2_Settings"
                    prefix = "start" if target == "daily_start" else "stop"
                if payload[top][f"{prefix}_hour"] != hour or payload[top][f"{prefix}_minute"] != minute:
                    changed.append(field_name)
                payload[top][f"{prefix}_hour"] = hour
                payload[top][f"{prefix}_minute"] = minute
                continue
            top, nested = target
            current = payload[top].get(nested)
            if isinstance(current, bool):
                value = raw.lower() in {"enabled", "true", "1", "yes"}
            elif isinstance(current, int):
                value = int(raw)
            elif isinstance(current, float):
                value = float(raw)
            else:
                value = raw
            if current != value:
                changed.append(field_name)
            payload[top][nested] = value

    async def _equipment_configuration_post(self, form) -> web.Response:
        candidate = {}
        try:
            for equipment_id in EQUIPMENT_IDS:
                prefix = f"{equipment_id}__"
                candidate[equipment_id] = EquipmentMetadata.model_validate({
                    "display_name": str(form[prefix + "display_name"]),
                    "usage_type": str(form[prefix + "usage_type"]),
                    "zone": str(form[prefix + "zone"]),
                    "icon": str(form[prefix + "icon"]),
                    "wiring_note": str(form[prefix + "wiring_note"]),
                    "dashboard_visible": str(form[prefix + "dashboard_visible"]).lower() == "true",
                    "out_of_service": str(form[prefix + "out_of_service"]).lower() == "true",
                })
            self.equipment_store.save(candidate)
        except (KeyError, ValueError, ValidationError, OSError) as exc:
            return self._html(conf_page(
                self.config, self.csrf_token, equipment=self.equipment_store.current,
                alarm_summary=self._operator_snapshot()["alarms"],
                errors={"__all__": f"Métadonnées refusées : {exc}"},
                active_section="equipment",
            ), status=422 if not isinstance(exc, OSError) else 500)
        info("Métadonnées des équipements sauvegardées", name=LOGGER_NAME)
        raise web.HTTPSeeOther(location="/conf?success=equipment#equipment")

    async def _sensor_quality_configuration_post(self, form) -> web.Response:
        payload = self.config.model_dump(by_alias=True, mode="json")
        quality = payload.setdefault("Sensor_Quality", {})
        quality.setdefault("profiles", {})
        quality.setdefault("redundancy_groups", {})
        quality.setdefault("ds18b20_bindings", {})
        action = str(form.get("sensor_key", ""))
        reset_key = None
        reset_stats_key = None
        try:
            common = {"csrf_token", "sensor_key"}
            allowed = (
                common | {"mode", "confirm_enforce"} if action == "__mode__" else
                common | {"ds18b-1", "ds18b-2", "ds18b-3"} if action == "__bindings__" else
                common | {"group_name", "members", "tolerance", "minimum_agreeing", "delete"} if action == "__group__" else
                common | {"offset", "calibrated_at", "calibration_valid_days", "freshness_seconds",
                          "plausible_min", "plausible_max", "freeze_epsilon",
                          "freeze_after_seconds", "freeze_min_samples"}
            )
            unexpected = set(form) - allowed
            duplicated = [key for key in form if len(form.getall(key)) != 1]
            if unexpected or duplicated:
                raise ValueError("forme de formulaire qualité invalide")
            if action == "__mode__":
                mode = str(form.get("mode", ""))
                if mode == "enforce" and self.config.sensor_quality.mode != "enforce":
                    if str(form.get("confirm_enforce", "")) != "ARMER":
                        raise ValueError("saisir ARMER pour activer le repli qualité")
                quality["mode"] = mode
            elif action == "__bindings__":
                bindings = {}
                for index in (1, 2, 3):
                    value = str(form.get(f"ds18b-{index}", "")).strip()
                    if value:
                        bindings[f"DS18B#{index}"] = value
                quality["ds18b20_bindings"] = bindings
            elif action == "__group__":
                name = str(form.get("group_name", "")).strip()
                if not name:
                    raise ValueError("nom de groupe requis")
                if str(form.get("delete", "")) == "yes":
                    quality["redundancy_groups"].pop(name, None)
                else:
                    members = [item.strip() for item in str(form.get("members", "")).split(",") if item.strip()]
                    quality["redundancy_groups"][name] = {
                        "members": members,
                        "tolerance": float(form.get("tolerance", "")),
                        "minimum_agreeing": int(form.get("minimum_agreeing", "")),
                    }
            elif action in SENSORS_BY_KEY:
                profile = {
                    "offset": float(form.get("offset", 0)),
                    "calibrated_at": str(form.get("calibrated_at", "")).strip() or None,
                    "calibration_valid_days": int(form["calibration_valid_days"])
                    if str(form.get("calibration_valid_days", "")).strip() else None,
                    "freshness_seconds": float(form.get("freshness_seconds", "")),
                    "plausible_min": float(form.get("plausible_min", "")),
                    "plausible_max": float(form.get("plausible_max", "")),
                    "freeze_epsilon": float(form.get("freeze_epsilon", "")),
                    "freeze_after_seconds": (
                        "disabled" if str(form.get("freeze_after_seconds", "")).strip().lower() == "disabled"
                        else float(form.get("freeze_after_seconds", ""))
                    ),
                    "freeze_min_samples": int(form.get("freeze_min_samples", "")),
                }
                previous = quality["profiles"].get(action, {})
                quality["profiles"][action] = profile
                if previous != profile:
                    reset_key = action
                if (previous.get("offset") != profile["offset"]
                        or previous.get("calibrated_at") != profile["calibrated_at"]):
                    reset_stats_key = action
            else:
                raise ValueError("action qualité inconnue")
            candidate = self.config.__class__.model_validate(payload)
            self.config_store.save(candidate)
        except (ValidationError, ValueError, OSError, KeyError) as exc:
            return self._html(conf_page(
                self.config, self.csrf_token, equipment=self.equipment_store.current,
                alarm_summary=self._operator_snapshot()["alarms"],
                errors={"__all__": f"Qualité capteur refusée : {exc}"},
                active_section="sensor-quality",
                sensor_snapshot=self.sensor_handler.snapshot(),
                discovered_ds18=getattr(self.sensor_handler, "discovered_ds18_ids", lambda: [])(),
            ), status=422 if not isinstance(exc, OSError) else 500)
        if reset_key and hasattr(self.sensor_handler, "reset_quality"):
            self.sensor_handler.reset_quality(reset_key)
        if reset_stats_key in self.stats.KEYS:
            self.stats.clear_key(reset_stats_key)
        if action == "__bindings__" and hasattr(self.sensor_handler, "reset_quality"):
            for key in ("DS18B#1", "DS18B#2", "DS18B#3"):
                self.sensor_handler.reset_quality(key)
        if self.supervisor is not None and action in {"__mode__", "BME280T", "BME280H"}:
            self.supervisor.request_reload("climate_control")
        info(f"Qualité capteur enregistrée : {action}", name=LOGGER_NAME)
        raise web.HTTPSeeOther(location="/conf?success=sensor-quality#sensor-quality")

    @staticmethod
    def _format_validation_errors(exc: Exception) -> dict[str, str]:
        if isinstance(exc, ValidationError):
            errors = {}
            for item in exc.errors(include_url=False):
                loc = ".".join(str(part) for part in item.get("loc", ()))
                errors[loc or "__all__"] = item.get("msg", "Valeur invalide")
            return errors
        return {"__all__": str(exc)}

    async def _apply_runtime_changes(self, section: str) -> None:
        if section == "logs":
            ui.apply_log_settings(self.config.logs.level, self.config.logs.retention_days)
        if section == "sensors":
            await self.sensor_handler.reconfigure(self.config)
        if section in {"sensors", "influx"}:
            influx_handler.reload_sensor_handler(self.config, self.sensor_handler)
        if self.supervisor is not None:
            for job_name in RELOAD_JOBS.get(section, ()):
                self.supervisor.request_reload(job_name)

    async def _console(self, request: web.Request) -> web.Response:
        return self._html(console_page(
            self.csrf_token, alarm_summary=self._operator_snapshot()["alarms"]
        ))

    @staticmethod
    def _alarm_filters(request: web.Request) -> dict:
        filters = {
            "status": request.query.get("status", "active"),
            "severity": request.query.get("severity", ""),
            "category": request.query.get("category", ""),
            "acknowledged": request.query.get("acknowledged", ""),
            "limit": request.query.get("limit", "500"),
        }
        if filters["status"] not in {"active", "resolved", "all"}:
            raise web.HTTPBadRequest(text="Filtre de statut invalide")
        if filters["severity"] not in {"", "warning", "error", "critical"}:
            raise web.HTTPBadRequest(text="Filtre de gravité invalide")
        if filters["acknowledged"] not in {"", "yes", "no"}:
            raise web.HTTPBadRequest(text="Filtre d'acquittement invalide")
        try:
            filters["limit"] = max(1, min(int(filters["limit"]), 2000))
        except ValueError:
            raise web.HTTPBadRequest(text="Limite invalide")
        return filters

    async def _alarms(self, request: web.Request) -> web.Response:
        if self.operator_service is None:
            raise web.HTTPServiceUnavailable(text="Service d'alarmes indisponible")
        filters = self._alarm_filters(request)
        alarms = await self.operator_service.list_alarm_payloads(filters)
        return self._html(alarms_page(
            alarms, filters, self._operator_snapshot()["alarms"], self.csrf_token,
        ))

    async def _api_alarms(self, request: web.Request) -> web.Response:
        if self.operator_service is None:
            raise web.HTTPServiceUnavailable(text="Service d'alarmes indisponible")
        filters = self._alarm_filters(request)
        return web.json_response({
            "generated_at": _utc_now(),
            "summary": self._operator_snapshot()["alarms"],
            "alarms": await self.operator_service.list_alarm_payloads(filters),
        })

    async def _api_active_alarms(self, request: web.Request) -> web.Response:
        if self.operator_service is None:
            raise web.HTTPServiceUnavailable(text="Service d'alarmes indisponible")
        return web.json_response({
            "schema_version": 1,
            "generated_at": _utc_now(),
            "summary": self.operator_service.alarms.summary(),
            "alarms": self.operator_service.alarms.active_payloads(),
        })

    async def _acknowledge_alarm(self, request: web.Request) -> web.Response:
        if self.operator_service is None:
            raise web.HTTPServiceUnavailable(text="Service d'alarmes indisponible")
        form = request["form_data"]
        occurrence_id = str(form.get("occurrence_id", ""))
        alias = str(form.get("alias", "")).strip()
        try:
            payload = await self.operator_service.acknowledge(occurrence_id, alias)
        except (ValueError, KeyError):
            raise web.HTTPBadRequest(text="Alarme ou alias invalide")
        if "application/json" in request.headers.get("Accept", ""):
            return web.json_response(payload)
        raise web.HTTPSeeOther(location="/alarms")

    async def _api_history(self, request: web.Request) -> web.Response:
        if self.operator_service is None or not self.operator_service.history.available:
            raise web.HTTPServiceUnavailable(text="Historique local indisponible")
        try:
            hours = int(request.query.get("hours", "24"))
        except ValueError:
            raise web.HTTPBadRequest(text="Période invalide")
        if hours not in {24, 48, 72}:
            raise web.HTTPBadRequest(text="Période acceptée : 24, 48 ou 72 heures")
        if self._history_query_running:
            raise web.HTTPTooManyRequests(
                text="Une requête d'historique est déjà en cours",
                headers={"Retry-After": "2"},
            )
        self._history_query_running = True
        try:
            return web.json_response(await self.operator_service.query_history(hours))
        except Exception as exc:
            warning(f"Historique HTTP indisponible ({exc.__class__.__name__})", name=LOGGER_NAME)
            raise web.HTTPServiceUnavailable(text="Historique local indisponible")
        finally:
            self._history_query_running = False

    async def _console_stream(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        })
        await response.prepare(request)
        queue = console_stream.subscribe()
        try:
            for past in list(console_stream.history):
                await response.write(self._sse(past))
            while True:
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=15.0)
                    payload = self._sse(line)
                except asyncio.TimeoutError:
                    payload = b": keep-alive\n\n"
                await response.write(payload)
        except (ConnectionResetError, asyncio.CancelledError):
            debug("Client SSE déconnecté", name=LOGGER_NAME)
        finally:
            console_stream.unsubscribe(queue)
        return response

    @staticmethod
    def _sse(line: str) -> bytes:
        chunks = "".join(f"data: {part}\n" for part in str(line).splitlines() or [""])
        return (chunks + "\n").encode("utf-8")

    async def _api_state(self, request: web.Request) -> web.Response:
        return web.json_response(self._state_payload())

    def _state_payload(self) -> dict:
        sensor_snapshot = self.sensor_handler.snapshot()
        sensors = [sensor_snapshot[d.key] for d in SENSOR_CATALOG if sensor_snapshot[d.key]["enabled"]]
        stats = []
        for key in self.stats.KEYS:
            item = self.stats.get_all().get(key, {})
            stats.append({
                "key": key,
                "min": item.get("min"),
                "min_at": item.get("min_date"),
                "max": item.get("max"),
                "max_at": item.get("max_date"),
            })
        equipment = self.equipment_store.payload()
        actuator_entries = (
            self.operator_service.actuator_snapshot()
            if self.operator_service is not None else operational_snapshot()
        )
        if self.operator_service is not None:
            motor_actual = actuator_entries.get("motor", {}).get("actual")
            measured_speed = motor_actual if isinstance(motor_actual, int) else None
        else:
            try:
                measured_speed = self.controller_status.get_motor_speed()
            except Exception:
                measured_speed = None
        # Le champ legacy garde son entier historique ; `actuators.motor.actual`
        # reste honnête et publie `unknown` si la relecture GPIO échoue.
        speed = measured_speed if measured_speed is not None else 0
        components = {
            "daily_1": getattr(self.dailytimer1, "component", None),
            "daily_2": getattr(self.dailytimer2, "component", None),
            "cyclic_1": getattr(self.cyclic_timer1, "component", None),
            "cyclic_2": getattr(self.cyclic_timer2, "component", None),
            "heater": self.heater_component,
        }
        for equipment_id, item in actuator_entries.items():
            if self.operator_service is not None:
                continue
            if equipment_id == "motor":
                item["actual"] = measured_speed if measured_speed is not None else "unknown"
            else:
                item["actual"] = self._logical_state(components.get(equipment_id))
            item["metadata"] = equipment.get(equipment_id, {})
            if item.get("stale"):
                item["requested"] = "unknown"
                item["reason"] = "publication métier périmée"
            requested = item.get("applied", item.get("requested"))
            actual = item.get("actual")
            normalized_requested = (
                1 if requested == "on" else 0 if requested == "off" else requested
            )
            normalized_actual = (
                1 if actual == "on" else 0 if actual == "off" else actual
            )
            item["tracking"] = (
                "unknown" if item.get("stale") or actual == "unknown"
                else "known_hardware_fault"
                if normalized_requested != normalized_actual and item["metadata"].get("out_of_service")
                else "mismatch" if normalized_requested != normalized_actual
                else "ok"
            )
        start_h, start_m, stop_h, stop_m = day_night_times(self.config)
        operator = self._operator_snapshot()
        return {
            "schema_version": 2,
            "version": DEPLOYED_VERSION,
            "generated_at": _utc_now(),
            "web": {
                "https": {
                    "configured": self._https_configured,
                    "ready": self._https_ready,
                    "port": self._https_port or None,
                },
            },
            "health": {
                "healthy": self.supervisor.is_healthy() if self.supervisor else True,
                "control_healthy": self.supervisor.control_healthy() if self.supervisor else True,
                "heater_alarm": get_climate_alarm(),
                "tasks": self.supervisor.snapshot() if self.supervisor else {},
                "domains": self.supervisor.health_domains() if self.supervisor else {},
            },
            "time": time_reliability().snapshot(),
            "alarms": operator["alarms"],
            "history": operator["history"],
            "network": operator["network"],
            "equipment": equipment,
            "actuators": actuator_entries,
            "day_night": {
                "source": self.config.day_night.source,
                "start": f"{start_h:02d}:{start_m:02d}",
                "stop": f"{stop_h:02d}:{stop_m:02d}",
                "empty": start_h == stop_h and start_m == stop_m,
            },
            "outputs": {
                "daily_timer_1": self._logical_state(getattr(self.dailytimer1, "component", None)),
                "daily_timer_2": self._logical_state(getattr(self.dailytimer2, "component", None)),
                "cyclic_1": self._logical_state(getattr(self.cyclic_timer1, "component", None)),
                "cyclic_2": self._logical_state(getattr(self.cyclic_timer2, "component", None)),
                "heater": self._logical_state(self.heater_component),
            },
            "motor": {"speed": speed, "percent": int(speed / 4 * 100)},
            "climate": get_climate_snapshot(),
            "timers": self._timer_payload(),
            "sensors": sensors,
            "stats": stats,
        }

    @staticmethod
    def _logical_state(component) -> str:
        try:
            return "on" if component.get_state() else "off"
        except Exception:
            return "unknown"

    def _timer_payload(self) -> list[dict]:
        timers = []
        for number, cfg, output in (
            (1, self.config.daily_timer1, "daily_timer_1"),
            (2, self.config.daily_timer2, "daily_timer_2"),
        ):
            timers.append({
                "id": f"daily-{number}", "kind": "daily", "enabled": cfg.enabled,
                "output": output,
                "schedule": {
                    "start": f"{cfg.start_hour:02d}:{cfg.start_minute:02d}",
                    "stop": f"{cfg.stop_hour:02d}:{cfg.stop_minute:02d}",
                },
            })
        for number, cfg, output in (
            (1, self.config.cyclic1, "cyclic_1"),
            (2, self.config.cyclic2, "cyclic_2"),
        ):
            schedule = {"mode": cfg.mode}
            if cfg.mode == "journalier":
                schedule.update({
                    "period_days": cfg.period_days,
                    "triggers_per_day": cfg.triggers_per_day,
                    "first_trigger_hour": cfg.first_trigger_hour,
                    "action_duration_seconds": cfg.action_duration_seconds,
                })
            else:
                schedule.update({
                    "on_time_day": cfg.on_time_day, "off_time_day": cfg.off_time_day,
                    "on_time_night": cfg.on_time_night, "off_time_night": cfg.off_time_night,
                })
            timers.append({
                "id": f"cyclic-{number}", "kind": "cyclic", "enabled": cfg.enabled,
                "output": output, "schedule": schedule,
            })
        return timers

    async def _reset_stats(self, request: web.Request) -> web.Response:
        form = request["form_data"]
        key = str(form.get("key", ""))
        if key not in self.stats.KEYS:
            raise web.HTTPBadRequest(text="Clé de statistique invalide")
        self.stats.clear_key(key)
        value = self.sensor_handler.snapshot().get(key, {}).get("value")
        if value is not None:
            self.stats.update(key, float(value))
        info(f"Stat {key} réinitialisée", name=LOGGER_NAME)
        raise web.HTTPSeeOther(location="/#statistiques")

    async def _reset_sensor_quality(self, request: web.Request) -> web.Response:
        key = str(request["form_data"].get("key", ""))
        if key not in SENSORS_BY_KEY or not hasattr(self.sensor_handler, "reset_quality"):
            raise web.HTTPBadRequest(text="Clé de diagnostic capteur invalide")
        self.sensor_handler.reset_quality(key)
        info(f"Diagnostic qualité {key} réinitialisé", name=LOGGER_NAME)
        raise web.HTTPSeeOther(location="/conf#sensor-quality")

    async def _legacy_monitor_action(self, request: web.Request) -> web.Response:
        form = request["form_data"]
        if "reset_sensor" in form:
            return await self._reset_stats(request)
        if form.get("reboot") == "1":
            return await self._reboot(request)
        if form.get("poweroff") == "1":
            return await self._poweroff(request)
        raise web.HTTPBadRequest(text="Action inconnue")

    async def _reboot(self, request: web.Request) -> web.Response:
        return await self._system_command(("sudo", "reboot"), "Redémarrage")

    async def _poweroff(self, request: web.Request) -> web.Response:
        return await self._system_command(("/sbin/shutdown", "-h", "now"), "Extinction")

    async def _system_command(self, command: tuple[str, ...], label: str) -> web.Response:
        warning(f"{label} demandé via l'interface web", name=LOGGER_NAME)
        if self.operator_service is not None:
            await self.operator_service.record_system_action(
                "reboot" if "reboot" in command else "poweroff"
            )
        try:
            process = await asyncio.create_subprocess_exec(*command)
            returncode = await process.wait()
        except OSError as exc:
            error(f"{label} impossible : {exc.__class__.__name__}", name=LOGGER_NAME)
            raise web.HTTPInternalServerError(text=f"{label} impossible")
        if returncode != 0:
            error(f"{label} échoué (code {returncode})", name=LOGGER_NAME)
            raise web.HTTPInternalServerError(text=f"{label} échoué")
        return web.Response(status=202, text=f"{label} demandé")

    async def _legacy_status(self, request: web.Request) -> web.Response:
        cs = self.controller_status
        payload = {
            "component_state": cs.get_component_state(),
            "motor_speed": cs.get_motor_speed(),
            "dailytimer1": {
                "start": cs.get_dailytimer_current_start_time(),
                "stop": cs.get_dailytimer_current_stop_time(),
            },
            "cyclic": {
                "period": self.config.cyclic1.period_days,
                "duration": self.config.cyclic1.action_duration_seconds,
            },
            "heater_alarm": get_climate_alarm(),
            "time": time_reliability().snapshot(),
            "operator": self._operator_snapshot(),
        }
        if self.supervisor is not None:
            payload["healthy"] = self.supervisor.is_healthy()
            payload["control_healthy"] = self.supervisor.control_healthy()
            payload["tasks"] = self.supervisor.snapshot()
            payload["health_domains"] = self.supervisor.health_domains()
        return web.json_response(payload)

    async def _health_live(self, request: web.Request) -> web.Response:
        return web.json_response({"live": True, "version": DEPLOYED_VERSION})

    async def _health_ready(self, request: web.Request) -> web.Response:
        healthy = self.supervisor.is_healthy() if self.supervisor else True
        return web.json_response(
            {"ready": healthy, "unhealthy": self.supervisor.unhealthy_names() if self.supervisor else []},
            status=200 if healthy else 503,
        )

    async def _manifest(self, request: web.Request) -> web.Response:
        icon_192 = f"/static/icons/pwa-192.png?v={ASSET_VERSIONS['icon_192']}"
        icon_512 = f"/static/icons/pwa-512.png?v={ASSET_VERSIONS['icon_512']}"
        maskable = (
            f"/static/icons/pwa-maskable-512.png?v={ASSET_VERSIONS['icon_maskable']}"
        )
        payload = {
            "id": "/",
            "name": "PhytoController",
            "short_name": "Phyto",
            "description": "Supervision locale de la serre PhytoController",
            "lang": "fr",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#07100c",
            "theme_color": "#020604",
            "icons": [
                {"src": icon_192, "sizes": "192x192", "type": "image/png", "purpose": "any"},
                {"src": icon_512, "sizes": "512x512", "type": "image/png", "purpose": "any"},
                {"src": maskable, "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            ],
            "shortcuts": [
                {"name": "Tableau de bord", "short_name": "Tableau", "url": "/", "icons": [{"src": icon_192, "sizes": "192x192", "type": "image/png"}]},
                {"name": "Alarmes", "short_name": "Alarmes", "url": "/alarms", "icons": [{"src": icon_192, "sizes": "192x192", "type": "image/png"}]},
            ],
        }
        response = web.Response(
            text=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            content_type="application/manifest+json",
            charset="utf-8",
        )
        response.headers["Cache-Control"] = "no-cache"
        return response

    async def _service_worker(self, request: web.Request) -> web.Response:
        source = (STATIC_DIR / "service-worker.js").read_text(encoding="utf-8")
        precache = [
            "/offline",
            f"/app.webmanifest?v={PWA_CACHE_VERSION}",
            f"/static/css/style.css?v={ASSET_VERSIONS['style']}",
            f"/static/js/pwa.js?v={ASSET_VERSIONS['pwa']}",
            f"/static/js/dashboard.js?v={ASSET_VERSIONS['dashboard']}",
            f"/static/js/alarms.js?v={ASSET_VERSIONS['alarms']}",
            f"/static/js/history.js?v={ASSET_VERSIONS['history']}",
            f"/static/fonts/visitor1.ttf?v={ASSET_VERSIONS['font']}",
            f"/favicon.svg?v={ASSET_VERSIONS['favicon']}",
            f"/static/equipment-icons.svg?v={ASSET_VERSIONS['equipment_icons']}",
            f"/static/icons/pwa-192.png?v={ASSET_VERSIONS['icon_192']}",
            f"/static/icons/pwa-512.png?v={ASSET_VERSIONS['icon_512']}",
            f"/static/icons/pwa-maskable-512.png?v={ASSET_VERSIONS['icon_maskable']}",
        ]
        source = source.replace("__PHYTO_CACHE_VERSION__", PWA_CACHE_VERSION)
        source = source.replace("__PHYTO_PRECACHE_URLS__", json.dumps(precache))
        response = web.Response(
            text=source,
            content_type="application/javascript",
            charset="utf-8",
        )
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Service-Worker-Allowed"] = "/"
        return response

    async def _offline(self, request: web.Request) -> web.Response:
        return self._html(offline_page())

    async def _asset(self, relative: str, content_type: str | None = None) -> web.FileResponse:
        response = web.FileResponse(STATIC_DIR / relative)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if content_type:
            response.content_type = content_type
        return response

    async def _style(self, request): return await self._asset("css/style.css", "text/css")
    async def _pwa_js(self, request): return await self._asset("js/pwa.js", "application/javascript")
    async def _dashboard_js(self, request): return await self._asset("js/dashboard.js", "application/javascript")
    async def _config_js(self, request): return await self._asset("js/config.js", "application/javascript")
    async def _console_js(self, request): return await self._asset("js/console.js", "application/javascript")
    async def _alarms_js(self, request): return await self._asset("js/alarms.js", "application/javascript")
    async def _history_js(self, request): return await self._asset("js/history.js", "application/javascript")
    async def _font(self, request): return await self._asset("fonts/visitor1.ttf", "font/ttf")
    async def _equipment_icons(self, request): return await self._asset("equipment-icons.svg", "image/svg+xml")
    async def _favicon(self, request): return await self._asset("favicon.svg", "image/svg+xml")
    async def _pwa_icon_192(self, request): return await self._asset("icons/pwa-192.png", "image/png")
    async def _pwa_icon_512(self, request): return await self._asset("icons/pwa-512.png", "image/png")
    async def _pwa_icon_maskable(self, request): return await self._asset("icons/pwa-maskable-512.png", "image/png")

    async def _favicon_redirect(self, request: web.Request) -> web.Response:
        raise web.HTTPFound(location="/favicon.svg")
