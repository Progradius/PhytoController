# controller/web/pages.py
# Author: Progradius (refactorisé)
# License: AGPL-3.0

from datetime import datetime
import RPi.GPIO as GPIO
from param.config import AppConfig

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
def conf_page(config: AppConfig) -> str:
    """
    Renvoie le formulaire HTML de configuration.
    Les champs sont pré-remplis à partir de `config`.
    """
    # GPIO
    gpio = config.gpio

    # DailyTimer
    dt1 = config.daily_timer1
    dt2 = config.daily_timer2

    # Cyclic
    c1 = config.cyclic1
    c2 = config.cyclic2

    # Heater
    heater = config.heater_settings

    # Motor
    motor = config.motor
    stage = config.life_period.stage

    # Network / Influx
    net  = config.network

    # Temperature
    temp = config.temperature

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
          <h2>DailyTimer 1 Pin</h2> <input type="number" name="dailytimer1_pin" value="{gpio.dailytimer1_pin}">
          <h2>DailyTimer 2 Pin</h2> <input type="number" name="dailytimer2_pin" value="{gpio.dailytimer2_pin}">
          <h2>Cyclic 1 Pin</h2>     <input type="number" name="cyclic1_pin"      value="{gpio.cyclic1_pin}">
          <h2>Cyclic 2 Pin</h2>     <input type="number" name="cyclic2_pin"      value="{gpio.cyclic2_pin}">
          <h2>Heater Pin</h2>       <input type="number" name="heater_pin"       value="{gpio.heater_pin}">
          <h2>Motor Pin 1</h2>      <input type="number" name="motor_pin1"       value="{gpio.motor_pin1}">
          <h2>Motor Pin 2</h2>      <input type="number" name="motor_pin2"       value="{gpio.motor_pin2}">
          <h2>Motor Pin 3</h2>      <input type="number" name="motor_pin3"       value="{gpio.motor_pin3}">
          <h2>Motor Pin 4</h2>      <input type="number" name="motor_pin4"       value="{gpio.motor_pin4}">
          <div class="div_center"><input class="button_base" type="submit" value="Save GPIO"></div>
        </form>
      </div></div>
    </div>

    <!-- DailyTimer #1 & #2 -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #1</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="time" name="dt1start" value="{dt1.start_hour:02d}:{dt1.start_minute:02d}">
          <h2>Stop</h2> <input type="time" name="dt1stop"  value="{dt1.stop_hour:02d}:{dt1.stop_minute:02d}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Timer 1"></div>
        </form>
      </div></div>
      <div class="col-md-6"><div class="formwrap">
        <h1>DailyTimer #2</h1><hr>
        <form method="get">
          <h2>Start</h2><input type="time" name="dt2start" value="{dt2.start_hour:02d}:{dt2.start_minute:02d}">
          <h2>Stop</h2> <input type="time" name="dt2stop"  value="{dt2.stop_hour:02d}:{dt2.stop_minute:02d}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Timer 2"></div>
        </form>
      </div></div>
    </div>

    <!-- Cyclic #1 & #2 -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #1</h1><hr>
        <form method="get">
          <h2>Period (min)</h2>  <input type="number" name="period"   value="{c1.period_minutes}">
          <h2>Duration (sec)</h2><input type="number" name="duration" value="{c1.action_duration_seconds}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Cyclic 1"></div>
        </form>
      </div></div>
      <div class="col-md-6"><div class="formwrap">
        <h1>Cyclic #2</h1><hr>
        <form method="get">
          <h2>Period (min)</h2>  <input type="number" name="period2"   value="{c2.period_minutes}">
          <h2>Duration (sec)</h2><input type="number" name="duration2" value="{c2.action_duration_seconds}">
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
            <option value="enabled"  {"selected" if heater.enabled else ""}>Enabled</option>
            <option value="disabled" {"selected" if not heater.enabled else ""}>Disabled</option>
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
          <h2>Stage</h2>       <input type="text"   name="stage"        value="{stage}">
          <h2>Mode</h2>        <select name="motor_mode">
            <option value="manual" {"selected" if motor.motor_mode=="manual" else ""}>Manual</option>
            <option value="auto"   {"selected" if motor.motor_mode=="auto"   else ""}>Auto</option>
          </select>
          <h2>User Speed</h2>   <input type="number" name="speed"        value="{motor.motor_user_speed}" min="0" max="4">
          <h2>Target Temp</h2>  <input type="number" name="target_temp"  value="{motor.target_temp}">
          <h2>Hysteresis</h2>   <input type="number" name="hysteresis"   value="{motor.hysteresis}">
          <h2>Min Speed</h2>    <input type="number" name="min_speed"    value="{motor.min_speed}" min="0" max="4">
          <h2>Max Speed</h2>    <input type="number" name="max_speed"    value="{motor.max_speed}" min="0" max="4">
          <div class="div_center"><input class="button_base" type="submit" value="Save Motor"></div>
        </form>
      </div></div>
    </div>

    <!-- Network & Influx -->
    <div class="row">
      <div class="col-md-6"><div class="formwrap">
        <h1>Network Settings</h1><hr>
        <form method="get">
          <h2>Host (IP)</h2>      <input type="text"   name="host"          value="{net.host_machine_address}">
          <h2>Wi-Fi SSID</h2>     <input type="text"   name="wifi_ssid"     value="{net.wifi_ssid}">
          <h2>Wi-Fi Password</h2> <input type="password" name="wifi_password" value="{net.wifi_password}">
          <div class="div_center"><input class="button_base" type="submit" value="Save Network"></div>
        </form>
      </div></div>
      <div class="col-md-6"><div class="formwrap">
        <h1>InfluxDB Settings</h1><hr>
        <form method="get">
          <h2>DB Name</h2>        <input type="text"   name="influx_db"   value="{net.influx_db_name}">
          <h2>Port</h2>           <input type="number" name="influx_port" value="{net.influx_db_port}">
          <h2>User</h2>           <input type="text"   name="influx_user" value="{net.influx_db_user}">
          <h2>Password</h2>       <input type="password" name="influx_pw"   value="{net.influx_db_password}">
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
          <label>Min</label> <input type="number" name="target_temp_min_day"   value="{temp.target_temp_min_day}" step="0.5">
          <label>Max</label> <input type="number" name="target_temp_max_day"   value="{temp.target_temp_max_day}" step="0.5">
          <h2>Night</h2>
          <label>Min</label> <input type="number" name="target_temp_min_night" value="{temp.target_temp_min_night}" step="0.5">
          <label>Max</label> <input type="number" name="target_temp_max_night" value="{temp.target_temp_max_night}" step="0.5">
          <h2>Hysteresis Offset</h2> <input type="number" name="hysteresis_offset" value="{temp.hysteresis_offset}" step="0.1">
          <div class="div_center"><input class="button_base" type="submit" value="Save Temp"></div>
        </form>
      </div></div>
    </div>

  </div>
