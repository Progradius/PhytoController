"""Serveur HTTP aiohttp de l'interface locale PhytoController."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
import secrets
import socket
import ssl
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from aiohttp import web
from multidict import MultiDict
from pydantic import ValidationError

from components.climate_control import get_climate_alarm, get_climate_snapshot
from components.climate_policy import preview_thresholds
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

class FormFieldError(ValueError):
    """Refus imputable à un champ précis du formulaire.

    Les parseurs du serveur (horaires, entiers, décimaux) refusent avant même
    d'atteindre Pydantic : sans porter le nom du champ, leur message finissait
    dans le bandeau global et l'opérateur devait deviner lequel corriger.
    """

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class FieldSpec(NamedTuple):
    """Une entrée du registre des champs de configuration.

    `target` est soit la cible `(section JSON, clé)` dans le document
    `param.json`, soit le nom d'un parseur dédié (`daily_start`, …) pour les
    champs dont une saisie unique alimente plusieurs clés.

    `label` est le libellé humain, celui-là même affiché par le formulaire :
    c'est lui qui rend un message de refus lisible sans obliger le lecteur à
    connaître le nom PascalCase de la clé sous-jacente.
    """

    target: tuple[str, str] | str
    label: str


# Parseurs dédiés : un `<input type="time">` alimente deux clés `*_hour` /
# `*_minute`, donc la cible ne peut pas être une simple paire.
TIME_TARGETS = frozenset({
    "daily_start", "daily_stop", "day_night_start", "day_night_stop",
    # Le mode Simple porte les deux minuteries dans un seul formulaire : la
    # cible ne peut plus être déduite du nom de la section.
    "daily1_start", "daily1_stop", "daily2_start", "daily2_stop",
})

_CYCLIC_LABELS = {
    "enabled": "Activation",
    "mode": "Mode de fonctionnement",
    "period_days": "Période",
    "triggers_per_day": "Activations par journée",
    "first_trigger_hour": "Première activation",
    "action_duration_seconds": "Durée d’activation",
    "on_time_day": "Jour · durée ON",
    "off_time_day": "Jour · durée OFF",
    "on_time_night": "Nuit · durée ON",
    "off_time_night": "Nuit · durée OFF",
}

_TEMPERATURE_LABELS = {
    "target_temp_min_day": "Jour · minimum",
    "target_temp_max_day": "Jour · maximum",
    "target_temp_min_night": "Nuit · minimum",
    "target_temp_max_night": "Nuit · maximum",
    "hysteresis_offset": "Hystérésis chauffage",
    "vent_deadband": "Zone morte",
    "vent_step": "Largeur d’un palier",
    "vent_release": "Relâchement de palier",
    "absolute_floor_temp": "Plancher absolu",
    "min_dwell_seconds": "Maintien minimal",
}

_MOTOR_LABELS = {
    "motor_mode": "Mode moteur",
    "motor_user_speed": "Vitesse manuelle",
    "min_speed": "Vitesse minimale",
    "max_speed": "Vitesse maximale",
    "sensor_fallback_speed": "Vitesse de repli capteur",
    "winter_default_speed": "Vitesse par défaut",
    "winter_temp_margin": "Marge basse",
    "winter_refresh_speed": "Vitesse de renouvellement",
    "winter_refresh_minutes_per_hour": "Renouvellement par heure",
    "winter_humidity_threshold": "Seuil d’humidité",
    "winter_humidity_minutes_per_hour": "Déshumidification par heure",
}

_SENSOR_LABELS = {
    "bme280_state": "BME280 · air",
    "ds18b20_state": "DS18B20 · sondes",
    "veml6075_state": "VEML6075 · UV",
    "vl53L0x_state": "VL53L0X · distance laser",
    "mlx90614_state": "MLX90614 · infrarouge",
    "tsl2591_state": "TSL2591 · lumière",
    "hcsr04_state": "HC-SR04 · distance ultrason",
}

_INFLUX_LABELS = {
    "host_machine_state": "Export InfluxDB",
    "host_machine_address": "Serveur",
    "influx_db_port": "Port",
    "influx_db_name": "Base de données",
    "influx_db_user": "Nouvel utilisateur",
    "influx_db_password": "Nouveau mot de passe",
}

_EQUIPMENT_LABELS = {
    "display_name": "Nom affiché",
    "usage_type": "Usage",
    "zone": "Zone",
    "icon": "Icône",
    "wiring_note": "Note de câblage",
    "dashboard_visible": "Visible sur le tableau de bord",
    "out_of_service": "Défaut matériel connu",
}


def _timer_section(number: int) -> dict[str, FieldSpec]:
    return {
        "enabled": FieldSpec((f"DailyTimer{number}_Settings", "enabled"), "Activation"),
        "start_time": FieldSpec("daily_start", "Début"),
        "stop_time": FieldSpec("daily_stop", "Fin"),
    }


def _mapped_section(top: str, labels: dict[str, str]) -> dict[str, FieldSpec]:
    return {name: FieldSpec((top, name), label) for name, label in labels.items()}


# ── Mode Simple ──────────────────────────────────────────────────────────────
# Réglages fins que le mode Simple impose pour que les quelques champs qu'il
# expose aient un effet déterministe. Les valeurs sont **celles de la
# configuration déployée** (arbitrage opérateur du 28 août 2026) : passer en
# mode Simple ne change donc rien tant qu'on ne touche pas aux champs exposés,
# et la prévisualisation affiche tout écart avant l'enregistrement.
SIMPLE_PROFILE: dict[tuple[str, str], tuple[object, str]] = {
    ("Temperature_Settings", "hysteresis_offset"): (2.0, "Hystérésis chauffage"),
    ("Temperature_Settings", "vent_deadband"): (1.0, "Zone morte"),
    ("Temperature_Settings", "vent_step"): (1.0, "Largeur d’un palier"),
    ("Temperature_Settings", "vent_release"): (0.5, "Relâchement de palier"),
    ("Temperature_Settings", "min_dwell_seconds"): (120, "Maintien minimal"),
    ("Temperature_Settings", "absolute_floor_temp"): (5.0, "Plancher absolu"),
    ("Motor_Settings", "min_speed"): (0, "Vitesse minimale"),
    ("Motor_Settings", "sensor_fallback_speed"): (0, "Vitesse de repli capteur"),
    ("Motor_Settings", "winter_default_speed"): (1, "Vitesse hiver par défaut"),
    ("Motor_Settings", "winter_temp_margin"): (2.0, "Marge basse hiver"),
    ("Motor_Settings", "winter_refresh_minutes_per_hour"): (5, "Renouvellement par heure"),
    ("Motor_Settings", "winter_humidity_minutes_per_hour"): (15, "Déshumidification par heure"),
}

# Intensité → (vitesse maximale, vitesse de renouvellement hiver).
# Rappel matériel consigné : les vitesses moteur 1 et 3 sont hors service côté
# puissance. « Normale » commande donc une vitesse morte tant que la panne dure —
# mapping conservé sur décision opérateur, l'annotation `out_of_service` des
# métadonnées reste le canal qui le signale.
SIMPLE_INTENSITY = {"douce": (2, 2), "normale": (3, 3), "forte": (4, 4)}

# Saison → mode moteur. `manuel` n'est proposé que si le moteur y est déjà :
# le mode Simple ne doit pas faire sortir d'un pilotage manuel sans un choix
# explicite, ni y faire entrer.
SIMPLE_SEASONS = {"ete": "auto", "hiver": "winter", "manuel": "manual"}

# Champs sans valeur par défaut sûre : leur absence est un refus, pas un
# « inchangé ». C'est ce qui force le choix explicite quand le moteur est en
# manuel — les boutons radio de saison sont alors rendus sans sélection.
REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "simple": {
        "season": "Choisir explicitement Été, Hiver, ou Manuel pour conserver le pilotage manuel.",
        "intensity": "Choisir une intensité de ventilation.",
    },
}

SECTION_FIELDS: dict[str, dict[str, FieldSpec]] = {
    "simple": {
        "source": FieldSpec(("Day_Night_Settings", "source"), "Référence jour / nuit"),
        "start_time": FieldSpec("day_night_start", "Début du jour"),
        "stop_time": FieldSpec("day_night_stop", "Fin du jour"),
        "target_temp_min_day": FieldSpec(
            ("Temperature_Settings", "target_temp_min_day"), "Jour · minimum"),
        "target_temp_max_day": FieldSpec(
            ("Temperature_Settings", "target_temp_max_day"), "Jour · maximum"),
        "target_temp_min_night": FieldSpec(
            ("Temperature_Settings", "target_temp_min_night"), "Nuit · minimum"),
        "target_temp_max_night": FieldSpec(
            ("Temperature_Settings", "target_temp_max_night"), "Nuit · maximum"),
        "humidity_max": FieldSpec(
            ("Motor_Settings", "winter_humidity_threshold"), "Humidité maximale"),
        "intensity": FieldSpec("simple_intensity", "Intensité de ventilation"),
        "season": FieldSpec("simple_season", "Saison"),
        "heater_enabled": FieldSpec(("Heater_Settings", "enabled"), "Chauffage"),
        "daily1_enabled": FieldSpec(("DailyTimer1_Settings", "enabled"), "Éclairage 1"),
        "daily1_start": FieldSpec("daily1_start", "Éclairage 1 · début"),
        "daily1_stop": FieldSpec("daily1_stop", "Éclairage 1 · fin"),
        "daily2_enabled": FieldSpec(("DailyTimer2_Settings", "enabled"), "Éclairage 2"),
        "daily2_start": FieldSpec("daily2_start", "Éclairage 2 · début"),
        "daily2_stop": FieldSpec("daily2_stop", "Éclairage 2 · fin"),
    },
    "life": {"stage": FieldSpec(("Life_Period", "stage"), "Stade actuel")},
    "daily-timer-1": _timer_section(1),
    "daily-timer-2": _timer_section(2),
    "day-night": {
        "source": FieldSpec(("Day_Night_Settings", "source"), "Source"),
        "start_time": FieldSpec("day_night_start", "Début"),
        "stop_time": FieldSpec("day_night_stop", "Fin"),
    },
    "cyclic-1": _mapped_section("Cyclic1_Settings", _CYCLIC_LABELS),
    "cyclic-2": _mapped_section("Cyclic2_Settings", _CYCLIC_LABELS),
    "temperature": _mapped_section("Temperature_Settings", _TEMPERATURE_LABELS),
    "heater": {"enabled": FieldSpec(("Heater_Settings", "enabled"), "Autorisation du chauffage")},
    "motor": _mapped_section("Motor_Settings", _MOTOR_LABELS),
    "sensors": _mapped_section("Sensor_State", _SENSOR_LABELS),
    "sensor-quality": {},
    "wifi": {
        "wifi_ssid": FieldSpec(("Network_Settings", "wifi_ssid"), "Nom du réseau (SSID)"),
        "wifi_password": FieldSpec(("Network_Settings", "wifi_password"), "Nouveau mot de passe"),
    },
    "influx": _mapped_section("Network_Settings", _INFLUX_LABELS),
    "logs": {
        "level": FieldSpec(("Log_Settings", "level"), "Niveau"),
        "retention_days": FieldSpec(("Log_Settings", "retention_days"), "Rétention"),
    },
    "equipment": {
        f"{equipment_id}__{field}": FieldSpec("equipment_metadata", f"{equipment_id} · {label}")
        for equipment_id in EQUIPMENT_IDS
        for field, label in _EQUIPMENT_LABELS.items()
    },
}


def _time_target(section: str, target: str) -> tuple[str, str]:
    """Résout un parseur d'horaire vers `(section JSON, préfixe start|stop)`."""
    prefix = "start" if target.endswith("start") else "stop"
    if target.startswith("day_night"):
        return "Day_Night_Settings", prefix
    if target.startswith("daily1_"):
        return "DailyTimer1_Settings", prefix
    if target.startswith("daily2_"):
        return "DailyTimer2_Settings", prefix
    top = "DailyTimer1_Settings" if section.endswith("1") else "DailyTimer2_Settings"
    return top, prefix


