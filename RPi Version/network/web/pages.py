# controller/web/pages.py
# Author: Progradius
# License: AGPL-3.0

from jinja2 import Environment, FileSystemLoader
from param.config import AppConfig
from typing import get_origin, get_args, Literal
from datetime import datetime
import RPi.GPIO as GPIO
import os

# Initialisation de Jinja2 (répertoire templates)
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))


def render_template(template_name: str, **context) -> str:
    template = env.get_template(template_name)
    return template.render(**context)


def _render_field(name: str, value, annotation) -> str:
    """
    Génère le HTML approprié pour un champ donné en fonction de son type.
    """
    # Les champs 'motor_mode' et 'mode' sont gérés manuellement dans les templates
    if name.endswith(".motor_mode") or name.endswith(".mode"):
        return ""

    # Gestion des champs avec des valeurs littérales (énumérations)
    if get_origin(annotation) is Literal:
        opts = get_args(annotation)
        html = [f'<select name="{name}">']
        for opt in opts:
            sel = ' selected' if value == opt else ''
            html.append(f'  <option value="{opt}"{sel}>{opt}</option>')
        html.append('</select>')
        return "\n".join(html)

    # Gestion des champs booléens
    if annotation is bool:
        sel_en = ' selected' if value else ''
        sel_dis = ' selected' if not value else ''
        return (
            f'<select name="{name}">'
            f'<option value="enabled"{sel_en}>Enabled</option>'
            f'<option value="disabled"{sel_dis}>Disabled</option>'
            '</select>'
        )

    # Gestion des champs numériques
    if annotation in (int, float):
        step = ' step="0.1"' if annotation is float else ''
        return f'<input type="number" name="{name}" value="{value}"{step}>'

    # Champ texte par défaut
    return f'<input type="text" name="{name}" value="{value}">'


def main_page(controller_status, sensor_handler, stats, config: AppConfig) -> str:
    """
    Génère la page principale affichant l'état des composants et les statistiques.
    """
    def gpio_state(pin: int) -> str:
        try:
            return "On" if GPIO.input(pin) == GPIO.LOW else "Off"
        except:
            return "—"

    # Configuration des minuteurs journaliers
    dt1 = config.daily_timer1
    dt2 = config.daily_timer2
    dt1_sched = f"{dt1.start_hour:02d}:{dt1.start_minute:02d} → {dt1.stop_hour:02d}:{dt1.stop_minute:02d}"
    dt2_sched = f"{dt2.start_hour:02d}:{dt2.start_minute:02d} → {dt2.stop_hour:02d}:{dt2.stop_minute:02d}"

    dt1_state = gpio_state(config.gpio.dailytimer1_pin)
    dt2_state = gpio_state(config.gpio.dailytimer2_pin)

    # Descriptions des modes cycliques
    def describe_cyclic(cyc):
        if cyc.mode == "journalier":
            return (
                "Mode : Journalier<br>"
                f"Période : {cyc.period_days} jour(s)<br>"
                f"Actions/jour : {cyc.triggers_per_day}<br>"
                f"Premier : {cyc.first_trigger_hour}h00<br>"
                f"Durée : {cyc.action_duration_seconds}s"
            )
        else:
            return (
                "Mode : Séquentiel<br>"
                f"Jour - ON {cyc.on_time_day}s / OFF {cyc.off_time_day}s<br>"
                f"Nuit - ON {cyc.on_time_night}s / OFF {cyc.off_time_night}s"
            )

    cyc1 = config.cyclic1
    cyc2 = config.cyclic2
    cyc1_desc = describe_cyclic(cyc1)
    cyc2_desc = describe_cyclic(cyc2)

    cyc1_state = gpio_state(config.gpio.cyclic1_pin)
    cyc2_state = gpio_state(config.gpio.cyclic2_pin)

    # État du chauffage
    heater_state = gpio_state(config.gpio.heater_pin)

    # Historique Min/Max des capteurs
    temps = []
    for key in ("BME280T", "DS18B#1", "DS18B#2", "DS18B#3", "MLX-AMB", "MLX-OBJ"):
        s = stats.get_all().get(key)
        if s:
            min_date = s.get("min_date")
            max_date = s.get("max_date")
            try:
                dmin = datetime.fromisoformat(min_date).strftime("%d/%m %H:%M") if min_date else "—"
            except Exception:
                dmin = "—"
            try:
                dmax = datetime.fromisoformat(max_date).strftime("%d/%m %H:%M") if max_date else "—"
            except Exception:
                dmax = "—"
            min_val = f"{s['min']:.1f}" if s.get("min") is not None else "—"
            max_val = f"{s['max']:.1f}" if s.get("max") is not None else "—"
            temps.append(
                f"<p><strong>{key}</strong> : Min {min_val}°C le {dmin} — Max {max_val}°C le {dmax}</p>"
            )
    temps_html = "\n".join(temps) or "<p>Aucune donnée</p>"

    # Liste des capteurs actifs
    sensors_list = [
        (name, "On" if getattr(sensor, "enabled", False) else "Off")
        for name, sensor in sensor_handler.sensor_dict.items()
    ]

    return render_template(
        "main.html",
        dt1_sched=dt1_sched,
        dt2_sched=dt2_sched,
        dt1_state=dt1_state,
        dt2_state=dt2_state,
        cyc1_desc=cyc1_desc,
        cyc2_desc=cyc2_desc,
        cyc1_state=cyc1_state,
        cyc2_state=cyc2_state,
        heater_state=heater_state,
        temps_html=temps_html,
        sensors_list=sensors_list
    )

