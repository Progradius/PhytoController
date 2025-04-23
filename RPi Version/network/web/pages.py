# controller/web/pages.py
# Author: Progradius (adapted)
# License: AGPL-3.0

from datetime import datetime
import RPi.GPIO as GPIO

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
p,a,li{font-family:'Dosis',sans-serif;font-size:13px;}
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

# Initialise RPi.GPIO pour lecture
GPIO.setmode(GPIO.BCM)

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
    Les champs sont pré-remplis à partir de `parameters`.
    """
    # --- DailyTimer #1
    dt1_start      = f"{parameters.get_dailytimer1_start_hour():02d}:{parameters.get_dailytimer1_start_minute():02d}"
    dt1_stop       = f"{parameters.get_dailytimer1_stop_hour():02d}:{parameters.get_dailytimer1_stop_minute():02d}"
    dt1_pin        = parameters.get_dailytimer1_pin()

    # --- DailyTimer #2
    dt2_start      = f"{parameters.get_dailytimer2_start_hour():02d}:{parameters.get_dailytimer2_start_minute():02d}"
    dt2_stop       = f"{parameters.get_dailytimer2_stop_hour():02d}:{parameters.get_dailytimer2_stop_minute():02d}"
    dt2_pin        = parameters.get_dailytimer2_pin()

    # --- Cyclic #1
    c1_period      = parameters.get_cyclic1_period_minutes()
    c1_dur         = parameters.get_cyclic1_action_duration_seconds()
    c1_pin         = parameters.get_cyclic1_pin()

    # --- Cyclic #2
    c2_period      = parameters.get_cyclic2_period_minutes()
    c2_dur         = parameters.get_cyclic2_action_duration_seconds()
    c2_pin         = parameters.get_cyclic2_pin()

    # --- Heater
    heater_enabled = parameters.get_heater_enabled()
    heater_pin     = parameters.get_heater_pin()

    # --- Motor (mode + vitesses)
    stage          = parameters.get_growth_stage()
    m_mode         = parameters.get_motor_mode()
    m_speed        = parameters.get_motor_user_speed()
    target_temp    = parameters.get_target_temp()
    hysteresis     = parameters.get_hysteresis()
    min_speed      = parameters.get_motor_min_speed()
    max_speed      = parameters.get_motor_max_speed()
    motor_pin1     = parameters.get_motor_pin1()
    motor_pin2     = parameters.get_motor_pin2()
    motor_pin3     = parameters.get_motor_pin3()
    motor_pin4     = parameters.get_motor_pin4()

    # --- Network & Influx
    host           = parameters.get_host_machine_address()
    wifi_ssid      = parameters.get_wifi_ssid()
    wifi_pw        = parameters.get_wifi_password()
    influx_name    = parameters.get_influx_db_name()
    influx_port    = parameters.get_influx_db_port()
    influx_user    = parameters.get_influx_db_user()
    influx_pw      = parameters.get_influx_db_password()

    # --- Temperature Settings
    tmin_day       = parameters.get_target_temp_min_day()
    tmax_day       = parameters.get_target_temp_max_day()
    tmin_night     = parameters.get_target_temp_min_night()
    tmax_night     = parameters.get_target_temp_max_night()
    hyst_offset    = parameters.get_hysteresis_offset()

    return f"""{html_header}
