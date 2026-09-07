from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from components.climate_policy import ClimateSettings
from param.config import AppConfig


@pytest.fixture
def climate_settings():
    """Fabrique de consignes thermiques déterministes et sans matériel."""
    defaults = {
        "heater_enabled": True,
        "temp_min": 20.0,
        "temp_max": 24.0,
        "heater_hysteresis": 1.0,
        "vent_deadband": 1.0,
        "vent_step": 1.0,
        "vent_release": 0.5,
        "absolute_floor_temp": 5.0,
        "min_dwell_seconds": 0.0,
        "motor_mode": "auto",
        "motor_user_speed": 0,
        "min_speed": 1,
        "max_speed": 4,
        "sensor_fallback_speed": 2,
        "winter_default_speed": 1,
        "winter_temp_margin": 2.0,
        "winter_refresh_speed": 3,
        "winter_refresh_minutes_per_hour": 5.0,
        "winter_humidity_threshold": 70.0,
        "winter_humidity_minutes_per_hour": 10.0,
    }

    def factory(**overrides) -> ClimateSettings:
        return ClimateSettings(**(defaults | overrides))

    return factory


@pytest.fixture
def valid_config_payload() -> dict:
    """Configuration complète fictive : aucune valeur ne vient de param.json."""
    return {
        "Life_Period": {"stage": "test"},
        "DailyTimer1_Settings": {
            "enabled": "enabled", "start_hour": 19, "start_minute": 0,
            "stop_hour": 7, "stop_minute": 0,
        },
        "DailyTimer2_Settings": {
            "enabled": "disabled", "start_hour": 8, "start_minute": 0,
            "stop_hour": 20, "stop_minute": 0,
        },
        "Day_Night_Settings": {
            "source": "dailytimer1", "start_hour": 8, "start_minute": 0,
            "stop_hour": 20, "stop_minute": 0,
        },
        "Cyclic1_Settings": {
            "enabled": "enabled", "mode": "séquentiel", "period_days": 1,
            "triggers_per_day": 1, "first_trigger_hour": 8,
            "action_duration_seconds": 60, "on_time_day": 30, "off_time_day": 30,
            "on_time_night": 60, "off_time_night": 60,
        },
        "Cyclic2_Settings": {
            "enabled": "disabled", "mode": "journalier", "period_days": 1,
            "triggers_per_day": 1, "first_trigger_hour": 8,
            "action_duration_seconds": 60, "on_time_day": 0, "off_time_day": 0,
            "on_time_night": 0, "off_time_night": 0,
        },
        "Temperature_Settings": {
            "target_temp_min_day": 20.0, "target_temp_max_day": 24.0,
            "target_temp_min_night": 18.0, "target_temp_max_night": 22.0,
            "hysteresis_offset": 1.0, "vent_deadband": 1.0,
            "vent_step": 1.0, "vent_release": 0.5,
            "absolute_floor_temp": 5.0, "min_dwell_seconds": 0,
        },
        "Heater_Settings": {"enabled": "enabled"},
        "Network_Settings": {
            "host_machine_address": "127.0.0.1", "host_machine_state": "offline",
            "wifi_ssid": "reseau-de-test", "wifi_password": "secret-fictif-wifi",
            "influx_db_port": "8086", "influx_db_name": "phyto_test",
            "influx_db_user": "utilisateur-test",
            "influx_db_password": "secret-fictif-influx",
        },
        "GPIO_Settings": {
            "i2c_sda": 2, "i2c_scl": 3, "ds18_pin": 4,
            "hcsr_trigger_pin": 26, "hcsr_echo_pin": 24,
            "dailytimer1_pin": 5, "dailytimer2_pin": 6,
            "cyclic1_pin": 12, "cyclic2_pin": 13, "heater_pin": 23,
            "motor_pin1": 16, "motor_pin2": 17, "motor_pin3": 18,
            "motor_pin4": 19,
        },
        "Motor_Settings": {
            "motor_mode": "auto", "motor_user_speed": 0, "target_temp": 24.0,
            "hysteresis": 1.0, "min_speed": 1, "max_speed": 4,
            "sensor_fallback_speed": 2, "winter_default_speed": 1,
            "winter_temp_margin": 2.0, "winter_refresh_speed": 3,
            "winter_refresh_minutes_per_hour": 5,
            "winter_humidity_threshold": 70.0,
            "winter_humidity_minutes_per_hour": 10,
        },
        "Sensor_State": {
            "bme280_state": "enabled", "ds18b20_state": "disabled",
            "veml6075_state": "disabled", "vl53L0x_state": "disabled",
            "mlx90614_state": "disabled", "tsl2591_state": "disabled",
            "hcsr04_state": "disabled",
        },
        "Log_Settings": {"level": "INFO", "retention_days": 7},
    }


@pytest.fixture
def valid_config(valid_config_payload) -> AppConfig:
    return AppConfig.model_validate(copy.deepcopy(valid_config_payload))


@pytest.fixture
def config_path(tmp_path: Path, valid_config_payload) -> Path:
    path = tmp_path / "param.json"
    path.write_text(
        json.dumps(valid_config_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path
