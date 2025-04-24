# controller/web/pages.py
# Author: Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Génère les pages HTML (aucune logique réseau ici)
# -------------------------------------------------------------

from datetime import datetime
import RPi.GPIO as GPIO
from typing import get_origin, get_args, Literal
from param.config import AppConfig

# ──────────────────────────────────────────────────────────────
# Réglages de taille de police (à modifier selon vos préférences)
# ──────────────────────────────────────────────────────────────
BODY_FONT_SIZE   = "1.5rem"    # taille du texte normal
HEADER_FONT_SIZE = "2rem"  # taille des titres h1, h2 et legend

# -------------------------------------------------------------
#  En-tête / pied de page HTML
# -------------------------------------------------------------
html_header = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet">
  <style>
    /* Reset basique */
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      background: #000;
      color: #eee;
      font-family: "Courier New", monospace;
      font-size: {BODY_FONT_SIZE};
      line-height: 1.4;
      padding: 1rem;
    }}
    hr {{ border:0; border-top:3px solid #fff; margin:10px 0; }}
    .mainwrap {{
      background: rgba(0,0,0,.7);
      margin: 5px 0;
      padding:10px;
    }}
    .formwrap {{
      background: rgba(0,0,0,.7);
      margin:20px 0;
      padding:10px;
    }}
    h1 {{
      font-size: {HEADER_FONT_SIZE};
      margin-bottom:0.5rem;
    }}
    h2 {{
      font-size: {HEADER_FONT_SIZE};
      margin-bottom:0.5rem;
    }}
    legend {{
      font-size: {HEADER_FONT_SIZE};
      margin-bottom:0.5rem;
    }}
    label {{
      display:block;
      margin-top:0.5rem;
      font-size: {BODY_FONT_SIZE};
    }}
    input, select {{
      font-family:"Courier New", monospace;
      font-size:{BODY_FONT_SIZE};
      color:#FCF7EE;
      background:transparent;
      border:1px solid #fff;
      width:100%;
      padding:6px;
      margin-top:4px;
    }}
    .button_base {{
      display:block;
      width:100%;
      max-width:200px;
      margin:10px auto;
      padding:8px;
      text-align:center;
      background:#fff;
      color:#000;
      text-transform:uppercase;
      cursor:pointer;
      border:1px solid #000;
    }}
    .button_base:hover {{
      background:transparent;
      color:#fff;
      border:1px solid #fff;
    }}
    .div_center {{ text-align:center; margin-top:1rem; }}
    fieldset {{
      border:1px solid #fff;
      padding:10px;
      margin-bottom:20px;
    }}
    .navbar {{
      margin-bottom:20px;
      font-family:"Courier New", monospace;
    }}
    .navbar a {{
      color:#fff;
      margin-right:15px;
      text-decoration:none;
    }}
    .row {{ display:flex; flex-wrap:wrap; margin:-0.5rem; }}
    .col {{ flex:1; min-width:200px; padding:0.5rem; }}
    @media (max-width: 600px) {{
      .row {{ flex-direction:column; }}
      .col {{ min-width:100%; }}
      body {{ padding:0.5rem; }}
      .navbar {{ font-size:0.9rem; }}
    }}
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="navbar">
    <a href="/">System State</a> |
    <a href="/monitor">Monitored Values</a> |
    <a href="/conf">Configuration</a> |
  <a href="/console">Console</a>
  </div>
"""

html_footer = """
</div>
</body>
</html>
"""

GPIO.setmode(GPIO.BCM)

# -------------------------------------------------------------
#  Helper : rend un <input> / <select> adapté à l’annotation
# -------------------------------------------------------------
def _render_field(name: str, value, annotation) -> str:
    # Literal[...] → <select>
    if get_origin(annotation) is Literal:
        opts = get_args(annotation)
        html = [f'<select name="{name}">']
        for opt in opts:
            sel = ' selected' if value == opt else ''
            html.append(f'  <option value="{opt}"{sel}>{opt}</option>')
        html.append('</select>')
        return "\n".join(html)

    # bool → Enabled/Disabled
    if annotation is bool:
        sel_en = ' selected' if value else ''
        sel_dis = ' selected' if not value else ''
        return (
            f'<select name="{name}">'
            f'<option value="enabled"{sel_en}>Enabled</option>'
            f'<option value="disabled"{sel_dis}>Disabled</option>'
            f'</select>'
        )

    # int/float → <input type="number">
    if annotation in (int, float):
        step = ' step="0.1"' if annotation is float else ''
        return f'<input type="number" name="{name}" value="{value}"{step}>'

    # fallback → <input type="text">
    return f'<input type="text" name="{name}" value="{value}">'

# ==============================================================
#  PAGE PRINCIPALE  (état système)
# ==============================================================
def main_page(controller_status) -> str:
    start = controller_status.get_dailytimer_current_start_time()
    stop  = controller_status.get_dailytimer_current_stop_time()
    state = controller_status.get_component_state()

    cfg = AppConfig.load().cyclic1
    if cfg.mode == "journalier":
        cyc_desc = (
            "Mode : Journalier<br>"
            f"Période : {cfg.period_days} jour{'s' if cfg.period_days > 1 else ''}<br>"
            f"Actions / jour : {cfg.triggers_per_day}<br>"
            f"Premier déclenchement : {cfg.first_trigger_hour}h00<br>"
            f"Durée action : {cfg.action_duration_seconds}s"
        )
    else:
        cyc_desc = (
            "Mode : Séquentiel<br>"
            f"Jour – ON {cfg.on_time_day}s / OFF {cfg.off_time_day}s<br>"
            f"Nuit – ON {cfg.on_time_night}s / OFF {cfg.off_time_night}s"
        )

    return f"""{html_header}
<div class="row">
  <div class="col">
    <div class="mainwrap"><h1>DailyTimer #1</h1><hr>
      <h2>Start : {start}</h2>
      <h2>Stop  : {stop}</h2>
    </div>
  </div>
  <div class="col">
    <div class="mainwrap"><h1>Cyclic #1</h1><hr>
      <h2 style="font-size:1rem;line-height:1.3;">{cyc_desc}</h2>
    </div>
  </div>
</div>
<div class="row">
  <div class="col">
    <div class="mainwrap"><h1>Component #1</h1><hr>
      <h2>State : {state}</h2>
    </div>
  </div>
</div>
{html_footer}"""

# ==============================================================
#  PAGE CONFIGURATION  (formulaire auto-généré)
# ==============================================================
def conf_page(config: AppConfig) -> str:
    html = [html_header, '<form method="post" action="/conf">']
    sections = list(config.model_fields.items())
    for idx, (section_name, field_info) in enumerate(sections):
        if idx % 3 == 0:
            html.append('<div class="row">')
        alias = field_info.alias or section_name
        section_obj = getattr(config, section_name)
        html.append('<div class="col"><fieldset>')
        html.append(f'<legend>{alias}</legend>')
        for attr_name, fld in section_obj.model_fields.items():
            fld_alias      = fld.alias or attr_name
            fld_annotation = fld.annotation
            fld_value      = getattr(section_obj, attr_name)
            input_name     = f"{alias}.{fld_alias}"
            html.append(f'<label for="{input_name}">{fld_alias}</label>')
            html.append(_render_field(input_name, fld_value, fld_annotation))
        html.append('</fieldset></div>')
        if idx % 3 == 2 or idx == len(sections) - 1:
            html.append('</div>')
    html.append('<div class="div_center"><button class="button_base" type="submit">Save configuration</button></div>')
    html.append('</form>')
    html.append(html_footer)
    return "\n".join(html)

# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques + GPIO + actions sys.
# ==============================================================
def monitor_page(sensor_handler, stats, config: AppConfig, controller_status=None) -> str:
    _fmt   = lambda v,u: f"{v:.1f}&nbsp;{u}" if isinstance(v, (int, float)) else "―"
    _stat  = lambda v  : f"{v:.1f}"          if isinstance(v, (int, float)) else "—"
    _fmt_d = lambda dt : datetime.fromisoformat(dt).strftime("%d/%m/%Y %H:%M:%S") if dt else "—"

    def _state(pin):
        try:
            return "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
        except:
            return "—"

    timers_state = {
        "DailyTimer #1": _state(config.gpio.dailytimer1_pin),
        "DailyTimer #2": _state(config.gpio.dailytimer2_pin),
        "Cyclic #1":     _state(config.gpio.cyclic1_pin),
        "Cyclic #2":     _state(config.gpio.cyclic2_pin),
    }

    motor_pins = [
        config.gpio.motor_pin1,
        config.gpio.motor_pin2,
        config.gpio.motor_pin3,
        config.gpio.motor_pin4,
    ]
    try:
        speed = next(i+1 for i,p in enumerate(motor_pins) if GPIO.input(p) == GPIO.HIGH)
    except:
        speed = 0
    pct = int(speed / 4 * 100)

    html = [html_header, '<div class="row">']
    html.append('  <div class="col"><div class="mainwrap"><h1>Timers state</h1><hr>')
    for name, st in timers_state.items():
        html.append(f"    <p>{name} : {st}</p>")
    html.append('  </div></div>')
    html.append(f'''
  <div class="col"><div class="mainwrap"><h1>Motor power</h1><hr>
    <p>Level : {speed} / 4</p>
    <div style="background:#555;width:100%;height:20px;">
      <div style="background:#0f0;height:20px;width:{pct}%"></div>
    </div>
  </div></div></div>''')

    readings = {
        "BME280T": "°C", "BME280H": "%",  "BME280P": "hPa",
        "DS18B#1": "°C", "DS18B#2": "°C", "DS18B#3": "°C",
        "MLX-AMB": "°C", "MLX-OBJ": "°C",
        "VL53-DIST": "mm", "HCSR-DIST": "cm", "TSL-LUX": "lx",
    }
    html.append('<div class="row">')
    for key, unit in readings.items():
        val = sensor_handler.get_sensor_value(key)
        html.append(
            f'<div class="col"><div class="mainwrap">'
            f'<h1>{key}</h1><hr><h2>{_fmt(val, unit)}</h2>'
            f'</div></div>'
        )
    html.append('</div>')

    html.append('<div class="formwrap"><h1>Historique min/max</h1><hr>')
    for key, s in stats.get_all().items():
        html.append(f'<h2>{key}</h2>')
        html.append(f'<p>Min : {_stat(s["min"])} le {_fmt_d(s["min_date"])}</p>')
        html.append(f'<p>Max : {_stat(s["max"])} le {_fmt_d(s["max_date"])}</p>')
        html.append(f'''
<form method="get" action="/monitor">
  <input type="hidden" name="reset_{key.replace("#","")}" value="1">
  <button class="button_base" type="submit">Reset {key}</button>
</form><hr>''')
    html.append('</div>')

    gpio = config.gpio
    html.append('<div class="formwrap"><h1>GPIO States</h1><hr><ul>')
    for name, pin in {
        "DailyTimer #1": gpio.dailytimer1_pin,
        "DailyTimer #2": gpio.dailytimer2_pin,
        "Cyclic #1":     gpio.cyclic1_pin,
        "Heater":        gpio.heater_pin,
        "Motor Pin 1":   gpio.motor_pin1,
    }.items():
        try:
            st = "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
        except:
            st = "—"
        html.append(f'<li>{name} (pin {pin}): {st}</li>')
    html.append('</ul></div>')

    html.append('<div class="formwrap"><h1>Actions système</h1><hr>')
    html.append('''
<form method="get" action="/monitor">
  <input type="hidden" name="shutdown" value="1">
  <button class="button_base" type="submit">Éteindre le Raspberry Pi</button>
</form>
<form method="get" action="/monitor">
  <input type="hidden" name="reboot" value="1">
  <button class="button_base" type="submit">Redémarrer le Raspberry Pi</button>
</form>
''')
    html.append(html_footer)
    return "\n".join(html)

def console_page() -> str:
    return f"""{html_header}
<div class="row">
  <div class="col" style="height:80vh; padding:0;">
    <div id="terminal" style="width:100%; height:100%; background:#000;"></div>
  </div>
</div>
<!-- xterm.css et xterm.js depuis un CDN -->
<link rel="stylesheet" href="https://unpkg.com/xterm/css/xterm.css" />
<script src="https://unpkg.com/xterm/lib/xterm.js"></script>
<script>
  document.addEventListener("DOMContentLoaded", () => {{
    // 1) Créer et ouvrir le terminal
    const term = new Terminal({{ convertEol: true }});
    term.open(document.getElementById('terminal'));
    term.focus();

    // 2) Se connecter au flux SSE
    const evtSource = new EventSource('/console/stream');
    evtSource.onmessage = ev => {{
      // ev.data contient la ligne brute avec codes ANSI
      term.write(ev.data + '\\r\\n');
    }};
    evtSource.onerror = err => {{
      console.error("Erreur SSE:", err);
      evtSource.close();
    }};
  }});
</script>
{html_footer}"""