<section id="conf">
  <div class="container-fluid">
    <h1 class="text-center">Configuration Page</h1><br>
    <p><a href="/">System State</a></p>
    <p><a href="monitor">Monitored Values</a></p>
    <p><a href="conf">System Configuration</a></p><br><br>

    <!-- GPIO Settings -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>GPIO Settings</h1><hr>
        <form method="get">
          <h2>DailyTimer 1 Pin</h2><input type="number" name="dailytimer1_pin" value="{dt1_pin}">
          <h2>DailyTimer 2 Pin</h2><input type="number" name="dailytimer2_pin" value="{dt2_pin}">
          <h2>Cyclic 1 Pin</h2>    <input type="number" name="cyclic1_pin"     value="{c1_pin}">
          <h2>Cyclic 2 Pin</h2>    <input type="number" name="cyclic2_pin"     value="{c2_pin}">
          <h2>Heater Pin</h2>      <input type="number" name="heater_pin"      value="{heater_pin}">
          <h2>Motor Pin 1</h2>     <input type="number" name="motor_pin1"      value="{motor_pin1}">
          <h2>Motor Pin 2</h2>     <input type="number" name="motor_pin2"      value="{motor_pin2}">
          <h2>Motor Pin 3</h2>     <input type="number" name="motor_pin3"      value="{motor_pin3}">
          <h2>Motor Pin 4</h2>     <input type="number" name="motor_pin4"      value="{motor_pin4}">
          <div class="div_center"><input class="button_base" type="submit" value="Save GPIO"></div>
        </form>
      </div></div>
    </div>

    <!-- DailyTimer #1 -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #1</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="hour" name="dt1start" value="{dt1_start}">
          <h2>Stop</h2> <input type="hour" name="dt1stop"  value="{dt1_stop}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Timer 1"></div>
        </form>
      </div></div>

    <!-- DailyTimer #2 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #2</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="hour" name="dt2start" value="{dt2_start}">
          <h2>Stop</h2> <input type="hour" name="dt2stop"  value="{dt2_stop}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Timer 2"></div>
        </form>
      </div></div>
    </div>

    <!-- Cyclic #1 -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #1</h1><hr>
        <form method="get">
          <h2>Period (min)</h2>  <input type="number" name="period"   value="{c1_period}">
          <h2>Duration (sec)</h2><input type="number" name="duration" value="{c1_dur}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Cyclic 1"></div>
        </form>
      </div></div>

    <!-- Cyclic #2 -->
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #2</h1><hr>
        <form method="get">
          <h2>Period (min)</h2>  <input type="number" name="period2"   value="{c2_period}">
          <h2>Duration (sec)</h2><input type="number" name="duration2" value="{c2_dur}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Cyclic 2"></div>
        </form>
      </div></div>
    </div>

    <!-- Heater Control -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>Heater Control</h1><hr>
        <form method="get">
          <h2>Activation</h2>
          <select name="heater_enabled">
            <option value="enabled"  {"selected" if heater_enabled=="enabled"  else ""}>Enabled</option>
            <option value="disabled" {"selected" if heater_enabled=="disabled" else ""}>Disabled</option>
          </select>
          <div class="div_center"><input class="button_base" type="submit" value="Save Heater"></div>
        </form>
      </div></div>
    </div>

    <!-- Motor Settings -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>Motor Settings</h1><hr>
        <form method="get">
          <h2>Mode</h2>
          <select name="motor_mode">
            <option value="manual" {"selected" if m_mode=="manual" else ""}>Manual</option>
            <option value="auto"   {"selected" if m_mode=="auto"   else ""}>Auto</option>
          </select>
          <h2>User Speed</h2>   <input type="number" name="speed"    value="{m_speed}" min="0" max="4">
          <h2>Target Temp (°C)</h2><input type="number" name="target_temp" value="{target_temp}">
          <h2>Hysteresis</h2>   <input type="number" name="hysteresis"   value="{hysteresis}">
          <h2>Min Speed</h2>    <input type="number" name="min_speed"   value="{min_speed}" min="0" max="4">
          <h2>Max Speed</h2>    <input type="number" name="max_speed"   value="{max_speed}" min="0" max="4">
          <div class="div_center"><input class="button_base" type="submit" value="Save Motor"></div>
        </form>
      </div></div>
    </div>

    <!-- Network Settings -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>Network Settings</h1><hr>
        <form method="get">
          <h2>Host (IP)</h2>       <input type="text"   name="host"          value="{host}">
          <h2>Wi-Fi SSID</h2>      <input type="text"   name="wifi_ssid"     value="{wifi_ssid}">
          <h2>Wi-Fi Password</h2>  <input type="password" name="wifi_password" value="{wifi_pw}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Network"></div>
        </form>
      </div></div>

      <div class="col-md-6"><div class="formwrap">
        <h1>InfluxDB Settings</h1><hr>
        <form method="get">
          <h2>DB Name</h2>         <input type="text"   name="influx_db"   value="{influx_name}">
          <h2>Port</h2>            <input type="number" name="influx_port" value="{influx_port}">
          <h2>User</h2>            <input type="text"   name="influx_user" value="{influx_user}">
          <h2>Password</h2>        <input type="password" name="influx_pw"   value="{influx_pw}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Influx"></div>
        </form>
      </div></div>
    </div>

    <!-- Temperature Settings -->
    <div class="row">
      <div class="col-md-12"><div class="formwrap">
        <h1>Temperature Settings</h1><hr>
        <form method="get">
          <h2>Day</h2>
          <label>Min</label> <input type="number" name="target_temp_min_day"   value="{tmin_day}"   step="0.5">
          <label>Max</label> <input type="number" name="target_temp_max_day"   value="{tmax_day}"   step="0.5">

          <h2>Night</h2>
          <label>Min</label> <input type="number" name="target_temp_min_night" value="{tmin_night}" step="0.5">
          <label>Max</label> <input type="number" name="target_temp_max_night" value="{tmax_night}" step="0.5">

          <h2>Hysteresis Offset (°C)</h2>
          <input type="number" name="hysteresis_offset" value="{hyst_offset}" step="0.1">

          <div class="div_center"><input class="button_base" type="submit" value="Save Temp"></div>
        </form>
      </div></div>
    </div>

  </div>
