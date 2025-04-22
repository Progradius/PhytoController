# controller/parameter_handler.py
# Author : Progradius
# License: AGPL‑3.0
# -------------------------------------------------------------
#  Lecture / écriture du fichier param.json
#  + mise à jour de l'instance Parameter en RAM
# -------------------------------------------------------------

from __future__ import annotations

import json
from pathlib import Path

from ui.pretty_console import (
    info, success, error, action
)

_JSON_PATH = Path("param/param.json")

# ──────────────────────────────────────────────────────────────
#  Helpers internes
# ──────────────────────────────────────────────────────────────
def _load_json() -> dict:
    try:
        data = json.loads(_JSON_PATH.read_text(encoding="utf‑8"))
        return data
    except FileNotFoundError:
        error(f"Fichier {_JSON_PATH} introuvable !")
        raise
    except json.JSONDecodeError as exc:
        error(f"JSON invalide : {exc}")
        raise

def _dump_json(data: dict) -> None:
    _JSON_PATH.write_text(json.dumps(data, indent=4), encoding="utf‑8")

# ──────────────────────────────────────────────────────────────
#  API publique
# ──────────────────────────────────────────────────────────────
def read_parameters_from_json() -> dict:
    """Lit _param.json_ et renvoie le dictionnaire."""
    info("Lecture des paramètres JSON …")
    return _load_json()

# -------------------------------------------------------------
def write_current_parameters_to_json(parameters) -> None:
    """
    Sauvegarde l'état courant de l'instance *parameters* vers param.json.
    """
    action("Sauvegarde des paramètres …")

    try:
        param_dict = {
            "life_period":          {"stage": parameters.get_growth_stage()},
            "DailyTimer1_Settings": {
                "start_hour" : parameters.get_dailytimer1_start_hour(),
                "start_minute": parameters.get_dailytimer1_start_minute(),
                "stop_hour"  : parameters.get_dailytimer1_stop_hour(),
                "stop_minute": parameters.get_dailytimer1_stop_minute(),
            },
            "DailyTimer2_Settings": {
                "start_hour" : parameters.get_dailytimer2_start_hour(),
                "start_minute": parameters.get_dailytimer2_start_minute(),
                "stop_hour"  : parameters.get_dailytimer2_stop_hour(),
                "stop_minute": parameters.get_dailytimer2_stop_minute(),
            },
            "Cyclic1_Settings": {
                "period_minutes"        : parameters.get_cyclic1_period_minutes(),
                "action_duration_seconds": parameters.get_cyclic1_action_duration_seconds(),
            },
            "Cyclic2_Settings": {
                "period_minutes"        : parameters.get_cyclic2_period_minutes(),
                "action_duration_seconds": parameters.get_cyclic2_action_duration_seconds(),
            },
            "Temperature_Settings": {
                "target_temp_min_day":    parameters.get_target_temp_min_day(),
                "target_temp_max_day":    parameters.get_target_temp_max_day(),
                "target_temp_min_night":  parameters.get_target_temp_min_night(),
                "target_temp_max_night":  parameters.get_target_temp_max_night()
            },
            "Network_Settings": {
                "host_machine_address": parameters.get_host_machine_address(),
                "host_machine_state"  : parameters.get_host_machine_state(),
                "wifi_ssid"           : parameters.get_wifi_ssid(),
                "wifi_password"       : parameters.get_wifi_password(),
                "influx_db_port"      : parameters.get_influx_db_port(),
                "influx_db_name"      : parameters.get_influx_db_name(),
                "influx_db_user"      : parameters.get_influx_db_user(),
                "influx_db_password"  : parameters.get_influx_db_password(),
            },
            "GPIO_Settings": {
                "i2c_sda"        : parameters.get_i2c_sda(),
                "i2c_scl"        : parameters.get_i2c_scl(),
                "ds18_pin"       : parameters.get_ds18_pin(),
                "hcsr_trigger_pin": parameters.get_hcsr_trigger_pin(),
                "hcsr_echo_pin"  : parameters.get_hcsr_echo_pin(),
                "dailytimer1_pin": parameters.get_dailytimer1_pin(),
                "dailytimer2_pin": parameters.get_dailytimer2_pin(),
                "cyclic1_pin"    : parameters.get_cyclic1_pin(),
                "cyclic2_pin"    : parameters.get_cyclic2_pin(),
                "motor_pin1"     : parameters.get_motor_pin1(),
                "motor_pin2"     : parameters.get_motor_pin2(),
                "motor_pin3"     : parameters.get_motor_pin3(),
                "motor_pin4"     : parameters.get_motor_pin4(),
            },
            "Motor_Settings": {
                "motor_mode"     : parameters.get_motor_mode(),
                "motor_user_speed": parameters.get_motor_user_speed(),
                "target_temp"    : parameters.get_target_temp(),
                "hysteresis"     : parameters.get_hysteresis(),
                "min_speed"      : parameters.get_min_speed(),
                "max_speed"      : parameters.get_max_speed(),
            },
            "Sensor_State": {
                "bme280_state" : parameters.get_bme_state(),
                "ds18b20_state": parameters.get_ds18_state(),
                "veml6075_state": parameters.get_veml_state(),
                "vl53L0x_state": parameters.get_vl53_state(),
                "mlx90614_state": parameters.get_mlx_state(),
                "tsl2591_state": parameters.get_tsl_state(),
                "hcsr04_state" : parameters.get_hcsr_state(),
            },
        }

        _dump_json(param_dict)
        success("Paramètres sauvegardés ✔️")

    except Exception as exc:
        error(f"Échec d'écriture du JSON : {exc}")

