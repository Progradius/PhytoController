# controller/web/pages.py
# Author: Progradius (adapted)
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
input, select{
  font-family:'Dosis',sans-serif;font-size:13px;font-weight:200;color:#FCF7EE;
  background:transparent;border:1px solid #fff;width:calc(100% - 12px);padding-left:12px;
  margin-bottom:8px;
}
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
    <div class="mainwrap"><h1>DailyTimer #1</h1><hr>
      <h2>Start time: {start}</h2><h2>Stop time: {stop}</h2></div>

    <div class="mainwrap"><h1>Cyclic #1</h1><hr>
      <h2>Action duration: {dur}s</h2><h2>Period: {period} min</h2></div>

    <div class="mainwrap"><h1>Component #1</h1><hr><h2>State: {state}</h2></div>
    <div class="mainwrap"><h1>Component #2</h1><hr><h2>State: {state}</h2></div>
  </div>
</div>
{html_footer}"""


# ==============================================================
#  PAGE CONFIGURATION  (formulaire complet)
# ==============================================================

def conf_page(parameters) -> str:
    """
    Renvoie le formulaire HTML de configuration.
    Les champs sont pré‑remplis à partir de `parameters`.
    """
    # --- DailyTimer #1
    dt1_start = f"{parameters.get_dailytimer1_start_hour():02d}:{parameters.get_dailytimer1_start_minute():02d}"
    dt1_stop  = f"{parameters.get_dailytimer1_stop_hour():02d}:{parameters.get_dailytimer1_stop_minute():02d}"

    # --- DailyTimer #2
    dt2_start = f"{parameters.get_dailytimer2_start_hour():02d}:{parameters.get_dailytimer2_start_minute():02d}"
    dt2_stop  = f"{parameters.get_dailytimer2_stop_hour():02d}:{parameters.get_dailytimer2_stop_minute():02d}"

    # --- Cyclic timers
    c1_period = parameters.get_cyclic1_period_minutes()
    c1_dur    = parameters.get_cyclic1_action_duration_seconds()
    c2_period = parameters.get_cyclic2_period_minutes()
    c2_dur    = parameters.get_cyclic2_action_duration_seconds()

    # --- Growth & Motor
    stage   = parameters.get_growth_stage()
    m_mode  = parameters.get_motor_mode()
    m_speed = parameters.get_motor_user_speed()
    target  = parameters.get_target_temp()
    hyst    = parameters.get_hysteresis()
    min_sp  = parameters.get_motor_min_speed()
    max_sp  = parameters.get_motor_max_speed()

    # --- Network & Influx
    host        = parameters.get_host_machine_address()
    wifi_ssid   = parameters.get_wifi_ssid()
    wifi_pw     = parameters.get_wifi_password()
    influx_name = parameters.get_influx_db_name()
    influx_port = parameters.get_influx_db_port()
    influx_user = parameters.get_influx_db_user()
    influx_pw   = parameters.get_influx_db_password()

    # --- Temperature Settings (nouveau bloc)
    tmin_day   = parameters.get_target_temp_min_day()
    tmax_day   = parameters.get_target_temp_max_day()
    tmin_night = parameters.get_target_temp_min_night()
    tmax_night = parameters.get_target_temp_max_night()
    offset     = parameters.get_hysteresis_offset()
    
    heater_enabled = parameters.get_heater_enabled()
    heater_pin     = parameters.get_heater_pin()

    return f"""{html_header}
