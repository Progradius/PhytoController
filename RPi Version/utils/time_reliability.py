"""Moniteur non bloquant de fiabilité de l'horloge murale."""

from __future__ import annotations

import os
import time
from pathlib import Path

from utils.pretty_console import info, warning
from utils.supervisor import beat, sleep as hb_sleep

LOGGER_NAME = "time"
SYNCHRONIZED_MARKER = Path("/run/systemd/timesync/synchronized")
TIMESYNCD_CLOCK = Path("/var/lib/systemd/timesync/clock")
UNKNOWN_SUSPENSION_SECONDS = 15 * 60
MONITOR_PERIOD_SECONDS = 30


class TimeReliability:
    def __init__(self) -> None:
        self.boot_mono = time.monotonic()
        self.state = "unknown"
        self.ever_synchronized = False
        self.updated_mono = self.boot_mono
        self._last_reported: str | None = None
        self.probe()

    def probe(self) -> str:
        """Sonde uniquement des métadonnées de fichiers, sans subprocess bloquant."""
        previous = self.state
        if os.getenv("PHYTO_FAKE_TIME_UNSYNCED") == "1":
            state = "unknown"
        elif SYNCHRONIZED_MARKER.exists():
            state = "synchronized"
        else:
            try:
                last_known = TIMESYNCD_CLOCK.stat().st_mtime
                state = "plausible" if time.time() >= last_known else "unknown"
            except OSError:
                state = "unknown"

        if state == "synchronized":
            self.ever_synchronized = True
        # Après une première preuve NTP, sa perte temporaire ne remet pas les
        # ordonnanceurs en suspension : l'horloge reste au moins plausible.
        if self.ever_synchronized and state == "unknown":
            state = "plausible"
        self.state = state
        self.updated_mono = time.monotonic()
        if state != previous or self._last_reported is None:
            if state == "synchronized":
                info("Horloge synchronisée par NTP", name=LOGGER_NAME)
            elif state == "plausible":
                warning("Horloge plausible mais sans preuve NTP actuelle", name=LOGGER_NAME)
            else:
                warning("Heure inconnue : minuteries journalières suspendues temporairement", name=LOGGER_NAME)
            self._last_reported = state
        return state

    @property
    def unknown_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.boot_mono) if self.state == "unknown" else 0.0

    def daily_suspended(self) -> bool:
        return self.state == "unknown" and self.unknown_seconds < UNKNOWN_SUSPENSION_SECONDS

    def use_day_settings(self) -> bool:
        """Le climat et les séquentiels restent en paramètres nuit sans preuve NTP."""
        return self.state == "synchronized"

    def snapshot(self) -> dict:
        bounded_resume = self.state == "unknown" and not self.daily_suspended()
        return {
            "state": "plausible" if bounded_resume else self.state,
            "observed_state": self.state,
            "ever_synchronized": self.ever_synchronized,
            "daily_timers_suspended": self.daily_suspended(),
            "unknown_seconds": round(self.unknown_seconds, 1),
            "suspension_limit_seconds": UNKNOWN_SUSPENSION_SECONDS,
            "alarm": "heure non fiable : reprise bornée après 15 min" if bounded_resume else None,
        }


_monitor = TimeReliability()


def time_reliability() -> TimeReliability:
    return _monitor


async def monitor_time_reliability() -> None:
    while True:
        beat()
        _monitor.probe()
        await hb_sleep(MONITOR_PERIOD_SECONDS)
