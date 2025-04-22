# controller/sensor/DS18Handler.py
# Author : Progradius
# License: AGPL-3.0
"""
Gestion des sondes DS18B20 :

1. essaie d'utiliser la bibliothèque *w1thermsensor* (plus rapide, CRC, etc.)
2. à défaut, lit directement les fichiers de /sys/bus/w1/devices/28-*/w1_slave
3. expose une API unifiée :

   • ``available``            → bool, au moins 1 sonde détectée  
   • ``get_address_list()``   → liste des IDs hexadécimaux  
   • ``get_ds18_temp(idx)``   → température °C de la sonde n°*idx* (1-based)
"""

from __future__ import annotations
import glob
from pathlib import Path
from typing import List, Optional

from ui.pretty_console import info, warning, error

# ───────────────────────────────────────────────────────────────
#  Détection de l'implémentation disponible
# ───────────────────────────────────────────────────────────────
try:
    from w1thermsensor import W1ThermSensor, Unit, NoSensorFoundError  # type: ignore
    _USE_W1TS = True
except ModuleNotFoundError:
    _USE_W1TS = False
    W1ThermSensor = None  # type: ignore

SYSFS_GLOB = "/sys/bus/w1/devices/28-*"


# ───────────────────────────────────────────────────────────────
#  Handler
# ───────────────────────────────────────────────────────────────
class DS18Handler:
    def __init__(self) -> None:
        self._impl: str
        self._sensors: List        = []
        self.available: bool       = False

        if _USE_W1TS:
            self._impl = "w1thermsensor"
            try:
                self._sensors = W1ThermSensor.get_available_sensors()
            except NoSensorFoundError:
                warning("Aucune sonde DS18B20 détectée via w1thermsensor.")
            else:
                info(f"✅ {len(self._sensors)} DS18B20 détectée(s) via w1thermsensor")
                self.available = bool(self._sensors)

        if not self.available:                          # fallback sysfs
            self._impl = "sysfs"
            self._sensors = [Path(p) for p in glob.glob(SYSFS_GLOB)]
            if self._sensors:
                info(f"✅ {len(self._sensors)} DS18B20 détectée(s) via sysfs")
                self.available = True
            else:
                warning("Aucune sonde DS18B20 détectée dans /sys/bus/w1/devices")

    # ------------------------------------------------------------------ #
    #  API publique
    # ------------------------------------------------------------------ #
    def get_address_list(self) -> List[str]:
        """Retourne la liste des IDs (ex : *28-00000a2b3c4d*)."""
        if self._impl == "w1thermsensor":
            return [s.id for s in self._sensors]               # type: ignore[attr-defined]
        return [p.name for p in self._sensors]                 # sysfs

    def get_ds18_temp(self, sensor_number: int) -> Optional[float]:
        """
        Param
        -----
        sensor_number : int   (1-based, tel qu'utilisé ailleurs dans le code)

        Returns
        -------
        float  température en °C (arrondie à 0.1) ou None si erreur.
        """
        idx = sensor_number - 1
        if idx < 0:
            warning(f"Indice DS18 négatif ({sensor_number})")
            return None

        # --- Impl. w1thermsensor ---------------------------------------
        if self._impl == "w1thermsensor":
            if idx >= len(self._sensors):
                warning(f"Capteur DS18B20 #{sensor_number} inexistant (w1thermsensor)")
                return None
            try:
                val = self._sensors[idx].get_temperature(Unit.CELSIUS)  # type: ignore[attr-defined]
                return round(val, 1)
            except Exception as e:
                error(f"Lecture DS18 #{sensor_number} (w1thermsensor) : {e}")
                return None

        # --- Impl. sysfs ----------------------------------------------
        if idx >= len(self._sensors):
            warning(f"Capteur DS18B20 #{sensor_number} inexistant (sysfs)")
            return None

        try:
            lines = (self._sensors[idx] / "w1_slave").read_text().splitlines()
            if not lines[0].strip().endswith("YES"):
                warning(f"CRC invalide pour DS18 #{sensor_number}")
                return None
            raw = lines[1].split("t=")[1]
            return round(int(raw) / 1000.0, 1)
        except Exception as e:
            error(f"Lecture DS18 #{sensor_number} (sysfs) : {e}")
            return None
