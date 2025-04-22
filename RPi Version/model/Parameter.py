# model/Parameter.py
# Author : Progradius (adapted)
# License : AGPL‑3.0
# ------------------------------------------------------------------
#  Accès / mise‑à‑jour des paramètres   (JSON ⇆ objet Python)
# ------------------------------------------------------------------
"""
Cette classe encapsule **param.json**

• À l'instanciation, toutes les valeurs sont lues depuis le fichier  
• Des getters et setters (très nombreux) donnent accès à chaque champ  
• `_refresh_from_json()` peut être rappelé pour recharger le fichier  
• Quelques alias pratiques (ex. `get_dailytimer1_start()`) simplifient
  l'usage dans `pages.py` et ailleurs  
• Des *setters génériques* (`set_stage`, `set_period_minutes`, …) sont
  utilisés par le serveur HTTP pour appliquer à chaud les changements
  envoyés depuis l'interface web.
"""

from controller.parameter_handler import read_parameters_from_json


class Parameter:
    # ────────────────────────── init / refresh ──────────────────────────
    def __init__(self) -> None:
        self._refresh_from_json()          # charge toutes les valeurs

        # Dictionnaire normalisé des capteurs exploités dans l'app
        self.sensor_dict = {
            "air":   ["DS18B#1", "DS18B#2", "DS18B#3",
                      "BME280T", "BME280H", "BME280P"],
            "light": ["TSL-LUX", "TSL-IR",
                      "VEML-UVA", "VEML-UVB", "VEML-UVINDEX"],
        }

    # -------------------------------------------------------------------
    #                     lecture complète depuis le JSON
    # -------------------------------------------------------------------
    def _refresh_from_json(self) -> None:
        p = read_parameters_from_json()  # dict brut

        # ――― Etape de croissance ―――――――――――――――――――――――――――――――――
        self.growth_stage = p["life_period"]["stage"]

        # ――― DailyTimer 1 ――――――――――――――――――――――――――――――――――――――
        dt1 = p["DailyTimer1_Settings"]
        self.dailytimer1_start_hour   = int(dt1["start_hour"])
        self.dailytimer1_start_minute = int(dt1["start_minute"])
        self.dailytimer1_stop_hour    = int(dt1["stop_hour"])
        self.dailytimer1_stop_minute  = int(dt1["stop_minute"])

        # ――― DailyTimer 2 ――――――――――――――――――――――――――――――――――――――
        dt2 = p["DailyTimer2_Settings"]
        self.dailytimer2_start_hour   = int(dt2["start_hour"])
        self.dailytimer2_start_minute = int(dt2["start_minute"])
        self.dailytimer2_stop_hour    = int(dt2["stop_hour"])
        self.dailytimer2_stop_minute  = int(dt2["stop_minute"])

        # ――― Cyclic 1 ――――――――――――――――――――――――――――――――――――――――――
        cy1 = p["Cyclic1_Settings"]
        self.cyclic1_period_minutes           = int(cy1["period_minutes"])
        self.cyclic1_action_duration_seconds  = int(cy1["action_duration_seconds"])

        # ――― Cyclic 2 ――――――――――――――――――――――――――――――――――――――――――
        cy2 = p["Cyclic2_Settings"]
        self.cyclic2_period_minutes           = int(cy2["period_minutes"])
        self.cyclic2_action_duration_seconds  = int(cy2["action_duration_seconds"])

        # ――― Réseau ―――――――――――――――――――――――――――――――――――――――――――
        net = p["Network_Settings"]
        self.host_machine_address = net["host_machine_address"]
        self.host_machine_state   = net["host_machine_state"]
        self.wifi_ssid            = net["wifi_ssid"]
        self.wifi_password        = net["wifi_password"]
        self.influx_db_port       = net["influx_db_port"]
        self.influx_db_name       = net["influx_db_name"]
        self.influx_db_user       = net["influx_db_user"]
        self.influx_db_password   = net["influx_db_password"]

        # ――― GPIO ―――――――――――――――――――――――――――――――――――――――――――――――
        g = p["GPIO_Settings"]
        (self.i2c_sda, self.i2c_scl,
         self.ds18_pin,
         self.hcsr_trigger_pin, self.hcsr_echo_pin,
         self.dailytimer1_pin, self.dailytimer2_pin,
         self.cyclic1_pin,    self.cyclic2_pin,
         self.motor_pin1, self.motor_pin2,
         self.motor_pin3, self.motor_pin4) = (
            g["i2c_sda"],  g["i2c_scl"],
            g["ds18_pin"],
            g["hcsr_trigger_pin"], g["hcsr_echo_pin"],
            g["dailytimer1_pin"],  g["dailytimer2_pin"],
            g["cyclic1_pin"],      g["cyclic2_pin"],
            g["motor_pin1"], g["motor_pin2"],
            g["motor_pin3"], g["motor_pin4"]
        )

        # ――― Moteur ――――――――――――――――――――――――――――――――――――――――――――
        m = p["Motor_Settings"]
        self.motor_mode       = m["motor_mode"]
        self.motor_user_speed = m["motor_user_speed"]
        self.target_temp      = m["target_temp"]
        self.hysteresis       = m["hysteresis"]
        self.motor_min_speed  = m["min_speed"]
        self.motor_max_speed  = m["max_speed"]

        # ――― Capteurs ――――――――――――――――――――――――――――――――――――――――――
        s = p["Sensor_State"]
        (self.bme_state, self.ds18_state, self.veml_state,
         self.vl53_state, self.mlx_state, self.tsl_state,
         self.hcsr_state) = (
            s["bme280_state"],  s["ds18b20_state"], s["veml6075_state"],
            s["vl53L0x_state"], s["mlx90614_state"], s["tsl2591_state"],
            s["hcsr04_state"]
        )

    # ===================================================================
    #                          ALIAS PRATIQUES
    # ===================================================================
    _fmt = staticmethod(lambda h, m: f"{int(h):02d}:{int(m):02d}")

    def get_dailytimer1_start(self): return self._fmt(
        self.dailytimer1_start_hour, self.dailytimer1_start_minute)

    def get_dailytimer1_stop(self):  return self._fmt(
        self.dailytimer1_stop_hour,  self.dailytimer1_stop_minute)

    get_cyclic1_period   = lambda self: self.cyclic1_period_minutes
    get_cyclic1_duration = lambda self: self.cyclic1_action_duration_seconds
    get_life_stage       = lambda self: self.growth_stage

    # ===================================================================
    #         SETTERS « généraux » utilisés par l'interface HTTP
    # ===================================================================
    # (Le serveur appelle `set_<clé>` dynamiquement)
    def set_stage(self, v):            self.set_growth_stage(v)
    def set_period_minutes(self, v):   self.set_cyclic1_period_minutes(int(v))
    def set_action_duration_seconds(self, v):
        self.set_cyclic1_action_duration_seconds(int(v))

    # pour dt1start/dt1stop → split HH:MM effectué côté serveur
    def set_start_hour(self, v):  self.set_dailytimer1_start_hour(int(v))
    def set_start_minute(self, v):self.set_dailytimer1_start_minute(int(v))
    def set_stop_hour(self, v):   self.set_dailytimer1_stop_hour(int(v))
    def set_stop_minute(self, v): self.set_dailytimer1_stop_minute(int(v))
    # Setters
    def set_dailytimer1_start_hour(self, start_hour):
        self.dailytimer1_start_hour = start_hour

    def set_dailytimer1_start_minute(self, start_minute):
        self.dailytimer1_start_minute = start_minute

    def set_dailytimer1_stop_hour(self, stop_hour):
        self.dailytimer1_stop_hour = stop_hour

    def set_dailytimer1_stop_minute(self, stop_minute):
        self.dailytimer1_stop_minute = stop_minute

    def set_dailytimer2_start_hour(self, start_hour):
        self.dailytimer2_start_hour = start_hour

    def set_dailytimer2_start_minute(self, start_minute):
        self.dailytimer2_start_minute = start_minute

    def set_dailytimer2_stop_hour(self, stop_hour):
        self.dailytimer2_stop_hour = stop_hour

    def set_dailytimer2_stop_minute(self, stop_minute):
        self.dailytimer2_stop_minute = stop_minute

    def set_cyclic1_period_minutes(self, period):
        self.cyclic1_period_minutes = period

    def set_cyclic1_action_duration_seconds(self, duration):
        self.cyclic1_action_duration_seconds = duration

    def set_cyclic2_period_minutes(self, period):
        self.cyclic2_period_minutes = period

    def set_cyclic2_action_duration_seconds(self, duration):
        self.cyclic2_action_duration_seconds = duration

    def set_growth_stage(self, stage):
        self.growth_stage = stage

    def set_host_machine_address(self, host):
        self.host_machine_address = host

    def set_host_machine_state(self, state):
        self.host_machine_state = state

    def set_wifi_ssid(self, ssid):
        self.wifi_ssid = ssid

    def set_wifi_password(self, password):
        self.wifi_password = password

    def set_influx_db_user(self, user):
        self.influx_db_user = user

    def set_influx_db_password(self, passwd):
        self.influx_db_password = passwd

    def set_influx_db_name(self, table):
        self.influx_db_name = table

    def set_influx_db_port(self, host):
        self.influx_db_port = host

    def set_i2c_sda(self, pin):
        self.i2c_sda = pin

    def set_i2c_scl(self, pin):
        self.i2c_scl = pin

    def set_ds18_pin(self, pin):
        self.ds18_pin = pin

    def set_hcsr_trigger_pin(self, pin):
        self.hcsr_trigger_pin = pin

    def set_hcsr_echo_pin(self, pin):
        self.hcsr_echo_pin = pin

    def set_dailytimer1_pin(self, pin):
        self.dailytimer1_pin = pin

    def set_dailytimer2_pin(self, pin):
        self.dailytimer2_pin = pin

    def set_cyclic1_pin(self, pin):
        self.cyclic1_pin = pin

    def set_cyclic2_pin(self, pin):
        self.cyclic2_pin = pin

    def set_motor_pin1(self, pin):
        self.motor_pin1 = pin

    def set_motor_pin2(self, pin):
        self.motor_pin2 = pin

    def set_motor_pin3(self, pin):
        self.motor_pin3 = pin

    def set_motor_pin4(self, pin):
        self.motor_pin4 = pin

    def set_min_speed(self, speed):
        self.motor_min_speed = speed

    def set_max_speed(self, speed):
        self.motor_max_speed = speed

    def set_motor_mode(self, mode):
        self.motor_mode = mode

    def set_motor_user_speed(self, speed):
        self.motor_user_speed = speed

    def set_target_temp(self, temp):
        self.target_temp = temp

    def set_hysteresis(self, hysteresis):
        self.hysteresis = hysteresis

    def set_motor_min_speed(self, speed):
        self.motor_min_speed = speed

    def set_motor_max_speed(self, speed):
        self.motor_max_speed = speed

    def set_bme_state(self, state):
        self.bme_state = state

    def set_ds18_state(self, state):
        self.ds18_state = state

    def set_veml_state(self, state):
        self.veml_state = state

    def set_vl53_state(self, state):
        self.vl53_state = state

    def set_mlx_state(self, state):
        self.mlx_state = state

    def set_tsl_state(self, state):
        self.tsl_state = state

    def set_hcsr_state(self, state):
        self.hcsr_state = state

    # Getters
    def get_dailytimer1_start_hour(self):
        return self.dailytimer1_start_hour

    def get_dailytimer1_start_minute(self):
        return self.dailytimer1_start_minute

    def get_dailytimer1_stop_hour(self):
        return self.dailytimer1_stop_hour

    def get_dailytimer1_stop_minute(self):
        return self.dailytimer1_stop_minute

    def get_dailytimer1_start_time_formated(self):
        if len(str(self.dailytimer1_start_hour)) < 2:
            dt_start_hour = '0' + str(self.dailytimer1_start_hour)
        else:
            dt_start_hour = str(self.dailytimer1_start_hour)

        if len(str(self.dailytimer1_start_minute)) < 2:
            dt_start_minute = '0' + str(self.dailytimer1_start_minute)
        else:
            dt_start_minute = str(self.dailytimer1_start_minute)
        return dt_start_hour + ':' + dt_start_minute

    def get_dailytimer1_stop_time_formated(self):
        if len(str(self.dailytimer1_stop_hour)) < 2:
            dt_stop_hour = '0' + str(self.dailytimer1_stop_hour)
        else:
            dt_stop_hour = str(self.dailytimer1_stop_hour)

        if len(str(self.dailytimer1_stop_minute)) < 2:
            dt_stop_minute = '0' + str(self.dailytimer1_stop_minute)
        else:
            dt_stop_minute = str(self.dailytimer1_stop_minute)
        return dt_stop_hour + ':' + dt_stop_minute

    def get_cyclic1_period_minutes(self):
        return self.cyclic1_period_minutes

    def get_cyclic1_action_duration_seconds(self):
        return self.cyclic1_action_duration_seconds

    def get_dailytimer2_start_hour(self):
        return self.dailytimer2_start_hour

    def get_dailytimer2_start_minute(self):
        return self.dailytimer2_start_minute

    def get_dailytimer2_stop_hour(self):
        return self.dailytimer2_stop_hour

    def get_dailytimer2_stop_minute(self):
        return self.dailytimer2_stop_minute

    def get_dailytimer2_start_time_formated(self):
        if len(str(self.dailytimer2_start_hour)) < 2:
            dt_start_hour = '0' + str(self.dailytimer2_start_hour)
        else:
            dt_start_hour = str(self.dailytimer2_start_hour)

        if len(str(self.dailytimer2_start_minute)) < 2:
            dt_start_minute = '0' + str(self.dailytimer2_start_minute)
        else:
            dt_start_minute = str(self.dailytimer2_start_minute)
        return dt_start_hour + ':' + dt_start_minute

    def get_dailytimer2_stop_time_formated(self):
        if len(str(self.dailytimer2_stop_hour)) < 2:
            dt_stop_hour = '0' + str(self.dailytimer2_stop_hour)
        else:
            dt_stop_hour = str(self.dailytimer2_stop_hour)

        if len(str(self.dailytimer2_stop_minute)) < 2:
            dt_stop_minute = '0' + str(self.dailytimer2_stop_minute)
        else:
            dt_stop_minute = str(self.dailytimer2_stop_minute)
        return dt_stop_hour + ':' + dt_stop_minute

    def get_cyclic2_period_minutes(self):
        return self.cyclic2_period_minutes

    def get_cyclic2_action_duration_seconds(self):
        return self.cyclic2_action_duration_seconds

    def get_growth_stage(self):
        return self.growth_stage

    def get_host_machine_address(self):
        return self.host_machine_address

    def get_host_machine_state(self):
        return self.host_machine_state

    def get_wifi_ssid(self):
        return self.wifi_ssid

    def get_wifi_password(self):
        return self.wifi_password

    def get_influx_db_user(self):
        return self.influx_db_user

    def get_influx_db_password(self):
        return self.influx_db_password

    def get_influx_db_name(self):
        return self.influx_db_name

    def get_influx_db_port(self):
        return self.influx_db_port

    def get_i2c_sda(self):
        return self.i2c_sda

    def get_i2c_scl(self):
        return self.i2c_scl

    def get_ds18_pin(self):
        return self.ds18_pin

    def get_hcsr_trigger_pin(self):
        return self.hcsr_trigger_pin

    def get_hcsr_echo_pin(self):
        return self.hcsr_echo_pin

    def get_dailytimer1_pin(self):
        return self.dailytimer1_pin

    def get_dailytimer2_pin(self):
        return self.dailytimer2_pin

    def get_cyclic1_pin(self):
        return self.cyclic1_pin

    def get_cyclic2_pin(self):
        return self.cyclic2_pin

    def get_motor_pin1(self):
        return self.motor_pin1

    def get_motor_pin2(self):
        return self.motor_pin2

    def get_motor_pin3(self):
        return self.motor_pin3

    def get_motor_pin4(self):
        return self.motor_pin4

    def get_min_speed(self):
        return self.motor_min_speed

    def get_max_speed(self):
        return self.motor_max_speed

    def get_motor_mode(self):
        return self.motor_mode

    def get_motor_user_speed(self):
        return self.motor_user_speed

    def get_bme_state(self):
        return self.bme_state

    def get_ds18_state(self):
        return self.ds18_state

    def get_veml_state(self):
        return self.veml_state

    def get_vl53_state(self):
        return self.vl53_state

    def get_mlx_state(self):
        return self.mlx_state

    def get_tsl_state(self):
        return self.tsl_state

    def get_hcsr_state(self):
        return self.hcsr_state

    def get_target_temp(self):
        return self.target_temp

    def get_hysteresis(self):
        return self.hysteresis

    def get_motor_min_speed(self):
        return self.motor_min_speed

    def get_motor_max_speed(self):
        return self.motor_max_speed
