# param/config.py
# Author: Progradius
# License: AGPL-3.0

from __future__ import annotations
import json
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

from utils import pretty_console as ui
from utils.atomic_io import write_text_atomic
from utils.log_dedup import StateLogger

# `load()` est appelée en boucle (toutes les 5-60 s) : on ne veut qu'une ligne
# à l'entrée en panne et une au rétablissement.
_load_state = StateLogger("Chargement de param.json", name="config")


# ────────────────────────────────────────────────────────────────
#  Blocs de configurations dédiés
# ────────────────────────────────────────────────────────────────

class ValidatedModel(BaseModel):
    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)


class DailyTimerSettings(ValidatedModel):
    enabled: bool = Field(True, alias="enabled")

    start_hour: int = Field(ge=0, le=23)
    start_minute: int = Field(ge=0, le=59)
    stop_hour: int = Field(ge=0, le=23)
    stop_minute: int = Field(ge=0, le=59)

    @validator("enabled", pre=True)
    def _parse_enabled(cls, v):
        return str(v).lower() in ("enabled", "true", "1", "yes")


class CyclicSettings(ValidatedModel):
    """
    Deux modes :
      • **journalier**  : *triggers_per_day* activations chaque *period_days*
      • **séquentiel**  : alternance ON/OFF jour-nuit
    """
    enabled: bool = Field(True, alias="enabled")

    mode: Literal["journalier", "séquentiel"] = Field("journalier", alias="mode")

    # —— mode « journalier » ——
    period_days: int  = Field(1,  alias="period_days", ge=1)
    triggers_per_day: int = Field(1,  alias="triggers_per_day", ge=1)
    first_trigger_hour: int = Field(8, alias="first_trigger_hour", ge=0, le=23)
    action_duration_seconds: int = Field(..., alias="action_duration_seconds", gt=0)

    # —— mode « séquentiel » ——
    on_time_day:   int = Field(0, alias="on_time_day", ge=0)
    off_time_day:  int = Field(0, alias="off_time_day", ge=0)
    on_time_night: int = Field(0, alias="on_time_night", ge=0)
    off_time_night:int = Field(0, alias="off_time_night", ge=0)

    @validator("enabled", pre=True)
    def _parse_enabled(cls, v):
        return str(v).lower() in ("enabled", "true", "1", "yes")


class TemperatureSettings(ValidatedModel):
    target_temp_min_day: float = Field(ge=-20, le=60)
    target_temp_max_day: float = Field(ge=-20, le=60)
    target_temp_min_night: float = Field(ge=-20, le=60)
    target_temp_max_night: float = Field(ge=-20, le=60)
    hysteresis_offset: float = Field(ge=0, le=20)

    @model_validator(mode="after")
    def _validate_ranges(self):
        if self.target_temp_min_day > self.target_temp_max_day:
            raise ValueError("la température minimale de jour dépasse le maximum")
        if self.target_temp_min_night > self.target_temp_max_night:
            raise ValueError("la température minimale de nuit dépasse le maximum")
        return self


class NetworkSettings(ValidatedModel):
    host_machine_address: str
    host_machine_state: Literal["online", "offline"]
    wifi_ssid: str
    wifi_password: str
    influx_db_port: str
    influx_db_name: str
    influx_db_user: str
    influx_db_password: str

    @validator("influx_db_port")
    def _valid_port(cls, value):
        try:
            port = int(value)
        except (TypeError, ValueError):
            raise ValueError("le port InfluxDB doit être numérique")
        if not 1 <= port <= 65535:
            raise ValueError("le port InfluxDB doit être compris entre 1 et 65535")
        return str(port)


class GPIOSettings(ValidatedModel):
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


class MotorSettings(ValidatedModel):
    motor_mode: Literal["manual", "auto", "winter"] = Field("auto", alias="motor_mode")

    motor_user_speed: int = Field(ge=0, le=4)
    target_temp: float = Field(ge=-20, le=60)
    hysteresis: float = Field(ge=0, le=20)
    min_speed: int = Field(ge=0, le=4)
    max_speed: int = Field(ge=0, le=4)

    # — Paramètres « hiver » —
    winter_default_speed: int = Field(1, ge=0, le=4, alias="winter_default_speed")
    winter_temp_margin: float = Field(2.0, ge=0.0, alias="winter_temp_margin")
    winter_refresh_speed: int = Field(4, ge=0, le=4, alias="winter_refresh_speed")
    winter_refresh_minutes_per_hour: int = Field(5, ge=0, le=60, alias="winter_refresh_minutes_per_hour")
    winter_humidity_threshold: float = Field(65.0, ge=0.0, le=100.0, alias="winter_humidity_threshold")

    @model_validator(mode="after")
    def _validate_speed_range(self):
        if self.min_speed > self.max_speed:
            raise ValueError("la vitesse minimale dépasse la vitesse maximale")
        return self


