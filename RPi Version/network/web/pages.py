# controller/web/pages.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Génère les pages HTML (pas de logique réseau ici)
# -------------------------------------------------------------

from datetime import datetime
import RPi.GPIO as GPIO
from typing import get_origin, get_args, Literal
from param.config import AppConfig

# -------------------------------------------------------------
#  En-tête / pied de page
# -------------------------------------------------------------
html_header = r"""<!DOCTYPE HTML>
<html><head>
<meta charset="utf8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet">
<style>
@import url('https://fonts.googleapis.com/css?family=Dosis:200,400');
body{background:#000;color:#fff;} hr{border:0;border-top:3px solid #fff;margin:10px 0;}
.mainwrap{width:100%;background:rgba(0,0,0,.7);margin:5px 0;padding:10px;}
.formwrap{background:rgba(0,0,0,.7);margin:20px 0;padding:10px;}
h1,h2,legend{font-family:'Dosis',sans-serif;font-weight:200;text-transform:uppercase;margin:0;}
h1{font-size:24px;}h2{font-size:16px;}
label{display:block;margin-top:8px;font-size:14px;}
input,select{font-family:'Dosis',sans-serif;font-size:13px;color:#FCF7EE;
  background:transparent;border:1px solid #fff;width:100%;padding:6px;margin-top:4px;}
.button_base{display:block;width:160px;margin:20px auto;padding:8px;text-align:center;
  background:#fff;color:#000;text-transform:uppercase;cursor:pointer;border:1px solid #000;}
.button_base:hover{background:transparent;color:#fff;border:1px solid #fff;}
.div_center{text-align:center;} fieldset{border:1px solid #fff;padding:10px;margin-bottom:20px;height:100%;}
legend{padding:0 10px;font-weight:bold;} .navbar{margin-bottom:20px;} .navbar a{color:#fff;margin-right:15px;}
</style></head><body><div class="container-fluid"><div class="navbar">
<a href="/">System State</a> | <a href="monitor">Monitored Values</a> | <a href="conf">Configuration</a>
</div>"""

html_footer = "</div></body></html>"

GPIO.setmode(GPIO.BCM)

# -------------------------------------------------------------
# Helper rendu input / select
# -------------------------------------------------------------
def _render_field(name: str, value, ann) -> str:
    if get_origin(ann) is Literal:
        opts = get_args(ann)
        out = ['<select name="{}">'.format(name)]
        for o in opts:
            sel = ' selected' if value == o else ''
            out.append(f'<option value="{o}"{sel}>{o}</option>')
        out.append('</select>')
        return "\n".join(out)

    if ann is bool:
        sel = lambda v: ' selected' if v else ''
        return (f'<select name="{name}">'
                f'<option value="enabled"{sel(value)}>Enabled</option>'
                f'<option value="disabled"{sel(not value)}>Disabled</option></select>')

    if ann in (int, float):
        step = ' step="0.1"' if ann is float else ''
        return f'<input type="number" name="{name}" value="{value}"{step}>'

    return f'<input type="text" name="{name}" value="{value}">'