def conf_page(config: AppConfig) -> str:
    """
    Génère la page de configuration en regroupant les paramètres par sections.
    """
    sections = []

    for section_name, field_info in config.model_fields.items():
        alias = field_info.alias or section_name
        section_obj = getattr(config, section_name)

        # Section Temperature_Settings
        if alias == "Temperature_Settings":
            fields = []
            for attr, fld in section_obj.model_fields.items():
                val = getattr(section_obj, attr)
                fields.append({
                    "name": f"{alias}.{(fld.alias or attr)}",
                    "label": fld.alias or attr,
                    "input_html": _render_field(f"{alias}.{(fld.alias or attr)}", val, fld.annotation)
                })
            sections.append({
                "type": "default",
                "title": "Temperature Settings",
                "fields": fields
            })
            continue

        # Section Heater_Settings
        if alias == "Heater_Settings":
            sections.append({
                "type": "heater",
                "title": "Heater",
                "enabled": "enabled" if section_obj.enabled else "disabled"
            })
            continue

        # Section Motor_Settings
        if alias == "Motor_Settings":
            sections.append({
                "type": "motor",
                "title": "Motor",
                "mode": section_obj.motor_mode,
                "user_speed": section_obj.motor_user_speed
            })
            continue

        # Sections Cyclic*_Settings
        if alias.startswith("Cyclic"):
            mode = section_obj.mode
            journalier_fields = []
            for attr in ("period_days", "triggers_per_day", "first_trigger_hour", "action_duration_seconds"):
                fld = section_obj.__class__.model_fields[attr]
                val = getattr(section_obj, attr)
                journalier_fields.append({
                    "name": f"{alias}.{(fld.alias or attr)}",
                    "label": fld.alias or attr,
                    "input_html": _render_field(f"{alias}.{(fld.alias or attr)}", val, fld.annotation)
                })
            sequentiel_fields = []
            for attr in ("on_time_day", "off_time_day", "on_time_night", "off_time_night"):
                fld = section_obj.__class__.model_fields[attr]
                val = getattr(section_obj, attr)
                sequentiel_fields.append({
                    "name": f"{alias}.{(fld.alias or attr)}",
                    "label": fld.alias or attr,
                    "input_html": _render_field(f"{alias}.{(fld.alias or attr)}", val, fld.annotation)
                })
            sections.append({
                "type": "cyclic",
                "title": alias,
                "id": alias,
                "mode": mode,
                "journalier_fields": journalier_fields,
                "sequentiel_fields": sequentiel_fields
            })
            continue

        # Section Sensor_State
        if alias == "Sensor_State":
            sensors = []
            for attr, fld in section_obj.model_fields.items():
                val = getattr(section_obj, attr)
                sensors.append({
                    "attr": fld.alias or attr,
                    "enabled": val
                })
            sections.append({
                "type": "sensor_state",
                "title": "Sensors",
                "id": alias,
                "sensors": sensors
            })
            continue

        # Autres sections par défaut
        fields = []
        for attr, fld in section_obj.model_fields.items():
            val = getattr(section_obj, attr)
            fields.append({
                "name": f"{alias}.{(fld.alias or attr)}",
                "label": fld.alias or attr,
                "input_html": _render_field(f"{alias}.{(fld.alias or attr)}", val, fld.annotation)
            })
        sections.append({
            "type": "default",
            "title": alias,
            "fields": fields
        })

    return render_template("conf.html", sections=sections)

