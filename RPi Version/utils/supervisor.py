# utils/supervisor.py
# Author : Progradius
# License: AGPL-3.0
# -------------------------------------------------------------
#  Superviseur générique des tâches asyncio (audit C6)
# -------------------------------------------------------------
"""
Le contrôle de la serre repose sur des boucles infinies. Jusqu'ici, une
exception dans l'une d'elles la tuait **définitivement** : le processus restait
« sain » (systemd le voyait vivant, le watchdog le caressait quand même), mais
plus rien ne repilotait la broche concernée — un relais 230 V pouvait rester
collé indéfiniment sans qu'aucun signal ne le dise.

Ce module transforme cette panne silencieuse en panne visible et récupérable :

  • chaque travail tourne dans un `while True: try/except` avec back-off
    exponentiel plafonné ;
  • **l'état sûr est repositionné AVANT chaque relance** (sortie coupée, moteur
    à l'arrêt) : on ne redémarre jamais une régulation par-dessus un relais
    dont on ignore l'état ;
  • chaque travail publie un **battement de cœur** ; un travail vivant mais
    muet (bloqué sur une attente sans fin) est détecté, annulé et relancé ;
  • l'état complet (vivant, silence, redémarrages, dernière erreur, domaine)
    est exposé pour `/status` ; le sous-ensemble `gates_watchdog` conditionne
    seul le coup de patte du watchdog (`utils/watchdog.py`).

Les battements sont propagés par `contextvars` : une tâche supervisée hérite du
contexte du superviseur, donc `beat()` et `sleep()` savent seuls à quel travail
ils appartiennent. Aucune signature de coroutine métier n'a besoin de porter le
superviseur.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import traceback
from collections import deque
from time import monotonic
from typing import Awaitable, Callable

from utils.pretty_console import debug, error, info, warning

LOGGER_NAME = "supervisor"

# Back-off entre deux relances : agressif au début (un défaut transitoire se
# rattrape en quelques secondes), plafonné pour ne pas marteler le matériel.
BACKOFF_INITIAL_SECONDS = 5.0
BACKOFF_MAX_SECONDS = 300.0
BACKOFF_FACTOR = 2.0
# Une tâche qui a tenu au moins ce temps repart d'un back-off neuf : une panne
# isolée après 2 h de fonctionnement n'est pas une boucle de crash.
BACKOFF_RESET_AFTER_SECONDS = 600.0
RESTART_WINDOW_SECONDS = 10 * 60.0

# Découpage des longues attentes : une sieste de 10 jours (cyclic journalier)
# ne doit pas ressembler à une tâche morte.
BEAT_SLICE_SECONDS = 30.0

_current_job: contextvars.ContextVar["SupervisedJob | None"] = contextvars.ContextVar(
    "phyto_supervised_job", default=None
)


# ─────────────────────────────────────────────────────────────
#  API appelée depuis les coroutines métier
# ─────────────────────────────────────────────────────────────
def beat() -> None:
    """
    Signale que la tâche supervisée courante est toujours vivante.
    Sans effet hors d'une tâche supervisée (tests, imports, scripts).
    """
    job = _current_job.get()
    if job is not None:
        job.last_beat = monotonic()


async def sleep(delay: float, slice_seconds: float = BEAT_SLICE_SECONDS) -> None:
    """
    `asyncio.sleep()` qui bat le cœur : une attente longue mais **voulue** ne
    doit pas être confondue avec un blocage. À utiliser partout dans les
    boucles supervisées à la place d'`asyncio.sleep()`.
    """
    beat()
    if delay <= 0:
        return
    end = monotonic() + delay
    while True:
        remaining = end - monotonic()
        if remaining <= 0:
            return
        await asyncio.sleep(min(slice_seconds, remaining))
        beat()


# ─────────────────────────────────────────────────────────────
#  Modèle d'un travail supervisé
# ─────────────────────────────────────────────────────────────
class SupervisedJob:
    """État d'un travail : sa fabrique de coroutine, son état sûr, sa santé."""

    def __init__(
        self,
        name: str,
        factory: Callable[[], Awaitable[None]],
        safe_state: Callable[[], None] | None,
        max_silence: float | None,
        domain: str,
        gates_watchdog: bool,
    ) -> None:
        self.name = name
        self.factory = factory
        self.safe_state = safe_state
        # None = pas de contrôle de silence (serveur HTTP : rester en attente de
        # connexion est son fonctionnement normal, pas un blocage).
        self.max_silence = max_silence
        self.domain = domain
        self.gates_watchdog = gates_watchdog

        self.last_beat: float = monotonic()
        self.restarts: int = 0
        self.restart_times: deque[float] = deque()
        self.reloads: int = 0
        self.stalls: int = 0
        self.last_error: str | None = None
        # `task` = le runner (jamais annulé sauf arrêt du processus) ;
        # `inner` = l'exécution courante du travail, seule cible d'une annulation
        # pour cause de silence.
        self.task: asyncio.Task | None = None
        self.inner: asyncio.Task | None = None
        self.stall_requested: bool = False
        self.reload_requested: bool = False

    # --- santé -------------------------------------------------
    @property
    def silence_seconds(self) -> float:
        return monotonic() - self.last_beat

    def is_alive(self) -> bool:
        # Le runner survit volontairement aux exceptions pour pouvoir relancer
        # le travail. Il ne prouve donc pas que la boucle métier tourne : en
        # plein back-off, `task` est vivant mais `inner` est déjà terminé.
        return (
            self.task is not None
            and not self.task.done()
            and self.inner is not None
            and not self.inner.done()
        )

    def is_stale(self) -> bool:
        return self.max_silence is not None and self.silence_seconds > self.max_silence

    def is_healthy(self) -> bool:
        return self.is_alive() and not self.is_stale()

    def recent_restart_count(self, now: float | None = None) -> int:
        current = monotonic() if now is None else now
        while self.restart_times and current - self.restart_times[0] >= RESTART_WINDOW_SECONDS:
            self.restart_times.popleft()
        return len(self.restart_times)

    def snapshot(self) -> dict:
        return {
            "domain": self.domain,
            "gates_watchdog": self.gates_watchdog,
            "alive": self.is_alive(),
            "healthy": self.is_healthy(),
            "silence_s": round(self.silence_seconds, 1),
            "max_silence_s": self.max_silence,
            "restarts": self.restarts,
            "restarts_10m": self.recent_restart_count(),
            "reloads": self.reloads,
            "stalls": self.stalls,
            "last_error": self.last_error,
        }


