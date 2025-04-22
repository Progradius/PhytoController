# controller/web/pages.py
# Author: Progradius (adapted)
# License: AGPL‑3.0
# -------------------------------------------------------------
#  Génère les pages HTML (aucune logique réseau ici)
# -------------------------------------------------------------

# ──────────────────────────  STYLE  ──────────────────────────
html_header = r""" 
<!DOCTYPE HTML>
<html>
<head>
  <meta charset="utf8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="//netdna.bootstrapcdn.com/bootstrap/3.1.0/css/bootstrap.min.css" rel="stylesheet">
  <link rel="stylesheet"
        href="https://use.fontawesome.com/releases/v5.7.2/css/all.css"
        integrity="sha384-fnmOCqbTlWIlj8LyTjo7mOUStjsKC4pOpQbqyi7RrhN7udi9RwhKkMHpvLbHG9Sr"
        crossorigin="anonymous">
  <style>
@import url('https://fonts.googleapis.com/css?family=Dosis:200,400');
body{background:#000;color:#fff;}
hr{border:0;border-top:3px solid #fff;border-bottom:1px solid #fff;}
.mainwrap{width:20em;height:10em;background:rgba(0,0,0,.7);margin:5px auto 25px;padding:10px;}
.formwrap{width:320px;background:rgba(0,0,0,.7);margin:50px auto;padding:10px;}
h1,h2{font-family:'Dosis',sans-serif;font-weight:200;text-transform:uppercase;margin:0;}
h1{font-size:22px;}h2{font-size:16px;}
p,a{font-family:'Dosis',sans-serif;font-size:13px;}
input[type=hour],input[type=number],input[type=text]{
  font-family:'Dosis',sans-serif;font-size:13px;font-weight:200;color:#FCF7EE;
  background:transparent;border:1px solid #fff;width:calc(100% - 12px);padding-left:12px;}
.button_base{position:relative;margin:auto;width:100px;height:42px;text-align:center;
  font-size:15px;font-family:'Dosis',sans-serif;text-transform:uppercase;
  border:1px solid #000;background:#fff;cursor:pointer;}
.button_base:hover{color:#fff;background:transparent;border:1px solid #fff;}
.div_center{text-align:center;}
  </style>
</head>
<body>
"""
html_footer = "</body></html>"
# ──────────────────────────────────────────────────────────────


# ==============================================================
#  PAGE PRINCIPALE  (état système)
# ==============================================================

def main_page(controller_status) -> str:
    start  = controller_status.get_dailytimer_current_start_time()
    stop   = controller_status.get_dailytimer_current_stop_time()
    dur    = controller_status.get_cyclic_duration()
    period = controller_status.get_cyclic_period()
    state  = controller_status.get_component_state()

    return f"""{html_header}
<div class="container-fluid">
  <h1 class="text-center">Main Page</h1><br>
  <p><a href="/">System State</a></p>
  <p><a href="monitor">Monitored Values</a></p>
  <p><a href="conf">System Configuration</a></p><br><br>

  <div class="col-md-6">
    <h1>System Settings</h1><hr>
    <div class="mainwrap"><h1>DailyTimer #1</h1><hr>
      <h2>Start time: {start}</h2><h2>Stop time: {stop}</h2></div>

    <div class="mainwrap"><h1>Cyclic #1</h1><hr>
      <h2>Action duration: {dur}s</h2><h2>Period: {period} min</h2></div>

    <div class="mainwrap"><h1>Component #1</h1><hr><h2>State: {state}</h2></div>
    <div class="mainwrap"><h1>Component #2</h1><hr><h2>State: {state}</h2></div>
  </div>
</div>
{html_footer}"""


# ==============================================================
#  PAGE CONFIGURATION  (formulaire)
# ==============================================================