class LifePeriod(ValidatedModel):
    stage: str = Field(min_length=1, max_length=64)


class HeaterSettings(ValidatedModel):
    enabled: bool

    @validator("enabled", pre=True)
    def _parse_enabled(cls, v):
        return str(v).lower() in ("enabled", "true", "1", "yes")


class LogSettings(ValidatedModel):
    """Journalisation : niveau et rétention des archives quotidiennes."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", alias="level")
    retention_days: int = Field(14, alias="retention_days", ge=1)

    @validator("level", pre=True)
    def _normalise_level(cls, v):
        return str(v).strip().upper() if v is not None else "INFO"


class SensorState(ValidatedModel):
    bme280_state: bool
    ds18b20_state: bool
    veml6075_state: bool
    vl53L0x_state: bool
    mlx90614_state: bool
    tsl2591_state: bool
    hcsr04_state: bool

    @validator("*", pre=True)
    def _parse_sensor(cls, v):
        if isinstance(v, bool):
            return v
        return str(v).lower() in ("enabled", "true", "1", "yes")


# ────────────────────────────────────────────────────────────────
#  Modèle principal
# ────────────────────────────────────────────────────────────────

class AppConfig(ValidatedModel):
    life_period: LifePeriod = Field(..., alias="Life_Period")
    daily_timer1: DailyTimerSettings = Field(..., alias="DailyTimer1_Settings")
    daily_timer2: DailyTimerSettings = Field(..., alias="DailyTimer2_Settings")
    cyclic1: CyclicSettings = Field(..., alias="Cyclic1_Settings")
    cyclic2: CyclicSettings = Field(..., alias="Cyclic2_Settings")
    temperature: TemperatureSettings = Field(..., alias="Temperature_Settings")
    heater_settings: HeaterSettings = Field(..., alias="Heater_Settings")
    network: NetworkSettings = Field(..., alias="Network_Settings")
    gpio: GPIOSettings = Field(..., alias="GPIO_Settings")
    motor: MotorSettings = Field(..., alias="Motor_Settings")
    sensors: SensorState = Field(..., alias="Sensor_State")
    logs: LogSettings = Field(default_factory=LogSettings, alias="Log_Settings")

    _path: ClassVar[Path] = Path(__file__).parent.parent / "param" / "param.json"

    @classmethod
    def load(cls) -> "AppConfig":
        try:
            raw = json.loads(cls._path.read_text(encoding="utf-8"))
            config = cls.model_validate(raw)
        except Exception as exc:
            # Appelée en boucle : on déduplique pour ne pas noyer le journal
            _load_state.fail(f"{exc.__class__.__name__} : {exc}")
            raise
        _load_state.ok()
        return config

    def save(self) -> None:
        payload = self.model_dump(by_alias=True, exclude={"_path"})

        # heater
        payload["Heater_Settings"]["enabled"] = (
            "enabled" if self.heater_settings.enabled else "disabled"
        )

        # daily timers
        payload["DailyTimer1_Settings"]["enabled"] = (
            "enabled" if self.daily_timer1.enabled else "disabled"
        )
        payload["DailyTimer2_Settings"]["enabled"] = (
            "enabled" if self.daily_timer2.enabled else "disabled"
        )

        # cyclic timers
        payload["Cyclic1_Settings"]["enabled"] = (
            "enabled" if self.cyclic1.enabled else "disabled"
        )
        payload["Cyclic2_Settings"]["enabled"] = (
            "enabled" if self.cyclic2.enabled else "disabled"
        )

        # capteurs
        payload["Sensor_State"] = {
            k: ("enabled" if v else "disabled")
            for k, v in self.sensors.model_dump().items()
        }

        # Écriture atomique : une boucle de contrôle peut relire param.json à
        # n'importe quel instant, et une coupure secteur en pleine écriture
        # laisserait un fichier tronqué — donc un boot mort.
        try:
            write_text_atomic(
                self._path,
                json.dumps(payload, indent=4, ensure_ascii=False),
                encoding="utf-8"
            )
        except OSError as exc:
            ui.error(
                f"Écriture de param.json impossible : {exc.__class__.__name__} : {exc}",
                name="config",
            )
            raise
        ui.debug("param.json enregistré", name="config")

    def replace_from(self, validated: "AppConfig") -> None:
        """Remplace sans attente la configuration active par une candidate validée."""
        for field_name in self.__class__.model_fields:
            setattr(self, field_name, getattr(validated, field_name))


AppConfig.model_rebuild()