def monitor_page(sensor_handler, stats, config: AppConfig, controller_status=None) -> str:
    def gpio_state(pin: int) -> str:
        try:
            return "On" if GPIO.input(pin) == GPIO.LOW else "Off"
        except:
            return "—"

    def fmt_d(dt: str) -> str:
        return datetime.fromisoformat(dt).strftime("%d/%m/%Y %H:%M:%S") if dt else "—"

    # Timers GPIO
    timers = {
        "DailyTimer #1": gpio_state(config.gpio.dailytimer1_pin),
        "DailyTimer #2": gpio_state(config.gpio.dailytimer2_pin),
        "Cyclic #1": gpio_state(config.gpio.cyclic1_pin),
        "Cyclic #2": gpio_state(config.gpio.cyclic2_pin),
    }

    # Motor power
    motor_pins = [
        config.gpio.motor_pin1, config.gpio.motor_pin2,
        config.gpio.motor_pin3, config.gpio.motor_pin4
    ]
    for p in motor_pins:
        GPIO.setup(p, GPIO.IN)

    speed = controller_status.get_motor_speed() if controller_status else 0
    percent = int(speed / 4 * 100)

    # Capteurs
    units = {
        "BME280T": "°C", "BME280H": "%", "BME280P": "hPa",
        "DS18B#1": "°C", "DS18B#2": "°C", "DS18B#3": "°C",
        "MLX-AMB": "°C", "MLX-OBJ": "°C",
        "VL53-DIST": "mm", "HCSR-DIST": "cm", "TSL-LUX": "lx",
    }
    sensors = {
        name: (f"{val:.1f}", unit) if isinstance(val := sensor_handler.get_sensor_value(name), (int, float))
        else ("—", unit)
        for name, unit in units.items()
    }

    # Historique min/max
    stats_data = {
        name: {
            "min": f"{s['min']:.1f}" if isinstance(s["min"], (int, float)) else "—",
            "min_date": fmt_d(s["min_date"]),
            "max": f"{s['max']:.1f}" if isinstance(s["max"], (int, float)) else "—",
            "max_date": fmt_d(s["max_date"]),
        }
        for name, s in stats.get_all().items()
    }

    # GPIO States
    gpio_states = {
        "DailyTimer #1": gpio_state(config.gpio.dailytimer1_pin),
        "DailyTimer #2": gpio_state(config.gpio.dailytimer2_pin),
        "Cyclic #1": gpio_state(config.gpio.cyclic1_pin),
        "Heater": gpio_state(config.gpio.heater_pin),
        "Motor Pin 1": gpio_state(config.gpio.motor_pin1),
    }

    return render_template(
        "monitor.html",
        timers=timers,
        motor_speed=speed,
        motor_percent=percent,
        sensors=sensors,
        stats=stats_data,
        gpio_states=gpio_states
    )


def console_page() -> str:
    return render_template("console.html")