def _build_payload_index() -> dict[str, dict[str, str]]:
    """Index inverse `« Section_JSON.clé » → champ de formulaire`, par section.

    Il est **dérivé** de `SECTION_FIELDS` et non saisi une seconde fois : c'est
    ce qui garantit qu'un refus Pydantic, dont la localisation est exprimée en
    clés PascalCase, retrouve toujours le champ que l'opérateur a réellement
    saisi.
    """
    index: dict[str, dict[str, str]] = {}
    for section, fields in SECTION_FIELDS.items():
        mapping: dict[str, str] = {}
        for field_name, spec in fields.items():
            target = spec.target
            if isinstance(target, tuple):
                mapping[f"{target[0]}.{target[1]}"] = field_name
            elif target in TIME_TARGETS:
                top, prefix = _time_target(section, target)
                mapping[f"{top}.{prefix}_hour"] = field_name
                mapping[f"{top}.{prefix}_minute"] = field_name
            elif target == "simple_intensity":
                mapping["Motor_Settings.max_speed"] = field_name
                mapping["Motor_Settings.winter_refresh_speed"] = field_name
            elif target == "simple_season":
                mapping["Motor_Settings.motor_mode"] = field_name
        index[section] = mapping
    return index


PAYLOAD_INDEX = _build_payload_index()

