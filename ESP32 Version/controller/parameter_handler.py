# Author: Progradius
# License: AGPL 3.0

import ujson
import gc


def read_parameters_from_json():
    """ Read parameters with dict like param_json["growth_stage"] """
    gc.collect()
    f = open('param.json', 'r')
    json = ujson.loads(f.read())
    return json


def write_current_parameters_to_json(parameters):
    """ Save current values from current parameter instance """

    print("Saving parameters...")
    # Dictionary to store parameters
    parameter_dict = {}
    try:
        parameter_dict["life_period"]["stage"] = parameters.get_growth_stage()
        # Dailytimer1 settings
        parameter_dict["DailyTimer1_Settings"]["start_hour"] = parameters.get_dailytimer1_start_hour()
        parameter_dict["DailyTimer1_Settings"]["start_minute"] = parameters.get_dailytimer1_start_minute()
        parameter_dict["DailyTimer1_Settings"]["stop_hour"] = parameters.get_dailytimer1_stop_hour()
        parameter_dict["DailyTimer1_Settings"]["stop_minute"] = parameters.get_dailytimer1_stop_minute()
        # Dailytimer2 settings
        parameter_dict["DailyTimer2_Settings"]["start_hour"] = parameters.get_dailytimer2_start_hour()
        parameter_dict["DailyTimer2_Settings"]["start_minute"] = parameters.get_dailytimer2_start_minute()
        parameter_dict["DailyTimer2_Settings"]["stop_hour"] = parameters.get_dailytimer2_stop_hour()
        parameter_dict["DailyTimer2_Settings"]["stop_minute"] = parameters.get_dailytimer2_stop_minute()
        # Cyclic1 settings
        parameter_dict["Cyclic1_Settings"]["period_minutes"] = parameters.get_cyclic1_period_minutes()
        parameter_dict["Cyclic1_Settings"]["action_duration_seconds"] = parameters.get_cyclic1_action_duration_seconds()
        # Cyclic2 settings
        parameter_dict["Cyclic2_Settings"]["period_minutes"] = parameters.get_cyclic2_period_minutes()
        parameter_dict["Cyclic2_Settings"]["action_duration_seconds"] = parameters.get_cyclic2_action_duration_seconds()
        # Host Machine
        parameter_dict["Network_Settings"]["host_machine_address"] = parameters.get_host_machine_address()
        parameter_dict["Network_Settings"]["host_machine_state"] = parameters.get_host_machine_state()
        # Wifi settings
        parameter_dict["Network_Settings"]["wifi_ssid"] = parameters.get_wifi_ssid()
        parameter_dict["Network_Settings"]["wifi_password"] = parameters.get_wifi_password()
        # InfluxDB settings
        parameter_dict["Network_Settings"]["influx_db_port"] = parameters.get_influx_db_port()
        parameter_dict["Network_Settings"]["influx_db_name"] = parameters.get_influx_db_name()
        parameter_dict["Network_Settings"]["influx_db_user"] = parameters.get_influx_db_user()
        parameter_dict["Network_Settings"]["influx_db_password"] = parameters.get_influx_db_password()
        # Hardware GPIO
        parameter_dict["GPIO_Settings"]["i2c_sda"] = parameters.get_i2c_sda()
        parameter_dict["GPIO_Settings"]["i2c_scl"] = parameters.get_i2c_scl()
        parameter_dict["GPIO_Settings"]["ds18_pin"] = parameters.get_ds18_pin()
        parameter_dict["GPIO_Settings"]["hcsr_trigger_pin"] = parameters.get_hcsr_trigger_pin()
        parameter_dict["GPIO_Settings"]["hcsr_echo_pin"] = parameters.get_hcsr_echo_pin()
        parameter_dict["GPIO_Settings"]["dailytimer1_pin"] = parameters.get_dailytimer1_pin()
        parameter_dict["GPIO_Settings"]["dailytimer2_pin"] = parameters.get_dailytimer2_pin()
        parameter_dict["GPIO_Settings"]["cyclic1_pin"] = parameters.get_cyclic1_pin()
        parameter_dict["GPIO_Settings"]["cyclic2_pin"] = parameters.get_cyclic2_pin()
        parameter_dict["GPIO_Settings"]["motor_pin1"] = parameters.get_motor_pin1()
        parameter_dict["GPIO_Settings"]["motor_pin2"] = parameters.get_motor_pin2()
        parameter_dict["GPIO_Settings"]["motor_pin3"] = parameters.get_motor_pin3()
        parameter_dict["GPIO_Settings"]["motor_pin4"] = parameters.get_motor_pin4()
        # Motor settings
        parameter_dict["Motor_Settings"]["motor_mode"] = parameters.get_motor_mode()
        parameter_dict["Motor_Settings"]["motor_user_speed"] = parameters.get_motor_user_speed()
        parameter_dict["Motor_Settings"]["target_temp"] = parameters.get_target_temp()
        parameter_dict["Motor_Settings"]["hysteresis"] = parameters.get_hysteresis()
        parameter_dict["Motor_Settings"]["min_speed"] = parameters.get_min_speed()
        parameter_dict["Motor_Settings"]["max_speed"] = parameters.get_max_speed()
        # Sensors State
        parameter_dict["Sensor_State"]["bme280_state"] = parameters.get_bme_state()
        parameter_dict["Sensor_State"]["ds18b20_state"] = parameters.get_ds18_state()
        parameter_dict["Sensor_State"]["veml6075_state"] = parameters.get_veml_state()
        parameter_dict["Sensor_State"]["vl53L0x_state"] = parameters.get_vl53_state()
        parameter_dict["Sensor_State"]["mlx90614_state"] = parameters.get_mlx_state()
        parameter_dict["Sensor_State"]["tsl2591_state"] = parameters.get_tsl_state()
        parameter_dict["Sensor_State"]["hcsr04_state"] = parameters.get_hcsr_state()

        print("Parameters ready to be shipped")

        try:
            # Open the json file on / in write mode
            f = open('param.json', 'w')
            # Write json to file using ujson.dump() method
            f.write(ujson.dumps(parameter_dict))
            # Closing file
            f.close()
            print("Parameters successfully written to file")

        except OSError as e:
            print("Can't write parameters to file: ", e)

    except OSError as e:
        print("Error constructing the dict parameter: ", e)


