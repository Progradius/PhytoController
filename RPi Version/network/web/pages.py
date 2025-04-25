# controller/web/pages.py
# Author: Progradius
# License: AGPL-3.0

from datetime import datetime
import RPi.GPIO as GPIO
from typing import get_origin, get_args, Literal
from param.config import AppConfig

BODY_FONT_SIZE   = "1.5rem"
HEADER_FONT_SIZE = "2rem"

html_header = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      background: #000; color: #eee;
      font-family: "Courier New", monospace;
      font-size: {BODY_FONT_SIZE};
      line-height:1.4;
      padding:1rem;
    }}
    a {{ color:inherit; text-decoration:none; }}
    hr {{ border:0; border-top:3px solid #fff; margin:10px 0; }}
    .navbar {{ margin-bottom:1rem; font-size:1.2rem; }}
    .navbar a {{ margin-right:1rem; }}
    .mainwrap, .formwrap {{
      background: rgba(0,0,0,0.7);
      padding:1rem; border:1px solid #fff;
      border-radius:6px;
    }}
    .formwrap {{ margin:1rem 0; }}
    h1,h2,legend {{
      font-size: {HEADER_FONT_SIZE};
      margin-bottom:0.5rem;
      font-weight:normal;
    }}
    label {{ display:block; margin-top:0.5rem; font-size:{BODY_FONT_SIZE}; }}
    input, select {{
      width:100%; padding:0.5rem; margin-top:0.3rem;
      background:transparent; border:1px solid #fff;
      font-family:"Courier New", monospace;
      font-size:{BODY_FONT_SIZE};
      color:#FCF7EE; border-radius:4px;
    }}
    .button_base, .button_param {{
      display:block; width:100%; max-width:200px;
      margin:1rem auto 0; padding:0.6rem; text-align:center;
      background:#fff; color:#000;
      text-transform:uppercase; border:1px solid #000;
      border-radius:4px; cursor:pointer;
    }}
    .button_base:hover, .button_param:hover {{
      background:transparent; color:#fff; border-color:#fff;
    }}
    .scroll-container {{
      display:flex; overflow-x:auto;
      scroll-snap-type:x mandatory;
      -webkit-overflow-scrolling: touch;
      padding-bottom:1rem; margin:1rem 0;
    }}
    .card {{
      flex:0 0 300px; min-width:250px; margin-right:1rem;
      scroll-snap-align:start;
      background:rgba(0,0,0,0.8);
      border:1px solid #fff; border-radius:6px;
      padding:1rem; position:relative;
    }}
    .card select, .card input {{
      margin-bottom: 1rem;
    }}
    .card:last-child {{ margin-right:0; }}
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

html_footer = "</body></html>"

GPIO.setmode(GPIO.BCM)

def _state(pin: int) -> str:
    try:
        return "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
    except:
        return "—"

def _render_field(name: str, value, annotation) -> str:
    if get_origin(annotation) is Literal:
        opts = get_args(annotation)
        html = [f'<select name="{name}">']
        for opt in opts:
            sel = ' selected' if value == opt else ''
            html.append(f'  <option value="{opt}"{sel}>{opt}</option>')
        html.append('</select>')
        return "\n".join(html)
    if annotation is bool:
        sel_en = ' selected' if value else ''
        sel_dis = ' selected' if not value else ''
        return (
            f'<select name="{name}">'
            f'<option value="enabled"{sel_en}>Enabled</option>'
            f'<option value="disabled"{sel_dis}>Disabled</option>'
            f'</select>'
        )
    if annotation in (int, float):
        step = ' step="0.1"' if annotation is float else ''
        return f'<input type="number" name="{name}" value="{value}"{step}>'
    return f'<input type="text" name="{name}" value="{value}">'



# -------------------------------------------------------------
#  PAGE PRINCIPALE  (état global)
# -------------------------------------------------------------
def main_page(controller_status, sensor_handler, stats, config: AppConfig) -> str:
    from datetime import datetime

    # Récupère infos des dailytimers
    dt1 = config.daily_timer1
    dt2 = config.daily_timer2
    dt1_sched = f"{dt1.start_hour:02d}:{dt1.start_minute:02d} → {dt1.stop_hour:02d}:{dt1.stop_minute:02d}"
    dt2_sched = f"{dt2.start_hour:02d}:{dt2.start_minute:02d} → {dt2.stop_hour:02d}:{dt2.stop_minute:02d}"

    # États GPIO
    def _state(pin):
        try: return "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
        except: return "—"

    dt1_state = _state(config.gpio.dailytimer1_pin)
    dt2_state = _state(config.gpio.dailytimer2_pin)
    cyc1_state = _state(config.gpio.cyclic1_pin)
    cyc2_state = _state(config.gpio.cyclic2_pin)
    heater_state = _state(config.gpio.heater_pin)

    # Description cyclique 1
    cyc1 = config.cyclic1
    if cyc1.mode == "journalier":
        cyc1_desc = (
            "Mode : Journalier<br>"
            f"Période : {cyc1.period_days} jour{'s' if cyc1.period_days > 1 else ''}<br>"
            f"Actions/jour : {cyc1.triggers_per_day}<br>"
            f"Premier : {cyc1.first_trigger_hour}h00<br>"
            f"Durée : {cyc1.action_duration_seconds}s"
        )
    else:
        cyc1_desc = (
            "Mode : Séquentiel<br>"
            f"Jour – ON {cyc1.on_time_day}s / OFF {cyc1.off_time_day}s<br>"
            f"Nuit – ON {cyc1.on_time_night}s / OFF {cyc1.off_time_night}s"
        )

    # Températures min/max
    temps = []
    for key in ("BME280T", "DS18B#1", "DS18B#2", "DS18B#3", "MLX-AMB", "MLX-OBJ"):
        s = stats.get_all().get(key)
        if s:
            dmin = datetime.fromisoformat(s["min_date"]).strftime("%d/%m %H:%M")
            dmax = datetime.fromisoformat(s["max_date"]).strftime("%d/%m %H:%M")
            temps.append(
                f"<p><strong>{key}</strong> : Min {s['min']:.1f}°C le {dmin} — Max {s['max']:.1f}°C le {dmax}</p>"
            )
    temps_html = "\n".join(temps) or "<p>Aucune donnée</p>"

    # Capteurs Enabled
    sensors = []
    for name, sensor in sensor_handler.sensor_dict.items():
        enabled = getattr(sensor, "enabled", True)
        sensors.append(f"<p>{name} : {'Enabled' if enabled else 'Disabled'}</p>")
    sensors_html = "\n".join(sensors)

    return f"""{html_header}

<div class="mainwrap">
  <h1>DailyTimer #1</h1><hr>
  <p>Planning : {dt1_sched}</p>
  <p>Etat     : {dt1_state}</p>
</div>

<div class="mainwrap">
  <h1>DailyTimer #2</h1><hr>
  <p>Planning : {dt2_sched}</p>
  <p>Etat     : {dt2_state}</p>
</div>

<div class="mainwrap">
  <h1>Cyclic #1</h1><hr>
  <div style="font-size:0.9rem;line-height:1.2;">{cyc1_desc}</div>
  <p>Etat : {cyc1_state}</p>
</div>

<div class="mainwrap">
  <h1>Cyclic #2</h1><hr>
  <p>Etat : {cyc2_state}</p>
</div>

<div class="mainwrap">
  <h1>Heater</h1><hr>
  <p>Etat : {heater_state}</p>
</div>

<div class="formwrap">
  <h1>Températures min/max</h1><hr>
  {temps_html}
</div>

<div class="formwrap">
  <h1>Sensors Status</h1><hr>
  {sensors_html}
</div>

{html_footer}"""



# -------------------------------------------------------------
#  PAGE CONFIGURATION
# -------------------------------------------------------------
def conf_page(config: AppConfig) -> str:
    sections = list(config.model_fields.items())
    cards: list[str] = []

    to_merge     = {"Temperature_Settings", "Heater_Settings"}
    merged_alias = "Temperature & Heater Settings"
    merged_done  = False

    for section_name, field_info in sections:
        alias = field_info.alias or section_name

        # ─── FUSION Temperature/Heater ─────────────────────────
        if section_name in to_merge:
            if merged_done:
                continue
            merged_done = True

            card = [
                '<div class="card">',
                '  <form method="post" action="/conf">',
                f'    <h2>{merged_alias}</h2><hr>'
            ]
            for key in ("Temperature_Settings", "Heater_Settings"):
                sub_alias   = config.model_fields[key].alias or key
                section_obj = getattr(config, key)
                for attr_name, fld in section_obj.model_fields.items():
                    fld_alias      = fld.alias or attr_name
                    fld_annotation = fld.annotation
                    fld_value      = getattr(section_obj, attr_name)
                    input_name     = f"{sub_alias}.{fld_alias}"
                    card.append(f'    <label for="{input_name}">{fld_alias}</label>')
                    card.append(f'    {_render_field(input_name, fld_value, fld_annotation)}')
            card += [
                '    <button type="submit" class="button_param">Save</button>',
                '  </form>',
                '</div>'
            ]
            cards.append("\n".join(card))
            continue

        # ─── MOTEUR (toggle MANUAL/AUTO) ──────────────────────
        if section_name == "Motor":
            section_obj = getattr(config, section_name)
            motor_mode  = getattr(section_obj, "motor_mode")
            motor_speed = getattr(section_obj, "motor_user_speed")

            card = [
                '<div class="card">',
                '  <form method="post" action="/conf">',
                '    <h2>Motor</h2><hr>',
                '    <label for="motor_mode_toggle">Motor Mode</label>',
                '    <select id="motor_mode_toggle" name="Motor.motor_mode">',
                f'      <option value="manual" {"selected" if motor_mode=="manual" else ""}>Manual</option>',
                f'      <option value="auto" {"selected" if motor_mode=="auto" else ""}>Auto</option>',
                '    </select>',
                '    <div id="motor_manual_fields">',
                f'      <label for="Motor.motor_user_speed">Motor User Speed</label>',
                f'      <input type="number" name="Motor.motor_user_speed" min="0" max="4" value="{motor_speed}">',
                '    </div>',
                '    <button type="submit" class="button_param">Save</button>',
                '  </form>',
                '</div>'
            ]
            cards.append("\n".join(card))
            continue

        # ─── CYCLICS (toggle JOURNALIER/SÉQUENTIEL) ────────────
        if section_name.startswith("Cyclic"):
            section_obj = getattr(config, section_name)
            cyc_mode = getattr(section_obj, "mode")

            card = [
                '<div class="card">',
                f'  <form method="post" action="/conf">',
                f'    <h2>{alias}</h2><hr>',
                f'    <label for="{section_name}_mode_toggle">Mode</label>',
                f'    <select id="{section_name}_mode_toggle" name="{alias}.mode">',
                f'      <option value="journalier" {"selected" if cyc_mode=="journalier" else ""}>Journalier</option>',
                f'      <option value="séquentiel" {"selected" if cyc_mode=="séquentiel" else ""}>Séquentiel</option>',
                '    </select>',
                f'    <div id="{section_name}_journalier_fields">'
            ]

            for attr in ("period_days", "triggers_per_day", "first_trigger_hour", "action_duration_seconds"):
                fld = section_obj.__class__.model_fields[attr]
                val = getattr(section_obj, attr)
                card.append(f'      <label for="{alias}.{fld.alias or attr}">{fld.alias or attr}</label>')
                card.append(f'      {_render_field(f"{alias}.{fld.alias or attr}", val, fld.annotation)}')

            card += [
                '    </div>',
                f'    <div id="{section_name}_séquentiel_fields">'
            ]

            for attr in ("on_time_day", "off_time_day", "on_time_night", "off_time_night"):
                fld = section_obj.__class__.model_fields[attr]
                val = getattr(section_obj, attr)
                card.append(f'      <label for="{alias}.{fld.alias or attr}">{fld.alias or attr}</label>')
                card.append(f'      {_render_field(f"{alias}.{fld.alias or attr}", val, fld.annotation)}')

            card += [
                '    </div>',
                '    <button type="submit" class="button_param">Save</button>',
                '  </form>',
                '</div>'
            ]
            cards.append("\n".join(card))
            continue

        # ─── SECTIONS NORMALES ────────────────────────────────
        section_obj = getattr(config, section_name)
        card = [
            '<div class="card">',
            '  <form method="post" action="/conf">',
            f'    <h2>{alias}</h2><hr>'
        ]
        for attr_name, fld in section_obj.model_fields.items():
            fld_alias      = fld.alias or attr_name
            fld_annotation = fld.annotation
            fld_value      = getattr(section_obj, attr_name)
            input_name     = f"{alias}.{fld_alias}"
            card.append(f'    <label for="{input_name}">{fld_alias}</label>')
            card.append(f'    {_render_field(input_name, fld_value, fld_annotation)}')
        card += [
            '    <button type="submit" class="button_param">Save</button>',
            '  </form>',
            '</div>'
        ]
        cards.append("\n".join(card))

    # ─── Assemblage avec JS dynamiques pour toggles ───────────
    return (
        html_header
        + "\n<h1>Configuration</h1><hr>\n"
        + '<div class="scroll-container">\n'
        + "\n".join(cards)
        + "\n</div>\n"
        + """
<script>
document.addEventListener("DOMContentLoaded", function() {
  // Toggle moteur
  const motorSelect = document.getElementById("motor_mode_toggle");
  const motorManualDiv = document.getElementById("motor_manual_fields");
  function toggleMotorFields() {
    if (motorSelect.value === "manual") {
      motorManualDiv.style.display = "block";
    } else {
      motorManualDiv.style.display = "none";
    }
  }
  motorSelect.addEventListener("change", toggleMotorFields);
  toggleMotorFields();

  // Toggle cyclic
  document.querySelectorAll('select[id$="_mode_toggle"]').forEach(sel => {
    const section = sel.id.replace("_mode_toggle", "");
    const journalierDiv = document.getElementById(section + "_journalier_fields");
    const sequentielDiv = document.getElementById(section + "_séquentiel_fields");
    function toggleCyclicFields() {
      if (sel.value === "journalier") {
        journalierDiv.style.display = "block";
        sequentielDiv.style.display = "none";
      } else {
        journalierDiv.style.display = "none";
        sequentielDiv.style.display = "block";
      }
    }
    sel.addEventListener("change", toggleCyclicFields);
    toggleCyclicFields();
  });
});
</script>
"""
        + html_footer
    )


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques + GPIO + actions sys.
# ==============================================================
def monitor_page(sensor_handler, stats, config: AppConfig, controller_status=None) -> str:
    _fmt  = lambda v,u: f"{v:.1f}&nbsp;{u}" if isinstance(v, (int, float)) else "―"
    _stat = lambda v: f"{v:.1f}"             if isinstance(v, (int, float)) else "—"
    fmt_d = lambda dt: datetime.fromisoformat(dt).strftime("%d/%m/%Y %H:%M:%S") if dt else "—"

    def state(pin):
        try: return "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
        except: return "—"

    # Timers
    timers = {
        "DailyTimer #1": state(config.gpio.dailytimer1_pin),
        "DailyTimer #2": state(config.gpio.dailytimer2_pin),
        "Cyclic #1"    : state(config.gpio.cyclic1_pin),
        "Cyclic #2"    : state(config.gpio.cyclic2_pin),
    }

    # Motor power
    motor_pins = [
        config.gpio.motor_pin1, config.gpio.motor_pin2,
        config.gpio.motor_pin3, config.gpio.motor_pin4
    ]
    try:
        speed = next(i + 1 for i, p in enumerate(motor_pins) if GPIO.input(p) == GPIO.HIGH)
    except:
        speed = 0
    pct = int(speed / 4 * 100)

    html = [html_header]

    html.append('<div class="mainwrap"><h1>Timers State</h1><hr>')
    for name, st in timers.items():
        html.append(f'<p>{name} : {st}</p>')
    html.append('</div>')

    html.append(f'''
<div class="mainwrap">
  <h1>Motor Power</h1><hr>
  <p>Level : {speed} / 4</p>
  <div style="background:#555;width:100%;height:20px;">
    <div style="background:#0f0;height:20px;width:{pct}%"></div>
  </div>
</div>
''')

    # Capteurs
    readings = {
        "BME280T":"°C", "BME280H":"%", "BME280P":"hPa",
        "DS18B#1":"°C", "DS18B#2":"°C", "DS18B#3":"°C",
        "MLX-AMB":"°C", "MLX-OBJ":"°C",
        "VL53-DIST":"mm", "HCSR-DIST":"cm", "TSL-LUX":"lx",
    }
    html.append('<div class="row">')
    for k, u in readings.items():
        v = sensor_handler.get_sensor_value(k)
        html.append(f'<div class="col"><div class="mainwrap"><h1>{k}</h1><hr><h2>{_fmt(v,u)}</h2></div></div>')
    html.append('</div>')

    # Historique min/max
    html.append('<div class="formwrap"><h1>Historique min/max</h1><hr>')
    for k, s in stats.get_all().items():
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
    for name, pin in {
        "DailyTimer #1": gpio.dailytimer1_pin,
        "DailyTimer #2": gpio.dailytimer2_pin,
        "Cyclic #1"    : gpio.cyclic1_pin,
        "Heater"       : gpio.heater_pin,
        "Motor Pin 1"  : gpio.motor_pin1
    }.items():
        try: st = "On" if GPIO.input(pin) == GPIO.HIGH else "Off"
        except: st = "—"
        html.append(f'<li>{name} (pin {pin}): {st}</li>')
    html.append('</ul></div>')

    # Actions système
    html.append('''
<div class="formwrap"><h1>Actions système</h1><hr>
<form method="get" action="/monitor">
  <input type="hidden" name="shutdown" value="1">
  <button class="button_base" type="submit">Éteindre le Raspberry Pi</button>
</form>
<form method="get" action="/monitor">
  <input type="hidden" name="reboot" value="1">
  <button class="button_base" type="submit">Redémarrer le Raspberry Pi</button>
</form>
</div>
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