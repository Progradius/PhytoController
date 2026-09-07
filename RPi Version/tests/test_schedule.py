from __future__ import annotations

from datetime import datetime

import pytest

from components.climate_policy import settings_from_config
from utils.schedule import day_night_times, is_day, minute_in_range


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (18, 59, False),
        (19, 0, True),
        (23, 59, True),
        (0, 0, True),
        (6, 59, True),
        (7, 0, False),
    ],
)
def test_plage_traversant_minuit(hour, minute, expected):
    assert minute_in_range(hour * 60 + minute, 19 * 60, 7 * 60) is expected


@pytest.mark.parametrize(
    ("minute", "expected"),
    [(7 * 60 + 59, False), (8 * 60, True), (19 * 60 + 59, True), (20 * 60, False)],
)
def test_plage_normale_est_semi_ouverte(minute, expected):
    assert minute_in_range(minute, 8 * 60, 20 * 60) is expected


def test_plage_de_longueur_nulle_est_vide():
    assert all(not minute_in_range(minute, 600, 600) for minute in range(24 * 60))


def test_source_jour_nuit_heritee_du_timer(valid_config):
    assert day_night_times(valid_config) == (19, 0, 7, 0)
    assert is_day(valid_config, datetime(2026, 8, 26, 0, 0)) is True
    assert is_day(valid_config, datetime(2026, 8, 26, 7, 0)) is False


def test_source_jour_nuit_personnalisee(valid_config):
    valid_config.day_night.source = "custom"
    valid_config.day_night.start_hour = 8
    valid_config.day_night.stop_hour = 20
    assert day_night_times(valid_config) == (8, 0, 20, 0)


def test_projection_des_consigne_jour_et_nuit(valid_config):
    day = settings_from_config(valid_config, True)
    night = settings_from_config(valid_config, False)
    assert (day.temp_min, day.temp_max) == (20.0, 24.0)
    assert (night.temp_min, night.temp_max) == (18.0, 22.0)