def conf_page(parameters=None) -> str:
    """
    Renvoie le formulaire HTML de configuration.
    Si `parameters` est fourni, les champs sont pré‑remplis avec les valeurs
    courantes de l’application.
    """
    # valeurs par défaut
    start, stop = "17:00", "11:00"
    period, dur = "10", "30"
    stage, speed = "veg", "1"

    if parameters:                       # lecture en mémoire sécurisée
        try:
            start = f"{parameters.get_dailytimer1_start_hour():02d}:{parameters.get_dailytimer1_start_minute():02d}"
            stop  = f"{parameters.get_dailytimer1_stop_hour():02d}:{parameters.get_dailytimer1_stop_minute():02d}"
            period = str(parameters.get_cyclic1_period_minutes())
            dur    = str(parameters.get_cyclic1_action_duration_seconds())
            stage  = parameters.get_growth_stage()
            speed  = str(parameters.get_motor_user_speed())
        except Exception:
            pass                         # n’importe quelle erreur → on garde le fallback

    return f"""{html_header}
<section id="conf">
  <div class="container-fluid">
    <h1 class="text-center">Configuration Page</h1><br>

    <p><a href="/">System State</a></p>
    <p><a href="monitor">Monitored Values</a></p>
    <p><a href="conf">System Configuration</a></p><br><br>

    <div class="row">
      <!-- DailyTimer -->
      <div class="col-md-6">
        <div class="formwrap">
          <h1>DailyTimer #1</h1><hr>
          <p>Turn a component ON / OFF at specific times.</p><br>
          <form method="get">
            <h2>Start hour</h2><input type="hour" name="dt1start" value="{start}">
            <h2>Stop hour</h2><input  type="hour" name="dt1stop"  value="{stop}">
            <div class="div_center"><input class="button_base" type="submit" value="Validate"></div>
          </form>
        </div>
      </div>

      <!-- Cyclic -->
      <div class="col-md-6">
        <div class="formwrap">
          <h1>Cyclic #1</h1><hr>
          <p>Activate a component periodically.</p><br>
          <form method="get">
            <h2>Period (min)</h2><input type="number" name="period" value="{period}">
            <h2>Duration (sec)</h2><input type="number" name="duration" value="{dur}">
            <div class="div_center"><input class="button_base" type="submit" value="Validate"></div>
          </form>
        </div>
      </div>
    </div>

    <!-- Growth stage & motor speed -->
    <div class="row">
      <div class="col-md-6">
        <div class="formwrap">
          <h1>Growth Stage</h1><hr>
          <form method="get">
            <h2>Stage</h2><input type="text" name="stage" value="{stage}">
            <div class="div_center"><input class="button_base" type="submit" value="Validate"></div>
          </form>
        </div>
      </div>

      <div class="col-md-6">
        <div class="formwrap">
          <h1>Motor Speed</h1><hr>
          <form method="get">
            <h2>Speed</h2><input type="number" name="speed" value="{speed}" min="0" max="4">
            <div class="div_center"><input class="button_base" type="submit" value="Validate"></div>
          </form>
        </div>
      </div>
    </div>
  </div>
</section>
{html_footer}"""


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques
# ==============================================================

def monitor_page(sensor_handler) -> str:
    """
    Page « Monitor » : affiche les valeurs en temps réel des capteurs.
    """
    # BME280
    t = sensor_handler.get_sensor_value("BME280T") or "―"
    h = sensor_handler.get_sensor_value("BME280H") or "―"
    p = sensor_handler.get_sensor_value("BME280P") or "―"

    # Trois éventuelles sondes DS18B20
    ds_vals = [sensor_handler.get_sensor_value(f"DS18#{i}") or "―" for i in (1, 2, 3)]

    def _fmt(val, unit):
        return f"{val:.1f}&nbsp;{unit}" if isinstance(val, (int, float)) else val

    return f"""{html_header}
<div class="container-fluid">
  <h1 class="text-center">Monitor Page</h1><br>
  <p><a href="/">System State</a></p>
  <p><a href="monitor">Monitored Values</a></p>
  <p><a href="conf">System Configuration</a></p><br><br>

  <div class="row">
    <!-- BME280 -->
    <div class="col-md-6">
      <h1>BME280</h1><hr>
      <div class="mainwrap"><h1>Temperature</h1><hr><h2>{_fmt(t,'°C')}</h2></div>
      <div class="mainwrap"><h1>Humidity</h1><hr><h2>{_fmt(h,'%')}</h2></div>
      <div class="mainwrap"><h1>Pressure</h1><hr><h2>{_fmt(p,'hPa')}</h2></div>
    </div>

    <!-- DS18B20 -->
    <div class="col-md-6">
      <h1>DS18B20</h1><hr>
      <div class="mainwrap"><h1>Probe #1</h1><hr><h2>{_fmt(ds_vals[0],'°C')}</h2></div>
      <div class="mainwrap"><h1>Probe #2</h1><hr><h2>{_fmt(ds_vals[1],'°C')}</h2></div>
      <div class="mainwrap"><h1>Probe #3</h1><hr><h2>{_fmt(ds_vals[2],'°C')}</h2></div>
    </div>
  </div>
</div>
{html_footer}"""
