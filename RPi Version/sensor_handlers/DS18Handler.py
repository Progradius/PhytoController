# controller/sensor/DS18Handler.py
# Author : Progradius
# License: AGPL-3.0

import glob
from pathlib import Path
from typing import List, Optional

from ui.pretty_console import info, warning, error

SYSFS_GLOB = "/sys/bus/w1/devices/28-*"

class DS18Handler:
    """
    Lecture des DS18B20 via les fichiers sysfs :
      • available        → True si au moins une sonde trouvée
      • get_address_list → liste des dossiers (ex: ['28-00000a2b3c4d', ...])
      • get_ds18_temp(n) → température en °C (1-based), ou None si erreur
    """

    def __init__(self) -> None:
        # recherche des répertoires 28-*
        self._sensors: List[Path] = [Path(p) for p in glob.glob(SYSFS_GLOB)]
        if self._sensors:
            info(f"✅ {len(self._sensors)} DS18B20 détectée(s) via sysfs")
            self.available = True
        else:
            warning("Aucune sonde DS18B20 trouvée dans /sys/bus/w1/devices")
            self.available = False

    def get_address_list(self) -> List[str]:
        """Retourne la liste des IDs (ex : '28-00000a2b3c4d')."""
        return [p.name for p in self._sensors]

    def get_ds18_temp(self, sensor_number: int) -> Optional[float]:
        """
        Renvoie la température (°C) de la sonde #sensor_number (1-based).
        Lit le fichier w1_slave et vérifie le CRC.
        """
        idx = sensor_number - 1
        if idx < 0 or idx >= len(self._sensors):
            warning(f"Capteur DS18B20 #{sensor_number} inexistant")
            return None

        slave_file = self._sensors[idx] / "w1_slave"
        try:
            text = slave_file.read_text().splitlines()
        except Exception as e:
            error(f"Lecture sysfs DS18B20 #{sensor_number} : {e}")
            return None

        # ligne 1 doit terminer par "YES"
        if not text or not text[0].strip().endswith("YES"):
            warning(f"CRC invalide pour DS18B20 #{sensor_number}")
            return None

        # on extrait la température après "t="
        try:
            raw = text[1].split("t=")[1]
            temp_c = int(raw) / 1000.0
            return round(temp_c, 1)
        except Exception as e:
            error(f"Parsing température DS18B20 #{sensor_number} : {e}")
            return None
