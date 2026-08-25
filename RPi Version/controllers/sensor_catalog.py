"""Catalogue canonique des mesures capteurs.

Une seule table décrit les clés internes, l'activation matérielle, les unités,
les libellés web et les measurements Influx. Elle évite les listes divergentes
qui rendaient les pages et les capteurs de distance incohérents.
"""

from __future__ import annotations

from dataclasses import dataclass


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


SENSOR_CATALOG: tuple[SensorDefinition, ...] = (
    SensorDefinition("BME280T", "BME280", "bme280_state", "air", "Température de l’air", "°C", tracked_stats=True),
    SensorDefinition("BME280H", "BME280", "bme280_state", "air", "Humidité de l’air", "%", tracked_stats=True),
    SensorDefinition("BME280P", "BME280", "bme280_state", "air", "Pression atmosphérique", "hPa"),
    SensorDefinition("MLX-AMB", "MLX90614", "mlx90614_state", "air", "Température infrarouge ambiante", "°C"),
    SensorDefinition("DS18B#1", "DS18B20", "ds18b20_state", "air", "Température sonde 1", "°C"),
    SensorDefinition("DS18B#2", "DS18B20", "ds18b20_state", "air", "Température sonde 2", "°C"),
    SensorDefinition("MLX-OBJ", "MLX90614", "mlx90614_state", "surface_temp", "Température de surface", "°C"),
    SensorDefinition("DS18B#3", "DS18B20", "ds18b20_state", "water", "Température de l’eau", "°C", tracked_stats=True),
    SensorDefinition("VL53L0X", "VL53L0X", "vl53L0x_state", "distance", "Distance laser", "mm"),
    SensorDefinition("HCSR04", "HC-SR04", "hcsr04_state", "distance", "Distance ultrason", "cm"),
    SensorDefinition("TSL-LUX", "TSL2591", "tsl2591_state", "lux", "Luminosité", "lx"),
    SensorDefinition("TSL-IR", "TSL2591", "tsl2591_state", "lux", "Infrarouge brut", "counts", 0),
    SensorDefinition("VEML-UVA", "VEML6075", "veml6075_state", "uv", "Rayonnement UVA", "counts"),
    SensorDefinition("VEML-UVB", "VEML6075", "veml6075_state", "uv", "Rayonnement UVB", "counts"),
    SensorDefinition("VEML-UVINDEX", "VEML6075", "veml6075_state", "uv", "Indice UV", "indice"),
)

SENSORS_BY_KEY = {definition.key: definition for definition in SENSOR_CATALOG}


def enabled_definitions(config) -> list[SensorDefinition]:
    """Retourne les mesures activées par ``Sensor_State`` dans l'ordre UI."""
    return [
        definition
        for definition in SENSOR_CATALOG
        if bool(getattr(config.sensors, definition.enabled_field, False))
    ]
