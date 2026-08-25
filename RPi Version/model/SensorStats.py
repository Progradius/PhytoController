# model/SensorStats.py
# Author: Progradius
# License: AGPL-3.0

import copy
import json
import threading
from pathlib import Path
from datetime import datetime
from utils.pretty_console import warning
from utils.atomic_io import write_text_atomic
from utils.log_dedup import StateLogger

LOGGER_NAME = "stats"

# `_dump()` est appelé à chaque lecture de capteur : on déduplique les échecs
# d'écriture (disque plein, permissions…).
_dump_state = StateLogger("Écriture de sensor_stats.json",
                          name=LOGGER_NAME, level="warning")

class SensorStats:
    """
    Stocke en JSON le min/max et leurs dates pour chaque capteur suivi.
    Crée automatiquement le dossier et le fichier s'il n'existent pas.
    """

    # On pointe désormais vers param/sensor_stats.json à partir du répertoire du module
    FILE = Path(__file__).parent.parent / "param" / "sensor_stats.json"
    KEYS = ("BME280T", "BME280H", "DS18B#3")

    def __init__(self):
        # Les min/max sont mis à jour depuis le fil d'exécution des capteurs et
        # remis à zéro depuis l'event loop (bouton du tableau de bord). Sans
        # verrou, deux `_dump()` concurrents restent atomiques au niveau du
        # fichier, mais la dernière écriture écrase silencieusement l'autre
        # mise à jour. Un `RLock` sérialise lecture, modification et écriture,
        # et supporte les appels imbriqués (`update()` → `_dump()`).
        self._lock = threading.RLock()

        # 1) S'assure que le dossier existe
        self.FILE.parent.mkdir(parents=True, exist_ok=True)

        # 2) Charge ou initialise les données
        if self.FILE.exists():
            try:
                with self.FILE.open(encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                warning(f"Stats corrompues : {e} → réinitialisation", name=LOGGER_NAME)
                self.data = self._default_data()
                self._dump()
            else:
                # Ajoute les clés manquantes si besoin
                for k in self.KEYS:
                    if k not in self.data:
                        self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
        else:
            self.data = self._default_data()
            self._dump()

    def _dump(self):
        """
        Écrit self.data dans le fichier JSON (échec non bloquant).

        Écriture atomique : `_dump()` est appelé à chaque lecture de capteur,
        donc très souvent — une coupure secteur pendant l'une d'elles ne doit
        pas laisser un fichier tronqué (qui serait ensuite réinitialisé au
        prochain boot, perdant l'historique min/max).
        """
        try:
            with self._lock:
                payload = json.dumps(self.data, indent=4)
                write_text_atomic(self.FILE, payload, encoding="utf-8")
        except OSError as e:
            _dump_state.fail(f"{e.__class__.__name__} : {e}")
        else:
            _dump_state.ok()

    def update(self, key: str, value: float):
        """
        Met à jour min/max pour la clé si `value` n'est pas None.
        """
        if value is None or key not in self.KEYS:
            return

        now = datetime.now().isoformat()
        with self._lock:
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
        with self._lock:
            if key is None:
                for k in self.KEYS:
                    self.data[k] = {"min": None, "min_date": None, "max": None, "max_date": None}
            elif key in self.data:
                self.data[key] = {"min": None, "min_date": None, "max": None, "max_date": None}
            self._dump()

    @property
    def stats(self) -> dict:
        """
        Copie des statistiques, sûre à parcourir depuis un autre fil.
        """
        return self.get_all()

    def get_all(self) -> dict:
        """
        Retourne une **copie** des statistiques.

        Rendre le dictionnaire interne exposerait l'appelant à une modification
        concurrente pendant qu'il le parcourt (l'IHM lit pendant que le fil des
        capteurs écrit).
        """
        with self._lock:
            return copy.deepcopy(self.data)
    
    def _default_data(self) -> dict:
        return {
            k: {"min": None, "min_date": None, "max": None, "max_date": None}
            for k in self.KEYS
        }