<section id="conf">
  <div class="container-fluid">
    <h1 class="text-center">Configuration Page</h1><br>
    <p><a href="/">System State</a></p>
    <p><a href="monitor">Monitored Values</a></p>
    <p><a href="conf">System Configuration</a></p><br><br>

    <div class="row">
      <!-- DailyTimer #1 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #1</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="hour" name="dt1start" value="{dt1_start}">
          <h2>Stop</h2><input type="hour"  name="dt1stop"  value="{dt1_stop}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>

      <!-- DailyTimer #2 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #2</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="hour" name="dt2start" value="{dt2_start}">
          <h2>Stop</h2><input type="hour"  name="dt2stop"  value="{dt2_stop}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>
    </div>

    <div class="row">
      <!-- Cyclic #1 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #1</h1><hr>
        <form method="get">
          <h2>Period (min)</h2><input type="number" name="period"   value="{c1_period}">
          <h2>Duration (sec)</h2><input type="number" name="duration" value="{c1_dur}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>

      <!-- Cyclic #2 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #2</h1><hr>
        <form method="get">
          <h2>Period (min)</h2><input type="number" name="period2"   value="{c2_period}">
          <h2>Duration (sec)</h2><input type="number" name="duration2" value="{c2_dur}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>
    </div>

    <div class="row">
      <!-- Growth Stage -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Growth Stage</h1><hr>
        <form method="get">
          <h2>Stage</h2><input type="text" name="stage" value="{stage}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>

      <!-- Motor Settings -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Motor Settings</h1><hr>
        <form method="get">
          <h2>Mode</h2>
          <select name="motor_mode">
            <option value="manual" {"selected" if m_mode=="manual" else ""}>Manual</option>
            <option value="auto"   {"selected" if m_mode=="auto"   else ""}>Auto</option>
          </select>
          <h2>User Speed</h2><input type="number" name="speed"      value="{m_speed}" min="0" max="4">
          <h2>Target Temp (°C)</h2><input type="number" name="target_temp" value="{target}">
          <h2>Hysteresis</h2><input type="number" name="hysteresis"   value="{hyst}">
          <h2>Min Speed</h2><input type="number" name="min_speed"    value="{min_sp}" min="0" max="4">
          <h2>Max Speed</h2><input type="number" name="max_speed"    value="{max_sp}" min="0" max="4">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>
    </div>

    <div class="row">
      <!-- Network Settings -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Network Settings</h1><hr>
        <form method="get">
          <h2>Host (IP)</h2><input type="text"   name="host"           value="{host}">
          <h2>Wi‑Fi SSID</h2><input type="text"   name="wifi_ssid"     value="{wifi_ssid}">
          <h2>Wi‑Fi Password</h2><input type="text" name="wifi_password" value="{wifi_pw}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>

      <!-- InfluxDB Settings -->
      <div class="col-md-6"><div class="formwrap">
        <h1>InfluxDB Settings</h1><hr>
        <form method="get">
          <h2>DB Name</h2><input type="text"   name="influx_db"   value="{influx_name}">
          <h2>Port</h2><input type="number"    name="influx_port" value="{influx_port}">
          <h2>User</h2><input type="text"      name="influx_user" value="{influx_user}">
          <h2>Password</h2><input type="text"   name="influx_pw"   value="{influx_pw}">
          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>
    </div>

    <!-- ─────────────────────────────────────────────────────── -->
    <!-- Temperature Settings -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>Temperature Settings</h1><hr>
        <form method="get">
          <!-- Jour -->
          <h2>Day</h2>
          <label>Min</label>
          <input type="number" name="target_temp_min_day"   value="{tmin_day}"   step="0.5">
          <label>Max</label>
          <input type="number" name="target_temp_max_day"   value="{tmax_day}"   step="0.5">

          <!-- Nuit -->
          <h2>Night</h2>
          <label>Min</label>
          <input type="number" name="target_temp_min_night" value="{tmin_night}" step="0.5">
          <label>Max</label>
          <input type="number" name="target_temp_max_night" value="{tmax_night}" step="0.5">

          <!-- Offset d’hystérésis -->
          <h2>Hysteresis Offset (°C)</h2><input type="number" name="hysteresis_offset" value="{offset}" step="0.1">

          <div class="div_center"><input class="button_base" type="submit" value="Save"></div>
        </form>
      </div></div>
    </div>
    
    <!-- ─────────────────────────────────────────────────────── -->
    <!-- Heater Control -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>Heater Control</h1><hr>
        <p>Le chauffage est piloté automatiquement selon les plages jour/nuit et l’hystérésis, mais vous pouvez l’activer ou le désactiver manuellement :</p>
        <form method="get">
          <h2>Activation</h2>
          <select name="heater_enabled">
            <option value="enabled"  {"selected" if heater_enabled=="enabled"  else ""}>Enabled</option>
            <option value="disabled" {"selected" if heater_enabled=="disabled" else ""}>Disabled</option>
          </select>
          <h2>GPIO Pin</h2>
          <input type="number" name="heater_pin" value="{heater_pin}">
          <div class="div_center">
            <input class="button_base" type="submit" value="Save">
          </div>
        </form>
      </div></div>
    </div>

  </div>