</section>
{html_footer}"""


# ==============================================================
#  PAGE MONITORING  – valeurs dynamiques + GPIO
# ==============================================================
def monitor_page(sensor_handler, stats, config: AppConfig) -> str:
    """
    Page « Monitor » :
    - Valeurs en temps réel des capteurs
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

    # Relevés capteurs
    t      = sensor_handler.get_sensor_value("BME280T")   or None
    h      = sensor_handler.get_sensor_value("BME280H")   or None
    p      = sensor_handler.get_sensor_value("BME280P")   or None
    ds1    = sensor_handler.get_sensor_value("DS18B#1")   or None
    ds2    = sensor_handler.get_sensor_value("DS18B#2")   or None
    ds3    = sensor_handler.get_sensor_value("DS18B#3")   or None
    mlx_a  = sensor_handler.get_sensor_value("MLX-AMB")   or None
    mlx_o  = sensor_handler.get_sensor_value("MLX-OBJ")   or None
    tof    = sensor_handler.get_sensor_value("VL53-DIST") or None
    us     = sensor_handler.get_sensor_value("HCSR-DIST") or None
    lux    = sensor_handler.get_sensor_value("TSL-LUX")   or None

    # Stats min/max
    all_stats = stats.get_all()

    # États GPIO
    gpio = config.gpio
    gpio_map = {
        "DailyTimer #1": (gpio.dailytimer1_pin, "daily"),
        "DailyTimer #2": (gpio.dailytimer2_pin, "daily"),
        "Cyclic #1"    : (gpio.cyclic1_pin,     "cyclic"),
        "Cyclic #2"    : (gpio.cyclic2_pin,     "cyclic"),
        "Heater"       : (gpio.heater_pin,      "heater"),
        "Motor Pin 1"  : (gpio.motor_pin1,      "motor"),
        "Motor Pin 2"  : (gpio.motor_pin2,      "motor"),
        "Motor Pin 3"  : (gpio.motor_pin3,      "motor"),
        "Motor Pin 4"  : (gpio.motor_pin4,      "motor"),
    }
    gpio_html = ""
    for name, (pin, _) in gpio_map.items():
        try:
            state = GPIO.input(pin)
            onoff = "On" if state == GPIO.HIGH else "Off"
        except Exception:
            onoff = "—"
        gpio_html += f"<li>{name} (pin {pin}): {onoff}</li>\n"

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
      <h1>DS18B20</h1><hr>
      <div class="mainwrap"><h1>#1</h1><hr><h2>{_fmt(ds1,'°C')}</h2></div>
      <div class="mainwrap"><h1>#2</h1><hr><h2>{_fmt(ds2,'°C')}</h2></div>
      <div class="mainwrap"><h1>#3</h1><hr><h2>{_fmt(ds3,'°C')}</h2></div>
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