# Messages Pydantic v2 traduits. Les bornes viennent du `ctx` de l'erreur : une
# phrase qui répète la limite refusée évite l'aller-retour vers la documentation.
PYDANTIC_MESSAGES: dict[str, str] = {
    "missing": "Ce champ est obligatoire.",
    "int_parsing": "Saisir un nombre entier.",
    "int_type": "Saisir un nombre entier.",
    "int_from_float": "Saisir un nombre entier, sans décimale.",
    "float_parsing": "Saisir un nombre (séparateur décimal : le point).",
    "float_type": "Saisir un nombre (séparateur décimal : le point).",
    "finite_number": "Saisir un nombre fini.",
    "bool_parsing": "Choisir « activé » ou « désactivé ».",
    "string_type": "Saisir du texte.",
    "string_too_short": "Saisir au moins {min_length} caractère(s).",
    "string_too_long": "Ne pas dépasser {max_length} caractères.",
    "string_pattern_mismatch": "Le format attendu n’est pas respecté.",
    "greater_than": "Saisir une valeur strictement supérieure à {gt}.",
    "greater_than_equal": "Saisir une valeur supérieure ou égale à {ge}.",
    "less_than": "Saisir une valeur strictement inférieure à {lt}.",
    "less_than_equal": "Saisir une valeur inférieure ou égale à {le}.",
    "multiple_of": "Saisir un multiple de {multiple_of}.",
    "literal_error": "Choisir une des valeurs proposées.",
    "enum": "Choisir une des valeurs proposées.",
    "extra_forbidden": "Ce champ n’est pas accepté ici.",
}

