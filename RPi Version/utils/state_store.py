# utils/state_store.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Persistance des états de régulation (audit E10, E6)
# -------------------------------------------------------------
"""
Certains états de régulation ne doivent **pas** repartir de zéro à chaque
redémarrage :

* le budget de renouvellement d'air du mode hiver — sinon un `systemctl restart`
  (ou un redémarrage de tâche par le superviseur) réaccorde 5 min de vitesse 4
  toutes les quelques minutes, exactement le défaut décrit par l'audit E10 ;
* la phase séquentielle des minuteurs cycliques — sinon un redémarrage relance
  une phase ON complète, doublant l'arrosage (E6).

Le magasin suit le patron déjà éprouvé de `SensorStats` : un unique fichier JSON
écrit **atomiquement** (`utils.atomic_io`), une corruption détectée au chargement
donne une réinitialisation plutôt qu'une exception, et les échecs d'écriture sont
dédupliqués (`utils.log_dedup`) car ils se répètent à chaque tick.

L'écriture est **throttlée** : ces états changent à chaque tick de régulation
(15-30 s), et graver la carte SD à cette cadence l'userait pour rien.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from time import monotonic

from utils.atomic_io import write_text_atomic
from utils.log_dedup import StateLogger
from utils.pretty_console import warning

LOGGER_NAME = "state"

_write_state = StateLogger("Écriture de runtime_state.json",
                           name=LOGGER_NAME, level="warning")

# Deux ticks de régulation suffisent rarement à changer quoi que ce soit
# d'important ; on écrit au plus une fois par minute, plus la sauvegarde forcée
# demandée explicitement (arrêt, bascule de fenêtre).
MIN_WRITE_INTERVAL_SECONDS = 60.0


class StateStore:
    """
    Petit magasin clé → dictionnaire, persisté en JSON.

    Chaque consommateur possède sa **section** (`climate`, `cyclic_1`, …) : le
    fichier reste lisible à l'œil nu pendant un dépannage, et deux sections ne
    peuvent pas se marcher dessus.
    """

    FILE = Path(__file__).parent.parent / "param" / "runtime_state.json"

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else self.FILE
        # Les sections sont écrites depuis l'event loop, mais `SensorStats` a
        # montré qu'un état partagé finit toujours par être touché depuis un fil
        # d'exécution : le verrou évite d'avoir à y revenir.
        self._lock = threading.RLock()
        self._last_write: float | None = None
        self._dirty = False
        self._data: dict = {}

        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as exc:
                warning(f"État persisté illisible ({exc.__class__.__name__}) → "
                        "réinitialisation", name=LOGGER_NAME)
                self._data = {}
        if not isinstance(self._data, dict):
            self._data = {}

    # ──────────────────────────────────────────────────────────
    def load(self, section: str) -> dict:
        """Contenu d'une section (copie), `{}` si elle n'existe pas encore."""
        with self._lock:
            value = self._data.get(section)
            return dict(value) if isinstance(value, dict) else {}

    def save(self, section: str, payload: dict, *, force: bool = False) -> None:
        """
        Met la section à jour et écrit le fichier si l'intervalle minimal est
        écoulé (ou si `force`). Un échec d'écriture ne remonte jamais : perdre
        un budget est infiniment moins grave que tuer la régulation.
        """
        with self._lock:
            if self._data.get(section) == payload and not force:
                return
            self._data[section] = dict(payload)
            self._dirty = True
            now = monotonic()
            if (not force and self._last_write is not None
                    and now - self._last_write < MIN_WRITE_INTERVAL_SECONDS):
                return
            self._flush(now)

    def flush(self) -> None:
        """Écriture immédiate si quelque chose est en attente."""
        with self._lock:
            if self._dirty:
                self._flush(monotonic())

    # ──────────────────────────────────────────────────────────
    def _flush(self, now: float) -> None:
        try:
            write_text_atomic(
                self._path,
                json.dumps(self._data, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            _write_state.fail(f"{exc.__class__.__name__} : {exc}")
            return
        _write_state.ok()
        self._last_write = now
        self._dirty = False


# Magasin partagé du processus : une seule instance, donc un seul fichier et un
# seul verrou, quel que soit le nombre de consommateurs.
_shared: StateStore | None = None


def shared_store() -> StateStore:
    global _shared
    if _shared is None:
        _shared = StateStore()
    return _shared
