"""Rendu des pages HTML de l'interface locale."""

from __future__ import annotations

import hashlib
import os
import socket
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from controllers.sensor_catalog import SENSOR_CATALOG, effective_quality_profile
from utils.overrides import shared_overrides


WEB_DIR = Path(__file__).parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(("html", "xml")),
)


def _mesure(value, decimals=1) -> str:
    """Arrondit une mesure pour l'affichage seulement.

    L'acquisition et la politique qualité travaillent en précision complète :
    c'est ici, et nulle part en amont, que la valeur est réduite au nombre de
    décimales du catalogue. Le rendu doit rester identique à celui de
    `dashboard.js` (`toFixed`), sinon la première peinture et le premier
    rafraîchissement afficheraient deux valeurs différentes.
    """
    try:
        places = int(decimals)
    except (TypeError, ValueError):
        places = 1
    try:
        return f"{float(value):.{places}f}"
    except (TypeError, ValueError):
        return "—"


env.filters["mesure"] = _mesure


def _asset_versions() -> dict[str, str]:
    assets = {
        "style": STATIC_DIR / "css" / "style.css",
        "dashboard": STATIC_DIR / "js" / "dashboard.js",
        "config": STATIC_DIR / "js" / "config.js",
        "console": STATIC_DIR / "js" / "console.js",
        "system": STATIC_DIR / "js" / "system.js",
        "alarms": STATIC_DIR / "js" / "alarms.js",
        "history": STATIC_DIR / "js" / "history.js",
        "pwa": STATIC_DIR / "js" / "pwa.js",
        "service_worker": STATIC_DIR / "service-worker.js",
        "font": STATIC_DIR / "fonts" / "visitor1.ttf",
        "favicon": STATIC_DIR / "favicon.svg",
        "icon_192": STATIC_DIR / "icons" / "pwa-192.png",
        "icon_512": STATIC_DIR / "icons" / "pwa-512.png",
        "icon_maskable": STATIC_DIR / "icons" / "pwa-maskable-512.png",
        "equipment_icons": STATIC_DIR / "equipment-icons.svg",
    }
    versions = {}
    for name, path in assets.items():
        try:
            versions[name] = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        except OSError:
            versions[name] = "missing"
    return versions


ASSET_VERSIONS = _asset_versions()
PWA_CACHE_VERSION = hashlib.sha256(
    "|".join(f"{key}:{value}" for key, value in sorted(ASSET_VERSIONS.items())).encode()
).hexdigest()[:16]


def _pwa_url() -> str:
    hostname = socket.gethostname().lower()
    try:
        port = int(os.getenv("PHYTO_HTTPS_PORT", "0"))
    except ValueError:
        port = 0
    suffix = "" if port in {0, 443} else f":{port}"
    return f"https://{hostname}.local{suffix}/"


def _pwa_https_configured() -> bool:
    try:
        port = int(os.getenv("PHYTO_HTTPS_PORT", "0"))
    except ValueError:
        return False
    return bool(
        port > 0
        and os.getenv("PHYTO_TLS_CERT_FILE", "").strip()
        and os.getenv("PHYTO_TLS_KEY_FILE", "").strip()
    )


def _override_summary() -> dict | None:
    """
    Résumé des forçages pour la bannière globale. Lecture en mémoire, sans I/O,
    et jamais fatale : une bannière absente vaut mieux qu'une page qui ne rend
    pas. Elle est calculée ici et non passée par chaque appelant pour être
    réellement globale — console et alarmes comprises.
    """
    try:
        return shared_overrides().payload()
    except Exception:
        return None


def render_template(template_name: str, **context) -> str:
    template = env.get_template(template_name)
    context.setdefault("alarm_summary", None)
    context.setdefault("override_summary", _override_summary())
    context.setdefault("pwa_url", _pwa_url())
    context.setdefault("pwa_https_configured", _pwa_https_configured())
    return template.render(asset_versions=ASSET_VERSIONS, **context)