# Sections dont la saisie passe par `_apply_section_to_payload` : les seules que
# la prévisualisation sache projeter sur un candidat `AppConfig` complet.
PREVIEWABLE_SECTIONS = frozenset(SECTION_FIELDS) - {"sensor-quality", "equipment"}

# Intervalle minimal entre deux prévisualisations d'un même processus. Une
# validation Pydantic complète n'est pas gratuite sur un Pi, et l'IHM n'a besoin
# que d'un retour à la frappe, pas d'un par caractère.
PREVIEW_MIN_INTERVAL_SECONDS = 0.4

# Compte rendu d'enregistrement. Le jeton de redirection est **opaque** : le
# contenu reste côté serveur, à usage unique et périmé, plutôt que recopié dans
# une URL que l'opérateur pourrait partager ou rejouer.
FLASH_TTL_SECONDS = 180.0
FLASH_MAX_ENTRIES = 8

# Contraintes croisées : un validateur de modèle refuse la *section* entière,
# donc Pydantic ne désigne aucun champ. Sans cette table, l'opérateur reçoit une
# erreur globale et doit deviner lequel des deux champs corriger.
CROSS_CONSTRAINTS: dict[str, tuple[tuple[str, tuple[str, ...], str], ...]] = {
    "Temperature_Settings": (
        (
            "minimale de jour",
            ("target_temp_min_day", "target_temp_max_day"),
            "Le minimum de jour doit rester sous le maximum de jour.",
        ),
        (
            "minimale de nuit",
            ("target_temp_min_night", "target_temp_max_night"),
            "Le minimum de nuit doit rester sous le maximum de nuit.",
        ),
    ),
    "Motor_Settings": (
        (
            "vitesse minimale",
            ("min_speed", "max_speed"),
            "La vitesse minimale doit rester sous la vitesse maximale.",
        ),
    ),
}

