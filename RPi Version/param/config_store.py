# param/config_store.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Magasin de configuration (audit C5, C7, E7, M4)
# -------------------------------------------------------------
"""
Propriétaire unique de `param.json`.

Avant ce magasin, `AppConfig` n'appartenait à personne : quatre boucles de
contrôle appelaient `AppConfig.load()` **à chaque tick**, c'est-à-dire une
lecture disque, un parse JSON et une validation Pydantic intégrale dans le
chemin qui pilote un relais. Chacune s'était recodé son propre filet de
sécurité — trois variantes du même `try/except` — et deux d'entre elles
(`DailyTimer.refresh_from_config`, `CyclicTimer.refresh_from_config`)
**remplaçaient** leur référence par un objet neuf, cessant du même coup de
partager la configuration distribuée au boot au moteur, aux capteurs et au
serveur. Il y avait donc plusieurs configurations vivantes à la fois (M4).

Trois principes tiennent tout le module :

1. **Une seule instance d'`AppConfig` pour tout le processus.** Elle n'est
   jamais remplacée, seulement mutée en place (`replace_from`). Toute référence
   distribuée au boot — `MotorHandler`, `SensorController`, `SystemStatus`,
   `Server`, les minuteurs — reste donc valide et à jour pour toujours, sans
   qu'aucun de ces objets ait à s'abonner à quoi que ce soit.
2. **Le chemin de contrôle ne fait plus d'I/O et ne lève plus.** `refresh()`
   compare `(mtime_ns, taille)` : fichier inchangé, il rend l'instance courante
   sans rien lire. Une relecture qui échoue garde la configuration courante — un
   `param.json` momentanément illisible ne doit jamais arrêter une régulation,
   parce que plus rien ne repiloterait la sortie concernée (C7).
3. **Le magasin est le seul écrivain**, et il revalide intégralement
   (`model_validate`) avant d'écrire. Une affectation de champ ne rejoue pas les
   validateurs croisés (`min_speed ≤ max_speed`, `temp_min ≤ temp_max`) : seule
   une validation du modèle complet les rejoue (C5). L'écriture passe par
   `utils.atomic_io`, et l'ancien contenu est conservé en `.bak`.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import ValidationError

from param.config import AppConfig
from utils import pretty_console as ui
from utils.atomic_io import write_text_atomic

LOGGER_NAME = "config"


class ConfigStore:
    """Source unique de vérité de la configuration du processus."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else AppConfig.config_path()
        self._backup = self._path.with_name(self._path.name + ".bak")
        # Les écritures viennent de l'event loop (POST /conf), mais `SensorStats`
        # a montré qu'un état partagé finit toujours par être touché depuis un
        # fil d'exécution : le verrou évite d'avoir à y revenir.
        self._lock = threading.RLock()
        self._stamp: tuple[int, int] | None = None
        self._current: AppConfig = self._boot_load()

    # ──────────────────────────────────────────────────────────
    #  Lecture
    # ──────────────────────────────────────────────────────────
    @property
    def current(self) -> AppConfig:
        """
        L'instance partagée. **Ne jamais la remplacer** chez l'appelant : c'est
        son identité qui garantit que tout le processus voit la même chose.
        """
        return self._current

    @property
    def path(self) -> Path:
        return self._path

    def refresh(self) -> AppConfig:
        """
        Prend en compte une modification du fichier, puis rend l'instance
        partagée. Ne lève jamais : c'est la méthode du chemin de contrôle.
        """
        with self._lock:
            stamp = self._stat_stamp()
            if stamp is not None and stamp == self._stamp:
                return self._current

            try:
                fresh = AppConfig.load(self._path)
            except Exception:
                # `AppConfig.load()` a déjà journalisé la cause, dédupliquée.
                # On retient quand même l'empreinte : sans cela, un fichier
                # cassé serait reparsé à chaque tick de chaque boucle.
                self._stamp = stamp
                return self._current

            self._current.replace_from(fresh)
            self._stamp = stamp
            ui.debug("Configuration rechargée depuis le disque", name=LOGGER_NAME)
            return self._current

    # ──────────────────────────────────────────────────────────
    #  Écriture
    # ──────────────────────────────────────────────────────────
    def save(self, candidate: AppConfig) -> AppConfig:
        """
        Valide intégralement `candidate`, l'écrit, puis l'adopte.

        Lève `ValidationError` si la candidate est refusée (rien n'est écrit,
        l'instance partagée est intacte) ou `OSError` si l'écriture échoue.
        """
        with self._lock:
            validated = self._revalidate(candidate)
            self._write(validated)
            self._current.replace_from(validated)
            return self._current

    def commit(self) -> AppConfig:
        """
        Écrit l'instance partagée après l'avoir mutée directement.

        Une mutation champ à champ ne rejoue pas les validateurs croisés : on
        revalide donc le modèle complet. Si le résultat est refusé, l'instance
        est **restaurée depuis le disque** avant de propager l'erreur — laisser
        en mémoire un état que le magasin vient de juger invalide serait pire
        que l'échec lui-même.
        """
        with self._lock:
            try:
                validated = self._revalidate(self._current)
            except ValidationError:
                self._rollback()
                raise
            self._write(validated)
            self._current.replace_from(validated)
            return self._current

    # ──────────────────────────────────────────────────────────
    #  Interne
    # ──────────────────────────────────────────────────────────
    def _stat_stamp(self) -> tuple[int, int] | None:
        """`(mtime_ns, taille)` du fichier, ou `None` s'il est inaccessible."""
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    @staticmethod
    def _revalidate(candidate: AppConfig) -> AppConfig:
        """Rejoue la validation du modèle **complet**, validateurs croisés compris."""
        return AppConfig.model_validate(candidate.model_dump(by_alias=True))

    def _write(self, config: AppConfig) -> None:
        self._backup_current_file()
        write_text_atomic(self._path, config.to_json(), encoding="utf-8")
        self._stamp = self._stat_stamp()
        ui.debug("param.json enregistré", name=LOGGER_NAME)

    def _backup_current_file(self) -> None:
        """
        Conserve le dernier contenu connu-bon avant de le remplacer.

        Un échec ici n'empêche pas l'écriture : perdre le filet est moins grave
        que refuser une modification de configuration demandée par l'utilisateur.
        """
        try:
            content = self._path.read_bytes()
        except OSError:
            return
        try:
            json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            # Ne jamais sauvegarder un fichier déjà cassé par-dessus un `.bak`
            # sain : ce serait détruire le seul exemplaire valide restant.
            return
        try:
            write_text_atomic(self._backup, content.decode("utf-8"), encoding="utf-8")
        except OSError as exc:
            ui.warning(
                f"Copie de secours de param.json impossible : "
                f"{exc.__class__.__name__} : {exc}",
                name=LOGGER_NAME,
            )

    def _rollback(self) -> None:
        """Restaure l'instance partagée depuis le disque après un refus."""
        try:
            self._current.replace_from(AppConfig.load(self._path))
        except Exception as exc:
            ui.critical(
                "Configuration en mémoire refusée ET disque illisible "
                f"({exc.__class__.__name__}) : l'instance partagée peut être "
                "incohérente jusqu'au prochain redémarrage",
                name=LOGGER_NAME,
            )

    def _boot_load(self) -> AppConfig:
        """
        Chargement initial, avec repli sur la copie de secours.

        Une coupure secteur au mauvais moment, un disque plein ou une édition
        manuelle malheureuse rendaient jusqu'ici le boot définitivement mort.
        Le `.bak` est le dernier contenu qui a été validé **et** écrit avec
        succès : s'il passe, on le remet en place pour que le boot suivant
        reparte propre.

        Il n'y a pas de « défaut sûr » à synthétiser au-delà : sans
        `GPIO_Settings`, aucune broche n'est connue, donc aucune sortie ne peut
        être mise dans un état sûr. Refuser de démarrer est alors la seule
        réponse honnête — et `main.py` n'a encore touché aucune broche à ce
        stade.
        """
        try:
            config = AppConfig.load(self._path)
        except Exception as exc:
            ui.error(
                f"param.json inutilisable ({exc.__class__.__name__} : {exc}) → "
                "tentative de reprise sur la copie de secours",
                name=LOGGER_NAME,
            )
            config = AppConfig.load(self._backup)
            ui.warning(
                f"Configuration reprise depuis {self._backup.name} et restaurée : "
                "vérifier les paramètres, ils datent de la dernière écriture réussie",
                name=LOGGER_NAME,
            )
            write_text_atomic(self._path, config.to_json(), encoding="utf-8")

        self._stamp = self._stat_stamp()
        return config


# Magasin partagé du processus : une seule instance, donc une seule
# configuration vivante et un seul écrivain, quel que soit le nombre de
# consommateurs (patron de `utils.state_store.shared_store`).
_shared: ConfigStore | None = None


def shared_config() -> ConfigStore:
    global _shared
    if _shared is None:
        _shared = ConfigStore()
    return _shared
