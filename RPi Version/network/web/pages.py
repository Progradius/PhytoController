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
from datetime import datetime
import RPi.GPIO as GPIO
from typing import get_origin, get_args, Literal
from param.config import AppConfig

# ──────────────────────────────────────────────────────────────
# Réglages de taille de police (à modifier selon vos préférences)
# ──────────────────────────────────────────────────────────────
BODY_FONT_SIZE   = "1.5rem"    # taille du texte normal
HEADER_FONT_SIZE = "2rem"      # taille des titres h1, h2 et legend

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
    /* Reset & global */
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      background: #000; color: #eee;
      font-family: "Courier New", monospace;
      font-size: {BODY_FONT_SIZE}; line-height:1.4;
      padding:1rem;
    }}
    a {{ color:inherit; text-decoration:none; }}
    hr {{ border:0; border-top:3px solid #fff; margin:10px 0; }}

    /* Navbar */
    .navbar {{ margin-bottom:1rem; font-size:1.2rem; }}
    .navbar a {{ margin-right:1rem; }}

    /* Conteneurs */
    .mainwrap, .formwrap {{ background:rgba(0,0,0,0.7); padding:1rem; border:1px solid #fff; border-radius:6px; }}
    .formwrap {{ margin:1rem 0; }}

    /* Titres */
    h1,h2,legend {{
      font-size: {HEADER_FONT_SIZE};
      margin-bottom:0.5rem;
      font-weight:normal;
    }}

    /* Champs */
    label {{ display:block; margin-top:0.5rem; font-size:{BODY_FONT_SIZE}; }}
    input, select {{
      width:100%; padding:0.5rem; margin-top:0.3rem;
      background:transparent; border:1px solid #fff;
      font-family:"Courier New", monospace; font-size:{BODY_FONT_SIZE};
      color:#FCF7EE; border-radius:4px;
    }}

    /* Boutons */
    .button_base, .button_param {{
      display:block; width:100%; max-width:200px;
      margin:1rem auto 0; padding:0.6rem; text-align:center;
      background:#fff; color:#000; text-transform:uppercase;
      border:1px solid #000; border-radius:4px; cursor:pointer;
    }}
    .button_base:hover, .button_param:hover {{
      background:transparent; color:#fff; border-color:#fff;
    }}

    /* Scroll-snap horizontal pour les cartes */
    .scroll-container {{
      display:flex; overflow-x:auto; scroll-snap-type:x mandatory;
      -webkit-overflow-scrolling: touch; padding-bottom:1rem; margin:1rem 0;
    }}
    .card {{
      flex:0 0 300px; min-width:250px; margin-right:1rem;
      scroll-snap-align:start; background:rgba(0,0,0,0.8);
      border:1px solid #fff; border-radius:6px; padding:1rem;
      position:relative;
    }}
    .card:last-child {{ margin-right:0; }}

    /* Responsive */
    @media(max-width:600px){{
      .navbar {{ font-size:1rem; }}
      .card {{ flex:0 0 80%; min-width:200px; }}
    }}
  </style>
</head>
<body>
  <div class="navbar">
    <a href="/">System State</a> |
    <a href="/monitor">Monitored Values</a> |
    <a href="/conf">Configuration</a> |
    <a href="/console">Console</a>
  </div>
"""

html_footer = """
</body>
</html>
"""

GPIO.setmode(GPIO.BCM)



# -------------------------------------------------------------
#  Helper : rend “On” / “Off” d'un pin GPIO
# -------------------------------------------------------------
def _state(pin: int) -> str:
    try:
        return "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
    except:
        return "—"
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


# -------------------------------------------------------------
#  PAGE PRINCIPALE  (état global)
# -------------------------------------------------------------
def main_page(
    controller_status,
    sensor_handler,
    stats,
    config: AppConfig
) -> str:
    # 1) DailyTimers
    dt1 = config.daily_timer1
    dt2 = config.daily_timer2
    dt1_sched = f"{dt1.start_hour:02d}:{dt1.start_minute:02d} → {dt1.stop_hour:02d}:{dt1.stop_minute:02d}"
    dt2_sched = f"{dt2.start_hour:02d}:{dt2.start_minute:02d} → {dt2.stop_hour:02d}:{dt2.stop_minute:02d}"
    dt1_state = _state(config.gpio.dailytimer1_pin)
    dt2_state = _state(config.gpio.dailytimer2_pin)

    # 2) Cyclic timers
    def _format_cyclic(cyc):
        if cyc.mode == "journalier":
            return (
                "Mode : Journalier<br>"
                f"Période : {cyc.period_days} jour{'s' if cyc.period_days>1 else ''}<br>"
                f"Actions/jour : {cyc.triggers_per_day}<br>"
                f"Premier : {cyc.first_trigger_hour}h00<br>"
                f"Durée : {cyc.action_duration_seconds}s"
            )
        else:
            return (
                "Mode : Séquentiel<br>"
                f"Jour – ON {cyc.on_time_day}s / OFF {cyc.off_time_day}s<br>"
                f"Nuit – ON {cyc.on_time_night}s / OFF {cyc.off_time_night}s"
            )
    cyc1 = config.cyclic1
    cyc2 = config.cyclic2
    cyc1_desc = _format_cyclic(cyc1)
    cyc2_desc = _format_cyclic(cyc2)
    cyc1_state = _state(config.gpio.cyclic1_pin)
    cyc2_state = _state(config.gpio.cyclic2_pin)

    # 3) Heater
    heater_state = _state(config.gpio.heater_pin)

    # 4) Températures min/max (récupérées depuis stats)
    temps = []
    for key in ("BME280T","DS18B#1","DS18B#2","DS18B#3","MLX-AMB","MLX-OBJ"):
        s = stats.get_all().get(key)
        if s:
            dmin = datetime.fromisoformat(s["min_date"]).strftime("%d/%m %H:%M")
            dmax = datetime.fromisoformat(s["max_date"]).strftime("%d/%m %H:%M")
            temps.append(
                f"<p><strong>{key}</strong> : Min {s['min']:.1f}°C le {dmin} — Max {s['max']:.1f}°C le {dmax}</p>"
            )
    temps_html = "\n".join(temps) or "<p>Aucune donnée</p>"

    # 5) Etat des capteurs (enabled/disabled)
    sensors = []
    for name, sensor in sensor_handler.sensor_dict.items():
        enabled = getattr(sensor, "enabled", True)
        sensors.append(f"<p>{name} : {'Enabled' if enabled else 'Disabled'}</p>")
    sensors_html = "\n".join(sensors)

    # --- Génération HTML ---
    return f"""{html_header}

  <div class="row">
    <div class="col"><div class="mainwrap">
      <h1>DailyTimer #1</h1><hr>
      <p>Planning : {dt1_sched}</p>
      <p>Etat    : {dt1_state}</p>
    </div></div>

    <div class="col"><div class="mainwrap">
      <h1>DailyTimer #2</h1><hr>
      <p>Planning : {dt2_sched}</p>
      <p>Etat    : {dt2_state}</p>
    </div></div>
  </div>

  <div class="row">
    <div class="col"><div class="mainwrap">
      <h1>Cyclic #1</h1><hr>
      <div style="font-size:0.9rem;line-height:1.2;">{cyc1_desc}</div>
      <p>Etat : {cyc1_state}</p>
    </div></div>

    <div class="col"><div class="mainwrap">
      <h1>Cyclic #2</h1><hr>
      <div style="font-size:0.9rem;line-height:1.2;">{cyc2_desc}</div>
      <p>Etat : {cyc2_state}</p>
    </div></div>
  </div>

  <div class="row">
    <div class="col"><div class="mainwrap">
      <h1>Heater</h1><hr>
      <p>Etat : {heater_state}</p>
    </div></div>
  </div>

  <div class="formwrap">
    <h1>Températures min/max</h1><hr>
    {temps_html}
  </div>

  <div class="formwrap">
    <h1>Sensors Enabled</h1><hr>
    {sensors_html}
  </div>

{html_footer}"""


# ==============================================================
#  PAGE CONFIGURATION  (formulaire par section, avec regroupement)
# ==============================================================
def conf_page(config: AppConfig) -> str:
    sections = list(config.model_fields.items())
    cards: list[str] = []

    # clés à regrouper
    to_merge = {"Temperature_Settings", "Heater_Settings"}
    merged_alias = "Temperature & Heater Settings"
    merged_done = False

    for section_name, field_info in sections:
        alias = field_info.alias or section_name

        # si on doit regrouper ces deux sections
        if section_name in to_merge:
            if merged_done:
                continue  # on l'a déjà fait
            merged_done = True

            # créer la carte fusionnée
            card = ['<div class="card">', f'  <form method="post" action="/conf">', f'    <h2>{merged_alias}</h2><hr>']
            # parcourir dans l'ordre Temperature puis Heater
            for key in ("Temperature_Settings", "Heater_Settings"):
                section_obj = getattr(config, key)
                sub_alias = config.model_fields[key].alias or key
                for attr_name, fld in section_obj.model_fields.items():
                    fld_alias      = fld.alias or attr_name
                    fld_annotation = fld.annotation
                    fld_value      = getattr(section_obj, attr_name)
                    input_name     = f"{sub_alias}.{fld_alias}"
                    card.append(f'    <label for="{input_name}">{fld_alias}</label>')
                    card.append(f'    {_render_field(input_name, fld_value, fld_annotation)}')
            card.append('    <button type="submit" class="button_param">Save</button>')
            card.append('  </form>')
            card.append('</div>')
            cards.append("\n".join(card))
            continue

        # sinon, carte normale pour la section seule
        if section_name in to_merge:
            # (sera géré par la fusion ci-dessus)
            continue

        section_obj = getattr(config, section_name)
        card = ['<div class="card">', f'  <form method="post" action="/conf">', f'    <h2>{alias}</h2><hr>']
        for attr_name, fld in section_obj.model_fields.items():
            fld_alias      = fld.alias or attr_name
            fld_annotation = fld.annotation
            fld_value      = getattr(section_obj, attr_name)
            input_name     = f"{alias}.{fld_alias}"
            card.append(f'    <label for="{input_name}">{fld_alias}</label>')
            card.append(f'    {_render_field(input_name, fld_value, fld_annotation)}')
        card.append('    <button type="submit" class="button_param">Save</button>')
        card.append('  </form>')
        card.append('</div>')
        cards.append("\n".join(card))

    return (
        html_header
        + "\n  <h1>Configuration</h1><hr>\n"
        + '  <div class="scroll-container">\n'
        + "\n".join(cards)
        + "\n  </div>\n"
        + html_footer
    )


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques + GPIO + actions sys.
# ==============================================================
def monitor_page(sensor_handler, stats, config: AppConfig, controller_status=None) -> str:
    _fmt   = lambda v,u: f"{v:.1f}&nbsp;{u}" if isinstance(v,(int,float)) else "―"
    _stat  = lambda v: f"{v:.1f}"         if isinstance(v,(int,float)) else "—"
    fmt_d  = lambda dt: datetime.fromisoformat(dt).strftime("%d/%m/%Y %H:%M:%S") if dt else "—"

    def state(pin):
        try: return "On" if GPIO.input(pin)==GPIO.HIGH else "Off"
        except: return "—"

    # Timers state
    timers = {
        "DailyTimer #1": state(config.gpio.dailytimer1_pin),
        "DailyTimer #2": state(config.gpio.dailytimer2_pin),
        "Cyclic #1":     state(config.gpio.cyclic1_pin),
        "Cyclic #2":     state(config.gpio.cyclic2_pin),
    }
    # Motor power
    motor_pins = [
        config.gpio.motor_pin1, config.gpio.motor_pin2,
        config.gpio.motor_pin3, config.gpio.motor_pin4
    ]
    try:
        speed = next(i+1 for i,p in enumerate(motor_pins) if GPIO.input(p)==GPIO.HIGH)
    except:
        speed = 0
    pct = int(speed/4*100)

    html = [html_header]

    html.append('<div class="mainwrap"><h1>Timers state</h1><hr>')
    for n,s in timers.items():
        html.append(f'<p>{n} : {s}</p>')
    html.append('</div>')

    html.append(f'''
  <div class="mainwrap">
    <h1>Motor power</h1><hr>
    <p>Level : {speed} / 4</p>
    <div style="background:#555;width:100%;height:20px;">
      <div style="background:#0f0;height:20px;width:{pct}%"></div>
    </div>
  </div>
''')

    # Capteurs
    readings = {
        "BME280T":"°C","BME280H":"%","BME280P":"hPa",
        "DS18B#1":"°C","DS18B#2":"°C","DS18B#3":"°C",
        "MLX-AMB":"°C","MLX-OBJ":"°C",
        "VL53-DIST":"mm","HCSR-DIST":"cm","TSL-LUX":"lx",
    }
    html.append('<div class="row">')
    for k,u in readings.items():
        v = sensor_handler.get_sensor_value(k)
        html.append(f'<div class="col"><div class="mainwrap"><h1>{k}</h1><hr><h2>{_fmt(v,u)}</h2></div></div>')
    html.append('</div>')

    # Historique min/max
    html.append('<div class="formwrap"><h1>Historique min/max</h1><hr>')
    for k,s in stats.get_all().items():
        html.append(f'<h2>{k}</h2>')
        html.append(f'<p>Min : {_stat(s["min"])} le {fmt_d(s["min_date"])}</p>')
        html.append(f'<p>Max : {_stat(s["max"])} le {fmt_d(s["max_date"])}</p>')
        html.append(f'''
<form method="get" action="/monitor">
  <input type="hidden" name="reset_{k.replace("#","")}" value="1">
  <button class="button_base" type="submit">Reset {k}</button>
</form><hr>''')
    html.append('</div>')

    # GPIO divers
    gpio = config.gpio
    html.append('<div class="formwrap"><h1>GPIO States</h1><hr><ul>')
    for n,p in {
        "DailyTimer #1":gpio.dailytimer1_pin,
        "DailyTimer #2":gpio.dailytimer2_pin,
        "Cyclic #1":    gpio.cyclic1_pin,
        "Heater":       gpio.heater_pin,
        "Motor Pin 1":  gpio.motor_pin1
    }.items():
        try: st="On" if GPIO.input(p)==GPIO.HIGH else "Off"
        except: st="—"
        html.append(f'<li>{n} (pin {p}): {st}</li>')
    html.append('</ul></div>')

    # Actions système
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


# ==============================================================
#  PAGE CONSOLE  (xterm.js + SSE)
# ==============================================================
def console_page() -> str:
    return f"""{html_header}
<div class="row">
  <div class="col" style="height:80vh; padding:0;">
    <div id="terminal" style="width:100%; height:100%; background:#000;"></div>
  </div>
</div>
<link rel="stylesheet" href="https://unpkg.com/xterm@3.8.0/dist/xterm.css" />
<script src="https://unpkg.com/xterm@3.8.0/dist/xterm.js"></script>
<script>
document.addEventListener("DOMContentLoaded", () => {{
  const term = new Terminal({{ convertEol: true }});
  term.open(document.getElementById('terminal'));
  term.focus();
  const es = new EventSource('/console/stream');
  es.onmessage = ev => term.write(ev.data + '\\r\\n');
  es.onerror   = _ => es.close();
}});
</script>
{html_footer}"""