def update_current_parameters_from_json(parameters):
    """ Update current parameter from json """
    # Read json file and return json object
    param_json = read_parameters_from_json()

    try:
        # Growth stage
        parameters.set_growth_stage(param_json["life_period"]["stage"])
        # Dailytimer #1
        parameters.set_dailytimer1_start_hour(param_json["DailyTimer1_Settings"]["start_hour"])
        parameters.set_dailytimer1_start_minute(param_json["DailyTimer1_Settings"]["start_minute"])
        parameters.set_dailytimer1_stop_hour(param_json["DailyTimer1_Settings"]["stop_hour"])
        parameters.set_dailytimer1_stop_minute(param_json["DailyTimer1_Settings"]["stop_minute"])
        # Dailytimer #2
        parameters.set_dailytimer2_start_hour(param_json["DailyTimer2_Settings"]["start_hour"])
        parameters.set_dailytimer2_start_minute(param_json["DailyTimer2_Settings"]["start_minute"])
        parameters.set_dailytimer2_stop_hour(param_json["DailyTimer2_Settings"]["stop_hour"])
        parameters.set_dailytimer2_stop_minute(param_json["DailyTimer2_Settings"]["stop_minute"])
        # Cyclic #1
        parameters.set_cyclic1_period_minutes(param_json["Cyclic1_Settings"]["period_minutes"])
        parameters.set_cyclic1_action_duration_seconds(param_json["Cyclic1_Settings"]["action_duration_seconds"])
        # Cyclic #2
        parameters.set_cyclic2_period_minutes(param_json["Cyclic2_Settings"]["period_minutes"])
        parameters.set_cyclic2_action_duration_seconds(param_json["Cyclic2_Settings"]["action_duration_seconds"])
        # Host Machine
        parameters.set_host_machine_address(param_json["Network_Settings"]["host_machine_address"])
        parameters.set_host_machine_state(param_json["Network_Settings"]["host_machine_state"])
        # Wifi settings
        parameters.set_wifi_ssid(param_json["Network_Settings"]["wifi_ssid"])
        parameters.set_wifi_password(param_json["Network_Settings"]["wifi_password"])
        # InfluxDB settings
        parameters.set_influx_db_port(param_json["Network_Settings"]["influx_db_port"])
        parameters.set_influx_db_name(param_json["Network_Settings"]["influx_db_name"])
        parameters.set_influx_db_user(param_json["Network_Settings"]["influx_db_user"])
        parameters.set_influx_db_password(param_json["Network_Settings"]["influx_db_password"])
        # Hardware GPIO
        parameters.set_i2c_sda(param_json["GPIO_Settings"]["i2c_sda"])
        parameters.set_i2c_scl(param_json["GPIO_Settings"]["i2c_scl"])
        parameters.set_ds18_pin(param_json["GPIO_Settings"]["ds18_pin"])
        parameters.set_hcsr_trigger_pin(param_json["GPIO_Settings"]["hcsr_trigger_pin"])
        parameters.set_hcsr_echo_pin(param_json["GPIO_Settings"]["hcsr_echo_pin"])
        parameters.set_dailytimer1_pin(param_json["GPIO_Settings"]["dailytimer1_pin"])
        parameters.set_dailytimer2_pin(param_json["GPIO_Settings"]["dailytimer2_pin"])
        parameters.set_cyclic1_pin(param_json["GPIO_Settings"]["cyclic1_pin"])
        parameters.set_cyclic2_pin(param_json["GPIO_Settings"]["cyclic2_pin"])
        parameters.set_motor_pin1(param_json["GPIO_Settings"]["motor_pin1"])
        parameters.set_motor_pin2(param_json["GPIO_Settings"]["motor_pin2"])
        parameters.set_motor_pin3(param_json["GPIO_Settings"]["motor_pin3"])
        parameters.set_motor_pin4(param_json["GPIO_Settings"]["motor_pin4"])
        # Motor settings
        parameters.set_motor_mode(param_json["Motor_Settings"]["motor_mode"])
        parameters.set_motor_user_speed(param_json["Motor_Settings"]["motor_user_speed"])
        parameters.set_target_temp(param_json["Motor_Settings"]["target_temp"])
        parameters.set_hysteresis(param_json["Motor_Settings"]["hysteresis"])
        parameters.set_min_speed(param_json["Motor_Settings"]["min_speed"])
        parameters.set_max_speed(param_json["Motor_Settings"]["max_speed"])
        # Sensors State
        parameters.set_bme_state(param_json["Sensor_State"]["bme280_state"])
        parameters.set_ds18_state(param_json["Sensor_State"]["ds18b20_state"])
        parameters.set_veml_state(param_json["Sensor_State"]["veml6075_state"])
        parameters.set_vl53_state(param_json["Sensor_State"]["vl53L0x_state"])
        parameters.set_mlx_state(param_json["Sensor_State"]["mlx90614_state"])
        parameters.set_tsl_state(param_json["Sensor_State"]["tsl2591_state"])
        parameters.set_hcsr_state(param_json["Sensor_State"]["hcsr04_state"])

    except OSError as e:
        print(("Could not refresh parameters: ", e))


def update_one_parameter(section, key, value):
    gc.collect()
    parameter_dict = read_parameters_from_json()
    parameter_dict[section][key] = value

    try:
        # Open the json file on / in write mode
        f = open('param.json', 'w')
        # Write json to file using ujson.dump() method
        f.write(ujson.dumps(parameter_dict))
        # Closing file
        f.close()
        print("Parameters " + key + ":" + value + " successfully written to file")

    except OSError as e:
        print("Can't write parameters to file: ", e)
