"""Catalogue canonique des mesures capteurs.

Une seule table décrit les clés internes, l'activation matérielle, les unités,
les libellés web et les measurements Influx. Elle évite les listes divergentes
qui rendaient les pages et les capteurs de distance incohérents.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SensorDefinition:
    key: str
    family: str
    enabled_field: str
    measurement: str
    label: str
    unit: str
    decimals: int = 1
    tracked_stats: bool = False
    slug: str = ""
    plausible_min: float = 0.0
    plausible_max: float = 0.0
    freshness_seconds: float = 30.0
    freeze_epsilon: float = 0.0
    freeze_after_seconds: float | None = None
    freeze_min_samples: int = 30
    control_role: str | None = None


# `freeze_epsilon` est une **bande morte**, pas une tolérance de pente : la
# mesure doit rester dans ±epsilon autour de la valeur du dernier changement
# réel pendant `freeze_after_seconds` pour être déclarée figée. Un epsilon
# **au-dessus du plancher de bruit** rend le diagnostic aveugle : une nuit calme
# et un registre I²C mort produisent alors la même observation, et aucun seuil
# ne peut les séparer. Un epsilon nul teste donc l'identité stricte, c'est-à-dire
# la vivacité de la chaîne d'acquisition — c'est le réglage sûr par défaut.
SENSOR_CATALOG: tuple[SensorDefinition, ...] = (
    # BME280 : relevé de 38 h en production (28-30/08/2026) — la plus longue
    # plage de valeurs strictement identiques est de 361 s (T), 181 s (H) et
    # 181 s (P), très loin des seuils de 1800/3600 s. Les epsilons précédents
    # (0,02 °C / 0,05 % / 0,1 hPa) étaient au-dessus du bruit à 10 s et
    # déclaraient figées 17 % à 22 % des lectures saines.
    SensorDefinition("BME280T", "BME280", "bme280_state", "air", "Température de l’air", "°C", 1, True, "bme280t", -20, 60, 20, 0.0, 1800, 30, "climate_temperature"),
    SensorDefinition("BME280H", "BME280", "bme280_state", "air", "Humidité de l’air", "%", 1, True, "bme280h", 0, 100, 20, 0.0, 1800, 30, "climate_humidity"),
    SensorDefinition("BME280P", "BME280", "bme280_state", "air", "Pression atmosphérique", "hPa", 1, False, "bme280p", 300, 1100, 30, 0.0, 3600, 30),
    SensorDefinition("MLX-AMB", "MLX90614", "mlx90614_state", "air", "Température infrarouge ambiante", "°C", 1, False, "mlx-amb", -20, 60, 30, 0.05, 1800, 30),
    SensorDefinition("DS18B#1", "DS18B20", "ds18b20_state", "air", "Température sonde 1", "°C", 1, False, "ds18b-1", -20, 60, 30, 0.0, 3600, 30),
    SensorDefinition("DS18B#2", "DS18B20", "ds18b20_state", "air", "Température sonde 2", "°C", 1, False, "ds18b-2", -20, 60, 30, 0.0, 3600, 30),
    SensorDefinition("MLX-OBJ", "MLX90614", "mlx90614_state", "surface_temp", "Température de surface", "°C", 1, False, "mlx-obj", -20, 100, 30, 0.05, 1800, 30),
    SensorDefinition("DS18B#3", "DS18B20", "ds18b20_state", "water", "Température de l’eau", "°C", 1, True, "ds18b-3", 0, 50, 30, 0.0, 3600, 30),
    SensorDefinition("VL53L0X", "VL53L0X", "vl53L0x_state", "distance", "Distance laser", "mm", 1, False, "vl53l0x", 0, 2000, 30),
    SensorDefinition("HCSR04", "HC-SR04", "hcsr04_state", "distance", "Distance ultrason", "cm", 1, False, "hcsr04", 2, 400, 30),
    SensorDefinition("TSL-LUX", "TSL2591", "tsl2591_state", "lux", "Luminosité", "lx", 1, False, "tsl-lux", 0, 100000, 30),
    SensorDefinition("TSL-IR", "TSL2591", "tsl2591_state", "lux", "Infrarouge brut", "counts", 0, False, "tsl-ir", 0, 65535, 30),
    SensorDefinition("VEML-UVA", "VEML6075", "veml6075_state", "uv", "Rayonnement UVA", "counts", 1, False, "veml-uva", 0, 65535, 30),
    SensorDefinition("VEML-UVB", "VEML6075", "veml6075_state", "uv", "Rayonnement UVB", "counts", 1, False, "veml-uvb", 0, 65535, 30),
    SensorDefinition("VEML-UVINDEX", "VEML6075", "veml6075_state", "uv", "Indice UV", "indice", 1, False, "veml-uvindex", 0, 20, 30),
)

SENSORS_BY_KEY = {definition.key: definition for definition in SENSOR_CATALOG}
SENSORS_BY_SLUG = {definition.slug: definition for definition in SENSOR_CATALOG}


def effective_quality_profile(config, definition: SensorDefinition) -> dict[str, Any]:
    """Fusionne les défauts sûrs du catalogue et la surcharge de configuration."""
    profile = {
        "offset": 0.0,
        "calibrated_at": None,
        "calibration_valid_days": None,
        "freshness_seconds": definition.freshness_seconds,
        "plausible_min": definition.plausible_min,
        "plausible_max": definition.plausible_max,
        "freeze_epsilon": definition.freeze_epsilon,
        "freeze_after_seconds": definition.freeze_after_seconds,
        "freeze_min_samples": definition.freeze_min_samples,
    }
    configured = getattr(getattr(config, "sensor_quality", None), "profiles", {}).get(definition.key)
    if configured is not None:
        for name, value in configured.model_dump(exclude_none=True).items():
            profile[name] = value
    if profile.get("freeze_after_seconds") == "disabled":
        profile["freeze_after_seconds"] = None
    profile["plausible_min"] = max(float(profile["plausible_min"]), definition.plausible_min)
    profile["plausible_max"] = min(float(profile["plausible_max"]), definition.plausible_max)
    return profile


def enabled_definitions(config) -> list[SensorDefinition]:
    """Retourne les mesures activées par ``Sensor_State`` dans l'ordre UI."""
    return [
        definition
        for definition in SENSOR_CATALOG
        if bool(getattr(config.sensors, definition.enabled_field, False))
    ]