def main_page(state: dict, csrf_token: str) -> str:
    return render_template(
        "main.html",
        page_title="Tableau de bord",
        current_page="dashboard",
        state=state,
        alarm_summary=state.get("alarms"),
        csrf_token=csrf_token,
    )


def conf_page(
    config,
    csrf_token: str,
    *,
    success: str | None = None,
    flash: dict | None = None,
    errors: dict[str, str] | None = None,
    field_errors: dict[str, dict[str, str]] | None = None,
    form_values: dict[str, dict[str, str]] | None = None,
    active_section: str | None = None,
    equipment=None,
    alarm_summary=None,
    sensor_snapshot=None,
    discovered_ds18=None,
    simple=None,
) -> str:
    # `form_values` et `field_errors` sont indexés par **portée** de formulaire —
    # l'identifiant de section, ou `sensor-quality:<clé capteur>` pour les
    # sous-fiches. Les noms de champs se répètent d'une section à l'autre
    # (`enabled`, `mode`, `start_time`) : sans portée, la saisie refusée d'une
    # section réapparaîtrait dans une autre.
    values = form_values or {}
    field_messages = field_errors or {}

    def form_value(scope: str, name: str, current):
        """Valeur à afficher : la saisie refusée si elle existe, sinon la config."""
        return values.get(scope, {}).get(name, current)

    def field_error(scope: str, name: str):
        return field_messages.get(scope, {}).get(name)

    return render_template(
        "conf.html",
        page_title="Configuration",
        current_page="config",
        config=config,
        csrf_token=csrf_token,
        success=success,
        flash=flash,
        errors=errors or {},
        form_value=form_value,
        field_error=field_error,
        error_count=len(errors or {}) + sum(len(item) for item in field_messages.values()),
        active_section=active_section,
        sensor_catalog=SENSOR_CATALOG,
        sensor_quality_profiles={
            definition.key: effective_quality_profile(config, definition)
            for definition in SENSOR_CATALOG
        },
        sensor_snapshot=sensor_snapshot or {},
        discovered_ds18=discovered_ds18 or [],
        wifi_password_set=bool(config.network.wifi_password),
        influx_user_set=bool(config.network.influx_db_user),
        influx_password_set=bool(config.network.influx_db_password),
        gpio_fields=[
            (name, getattr(config.gpio, name))
            for name in config.gpio.__class__.model_fields
        ],
        equipment=equipment or {},
        alarm_summary=alarm_summary,
        simple=simple or {},
    )


SYSTEM_ACTIONS = {
    "reboot": ("Redémarrage en cours", "Redémarrage"),
    "poweroff": ("Extinction en cours", "Extinction"),
}


def system_action_page(action: str, csrf_token: str) -> str:
    """
    Page de suivi rendue **avant** que la commande ne parte. Le navigateur y
    observe `/health/live` : c'est la seule détection d'échec qui reste une fois
    la réponse partie en 202.
    """
    title, label = SYSTEM_ACTIONS.get(action, SYSTEM_ACTIONS["reboot"])
    return render_template(
        "system_action.html",
        page_title=title,
        current_page="dashboard",
        action=action,
        action_label=label,
        csrf_token=csrf_token,
    )


def console_page(csrf_token: str, *, alarm_summary=None) -> str:
    return render_template(
        "console.html",
        page_title="Console",
        current_page="console",
        csrf_token=csrf_token,
        alarm_summary=alarm_summary,
    )


def alarms_page(
    alarms: list[dict], filters: dict, alarm_summary: dict, csrf_token: str
) -> str:
    return render_template(
        "alarms.html",
        page_title="Alarmes",
        current_page="alarms",
        alarms=alarms,
        filters=filters,
        alarm_summary=alarm_summary,
        csrf_token=csrf_token,
    )


def error_page(status: int, title: str, message: str) -> str:
    return render_template(
        "error.html",
        page_title=title,
        current_page=None,
        status=status,
        title=title,
        message=message,
    )


def offline_page() -> str:
    return render_template(
        "offline.html",
        page_title="Hors ligne",
        current_page="offline",
        csrf_token=None,
    )
