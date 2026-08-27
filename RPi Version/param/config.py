# param/config.py
# Author: Progradius
# License: AGPL-3.0

from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path
from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator, validator

from utils.log_dedup import StateLogger

# `load()` est relayée par `config_store`, qui l'appelle à chaque changement du
# fichier : on ne veut qu'une ligne à l'entrée en panne et une au rétablissement.
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


class DayNightSettings(ValidatedModel):
    """Référence globale du jour/nuit, héritée explicitement ou personnalisée."""
    source: Literal["dailytimer1", "custom"] = "dailytimer1"
    start_hour: int = Field(8, ge=0, le=23)
    start_minute: int = Field(0, ge=0, le=59)
    stop_hour: int = Field(20, ge=0, le=23)
    stop_minute: int = Field(0, ge=0, le=59)


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
    # Bande morte du **chauffage** uniquement : il s'éteint à
    # `target_temp_min + hysteresis_offset`. Avant l'arbitre thermique, ce seul
    # champ portait trois sémantiques incompatibles (audit M11) ; les paliers de
    # ventilation ont désormais les leurs.
    hysteresis_offset: float = Field(ge=0, le=20)

    # — Arbitre thermique (audit C9, E9) —
    # Écart minimal entre l'extinction du chauffage et le démarrage de la
    # ventilation : c'est lui qui interdit de chauffer et d'extraire en même
    # temps. Le seuil de ventilation effectif ne descend jamais en dessous de
    # `target_temp_min + hysteresis_offset + vent_deadband`.
    vent_deadband: float = Field(1.0, alias="vent_deadband", ge=0, le=20)
    # Largeur d'un palier de vitesse au-dessus du seuil de ventilation.
    vent_step: float = Field(1.0, alias="vent_step", gt=0, le=20)
    # Seuil de relâchement d'un palier : sans lui, une température qui oscille
    # d'un dixième fait battre le relais des centaines de fois par heure.
    vent_release: float = Field(0.5, alias="vent_release", ge=0, le=20)
    # Plancher absolu : au-dessous, aucune ventilation n'est autorisée, quel que
    # soit le budget de renouvellement restant (audit C8).
    absolute_floor_temp: float = Field(5.0, alias="absolute_floor_temp", ge=-20, le=60)
    # Temps de maintien minimal entre deux changements de vitesse (audit E9).
    min_dwell_seconds: int = Field(120, alias="min_dwell_seconds", ge=0, le=3600)

    @model_validator(mode="after")
    def _validate_ranges(self):
        if self.target_temp_min_day > self.target_temp_max_day:
            raise ValueError("la température minimale de jour dépasse le maximum")
        if self.target_temp_min_night > self.target_temp_max_night:
            raise ValueError("la température minimale de nuit dépasse le maximum")
        return self


class NetworkSettings(ValidatedModel):
    host_machine_address: str = Field(min_length=1)
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


# Broches BCM valides sur un en-tête 40 points : 0 à 27.
BCMPin = Annotated[int, Field(ge=0, le=27)]


class GPIOSettings(ValidatedModel):
    """
    Affectation des broches, en numérotation **BCM**.

    Seules les bornes sont vérifiées ici. L'unicité ne l'est **pas**, et c'est
    délibéré : la configuration en production porte aujourd'hui deux rôles sur
    la 27 (cyclic1 / hcsr_echo) et deux sur la 22 (cyclic2 / i2c_scl). Un
    validateur d'unicité refuserait cette configuration, donc tuerait le boot —
    exactement ce que la Phase 2 avait déjà refusé de faire pour la zone morte
    thermique. Les collisions relèvent du `PinRegistry` de la Phase 1, qui vient
    avec la migration de broches correspondante (audit F1, M1).
    """
    i2c_sda: BCMPin
    i2c_scl: BCMPin
    ds18_pin: BCMPin
    hcsr_trigger_pin: BCMPin
    hcsr_echo_pin: BCMPin
    dailytimer1_pin: BCMPin
    dailytimer2_pin: BCMPin
    cyclic1_pin: BCMPin
    cyclic2_pin: BCMPin
    heater_pin: BCMPin
    motor_pin1: BCMPin
    motor_pin2: BCMPin
    motor_pin3: BCMPin
    motor_pin4: BCMPin


