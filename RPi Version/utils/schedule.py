"""Primitives communes de planning horaire.

La plage est toujours semi-ouverte ``[début, fin)``. Une plage dont les deux
bornes sont égales est vide : elle n'est jamais active.
"""

from __future__ import annotations

from datetime import datetime


def minute_in_range(now_minute: int, start_minute: int, stop_minute: int) -> bool:
    """Indique si une minute appartient à une plage, y compris à cheval sur minuit."""
    if start_minute == stop_minute:
        return False
    if start_minute < stop_minute:
        return start_minute <= now_minute < stop_minute
    return now_minute >= start_minute or now_minute < stop_minute


def clock_in_range(now: datetime, start_hour: int, start_minute: int,
                   stop_hour: int, stop_minute: int) -> bool:
    return minute_in_range(
        now.hour * 60 + now.minute,
        start_hour * 60 + start_minute,
        stop_hour * 60 + stop_minute,
    )


def day_night_times(config) -> tuple[int, int, int, int]:
    """Résout la source explicite du planning jour/nuit."""
    settings = config.day_night
    if settings.source == "dailytimer1":
        daily = config.daily_timer1
        return daily.start_hour, daily.start_minute, daily.stop_hour, daily.stop_minute
    return (
        settings.start_hour,
        settings.start_minute,
        settings.stop_hour,
        settings.stop_minute,
    )


def is_day(config, now: datetime | None = None) -> bool:
    start_h, start_m, stop_h, stop_m = day_night_times(config)
    return clock_in_range(now or datetime.now(), start_h, start_m, stop_h, stop_m)
