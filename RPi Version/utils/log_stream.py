# utils/log_stream.py
# Author : Progradius
# License : AGPL-3.0
"""
Diffusion des logs du **processus courant** vers la page /console (SSE).

Remplace l'ancien PTY qui lançait un second `main.py` (deux processus sur les
mêmes GPIO, double rotation du même fichier de log).

    from utils.log_stream import console_stream
    console_stream.install()            # une fois, au démarrage
    q = console_stream.subscribe()      # côté route SSE
    ...
    console_stream.unsubscribe(q)
"""

import asyncio
import logging
import re
import threading
from collections import deque

from utils.pretty_console import ROOT_LOGGER_NAME

HISTORY_SIZE = 1000
QUEUE_SIZE = 500

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class ConsoleStream(logging.Handler):
    """Handler mémoire : garde les dernières lignes et les pousse aux clients SSE."""

    def __init__(self, history_size: int = HISTORY_SIZE):
        super().__init__()
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s", "%H:%M:%S"
        ))
        self.history: deque[str] = deque(maxlen=history_size)
        self._queues: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()
        self._installed = False

    # ── installation ──────────────────────────────────────────
    def install(self) -> None:
        """Branche le handler sur le logger « phyto » (idempotent)."""
        if self._installed:
            return
        logging.getLogger(ROOT_LOGGER_NAME).addHandler(self)
        self._installed = True

    # ── abonnements ───────────────────────────────────────────
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        loop = asyncio.get_event_loop()
        with self._lock:
            self._queues.append((loop, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Retrait idempotent (la route SSE peut passer plusieurs fois ici)."""
        with self._lock:
            self._queues = [(l, q) for (l, q) in self._queues if q is not queue]

    # ── émission ──────────────────────────────────────────────
    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = _ANSI_RE.sub("", self.format(record))
        except Exception:  # jamais faire tomber l'appelant pour un log
            return

        self.history.append(line)

        with self._lock:
            targets = list(self._queues)

        for loop, queue in targets:
            try:
                if loop.is_closed():
                    continue
                # emit() peut venir d'un thread (watchdog) → on repasse par la boucle
                loop.call_soon_threadsafe(_offer, queue, line)
            except RuntimeError:
                continue


def _offer(queue: asyncio.Queue, line: str) -> None:
    """Dépose sans jamais bloquer : si le client est trop lent, on perd la ligne."""
    try:
        queue.put_nowait(line)
    except asyncio.QueueFull:
        pass


console_stream = ConsoleStream()