</section>
{html_footer}"""


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques
# ==============================================================
def monitor_page(sensor_handler, stats, parameters) -> str:
    """
    Page « Monitor » :
    - Valeurs temps réel des capteurs
    - Historique min/max avec dates formatées
    - États GPIO (On/Off)
    """
    def _fmt(val, unit):
        return f"{val:.1f}&nbsp;{unit}" if isinstance(val, (int, float)) else "―"
    def _fmt_stat(val, unit=""):
        return f"{val:.1f}{unit}" if isinstance(val, (int, float)) else "—"
    def _fmt_date(dt_str):
        if not dt_str:
            return "—"
        try:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            return dt_str

    # → relevés actuels
    t       = sensor_handler.get_sensor_value("BME280T")   or None
    h       = sensor_handler.get_sensor_value("BME280H")   or None
    p       = sensor_handler.get_sensor_value("BME280P")   or None
    ds1     = sensor_handler.get_sensor_value("DS18B#1")   or None
    ds2     = sensor_handler.get_sensor_value("DS18B#2")   or None
    ds3     = sensor_handler.get_sensor_value("DS18B#3")   or None
    mlx_amb = sensor_handler.get_sensor_value("MLX-AMB")   or None
    mlx_obj = sensor_handler.get_sensor_value("MLX-OBJ")   or None
    tof     = sensor_handler.get_sensor_value("VL53-DIST") or None
    us      = sensor_handler.get_sensor_value("HCSR-DIST") or None
    lux     = sensor_handler.get_sensor_value("TSL-LUX")   or None

    # stats
    all_stats = stats.get_all()

    # GPIO etats
    gpio_map = {
        "DailyTimer #1": parameters.get_dailytimer1_pin(),
        "DailyTimer #2": parameters.get_dailytimer2_pin(),
        "Cyclic #1"    : parameters.get_cyclic1_pin(),
        "Cyclic #2"    : parameters.get_cyclic2_pin(),
        "Heater"       : parameters.get_heater_pin(),
        "Motor Pin 1"  : parameters.get_motor_pin1(),
        "Motor Pin 2"  : parameters.get_motor_pin2(),
        "Motor Pin 3"  : parameters.get_motor_pin3(),
        "Motor Pin 4"  : parameters.get_motor_pin4(),
    }
    gpio_html = ""
    for name, pin in gpio_map.items():
        try:
            state = GPIO.input(pin)
            onoff = "On" if state == GPIO.HIGH else "Off"
        except Exception:
            onoff = "—"
        gpio_html += f"<li>{name} (pin {pin}) : {onoff}</li>\n"

    return f"""{html_header}
<div class="container-fluid">
  <h1 class="text-center">Monitor Page</h1><br>
  <p><a href="/">System State</a></p>
  <p><a href="monitor">Monitored Values</a></p>
  <p><a href="conf">System Configuration</a></p><br><br>

  <!-- Valeurs en temps réel -->
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
      <div class="mainwrap"><h1>ToF (mm)</h1><hr><h2>{_fmt(tof,'mm')}</h2></div>
      <div class="mainwrap"><h1>US (cm)</h1><hr><h2>{_fmt(us,'cm')}</h2></div>
      <div class="mainwrap"><h1>Lux</h1><hr><h2>{_fmt(lux,'lx')}</h2></div>
    </div>
  </div>

  <!-- Historique min/max -->
  <div class="row">
    <div class="col-md-12"><div class="formwrap">
      <h1>Historique min/max</h1><hr>

      <h2>BME280 Temp</h2>
      <p>Min : {_fmt_stat(all_stats["BME280T"]["min"],"°C")} le {_fmt_date(all_stats["BME280T"]["min_date"])}</p>
      <p>Max : {_fmt_stat(all_stats["BME280T"]["max"],"°C")} le {_fmt_date(all_stats["BME280T"]["max_date"])}</p>
      <form method="get" action="/monitor">
        <input type="hidden" name="reset_BME280T" value="1">
        <input class="button_base" type="submit" value="Reset BME Temp">
      </form><hr>

      <h2>BME280 Humid</h2>
      <p>Min : {_fmt_stat(all_stats["BME280H"]["min"],"%")} le {_fmt_date(all_stats["BME280H"]["min_date"])}</p>
      <p>Max : {_fmt_stat(all_stats["BME280H"]["max"],"%")} le {_fmt_date(all_stats["BME280H"]["max_date"])}</p>
      <form method="get" action="/monitor">
        <input type="hidden" name="reset_BME280H" value="1">
        <input class="button_base" type="submit" value="Reset BME Humid">
      </form><hr>

      <h2>DS18B#3 (Water)</h2>
      <p>Min : {_fmt_stat(all_stats["DS18B#3"]["min"],"°C")} le {_fmt_date(all_stats["DS18B#3"]["min_date"])}</p>
      <p>Max : {_fmt_stat(all_stats["DS18B#3"]["max"],"°C")} le {_fmt_date(all_stats["DS18B#3"]["max_date"])}</p>
      <form method="get" action="/monitor">
        <input type="hidden" name="reset_DS18B#3" value="1">
        <input class="button_base" type="submit" value="Reset Water Temp">
      </form>
    </div></div>
  </div>

  <!-- États GPIO -->
  <div class="row">
    <div class="col-md-12"><div class="formwrap">
      <h1>GPIO States</h1><hr>
      <ul>
        {gpio_html}
      </ul>
    </div></div>
  </div>

</div>
{html_footer}"""
