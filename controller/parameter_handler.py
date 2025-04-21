# Author: Progradius
# License: AGPL 3.0

import json

# === Lire le fichier JSON de paramètres ===
def read_parameters_from_json():
    """ Lit le fichier param.json et retourne un dictionnaire """
    with open('param.json', 'r', encoding='utf-8') as f:
        return json.load(f)

# === Écrire les paramètres courants dans le JSON ===
def write_current_parameters_to_json(parameters):
    """ Sauvegarde les valeurs actuelles de l'instance parameters dans param.json """
    print("Saving parameters...")

    try:
        parameter_dict = {
            "life_period": {
                "stage": parameters.get_growth_stage()
            },
            "DailyTimer1_Settings": {
                "start_hour": parameters.get_dailytimer1_start_hour(),
                "start_minute": parameters.get_dailytimer1_start_minute(),
                "stop_hour": parameters.get_dailytimer1_stop_hour(),
                "stop_minute": parameters.get_dailytimer1_stop_minute()
            },
            "DailyTimer2_Settings": {
                "start_hour": parameters.get_dailytimer2_start_hour(),
                "start_minute": parameters.get_dailytimer2_start_minute(),
                "stop_hour": parameters.get_dailytimer2_stop_hour(),
                "stop_minute": parameters.get_dailytimer2_stop_minute()
            },
            "Cyclic1_Settings": {
                "period_minutes": parameters.get_cyclic1_period_minutes(),
                "action_duration_seconds": parameters.get_cyclic1_action_duration_seconds()
            },
            "Cyclic2_Settings": {
                "period_minutes": parameters.get_cyclic2_period_minutes(),
                "action_duration_seconds": parameters.get_cyclic2_action_duration_seconds()
            },
            "Network_Settings": {
                "host_machine_address": parameters.get_host_machine_address(),
                "host_machine_state": parameters.get_host_machine_state(),
                "wifi_ssid": parameters.get_wifi_ssid(),
                "wifi_password": parameters.get_wifi_password(),
                "influx_db_port": parameters.get_influx_db_port(),
                "influx_db_name": parameters.get_influx_db_name(),
                "influx_db_user": parameters.get_influx_db_user(),
                "influx_db_password": parameters.get_influx_db_password()
            },
            "GPIO_Settings": {
                "i2c_sda": parameters.get_i2c_sda(),
                "i2c_scl": parameters.get_i2c_scl(),
                "ds18_pin": parameters.get_ds18_pin(),
                "hcsr_trigger_pin": parameters.get_hcsr_trigger_pin(),
                "hcsr_echo_pin": parameters.get_hcsr_echo_pin(),
                "dailytimer1_pin": parameters.get_dailytimer1_pin(),
                "dailytimer2_pin": parameters.get_dailytimer2_pin(),
                "cyclic1_pin": parameters.get_cyclic1_pin(),
                "cyclic2_pin": parameters.get_cyclic2_pin(),
                "motor_pin1": parameters.get_motor_pin1(),
                "motor_pin2": parameters.get_motor_pin2(),
                "motor_pin3": parameters.get_motor_pin3(),
                "motor_pin4": parameters.get_motor_pin4()
            },
            "Motor_Settings": {
                "motor_mode": parameters.get_motor_mode(),
                "motor_user_speed": parameters.get_motor_user_speed(),
                "target_temp": parameters.get_target_temp(),
                "hysteresis": parameters.get_hysteresis(),
                "min_speed": parameters.get_min_speed(),
                "max_speed": parameters.get_max_speed()
            },
            "Sensor_State": {
                "bme280_state": parameters.get_bme_state(),
                "ds18b20_state": parameters.get_ds18_state(),
                "veml6075_state": parameters.get_veml_state(),
                "vl53L0x_state": parameters.get_vl53_state(),
                "mlx90614_state": parameters.get_mlx_state(),
                "tsl2591_state": parameters.get_tsl_state(),
                "hcsr04_state": parameters.get_hcsr_state()
            }
        }

        with open('param.json', 'w', encoding='utf-8') as f:
            json.dump(parameter_dict, f, indent=4)
        print("Parameters successfully written to file")

    except Exception as e:
        print("Error while writing parameters to file:", e)

