# utils/log_dedup.py
# Author : Progradius
# License : AGPL-3.0
"""
Anti-flood : journalise les *transitions* d'une panne, pas chacune de ses répétitions.

Une panne réseau de 3 h sur le push InfluxDB produit 2 lignes (entrée en panne +
rétablissement) au lieu de 180.

    influx_state = StateLogger("push InfluxDB", name="influx")
    ...
    try:
        ...
        influx_state.ok()
    except RequestException as exc:
        influx_state.fail(f"POST refusé : {exc.__class__.__name__}")
"""

from time import monotonic

from utils import pretty_console as ui


class StateLogger:
    """
    • 1ʳᵉ défaillance         → ERROR (ou WARNING si `level="warning"`)
    • défaillances suivantes  → comptées en silence (DEBUG)
    • retour à la normale     → INFO avec durée et nombre d'échecs
    """

    def __init__(self, label: str, *, name: str | None = None, level: str = "error"):
        self.label = label
        self.name = name
        self.level = level
        self.failures = 0
        self._since: float | None = None

    # ──────────────────────────────────────────────────────────
    def fail(self, detail: str = "") -> None:
        """Signale un échec ; ne journalise vraiment que le premier."""
        self.failures += 1
        suffix = f" : {detail}" if detail else ""

        if self.failures == 1:
            self._since = monotonic()
            emit = ui.warning if self.level == "warning" else ui.error
            emit(f"{self.label} en échec{suffix}", name=self.name)
        else:
            ui.debug(
                f"{self.label} toujours en échec (#{self.failures}){suffix}",
                name=self.name,
            )

    # ──────────────────────────────────────────────────────────
    def ok(self, detail: str = "") -> None:
        """Signale un succès ; ne journalise que le rétablissement."""
        if not self.failures:
            return

        duration = monotonic() - (self._since or monotonic())
        failures = self.failures
        self.failures = 0
        self._since = None

        suffix = f" : {detail}" if detail else ""
        ui.info(
            f"{self.label} rétabli après {_human_duration(duration)} "
            f"et {failures} échec(s){suffix}",
            name=self.name,
        )

    # ──────────────────────────────────────────────────────────
    @property
    def failing(self) -> bool:
        return self.failures > 0


def _human_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {(seconds % 3600) // 60:02d} min"