# -------------------------------------------------------------
def update_current_parameters_from_json(parameters) -> None:
    """
    Recharge param.json et met à jour en-mémoire l'objet *parameters*
    via ses setters.
    """
    info("Actualisation des paramètres depuis le JSON …")
    data = _load_json()

    try:
        parameters.set_growth_stage(data["life_period"]["stage"])

        dt1 = data["DailyTimer1_Settings"]
        parameters.set_dailytimer1_start_hour(dt1["start_hour"])
        parameters.set_dailytimer1_start_minute(dt1["start_minute"])
        parameters.set_dailytimer1_stop_hour(dt1["stop_hour"])
        parameters.set_dailytimer1_stop_minute(dt1["stop_minute"])

        dt2 = data["DailyTimer2_Settings"]
        parameters.set_dailytimer2_start_hour(dt2["start_hour"])
        parameters.set_dailytimer2_start_minute(dt2["start_minute"])
        parameters.set_dailytimer2_stop_hour(dt2["stop_hour"])
        parameters.set_dailytimer2_stop_minute(dt2["stop_minute"])

        cyc1 = data["Cyclic1_Settings"]
        parameters.set_cyclic1_period_minutes(cyc1["period_minutes"])
        parameters.set_cyclic1_action_duration_seconds(cyc1["action_duration_seconds"])

        cyc2 = data["Cyclic2_Settings"]
        parameters.set_cyclic2_period_minutes(cyc2["period_minutes"])
        parameters.set_cyclic2_action_duration_seconds(cyc2["action_duration_seconds"])
        
        temps = data["Temperature_Settings"]
        parameters.set_target_temp_min_day(  temps["target_temp_min_day"])
        parameters.set_target_temp_max_day(  temps["target_temp_max_day"])
        parameters.set_target_temp_min_night(temps["target_temp_min_night"])
        parameters.set_target_temp_max_night(temps["target_temp_max_night"])

        net = data["Network_Settings"]
        parameters.set_host_machine_address(net["host_machine_address"])
        parameters.set_host_machine_state(net["host_machine_state"])
        parameters.set_wifi_ssid(net["wifi_ssid"])
        parameters.set_wifi_password(net["wifi_password"])
        parameters.set_influx_db_port(net["influx_db_port"])
        parameters.set_influx_db_name(net["influx_db_name"])
        parameters.set_influx_db_user(net["influx_db_user"])
        parameters.set_influx_db_password(net["influx_db_password"])

        gpio = data["GPIO_Settings"]
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

        motor = data["Motor_Settings"]
        parameters.set_motor_mode(motor["motor_mode"])
        parameters.set_motor_user_speed(motor["motor_user_speed"])
        parameters.set_target_temp(motor["target_temp"])
        parameters.set_hysteresis(motor["hysteresis"])
        parameters.set_min_speed(motor["min_speed"])
        parameters.set_max_speed(motor["max_speed"])

        sensor = data["Sensor_State"]
        parameters.set_bme_state(sensor["bme280_state"])
        parameters.set_ds18_state(sensor["ds18b20_state"])
        parameters.set_veml_state(sensor["veml6075_state"])
        parameters.set_vl53_state(sensor["vl53L0x_state"])
        parameters.set_mlx_state(sensor["mlx90614_state"])
        parameters.set_tsl_state(sensor["tsl2591_state"])
        parameters.set_hcsr_state(sensor["hcsr04_state"])

        success("Paramètres mis à jour en mémoire")

    except Exception as exc:
        error(f"Impossible de rafraîchir les paramètres : {exc}")

# -------------------------------------------------------------
def update_one_parameter(section: str, key: str, value) -> None:
    """
    Met à jour UN champ (section/clé) dans param.json.
    """
    action(f"Mise à jour {section}/{key} → {value}")

    try:
        data = _load_json()
        data[section][key] = value
        _dump_json(data)
        success(f"Paramètre {section}/{key} enregistré")

    except Exception as exc:
        error(f"Échec écriture paramètre {key} : {exc}")