</section>
{html_footer}"""


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques
# ==============================================================

def monitor_page(sensor_handler) -> str:
    """
    Page « Monitor » : affiche les valeurs en temps réel des capteurs.
    """
    def _fmt(val, unit):
        return f"{val:.1f}&nbsp;{unit}" if isinstance(val, (int, float)) else val

    # BME280
    t   = sensor_handler.get_sensor_value("BME280T")   or "―"
    h   = sensor_handler.get_sensor_value("BME280H")   or "―"
    p   = sensor_handler.get_sensor_value("BME280P")   or "―"
    # DS18B20
    ds1 = sensor_handler.get_sensor_value("DS18B#1")   or "―"
    ds2 = sensor_handler.get_sensor_value("DS18B#2")   or "―"
    ds3 = sensor_handler.get_sensor_value("DS18B#3")   or "―"
    # MLX IR
    mlx_amb = sensor_handler.get_sensor_value("MLX-AMB") or "―"
    mlx_obj = sensor_handler.get_sensor_value("MLX-OBJ") or "―"
    # Distance
    tof     = sensor_handler.get_sensor_value("VL53-DIST") or "―"
    us      = sensor_handler.get_sensor_value("HCSR-DIST") or "―"
    # Light
    lux     = sensor_handler.get_sensor_value("TSL-LUX")    or "―"

    return f"""{html_header}
<div class="container-fluid">
  <h1 class="text-center">Monitor Page</h1><br>
  <p><a href="/">System State</a></p>
  <p><a href="monitor">Monitored Values</a></p>
  <p><a href="conf">System Configuration</a></p><br><br>

  <div class="row">
    <div class="col-md-6">
      <h1>BME280</h1><hr>
      <div class="mainwrap"><h1>Temp</h1><hr><h2>{_fmt(t,'°C')}</h2></div>
      <div class="mainwrap"><h1>Humid</h1><hr><h2>{_fmt(h,'%')}</h2></div>
      <div class="mainwrap"><h1>Pres</h1><hr><h2>{_fmt(p,'hPa')}</h2></div>
    </div>
    <div class="col-md-6">
      <h1>Other Sensors</h1><hr>
      <div class="mainwrap"><h1>DS18 #1</h1><hr><h2>{_fmt(ds1,'°C')}</h2></div>
      <div class="mainwrap"><h1>DS18 #2</h1><hr><h2>{_fmt(ds2,'°C')}</h2></div>
      <div class="mainwrap"><h1>DS18 #3</h1><hr><h2>{_fmt(ds3,'°C')}</h2></div>
      <div class="mainwrap"><h1>MLX Amb</h1><hr><h2>{_fmt(mlx_amb,'°C')}</h2></div>
      <div class="mainwrap"><h1>MLX Obj</h1><hr><h2>{_fmt(mlx_obj,'°C')}</h2></div>
      <div class="mainwrap"><h1>ToF (mm)</h1><hr><h2>{tof}</h2></div>
      <div class="mainwrap"><h1>US (cm)</h1><hr><h2>{us}</h2></div>
      <div class="mainwrap"><h1>Lux</h1><hr><h2>{lux}</h2></div>
    </div>
  </div>
</div>
{html_footer}"""