# -------------------------------------------------------------
#  PAGE PRINCIPALE
# -------------------------------------------------------------
def main_page(controller_status) -> str:
    start = controller_status.get_dailytimer_current_start_time()
    stop  = controller_status.get_dailytimer_current_stop_time()
    state = controller_status.get_component_state()

    cfg = AppConfig.load().cyclic1
    if cfg.mode == "journalier":
        cyc_desc = (
            "Mode : Journalier<br>"
            f"Période : {cfg.period_days} jour{'s' if cfg.period_days>1 else ''}<br>"
            f"Actions / jour : {cfg.triggers_per_day}<br>"
            f"Premier décl. : {cfg.first_trigger_hour}h00<br>"
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
  <div class="col-md-6"><div class="mainwrap"><h1>DailyTimer #1</h1><hr>
      <h2>Start : {start}</h2><h2>Stop  : {stop}</h2></div></div>
  <div class="col-md-6"><div class="mainwrap"><h1>Cyclic #1</h1><hr>
      <h2 style="font-size:14px;line-height:1.2;">{cyc_desc}</h2></div></div>
</div>
<div class="row"><div class="col-md-6">
  <div class="mainwrap"><h1>Component #1</h1><hr><h2>State : {state}</h2></div></div>
</div>{html_footer}"""

# -------------------------------------------------------------
#  PAGE CONFIGURATION
# -------------------------------------------------------------
def conf_page(config: AppConfig) -> str:
    html = [html_header, '<form method="post" action="/conf">']       # ⬅️ POST
    for idx, (section_name, field_info) in enumerate(config.model_fields.items()):
        if idx % 3 == 0:
            html.append('<div class="row">')
        alias = field_info.alias or section_name
        section_obj = getattr(config, section_name)
        html.append(f'<div class="col-md-4"><fieldset><legend>{alias}</legend>')
        for attr, fld in section_obj.model_fields.items():
            fld_alias, ann = fld.alias or attr, fld.annotation
            val = getattr(section_obj, attr)
            html.append(f'<label for="{alias}.{fld_alias}">{fld_alias}</label>')
            html.append(_render_field(f"{alias}.{fld_alias}", val, ann))
        html.append('</fieldset></div>')
        if idx % 3 == 2 or idx == len(config.model_fields) - 1:
            html.append('</div>')
    html.append('<div class="div_center"><button class="button_base" type="submit">Save configuration</button></div>')
    html.append('</form>' + html_footer)
    return "\n".join(html)


# ==============================================================
#  PAGE MONITORING
# ==============================================================
def monitor_page(sensor_handler, stats, config: AppConfig, controller_status=None) -> str:
    _fmt  = lambda v,u: f"{v:.1f}&nbsp;{u}" if isinstance(v,(int,float)) else "―"
    _stat = lambda v  : f"{v:.1f}"          if isinstance(v,(int,float)) else "—"
    def _d(dt): return datetime.fromisoformat(dt).strftime("%d/%m/%Y %H:%M:%S") if dt else "—"

    # ---------- Timers state ----------
    def _st(pin):
        try: return "On" if GPIO.input(pin)==GPIO.HIGH else "Off"
        except Exception: return "—"

    timers = {
        "DailyTimer&nbsp;#1": _st(config.gpio.dailytimer1_pin),
        "DailyTimer&nbsp;#2": _st(config.gpio.dailytimer2_pin),
        "Cyclic&nbsp;#1":     _st(config.gpio.cyclic1_pin),
        "Cyclic&nbsp;#2":     _st(config.gpio.cyclic2_pin),
    }

    # ---------- Motor power ----------
    motor_pins = [config.gpio.motor_pin1,
                  config.gpio.motor_pin2,
                  config.gpio.motor_pin3,
                  config.gpio.motor_pin4]

    try:
        # vitesse = index du premier pin HIGH (1-4), 0 si aucun
        speed = next((i+1 for i,p in enumerate(motor_pins) if GPIO.input(p)==GPIO.HIGH), 0)
    except Exception:
        speed = 0
    pct = int(speed/4 * 100)

    html = [html_header, '''
<div class="row">
  <div class="col-md-6"><div class="mainwrap"><h1>Timers state</h1><hr>''']
    for n,s in timers.items():
        html.append(f"<p>{n} : {s}</p>")
    html += [f'''</div></div>
  <div class="col-md-6"><div class="mainwrap"><h1>Motor power</h1><hr>
      <p>Level : {speed} / 4</p>
      <div style="background:#555;width:100%;height:20px;">
        <div style="background:#0f0;height:20px;width:{pct}%"></div>
      </div>
  </div></div></div>''']

    # ---------- Capteurs ----------
    readings = {"BME280T":"°C","BME280H":"%","BME280P":"hPa",
                "DS18B#1":"°C","DS18B#2":"°C","DS18B#3":"°C",
                "MLX-AMB":"°C","MLX-OBJ":"°C",
                "VL53-DIST":"mm","HCSR-DIST":"cm","TSL-LUX":"lx"}

    html.append('<div class="row">')
    for key,unit in readings.items():
        val = sensor_handler.get_sensor_value(key)
        html.append(f'<div class="col-md-3"><div class="mainwrap"><h1>{key}</h1><hr>'
                    f'<h2>{_fmt(val,unit)}</h2></div></div>')
    html.append('</div>')

    # ---------- Stats ----------
    html.append('<div class="formwrap"><h1>Historique min/max</h1><hr>')
    for k,s in stats.get_all().items():
        html.append(f'<h2>{k}</h2>'
                    f'<p>Min : {_stat(s["min"])} le {_d(s["min_date"])}</p>'
                    f'<p>Max : {_stat(s["max"])} le {_d(s["max_date"])}</p>'
                    f'<form method="get" action="/monitor"><input type="hidden" name="reset_{k.replace("#","")}" value="1">'
                    f'<button class="button_base" type="submit">Reset {k}</button></form><hr>')
    html.append('</div>')

    # ---------- GPIO divers ----------
    gpio = config.gpio
    html.append('<div class="formwrap"><h1>GPIO States</h1><hr><ul>')
    for name,pin in {"DailyTimer #1":gpio.dailytimer1_pin,"DailyTimer #2":gpio.dailytimer2_pin,
                     "Cyclic #1":gpio.cyclic1_pin,"Heater":gpio.heater_pin,
                     "Motor Pin 1":gpio.motor_pin1}.items():
        try: st="On" if GPIO.input(pin)==GPIO.HIGH else "Off"
        except Exception: st="—"
        html.append(f"<li>{name} (pin {pin}): {st}</li>")
    html.append('</ul></div>'+html_footer)
    return "\n".join(html)