RELOAD_JOBS = {
    "simple": (
        "daily_timer_1", "daily_timer_2",
        "cyclic_timer_1", "cyclic_timer_2", "climate_control",
    ),
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
        # Une prévisualisation valide tout le modèle Pydantic : sur un Pi, une
        # frappe au clavier par validation complète est un coût réel, et rien
        # n'oblige un client du LAN à se limiter tout seul.
        self._preview_running = False
        self._preview_last_at = 0.0
        self._flashes: dict[str, dict] = {}
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
            web.post("/api/v1/config/preview", self._config_preview),
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

    def _simple_view(self) -> dict:
        """Projection de la configuration sur les quelques choix du mode Simple.

        Un moteur en pilotage manuel ne présélectionne **aucune** saison : le
        mode Simple exige alors un choix explicite, faute de quoi le seul fait
        d'enregistrer ferait sortir du manuel sans le dire.
        """
        motor = self.config.motor
        current = self.config.model_dump(by_alias=True)
        manual = motor.motor_mode == "manual"
        seasons = [("ete", "Été"), ("hiver", "Hiver")]
        if manual:
            seasons.append(("manuel", "Conserver le pilotage manuel"))
        return {
            "intensity": next(
                (name for name, speeds in SIMPLE_INTENSITY.items()
                 if (motor.max_speed, motor.winter_refresh_speed) == speeds),
                "",
            ),
            "season": "" if manual else {"auto": "ete", "winter": "hiver"}.get(motor.motor_mode, ""),
            "seasons": seasons,
            "manual": manual,
            "manual_speed": motor.motor_user_speed,
            "profile_pending": [
                {"label": label, "from": current[top].get(nested), "to": value}
                for (top, nested), (value, label) in SIMPLE_PROFILE.items()
                if current[top].get(nested) != value
            ],
        }

    def _apply_note(self, section: str) -> str:
        if section == "wifi":
            return "Pris en compte au prochain redémarrage : la connexion n'est pas recréée à chaud."
        if section == "logs":
            return "Appliqué à chaud : niveau et rétention de journalisation."
        jobs = RELOAD_JOBS.get(section, ())
        if jobs:
            return "Appliqué à chaud, avec relance de : " + ", ".join(jobs) + "."
        return "Appliqué à chaud."

    def _store_flash(self, section: str, changed: list[str], profile: list[dict] | None = None) -> str:
        """Range un compte rendu d'enregistrement et renvoie son jeton opaque."""
        now = time.monotonic()
        self._flashes = {
            key: value for key, value in self._flashes.items()
            if now - value["mono"] < FLASH_TTL_SECONDS
        }
        while len(self._flashes) >= FLASH_MAX_ENTRIES:
            self._flashes.pop(next(iter(self._flashes)))
        fields = SECTION_FIELDS.get(section, {})
        token = secrets.token_urlsafe(12)
        self._flashes[token] = {
            "mono": now,
            "section": section,
            "at": datetime.now().strftime("%d/%m/%Y à %H:%M:%S"),
            "apply": self._apply_note(section),
            "changes": [
                (fields[name].label if name in fields else name)
                + (" (valeur masquée)" if name in SENSITIVE_FIELDS else "")
                for name in changed
            ],
            "profile": [item["label"] for item in (profile or [])],
        }
        return token

    def _pop_flash(self, token: str | None) -> dict | None:
        if not token:
            return None
        entry = self._flashes.pop(token, None)
        if entry is None or time.monotonic() - entry["mono"] >= FLASH_TTL_SECONDS:
            return None
        return entry

    async def _configuration(self, request: web.Request) -> web.Response:
        flash = self._pop_flash(request.query.get("flash"))
        success_section = flash["section"] if flash else request.query.get("success")
        if success_section not in SECTION_FIELDS:
            success_section = None
        return self._html(conf_page(
            self.config,
            self.csrf_token,
            alarm_summary=self._operator_snapshot()["alarms"],
            equipment=self.equipment_store.current,
            success=success_section,
            flash=flash,
            simple=self._simple_view(),
            active_section=success_section,
            sensor_snapshot=self.sensor_handler.snapshot(),
            discovered_ds18=getattr(self.sensor_handler, "discovered_ds18_ids", lambda: [])(),
        ))

    def _conf_refusal(
        self,
        section: str,
        errors: dict[str, str],
        *,
        scope: str | None = None,
        values: dict[str, str] | None = None,
        status: int = 422,
    ) -> web.Response:
        """Rend `/conf` après un refus, **avec la saisie de l'opérateur**.

        Point unique de sortie des quatre chemins de refus : re-rendre la
        configuration enregistrée au lieu du POST faisait perdre toute la
        section à la moindre valeur fautive. Les erreurs rattachables à un champ
        sont rendues sous ce champ ; les autres restent dans le bandeau.
        """
        scope = scope or section
        known = SECTION_FIELDS.get(section, {})
        field_errors = {name: message for name, message in errors.items() if name in known}
        banner = {name: message for name, message in errors.items() if name not in known}
        return self._html(conf_page(
            self.config,
            self.csrf_token,
            equipment=self.equipment_store.current,
            alarm_summary=self._operator_snapshot()["alarms"],
            errors=banner,
            field_errors={scope: field_errors} if field_errors else {},
            form_values={scope: values} if values else {},
            simple=self._simple_view(),
            active_section=section,
            sensor_snapshot=self.sensor_handler.snapshot(),
            discovered_ds18=getattr(self.sensor_handler, "discovered_ds18_ids", lambda: [])(),
        ), status=status)

    @staticmethod
    def _submitted_values(section: str, form) -> dict[str, str]:
        """Saisie à réafficher : champs connus de la section, secrets exclus.

        Un secret n'est jamais réémis, même refusé — il repartirait dans le HTML
        d'une interface sans authentification. Le champ se re-rend vide, ce que
        l'aide du formulaire décrit déjà comme « laisser vide pour conserver ».
        """
        values: dict[str, str] = {}
        for name in SECTION_FIELDS.get(section, {}):
            if name in SENSITIVE_FIELDS or name not in form:
                continue
            values[name] = str(form[name])
        return values

    async def _configuration_post(self, request: web.Request) -> web.Response:
        section = request.match_info["section"]
        if section not in SECTION_FIELDS:
            raise web.HTTPNotFound(text="Section inconnue")
        form = request["form_data"]
        if section == "sensor-quality":
            return await self._sensor_quality_configuration_post(form)
        submitted = self._submitted_values(section, form)
        errors = self._validate_form_shape(section, form)
        if errors:
            return self._conf_refusal(section, errors, values=submitted)

        if section == "equipment":
            return await self._equipment_configuration_post(form, submitted)

        before = self.config.model_dump(by_alias=True)
        payload = self.config.model_dump(by_alias=True)
        changed_fields: list[str] = []
        try:
            self._apply_section_to_payload(section, form, payload, changed_fields)
            candidate = self.config.__class__.model_validate(payload)
        except (ValidationError, ValueError) as exc:
            return self._conf_refusal(
                section, self._format_validation_errors(exc, section), values=submitted,
            )
        profile_changes = self._profile_changes(before, payload) if section == "simple" else []

        try:
            # Le magasin revalide, sauvegarde l'ancien contenu en `.bak`, écrit
            # atomiquement puis adopte la candidate dans l'instance partagée —
            # celle que tient déjà `self.config` (audit C5, M4).
            self.config_store.save(candidate)
        except OSError:
            return self._conf_refusal(
                section,
                {"__all__": "Écriture impossible : la configuration active est inchangée."},
                values=submitted,
                status=500,
            )
        await self._apply_runtime_changes(section)
        if changed_fields:
            safe_names = [f"{name} modifié" if name in SENSITIVE_FIELDS else name for name in changed_fields]
            info(f"Configuration « {section} » sauvegardée : {', '.join(safe_names)}", name=LOGGER_NAME)
        else:
            info(f"Configuration « {section} » enregistrée sans écart", name=LOGGER_NAME)
        token = self._store_flash(section, changed_fields, profile_changes)
        raise web.HTTPSeeOther(location=f"/conf?flash={token}#{section}")

    async def _config_preview(self, request: web.Request) -> web.Response:
        """Projette une saisie sur un candidat complet, **sans rien écrire**.

        Même registre, mêmes parseurs et mêmes formules que l'enregistrement :
        rejouer l'arbitrage thermique en JavaScript créerait une seconde vérité,
        et c'est le seuil de ventilation qui en souffrirait — il peut dépasser la
        consigne haute saisie de l'hystérésis plus la zone morte sans que le
        formulaire le dise.

        Le corps n'est jamais journalisé et la réponse ne porte aucun secret.
        """
        if self._preview_running:
            raise web.HTTPTooManyRequests(
                text="Une prévisualisation est déjà en cours", headers={"Retry-After": "1"},
            )
        elapsed = time.monotonic() - self._preview_last_at
        if elapsed < PREVIEW_MIN_INTERVAL_SECONDS:
            raise web.HTTPTooManyRequests(
                text="Prévisualisation trop fréquente", headers={"Retry-After": "1"},
            )
        self._preview_running = True
        try:
            try:
                body = await request.json()
            except (ValueError, json.JSONDecodeError):
                raise web.HTTPBadRequest(text="Corps JSON attendu")
            if not isinstance(body, dict):
                raise web.HTTPBadRequest(text="Corps JSON attendu")
            section = str(body.get("section", ""))
            if section not in PREVIEWABLE_SECTIONS:
                raise web.HTTPBadRequest(text="Section non prévisualisable")
            fields = body.get("fields")
            if not isinstance(fields, dict):
                raise web.HTTPBadRequest(text="« fields » doit être un objet")
            form = MultiDict()
            for name, value in fields.items():
                if isinstance(value, (dict, list)):
                    raise web.HTTPBadRequest(text="Valeur de champ invalide")
                form.add(str(name), "" if value is None else str(value))
            return web.json_response(self._preview_payload(section, form))
        finally:
            self._preview_running = False
            self._preview_last_at = time.monotonic()

    def _preview_payload(self, section: str, form) -> dict:
        errors = self._validate_form_shape(section, form)
        before = self.config.model_dump(by_alias=True)
        payload = self.config.model_dump(by_alias=True)
        changed: list[str] = []
        candidate = None
        if not errors:
            try:
                self._apply_section_to_payload(section, form, payload, changed)
                candidate = self.config.__class__.model_validate(payload)
            except (ValidationError, ValueError) as exc:
                errors = self._format_validation_errors(exc, section)
        return {
            "section": section,
            "valid": not errors,
            "errors": errors,
            "changes": self._preview_changes(section, changed, before, payload) if not errors else [],
            "profile_changes": (
                self._profile_changes(before, payload)
                if section == "simple" and not errors else []
            ),
            "apply_note": self._apply_note(section),
            "climate": preview_thresholds(candidate) if candidate is not None else None,
            "current_climate": preview_thresholds(self.config),
            # C'est le serveur qui dit si la section touche l'arbitre thermique :
            # `RELOAD_JOBS` porte déjà cette vérité, la redire côté navigateur en
            # ferait une seconde.
            "climate_relevant": "climate_control" in RELOAD_JOBS.get(section, ()),
        }

    @staticmethod
    def _preview_changes(section: str, changed: list[str], before: dict, after: dict) -> list[dict]:
        changes = []
        for name in changed:
            spec = SECTION_FIELDS[section][name]
            entry = {"field": name, "label": spec.label, "secret": name in SENSITIVE_FIELDS}
            if not entry["secret"]:
                if isinstance(spec.target, tuple):
                    top, nested = spec.target
                    entry["from"] = before[top].get(nested)
                    entry["to"] = after[top].get(nested)
                else:
                    top, prefix = _time_target(section, spec.target)
                    entry["from"] = "%02d:%02d" % (
                        before[top][f"{prefix}_hour"], before[top][f"{prefix}_minute"],
                    )
                    entry["to"] = "%02d:%02d" % (
                        after[top][f"{prefix}_hour"], after[top][f"{prefix}_minute"],
                    )
            changes.append(entry)
        return changes

    def _validate_form_shape(self, section: str, form) -> dict[str, str]:
        allowed = set(SECTION_FIELDS[section]) | {"csrf_token"}
        errors = {}
        for key in form:
            if key not in allowed:
                errors[key] = "Champ inattendu."
            elif len(form.getall(key)) != 1:
                errors[key] = "Le champ est présent plusieurs fois."
        for name, message in REQUIRED_FIELDS.get(section, {}).items():
            if name not in form:
                errors.setdefault(name, message)
        return errors

    def _apply_section_to_payload(self, section: str, form, payload: dict, changed: list[str]) -> None:
        section_fields = SECTION_FIELDS[section]
        for field_name, spec in section_fields.items():
            if field_name not in form:
                continue
            target = spec.target
            raw = str(form[field_name])
            if field_name in SENSITIVE_FIELDS and raw == "":
                continue
            if target == "simple_intensity":
                speeds = SIMPLE_INTENSITY.get(raw)
                if speeds is None:
                    raise FormFieldError(field_name, "Choisir une des intensités proposées.")
                for nested, value in zip(("max_speed", "winter_refresh_speed"), speeds):
                    if payload["Motor_Settings"][nested] != value:
                        changed.append(field_name)
                        break
                payload["Motor_Settings"]["max_speed"] = speeds[0]
                payload["Motor_Settings"]["winter_refresh_speed"] = speeds[1]
                continue
            if target == "simple_season":
                mode = SIMPLE_SEASONS.get(raw)
                if mode is None:
                    raise FormFieldError(field_name, "Choisir une des saisons proposées.")
                # Le mode Simple ne fait pas *entrer* en pilotage manuel : cette
                # option n'existe que pour conserver un manuel déjà en place.
                if mode == "manual" and payload["Motor_Settings"]["motor_mode"] != "manual":
                    raise FormFieldError(
                        field_name, "Le pilotage manuel se règle dans le mode avancé.",
                    )
                if payload["Motor_Settings"]["motor_mode"] != mode:
                    changed.append(field_name)
                payload["Motor_Settings"]["motor_mode"] = mode
                continue
            if target in TIME_TARGETS:
                # `<input type="time">` renvoie « HH:MM », mais certains
                # navigateurs ajoutent les secondes : elles sont ignorées.
                try:
                    parts = raw.split(":")
                    hour, minute = int(parts[0]), int(parts[1])
                except (IndexError, ValueError, TypeError):
                    raise FormFieldError(field_name, "Saisir un horaire au format HH:MM.")
                top, prefix = _time_target(section, target)
                if payload[top][f"{prefix}_hour"] != hour or payload[top][f"{prefix}_minute"] != minute:
                    changed.append(field_name)
                payload[top][f"{prefix}_hour"] = hour
                payload[top][f"{prefix}_minute"] = minute
                continue
            top, nested = target
            current = payload[top].get(nested)
            try:
                if isinstance(current, bool):
                    value = raw.lower() in {"enabled", "true", "1", "yes"}
                elif isinstance(current, int):
                    value = int(raw)
                elif isinstance(current, float):
                    value = float(raw)
                else:
                    value = raw
            except ValueError:
                # Le refus vient du typage du formulaire, pas du modèle : sans
                # ce rattachement, il ressortait en message anglais de CPython
                # dans le bandeau global.
                raise FormFieldError(
                    field_name,
                    PYDANTIC_MESSAGES["int_parsing" if isinstance(current, int) else "float_parsing"],
                )
            if current != value:
                changed.append(field_name)
            payload[top][nested] = value

        if section == "simple":
            # Le profil est appliqué **après** les champs saisis : il ne doit
            # jamais écraser une consigne que l'opérateur vient de régler.
            for (top, nested), (value, _label) in SIMPLE_PROFILE.items():
                payload[top][nested] = value

    @staticmethod
    def _profile_changes(before: dict, after: dict) -> list[dict]:
        """Écarts imputables au profil imposé, pas à la saisie.

        Ils sont listés à part : ce sont de vrais paramètres thermiques, et
        l'opérateur doit les voir avant d'enregistrer, pas les découvrir après.
        """
        return [
            {"label": label, "from": before[top].get(nested), "to": after[top].get(nested)}
            for (top, nested), (_value, label) in SIMPLE_PROFILE.items()
            if before[top].get(nested) != after[top].get(nested)
        ]

    async def _equipment_configuration_post(self, form, submitted: dict[str, str]) -> web.Response:
        candidate = {}
        equipment_id = ""
        # Le magasin ne suit pas les écarts : sans cette photo préalable, le
        # compte rendu listerait les 42 champs postés comme « modifiés ».
        previous = {
            key: value.model_dump() for key, value in self.equipment_store.current.items()
        }
        changed_fields: list[str] = []
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
                before = previous.get(equipment_id, {})
                changed_fields.extend(
                    f"{equipment_id}__{field}"
                    for field in _EQUIPMENT_LABELS
                    if before.get(field) != getattr(candidate[equipment_id], field)
                )
            self.equipment_store.save(candidate)
        except OSError:
            return self._conf_refusal(
                "equipment",
                {"__all__": "Écriture impossible : les métadonnées sont inchangées."},
                values=submitted,
                status=500,
            )
        except KeyError as exc:
            return self._conf_refusal(
                "equipment", {str(exc.args[0]): "Ce champ est obligatoire."}, values=submitted,
            )
        except (ValueError, ValidationError) as exc:
            # La validation se fait équipement par équipement : le préfixe manque
            # à la localisation Pydantic, on le rétablit ici.
            errors = {
                f"{equipment_id}__{name}" if name != "__all__" else "__all__": message
                for name, message in self._format_validation_errors(exc, None).items()
            }
            return self._conf_refusal("equipment", errors, values=submitted)
        info("Métadonnées des équipements sauvegardées", name=LOGGER_NAME)
        token = self._store_flash("equipment", changed_fields)
        raise web.HTTPSeeOther(location=f"/conf?flash={token}#equipment")

    async def _sensor_quality_configuration_post(self, form) -> web.Response:
        payload = self.config.model_dump(by_alias=True, mode="json")
        quality = payload.setdefault("Sensor_Quality", {})
        quality.setdefault("profiles", {})
        quality.setdefault("redundancy_groups", {})
        quality.setdefault("ds18b20_bindings", {})
        action = str(form.get("sensor_key", ""))
        reset_key = None
        reset_stats_key = None
        allowed: set[str] = set()
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
            if isinstance(exc, OSError):
                message = "Écriture impossible : la configuration active est inchangée."
            else:
                message = "Qualité capteur refusée : " + " ; ".join(
                    self._format_validation_errors(exc, None).values()
                )
            # La portée est la sous-fiche réellement soumise : les noms de champs
            # (`offset`, `plausible_min`, …) sont identiques d'un capteur à
            # l'autre, une portée unique replacerait la saisie sur toutes.
            return self._conf_refusal(
                "sensor-quality",
                {"__all__": message},
                scope=f"sensor-quality:{action}",
                values={
                    key: str(form[key])
                    for key in sorted(set(form) & allowed)
                    if key not in {"csrf_token", "sensor_key"}
                },
                status=500 if isinstance(exc, OSError) else 422,
            )
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
        token = self._store_flash("sensor-quality", [action])
        raise web.HTTPSeeOther(location=f"/conf?flash={token}#sensor-quality")

    @staticmethod
    def _humanize(item: dict) -> str:
        """Traduit un refus Pydantic en une phrase actionnable.

        Les messages natifs sont anglais et décrivent le *modèle* (« Input should
        be less than or equal to 60 »), pas le geste à faire. Les bornes sont
        réinjectées depuis le `ctx` de l'erreur pour que la phrase porte la
        limite réellement dépassée.
        """
        kind = str(item.get("type", ""))
        if kind == "value_error":
            # Message métier des validateurs de `param/config.py` : déjà français.
            raw = str(item.get("msg", "Valeur invalide"))
            message = raw.split("Value error, ", 1)[-1].strip()
            return (message[:1].upper() + message[1:] + ".") if message else "Valeur invalide."
        template = PYDANTIC_MESSAGES.get(kind)
        if template is None:
            return "Valeur refusée."
        try:
            return template.format(**(item.get("ctx") or {}))
        except (KeyError, IndexError, ValueError):
            return template

    @classmethod
    def _format_validation_errors(cls, exc: Exception, section: str | None) -> dict[str, str]:
        """Localise chaque refus sur le champ que l'opérateur a saisi.

        Trois cas : un refus de champ imbriqué (`Section_JSON.clé`) retrouve son
        champ par l'index inverse du registre ; un refus de validateur de modèle
        ne désigne que la section et se rattache aux deux champs de la contrainte
        croisée ; le reste reste global.
        """
        if isinstance(exc, FormFieldError):
            return {exc.field: exc.message}
        if not isinstance(exc, ValidationError):
            return {"__all__": str(exc)}
        index = PAYLOAD_INDEX.get(section or "", {})
        known = SECTION_FIELDS.get(section or "", {})
        errors: dict[str, str] = {}
        for item in exc.errors(include_url=False):
            loc = tuple(str(part) for part in item.get("loc", ()))
            message = cls._humanize(item)
            targets: tuple[str, ...] = ()
            if len(loc) >= 2:
                field = index.get(f"{loc[0]}.{loc[1]}")
                targets = (field,) if field else ()
            elif len(loc) == 1:
                for marker, fields, explanation in CROSS_CONSTRAINTS.get(loc[0], ()):
                    if marker in str(item.get("msg", "")):
                        targets = tuple(name for name in fields if name in known)
                        message = explanation
                        break
            if targets:
                for name in targets:
                    errors.setdefault(name, message)
            else:
                errors.setdefault(".".join(loc) or "__all__", message)
        return errors

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
            definition = SENSORS_BY_KEY.get(key)
            stats.append({
                "key": key,
                # Les min/max sont mémorisés en précision complète ; le nombre
                # de décimales voyage avec eux pour que l'affichage arrondisse.
                "decimals": definition.decimals if definition else 1,
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
