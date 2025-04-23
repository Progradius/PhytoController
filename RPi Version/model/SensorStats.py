# model/SensorStats.py
# Author: Progradius (refactorisé)
# License: AGPL-3.0

import json
from pathlib import Path
from datetime import datetime

class SensorStats:
    """
    Stocke en JSON le min/max et leurs dates pour chaque capteur suivi.
    Crée automatiquement le dossier et le fichier s'il n'existent pas.
    """

    # On pointe désormais vers param/sensor_stats.json à partir du répertoire du module
    FILE = Path(__file__).parent.parent / "param" / "sensor_stats.json"
    KEYS = ("BME280T", "BME280H", "DS18B#3")

    def __init__(self):
        # 1) S’assure que le dossier existe
        self.FILE.parent.mkdir(parents=True, exist_ok=True)

        # 2) Charge ou initialise les données
        if self.FILE.exists():
            with self.FILE.open(encoding="utf-8") as f:
                self.data = json.load(f)
            # Ajoute les clés manquantes si besoin
            for k in self.KEYS:
                if k not in self.data:
                    self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
        else:
            # Dossier ok, mais pas de fichier → on crée tout à None
            self.data = {
                k: {"min": None, "min_date": None, "max": None, "max_date": None}
                for k in self.KEYS
            }
            self._dump()

    def _dump(self):
        """Écrit self.data dans le fichier JSON."""
        # En cas d’appel isolé on recrée aussi le dossier
        self.FILE.parent.mkdir(parents=True, exist_ok=True)
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
            for k in self.KEYS:
                self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
        elif key in self.data:
            self.data[key] = {"min": None, "min_date": None, "max": None, "max_date": None}
        self._dump()

    @property
    def stats(self) -> dict:
        """
        Expose le dictionnaire interne de stats.
        """
        return self.data

    def get_all(self) -> dict:
        """
        Retourne tout le dictionnaire de stats.
        """
        return self.data
