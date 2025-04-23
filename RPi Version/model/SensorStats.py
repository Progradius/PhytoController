# model/SensorStats.py
# Author: Progradius (adapted)
# License: AGPL-3.0

import json
from pathlib import Path
from datetime import datetime

class SensorStats:
    """
    Stocke en JSON le min/max et leurs dates pour chaque capteur suivi.
    Ne réinitialise pas le fichier s'il existe déjà.
    """

    FILE = Path("param/sensor_stats.json")
    KEYS = ("BME280T", "BME280H", "DS18B#3")

    def __init__(self):
        if self.FILE.exists():
            # charge le JSON existant
            with self.FILE.open(encoding="utf-8") as f:
                self.data = json.load(f)
            # ajoute au besoin les clés manquantes
            for k in self.KEYS:
                if k not in self.data:
                    self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
        else:
            # crée tout à None
            self.data = {
                k: {"min": None, "min_date": None, "max": None, "max_date": None}
                for k in self.KEYS
            }
            self._dump()

    def _dump(self):
        with self.FILE.open("w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def update(self, key: str, value: float):
        """
        Met à jour min/max pour la clé si `value` n'est pas None.
        """
        if value is None or key not in self.KEYS:
            return

        now = datetime.now().isoformat()
        entry = self.data[key]

        if entry["min"] is None or value < entry["min"]:
            entry["min"] = value
            entry["min_date"] = now

        if entry["max"] is None or value > entry["max"]:
            entry["max"] = value
            entry["max_date"] = now

        self._dump()

    def clear_key(self, key: str = None):
        """
        Remet à None le min/max pour une clé donnée,
        ou pour toutes les clés si key est None.
        """
        if key is None:
            # reset global
            for k in self.KEYS:
                self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
        else:
            # reset sur une seule clé
            if key in self.data:
                self.data[key] = {"min": None, "min_date": None, "max": None, "max_date": None}
        self._dump()

    @property
    def stats(self) -> dict:
        """
        Expose le dictionnaire interne de stats.
        """
        return self.data

    def get_all(self):
        """
        Retourne tout le dictionnaire de stats.
        """
        return self.data
