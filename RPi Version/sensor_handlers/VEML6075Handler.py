# controller/sensor/VEML6075Handler.py
# Author: Progradius
# License: AGPL-3.0

"""
Wrapper pour le capteur UV VEML6075.

‣Initialisation «safe»: en cas d'échec I²C, le handler reste
  désactivé (`self.available = False`) mais l'appli continue de tourner.
‣Toutes les lectures retournent `None` sur erreur et journalisent
  l'évènement via Pretty-Console.
"""

from lib.sensors.VEML6075 import VEML6075
from utils.pretty_console import info, warning, error


class VEMLHandler:
    """
    Handler haut-niveau pour le VEML6075.
    """

    # ──────────────────────────────────────────────────────────
    def __init__(self, i2c, *, integration_time: int = 100,
                 high_dynamic: bool = True) -> None:
        """
        Parameters
        ----------
        i2c : smbus2.SMBus
            Bus I²C initialisé (/dev/i2c-1 par ex.).
        integration_time : {50,100,200,400,800}
            Durée d'intégration en millisecondes.
        high_dynamic : bool
            Active la plage dynamique étendue si True.
        """
        self.available = False
        try:
            self._veml = VEML6075(
                i2c=i2c,
                integration_time=integration_time,
                high_dynamic=high_dynamic
            )
            self.available = True
            info("VEML6075 ready ✔")
        except Exception as exc:
            warning(f"VEML6075 init failed → capteur désactivé ({exc})")
            self._veml = None

    # ──────────────────────────────────────────────────────────
    def _safe_read(self, attr: str, label: str):
        """Lecture protégée; retourne None si indisponible/erreur."""
        if not self.available:
            warning(f"VEML6075 indisponible pour {label}")
            return None
        try:
            return getattr(self._veml, attr)
        except Exception as exc:
            error(f"Lecture {label} VEML6075 impossible: {exc}")
            return None

    # ───────────────────────────────────── Lectures publiques ─
    def get_veml_uva(self):
        """UVA calibré (counts) ou None."""
        return self._safe_read("uva", "UVA")

    def get_veml_uvb(self):
        """UVB calibré (counts) ou None."""
        return self._safe_read("uvb", "UVB")

    def get_veml_uv_index(self):
        """Indice UV ou None."""
        return self._safe_read("uv_index", "UV-index")
