"""Rendu des pages HTML de l'interface locale."""

from __future__ import annotations

import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from controllers.sensor_catalog import SENSOR_CATALOG


WEB_DIR = Path(__file__).parent
TEMPLATE_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(("html", "xml")),
)


def _asset_versions() -> dict[str, str]:
    assets = {
        "style": STATIC_DIR / "css" / "style.css",
        "dashboard": STATIC_DIR / "js" / "dashboard.js",
        "config": STATIC_DIR / "js" / "config.js",
        "console": STATIC_DIR / "js" / "console.js",
        "font": STATIC_DIR / "fonts" / "visitor1.ttf",
        "favicon": STATIC_DIR / "favicon.svg",
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


def render_template(template_name: str, **context) -> str:
    template = env.get_template(template_name)
    return template.render(asset_versions=ASSET_VERSIONS, **context)


def main_page(state: dict, csrf_token: str) -> str:
    return render_template(
        "main.html",
        page_title="Tableau de bord",
        current_page="dashboard",
        state=state,
        csrf_token=csrf_token,
    )


def conf_page(
    config,
    csrf_token: str,
    *,
    success: str | None = None,
    errors: dict[str, str] | None = None,
    active_section: str | None = None,
    equipment=None,
) -> str:
    return render_template(
        "conf.html",
        page_title="Configuration",
        current_page="config",
        config=config,
        csrf_token=csrf_token,
        success=success,
        errors=errors or {},
        active_section=active_section,
        sensor_catalog=SENSOR_CATALOG,
        wifi_password_set=bool(config.network.wifi_password),
        influx_user_set=bool(config.network.influx_db_user),
        influx_password_set=bool(config.network.influx_db_password),
        gpio_fields=[
            (name, getattr(config.gpio, name))
            for name in config.gpio.__class__.model_fields
        ],
        equipment=equipment or {},
    )


def console_page(csrf_token: str) -> str:
    return render_template(
        "console.html",
        page_title="Console",
        current_page="console",
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
