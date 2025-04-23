# param/config.py
from __future__ import annotations
import json
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field, validator


# ────────────────────────────────────────────────────────────────
#  Blocs de configurations dédiés
# ────────────────────────────────────────────────────────────────

class DailyTimerSettings(BaseModel):
    start_hour: int
    start_minute: int
    stop_hour: int
    stop_minute: int

class CyclicSettings(BaseModel):
    period_minutes: int
    action_duration_seconds: int

class TemperatureSettings(BaseModel):
    target_temp_min_day: float
    target_temp_max_day: float
    target_temp_min_night: float
    target_temp_max_night: float
    hysteresis_offset: float

class NetworkSettings(BaseModel):
    host_machine_address: str
    host_machine_state: str
    wifi_ssid: str
    wifi_password: str
    influx_db_port: str
    influx_db_name: str
    influx_db_user: str
    influx_db_password: str

class GPIOSettings(BaseModel):
    i2c_sda: int
    i2c_scl: int
    ds18_pin: int
    hcsr_trigger_pin: int
    hcsr_echo_pin: int
    dailytimer1_pin: int
    dailytimer2_pin: int
    cyclic1_pin: int
    cyclic2_pin: int
    heater_pin: int
    motor_pin1: int
    motor_pin2: int
    motor_pin3: int
    motor_pin4: int

class MotorSettings(BaseModel):
    motor_mode: str
    motor_user_speed: int
    target_temp: float
    hysteresis: float
    min_speed: int
    max_speed: int

class LifePeriod(BaseModel):
    stage: str

class HeaterSettings(BaseModel):
    enabled: bool

    @validator("enabled", pre=True)
    def _parse_enabled(cls, v):
        return str(v).lower() in ("enabled", "true", "1", "yes")

class SensorState(BaseModel):
    bme280_state: bool
    ds18b20_state: bool
    veml6075_state: bool
    vl53L0x_state: bool
    mlx90614_state: bool
    tsl2591_state: bool
    hcsr04_state: bool

    @validator("*", pre=True)
    def _parse_sensor(cls, v):
        return str(v).lower() == "enabled"


# ────────────────────────────────────────────────────────────────
#  Modèle principal
# ────────────────────────────────────────────────────────────────

class AppConfig(BaseModel):
    life_period:     LifePeriod           = Field(..., alias="Life_Period")
    daily_timer1:    DailyTimerSettings   = Field(..., alias="DailyTimer1_Settings")
    daily_timer2:    DailyTimerSettings   = Field(..., alias="DailyTimer2_Settings")
    cyclic1:         CyclicSettings       = Field(..., alias="Cyclic1_Settings")
    cyclic2:         CyclicSettings       = Field(..., alias="Cyclic2_Settings")
    temperature:     TemperatureSettings  = Field(..., alias="Temperature_Settings")
    heater_settings: HeaterSettings       = Field(..., alias="Heater_Settings")
    network:         NetworkSettings      = Field(..., alias="Network_Settings")
    gpio:            GPIOSettings         = Field(..., alias="GPIO_Settings")
    motor:           MotorSettings        = Field(..., alias="Motor_Settings")
    sensors:         SensorState          = Field(..., alias="Sensor_State")

    # chemin fixe vers le JSON de config
    _path: ClassVar[Path] = Path(__file__).parent.parent / "param" / "param.json"

    class Config:
        validate_by_name = True
        alias_generator = None
        # allow_mutation a été supprimé en v2

    @classmethod
    def load(cls) -> AppConfig:
        raw = json.loads(cls._path.read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def save(self) -> None:
        # Dump sous forme JSON avec clés d'origine
        payload = self.model_dump(by_alias=True, exclude={"_path"})
        # Reconvertir les booléens en "enabled"/"disabled"
        payload["Heater_Settings"]["enabled"] = "enabled" if self.heater_settings.enabled else "disabled"
        payload["Sensor_State"] = {
            k: ("enabled" if v else "disabled")
            for k, v in self.sensors.model_dump().items()
        }
        self._path.write_text(json.dumps(payload, indent=4), encoding="utf-8")


# ────────────────────────────────────────────────────────────────
#  Reconstruction du modèle (Pydantic v2)
# ────────────────────────────────────────────────────────────────

AppConfig.model_rebuild()