# === Met à jour les attributs d'un objet parameters depuis le JSON ===
def update_current_parameters_from_json(parameters):
    param_json = read_parameters_from_json()

    try:
        parameters.set_growth_stage(param_json["life_period"]["stage"])

        parameters.set_dailytimer1_start_hour(param_json["DailyTimer1_Settings"]["start_hour"])
        parameters.set_dailytimer1_start_minute(param_json["DailyTimer1_Settings"]["start_minute"])
        parameters.set_dailytimer1_stop_hour(param_json["DailyTimer1_Settings"]["stop_hour"])
        parameters.set_dailytimer1_stop_minute(param_json["DailyTimer1_Settings"]["stop_minute"])

        parameters.set_dailytimer2_start_hour(param_json["DailyTimer2_Settings"]["start_hour"])
        parameters.set_dailytimer2_start_minute(param_json["DailyTimer2_Settings"]["start_minute"])
        parameters.set_dailytimer2_stop_hour(param_json["DailyTimer2_Settings"]["stop_hour"])
        parameters.set_dailytimer2_stop_minute(param_json["DailyTimer2_Settings"]["stop_minute"])

        parameters.set_cyclic1_period_minutes(param_json["Cyclic1_Settings"]["period_minutes"])
        parameters.set_cyclic1_action_duration_seconds(param_json["Cyclic1_Settings"]["action_duration_seconds"])

        parameters.set_cyclic2_period_minutes(param_json["Cyclic2_Settings"]["period_minutes"])
        parameters.set_cyclic2_action_duration_seconds(param_json["Cyclic2_Settings"]["action_duration_seconds"])

        net = param_json["Network_Settings"]
        parameters.set_host_machine_address(net["host_machine_address"])
        parameters.set_host_machine_state(net["host_machine_state"])
        parameters.set_wifi_ssid(net["wifi_ssid"])
        parameters.set_wifi_password(net["wifi_password"])
        parameters.set_influx_db_port(net["influx_db_port"])
        parameters.set_influx_db_name(net["influx_db_name"])
        parameters.set_influx_db_user(net["influx_db_user"])
        parameters.set_influx_db_password(net["influx_db_password"])

        gpio = param_json["GPIO_Settings"]
        parameters.set_i2c_sda(gpio["i2c_sda"])
        parameters.set_i2c_scl(gpio["i2c_scl"])
        parameters.set_ds18_pin(gpio["ds18_pin"])
        parameters.set_hcsr_trigger_pin(gpio["hcsr_trigger_pin"])
        parameters.set_hcsr_echo_pin(gpio["hcsr_echo_pin"])
        parameters.set_dailytimer1_pin(gpio["dailytimer1_pin"])
        parameters.set_dailytimer2_pin(gpio["dailytimer2_pin"])
        parameters.set_cyclic1_pin(gpio["cyclic1_pin"])
        parameters.set_cyclic2_pin(gpio["cyclic2_pin"])
        parameters.set_motor_pin1(gpio["motor_pin1"])
        parameters.set_motor_pin2(gpio["motor_pin2"])
        parameters.set_motor_pin3(gpio["motor_pin3"])
        parameters.set_motor_pin4(gpio["motor_pin4"])

        motor = param_json["Motor_Settings"]
        parameters.set_motor_mode(motor["motor_mode"])
        parameters.set_motor_user_speed(motor["motor_user_speed"])
        parameters.set_target_temp(motor["target_temp"])
        parameters.set_hysteresis(motor["hysteresis"])
        parameters.set_min_speed(motor["min_speed"])
        parameters.set_max_speed(motor["max_speed"])

        sensor = param_json["Sensor_State"]
        parameters.set_bme_state(sensor["bme280_state"])
        parameters.set_ds18_state(sensor["ds18b20_state"])
        parameters.set_veml_state(sensor["veml6075_state"])
        parameters.set_vl53_state(sensor["vl53L0x_state"])
        parameters.set_mlx_state(sensor["mlx90614_state"])
        parameters.set_tsl_state(sensor["tsl2591_state"])
        parameters.set_hcsr_state(sensor["hcsr04_state"])

    except Exception as e:
        print("Could not refresh parameters:", e)

# === Mise à jour d'un seul paramètre ===
def update_one_parameter(section, key, value):
    try:
        parameter_dict = read_parameters_from_json()
        parameter_dict[section][key] = value

        with open('param.json', 'w', encoding='utf-8') as f:
            json.dump(parameter_dict, f, indent=4)
        print(f"Parameter {section}/{key} updated to: {value}")

    except Exception as e:
        print(f"Could not update parameter {key}: {e}")