# ─────────────────────────────────────────────────────────────
#  Superviseur
# ─────────────────────────────────────────────────────────────
class TaskSupervisor:
    """
    Lance les travaux enregistrés, les relance indéfiniment et publie leur
    santé. Le superviseur ne meurt jamais de la mort d'un travail.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, SupervisedJob] = {}
        self._runners: list[asyncio.Task] = []
        self._watch_task: asyncio.Task | None = None

    # --- enregistrement ----------------------------------------
    def register(
        self,
        name: str,
        factory: Callable[[], Awaitable[None]],
        *,
        safe_state: Callable[[], None] | None = None,
        max_silence: float | None = 300.0,
        domain: str = "auxiliary",
        gates_watchdog: bool = False,
    ) -> SupervisedJob:
        """
        `factory` doit **fabriquer** la coroutine à chaque appel : une coroutine
        déjà créée n'est consommable qu'une fois, donc non relançable.
        """
        if name in self._jobs:
            raise ValueError(f"Travail « {name} » déjà enregistré")
        job = SupervisedJob(name, factory, safe_state, max_silence, domain, gates_watchdog)
        self._jobs[name] = job
        return job

    # --- cycle de vie ------------------------------------------
    def start(self) -> None:
        """Démarre un runner par travail enregistré, plus le veilleur de silence."""
        gated = [job.name for job in self._jobs.values() if job.gates_watchdog]
        if not gated:
            raise RuntimeError("Aucune tâche de contrôle ne gouverne le watchdog")
        loop = asyncio.get_event_loop()
        for job in self._jobs.values():
            job.task = loop.create_task(self._runner(job), name=job.name)
            self._runners.append(job.task)
        self._watch_task = loop.create_task(self._watch_stalls(), name="supervisor_watch")
        info(
            "Tâches supervisées : " + ", ".join(self._jobs),
            name=LOGGER_NAME,
        )
        info("Watchdog gouverné par : " + ", ".join(gated), name=LOGGER_NAME)

    async def wait(self) -> None:
        """
        Bloque tant que des runners tournent. Ils ne se terminent jamais d'
        eux-mêmes : seule l'annulation (arrêt du processus) sort d'ici.
        """
        if not self._runners:
            return
        await asyncio.gather(*self._runners)

    # --- santé globale -----------------------------------------
    def is_healthy(self) -> bool:
        return all(job.is_healthy() for job in self._jobs.values())

    def control_healthy(self) -> bool:
        """Santé des seuls domaines de contrôle physique."""
        if os.getenv("PHYTO_FAKE_CONTROL_UNHEALTHY") == "1":
            return False
        gated = [job for job in self._jobs.values() if job.gates_watchdog]
        return bool(gated) and all(job.is_healthy() for job in gated)

    def unhealthy_control_names(self) -> list[str]:
        if os.getenv("PHYTO_FAKE_CONTROL_UNHEALTHY") == "1":
            return ["injection_de_test"]
        return [
            name for name, job in self._jobs.items()
            if job.gates_watchdog and not job.is_healthy()
        ]

    def health_domains(self) -> dict[str, dict]:
        domains: dict[str, list[SupervisedJob]] = {}
        for job in self._jobs.values():
            domains.setdefault(job.domain, []).append(job)
        return {
            domain: {
                "healthy": all(job.is_healthy() for job in jobs),
                "tasks": [job.name for job in jobs],
                "unhealthy": [job.name for job in jobs if not job.is_healthy()],
            }
            for domain, jobs in domains.items()
        }

    def unhealthy_names(self) -> list[str]:
        return [name for name, job in self._jobs.items() if not job.is_healthy()]

    def snapshot(self) -> dict:
        return {name: job.snapshot() for name, job in self._jobs.items()}

    def request_reload(self, name: str) -> bool:
        """Relance volontairement un travail sans réappliquer son état sûr."""
        job = self._jobs.get(name)
        if job is None or job.inner is None or job.inner.done():
            return False
        job.reload_requested = True
        job.inner.cancel()
        return True

    # --- interne -----------------------------------------------
    def _to_safe_state(self, job: SupervisedJob) -> None:
        """
        Remise à l'état sûr avant relance. Une exception ici ne doit surtout pas
        empêcher le redémarrage du travail : on journalise et on continue.
        """
        if job.safe_state is None:
            return
        try:
            job.safe_state()
            debug(f"Tâche « {job.name} » : état sûr repositionné", name=LOGGER_NAME)
        except Exception as exc:
            error(
                f"Tâche « {job.name} » : mise à l'état sûr impossible → "
                f"{exc.__class__.__name__} : {exc}",
                name=LOGGER_NAME,
            )

    async def _runner(self, job: SupervisedJob) -> None:
        _current_job.set(job)
        backoff = BACKOFF_INITIAL_SECONDS

        while True:
            manual_reload = False
            job.last_beat = monotonic()
            started = monotonic()
            # Le travail tourne dans une tâche fille : le veilleur de silence
            # peut l'annuler sans tuer le runner qui doit, lui, survivre à tout.
            inner = asyncio.get_event_loop().create_task(
                job.factory(), name=f"{job.name}#{job.restarts}"
            )
            job.inner = inner
            try:
                await inner
            except asyncio.CancelledError:
                if job.reload_requested:
                    job.reload_requested = False
                    manual_reload = True
                elif job.stall_requested:
                    # Annulation décidée par le veilleur : on enchaîne sur la
                    # remise à l'état sûr et la relance (le `finally` du contexte
                    # `energized()` a déjà coupé la sortie).
                    job.stall_requested = False
                else:
                    # Arrêt du processus : on propage, après avoir laissé la
                    # tâche fille dérouler ses `finally`.
                    if not inner.done():
                        inner.cancel()
                    raise
            except Exception as exc:
                job.last_error = f"{exc.__class__.__name__} : {exc}"
                tb = "".join(
                    traceback.format_exception(type(exc), exc, exc.__traceback__)
                ).strip()
                error(f"Tâche « {job.name} » interrompue :\n{tb}", name=LOGGER_NAME)
            else:
                # Ces boucles sont infinies : un retour propre est une anomalie.
                job.last_error = "terminaison sans exception"
                error(
                    f"Tâche « {job.name} » terminée alors qu'elle ne devrait "
                    "jamais s'arrêter",
                    name=LOGGER_NAME,
                )

            if manual_reload:
                # Pas d'état sûr ici, contrairement à une panne : le travail
                # était sain, il est relancé volontairement pour prendre une
                # nouvelle consigne. Repositionner l'état sûr couperait la
                # charge à chaque sauvegarde d'une section de configuration —
                # une lampe qui cligne à chaque clic. Ce qui *doit* être
                # relâché l'est déjà par les `finally` du travail lui-même :
                # le contexte `energized()` coupe sa sortie à l'annulation.
                job.reloads += 1
                job.last_error = None
                info(
                    f"Tâche « {job.name} » rechargée volontairement "
                    f"(rechargement n°{job.reloads})",
                    name=LOGGER_NAME,
                )
                continue

            # Panne, blocage ou terminaison anormale : l'état sûr est repositionné
            # avant toute relance, et avant le back-off — la charge ne reste pas
            # alimentée pendant que le superviseur attend.
            self._to_safe_state(job)
            job.restarts += 1
            job.restart_times.append(monotonic())
            job.recent_restart_count()

            if monotonic() - started >= BACKOFF_RESET_AFTER_SECONDS:
                backoff = BACKOFF_INITIAL_SECONDS

            warning(
                f"Tâche « {job.name} » relancée dans {backoff:.0f} s "
                f"(redémarrage n°{job.restarts})",
                name=LOGGER_NAME,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * BACKOFF_FACTOR, BACKOFF_MAX_SECONDS)

    async def _watch_stalls(self, period: float = 30.0) -> None:
        """
        Veille sur les travaux vivants mais muets. Une tâche bloquée sur une
        attente sans fin (lecture réseau sans délai de garde, verrou jamais
        relâché) ne lève rien : sans ce veilleur, elle serait invisible.

        Le remède est l'annulation, qui déclenche les `finally` des travaux
        (contexte `energized()` → sortie coupée) puis la relance normale par le
        runner, état sûr compris.
        """
        while True:
            await asyncio.sleep(period)
            try:
                self._cancel_stalled_jobs()
            except Exception as exc:
                # Le veilleur est le dernier filet : il ne meurt pas.
                error(
                    f"Veilleur de silence : {exc.__class__.__name__} : {exc}",
                    name=LOGGER_NAME,
                )

    def _cancel_stalled_jobs(self) -> None:
        for job in self._jobs.values():
            if job.is_alive() and job.is_stale():
                job.stalls += 1
                job.last_error = (
                    f"silence de {job.silence_seconds:.1f} s "
                    f"(> {job.max_silence:.0f} s)"
                )
                error(
                    f"Tâche « {job.name} » vivante mais muette depuis "
                    f"{job.silence_seconds:.1f} s → annulation et relance",
                    name=LOGGER_NAME,
                )
                # `last_beat` est réarmé ici, sinon le veilleur relancerait
                # en boucle pendant que l'annulation se propage.
                job.last_beat = monotonic()
                job.stall_requested = True
                if job.inner is not None and not job.inner.done():
                    job.inner.cancel()
