# Author: Progradius
# License: AGPL 3.0

from controller.parameter_handler import read_parameters_from_json


class Parameter:
    """
    Class used to represent program parameters, allowing you to access/modify them
    """

    def __init__(self):
        # Get parameters from JSON
        self.param_json = read_parameters_from_json()

        # Growth stage
        self.growth_stage = self.param_json["life_period"]["stage"]

        # Dailytimer #1
        self.dailytimer1_start_hour = int(self.param_json["DailyTimer1_Settings"]["start_hour"])
        self.dailytimer1_start_minute = int(self.param_json["DailyTimer1_Settings"]["start_minute"])
        self.dailytimer1_stop_hour = int(self.param_json["DailyTimer1_Settings"]["stop_hour"])
        self.dailytimer1_stop_minute = int(self.param_json["DailyTimer1_Settings"]["stop_minute"])

        # Dailytimer #2
        self.dailytimer2_start_hour = int(self.param_json["DailyTimer2_Settings"]["start_hour"])
        self.dailytimer2_start_minute = int(self.param_json["DailyTimer2_Settings"]["start_minute"])
        self.dailytimer2_stop_hour = int(self.param_json["DailyTimer2_Settings"]["stop_hour"])
        self.dailytimer2_stop_minute = int(self.param_json["DailyTimer2_Settings"]["stop_minute"])

        # Cyclic #1
        self.cyclic1_period_minutes = int(self.param_json["Cyclic1_Settings"]["period_minutes"])
        self.cyclic1_action_duration_seconds = int(self.param_json["Cyclic1_Settings"]["action_duration_seconds"])

        # Cyclic #2
        self.cyclic2_period_minutes = int(self.param_json["Cyclic2_Settings"]["period_minutes"])
        self.cyclic2_action_duration_seconds = int(self.param_json["Cyclic2_Settings"]["action_duration_seconds"])

        # Host Machine
        self.host_machine_address = self.param_json["Network_Settings"]["host_machine_address"]
        self.host_machine_state = self.param_json["Network_Settings"]["host_machine_state"]
        # Wifi Parameters
        self.wifi_ssid = self.param_json["Network_Settings"]["wifi_ssid"]
        self.wifi_password = self.param_json["Network_Settings"]["wifi_password"]
        # InfluxDB Parameters
        self.influx_db_port = self.param_json["Network_Settings"]["influx_db_port"]
        self.influx_db_user = self.param_json["Network_Settings"]["influx_db_user"]
        self.influx_db_password = self.param_json["Network_Settings"]["influx_db_password"]
        self.influx_db_name = self.param_json["Network_Settings"]["influx_db_name"]

        # Hardware GPIO:
        self.i2c_sda = self.param_json["GPIO_Settings"]["i2c_sda"]
        self.i2c_scl = self.param_json["GPIO_Settings"]["i2c_scl"]
        self.ds18_pin = self.param_json["GPIO_Settings"]["ds18_pin"]
        self.hcsr_trigger_pin = self.param_json["GPIO_Settings"]["hcsr_trigger_pin"]
        self.hcsr_echo_pin = self.param_json["GPIO_Settings"]["hcsr_echo_pin"]
        self.dailytimer1_pin = self.param_json["GPIO_Settings"]["dailytimer1_pin"]
        self.dailytimer2_pin = self.param_json["GPIO_Settings"]["dailytimer2_pin"]
        self.cyclic1_pin = self.param_json["GPIO_Settings"]["cyclic1_pin"]
        self.cyclic2_pin = self.param_json["GPIO_Settings"]["cyclic2_pin"]
        self.motor_pin1 = self.param_json["GPIO_Settings"]["motor_pin1"]
        self.motor_pin2 = self.param_json["GPIO_Settings"]["motor_pin2"]
        self.motor_pin3 = self.param_json["GPIO_Settings"]["motor_pin3"]
        self.motor_pin4 = self.param_json["GPIO_Settings"]["motor_pin4"]
        # Motor settings
        self.motor_mode = self.param_json["Motor_Settings"]["motor_mode"]
        self.motor_user_speed = self.param_json["Motor_Settings"]["motor_user_speed"]
        self.target_temp = self.param_json["Motor_Settings"]["target_temp"]
        self.hysteresis = self.param_json["Motor_Settings"]["hysteresis"]
        self.motor_min_speed = self.param_json["Motor_Settings"]["min_speed"]
        self.motor_max_speed = self.param_json["Motor_Settings"]["max_speed"]
        # Sensors State:
        self.bme_state = self.param_json["Sensor_State"]["bme280_state"]
        self.ds18_state = self.param_json["Sensor_State"]["ds18b20_state"]
        self.veml_state = self.param_json["Sensor_State"]["veml6075_state"]
        self.vl53_state = self.param_json["Sensor_State"]["vl53L0x_state"]
        self.mlx_state = self.param_json["Sensor_State"]["mlx90614_state"]
        self.tsl_state = self.param_json["Sensor_State"]["tsl2591_state"]
        self.hcsr_state = self.param_json["Sensor_State"]["hcsr04_state"]

        # Sensor Dictionary, normalized names
        self.sensor_dict = {"air": ["DS18B#1", "DS18B#2", "DS18B#3", "BME280T", "BME280H", "BME280P"],
                            "light": ["TSL-LUX", "TSL-IR", "VEML-UVA", "VEML-UVB", "VEML-UVINDEX"]}

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