class MotorSettings(ValidatedModel):
    motor_mode: Literal["manual", "auto", "winter"] = Field("auto", alias="motor_mode")

    motor_user_speed: int = Field(ge=0, le=4)
    target_temp: float = Field(ge=-20, le=60)
    hysteresis: float = Field(ge=0, le=20)
    min_speed: int = Field(ge=0, le=4)
    max_speed: int = Field(ge=0, le=4)
    # Vitesse appliquée quand la température devient illisible durablement
    # (état `REPLI_CAPTEUR`). 0 par défaut : sans mesure, on ne ventile pas une
    # serre qu'on ne sait plus lire.
    sensor_fallback_speed: int = Field(0, alias="sensor_fallback_speed", ge=0, le=4)

    # — Paramètres « hiver » —
    winter_default_speed: int = Field(1, ge=0, le=4, alias="winter_default_speed")
    winter_temp_margin: float = Field(2.0, ge=0.0, alias="winter_temp_margin")
    winter_refresh_speed: int = Field(4, ge=0, le=4, alias="winter_refresh_speed")
    winter_refresh_minutes_per_hour: int = Field(5, ge=0, le=60, alias="winter_refresh_minutes_per_hour")
    winter_humidity_threshold: float = Field(65.0, ge=0.0, le=100.0, alias="winter_humidity_threshold")
    # Budget de déshumidification, **distinct et borné** (audit C8) : l'humidité
    # ne court-circuite plus le quota de renouvellement, elle dispose de son
    # propre crédit horaire. 0 = déshumidification désactivée.
    winter_humidity_minutes_per_hour: int = Field(
        15, ge=0, le=60, alias="winter_humidity_minutes_per_hour"
    )

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


class SensorQualityProfile(ValidatedModel):
    """Surcharge facultative des valeurs qualité portées par le catalogue."""
    offset: float | None = None
    calibrated_at: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    calibration_valid_days: int | None = Field(None, ge=1, le=3650)
    freshness_seconds: float | None = Field(None, gt=0, le=3600)
    plausible_min: float | None = None
    plausible_max: float | None = None
    freeze_epsilon: float | None = Field(None, ge=0)
    freeze_after_seconds: float | Literal["disabled"] | None = None
    freeze_min_samples: int | None = Field(None, ge=2, le=100000)

    @model_validator(mode="after")
    def _validate_profile(self):
        import math
        for name in ("offset", "freshness_seconds", "plausible_min", "plausible_max", "freeze_epsilon"):
            value = getattr(self, name)
            if value is not None and not math.isfinite(float(value)):
                raise ValueError(f"{name} doit être fini")
        if isinstance(self.freeze_after_seconds, (int, float)):
            if not math.isfinite(float(self.freeze_after_seconds)) or not 30 <= self.freeze_after_seconds <= 30 * 24 * 3600:
                raise ValueError("freeze_after_seconds doit être compris entre 30 s et 30 jours")
        if self.plausible_min is not None and self.plausible_max is not None:
            if self.plausible_min >= self.plausible_max:
                raise ValueError("la borne plausible minimale doit être inférieure au maximum")
        if self.calibrated_at is not None:
            try:
                date.fromisoformat(self.calibrated_at)
            except ValueError as exc:
                raise ValueError("calibrated_at doit être une date réelle") from exc
        return self


class SensorRedundancyGroup(ValidatedModel):
    members: list[str] = Field(min_length=2)
    tolerance: float = Field(gt=0)
    minimum_agreeing: int = Field(2, ge=2)

    @model_validator(mode="after")
    def _validate_group(self):
        import math
        if not math.isfinite(float(self.tolerance)):
            raise ValueError("la tolérance redondante doit être finie")
        if len(set(self.members)) != len(self.members):
            raise ValueError("un groupe redondant contient une mesure en double")
        if self.minimum_agreeing > len(self.members):
            raise ValueError("le quorum dépasse le nombre de membres")
        return self


class SensorQualitySettings(ValidatedModel):
    mode: Literal["observe", "enforce"] = "observe"
    profiles: dict[str, SensorQualityProfile] = Field(default_factory=dict)
    redundancy_groups: dict[str, SensorRedundancyGroup] = Field(default_factory=dict)
    ds18b20_bindings: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_catalog_references(self):
        from controllers.sensor_catalog import SENSORS_BY_KEY
        unknown_profiles = set(self.profiles) - set(SENSORS_BY_KEY)
        if unknown_profiles:
            raise ValueError(f"profils capteur inconnus : {', '.join(sorted(unknown_profiles))}")
        if any(not name.strip() or len(name) > 64 for name in self.redundancy_groups):
            raise ValueError("le nom d'un groupe redondant doit contenir 1 à 64 caractères")
        for key, profile in self.profiles.items():
            definition = SENSORS_BY_KEY[key]
            minimum = (
                definition.plausible_min
                if profile.plausible_min is None else profile.plausible_min
            )
            maximum = (
                definition.plausible_max
                if profile.plausible_max is None else profile.plausible_max
            )
            if minimum < definition.plausible_min or maximum > definition.plausible_max:
                raise ValueError(
                    f"profil {key} : la plage ne peut pas dépasser la plage matérielle"
                )
            if minimum >= maximum:
                raise ValueError(f"profil {key} : plage plausible vide")
        assigned: set[str] = set()
        for name, group in self.redundancy_groups.items():
            unknown = set(group.members) - set(SENSORS_BY_KEY)
            if unknown:
                raise ValueError(f"groupe {name} : capteurs inconnus {', '.join(sorted(unknown))}")
            units = {SENSORS_BY_KEY[key].unit for key in group.members}
            if len(units) != 1:
                raise ValueError(f"groupe {name} : unités incompatibles")
            overlap = assigned.intersection(group.members)
            if overlap:
                raise ValueError(f"mesures présentes dans plusieurs groupes : {', '.join(sorted(overlap))}")
            assigned.update(group.members)
        allowed_ds = {"DS18B#1", "DS18B#2", "DS18B#3"}
        if set(self.ds18b20_bindings) - allowed_ds:
            raise ValueError("liaison DS18B20 inconnue")
        bindings = list(self.ds18b20_bindings.values())
        if len(set(bindings)) != len(bindings):
            raise ValueError("un identifiant DS18B20 est lié plusieurs fois")
        if any(re.fullmatch(r"28-[0-9a-fA-F]{12}", value) is None for value in bindings):
            raise ValueError("un identifiant DS18B20 doit suivre le format 28-xxxxxxxxxxxx")
        return self


# ────────────────────────────────────────────────────────────────
#  Modèle principal
# ────────────────────────────────────────────────────────────────

class AppConfig(ValidatedModel):
    life_period: LifePeriod = Field(..., alias="Life_Period")
    daily_timer1: DailyTimerSettings = Field(..., alias="DailyTimer1_Settings")
    daily_timer2: DailyTimerSettings = Field(..., alias="DailyTimer2_Settings")
    day_night: DayNightSettings = Field(default_factory=DayNightSettings, alias="Day_Night_Settings")
    cyclic1: CyclicSettings = Field(..., alias="Cyclic1_Settings")
    cyclic2: CyclicSettings = Field(..., alias="Cyclic2_Settings")
    temperature: TemperatureSettings = Field(..., alias="Temperature_Settings")
    heater_settings: HeaterSettings = Field(..., alias="Heater_Settings")
    network: NetworkSettings = Field(..., alias="Network_Settings")
    gpio: GPIOSettings = Field(..., alias="GPIO_Settings")
    motor: MotorSettings = Field(..., alias="Motor_Settings")
    sensors: SensorState = Field(..., alias="Sensor_State")
    sensor_quality: SensorQualitySettings = Field(default_factory=SensorQualitySettings, alias="Sensor_Quality")
    logs: LogSettings = Field(default_factory=LogSettings, alias="Log_Settings")

    _path: ClassVar[Path] = Path(__file__).parent.parent / "param" / "param.json"

    @classmethod
    def config_path(cls) -> Path:
        """Emplacement canonique de `param.json`."""
        return cls._path

    @classmethod
    def load(cls, path: Path | None = None) -> "AppConfig":
        """
        Lit et valide un fichier de configuration.

        Primitive de lecture, sans mémoire : c'est `param.config_store` qui
        possède l'instance vivante et décide quand relire. Les boucles de
        contrôle ne doivent **pas** appeler cette méthode — elles feraient une
        I/O disque et une validation complète à chaque tick, et devraient
        rattraper l'exception elles-mêmes (audit C7, E7).
        """
        target = cls._path if path is None else Path(path)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            config = cls.model_validate(raw)
        except Exception as exc:
            # Appelée en boucle par le magasin : on déduplique pour ne pas
            # noyer le journal.
            _load_state.fail(f"{target.name} : {exc.__class__.__name__} : {exc}")
            raise
        _load_state.ok()
        return config

    def to_json(self) -> str:
        """
        Sérialisation JSON du modèle, dans le format historique du fichier.

        Les booléens redeviennent les chaînes `"enabled"` / `"disabled"` : le
        fichier reste lisible par l'`initial_setup_tool` et par la version
        ESP32. **Tout nouveau champ booléen doit être traité ici aussi.**

        L'écriture elle-même appartient à `param.config_store.ConfigStore` :
        c'est lui qui revalide, sauvegarde l'ancien contenu et écrit
        atomiquement. Un modèle qui s'écrit tout seul, c'est un second écrivain
        de `param.json` — donc deux vérités possibles.
        """
        payload = self.model_dump(by_alias=True, exclude={"_path"}, mode="json")

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

        return json.dumps(payload, indent=4, ensure_ascii=False)

    def replace_from(self, validated: "AppConfig") -> None:
        """
        Recopie champ par champ une configuration validée dans cette instance.

        Mutation **en place** : l'identité de l'objet ne change jamais, ce qui
        est toute la raison d'être du magasin. Les composants ont reçu cette
        instance au boot et n'ont rien à réabonner (audit M4).
        """
        for field_name in self.__class__.model_fields:
            setattr(self, field_name, getattr(validated, field_name))


AppConfig.model_rebuild()
