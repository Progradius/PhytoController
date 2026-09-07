from __future__ import annotations

import asyncio

import pytest

from tests.helpers import wait_until
from utils import supervisor as supervisor_module
from utils.supervisor import TaskSupervisor, beat


async def stop_supervisor(supervisor: TaskSupervisor) -> None:
    tasks = [*supervisor._runners]
    if supervisor._watch_task is not None:
        tasks.append(supervisor._watch_task)
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def fast_backoff(monkeypatch, initial=0.002, maximum=0.01):
    monkeypatch.setattr(supervisor_module, "BACKOFF_INITIAL_SECONDS", initial)
    monkeypatch.setattr(supervisor_module, "BACKOFF_MAX_SECONDS", maximum)
    monkeypatch.setattr(supervisor_module, "BACKOFF_FACTOR", 2.0)


async def test_crash_applique_etat_sur_avant_relance(monkeypatch):
    fast_backoff(monkeypatch)
    events = []
    keep_running = asyncio.Event()
    starts = 0

    async def job():
        nonlocal starts
        starts += 1
        events.append(f"start-{starts}")
        if starts == 1:
            raise RuntimeError("panne simulée")
        beat()
        await keep_running.wait()

    supervisor = TaskSupervisor()
    registered = supervisor.register(
        "controle", job, safe_state=lambda: events.append("safe"),
        max_silence=None, domain="control", gates_watchdog=True,
    )
    supervisor.start()
    try:
        await wait_until(lambda: starts == 2)
        assert events[:3] == ["start-1", "safe", "start-2"]
        assert registered.restarts == 1
        assert registered.last_error == "RuntimeError : panne simulée"
        assert registered.is_healthy()
    finally:
        await stop_supervisor(supervisor)


async def test_retour_normal_est_une_anomalie_relançable(monkeypatch):
    fast_backoff(monkeypatch)
    safe_calls = 0
    starts = 0
    keep_running = asyncio.Event()

    async def job():
        nonlocal starts
        starts += 1
        if starts == 1:
            return
        await keep_running.wait()

    def safe():
        nonlocal safe_calls
        safe_calls += 1

    supervisor = TaskSupervisor()
    registered = supervisor.register(
        "controle", job, safe_state=safe, max_silence=None,
        gates_watchdog=True,
    )
    supervisor.start()
    try:
        await wait_until(lambda: starts == 2)
        assert safe_calls == 1
        assert registered.restarts == 1
        assert registered.last_error == "terminaison sans exception"
    finally:
        await stop_supervisor(supervisor)


async def test_backoff_croit_et_est_plafonne(monkeypatch):
    fast_backoff(monkeypatch, initial=0.01, maximum=0.02)
    loop = asyncio.get_running_loop()
    starts = []

    async def job():
        starts.append(loop.time())
        raise RuntimeError("boucle de crash")

    supervisor = TaskSupervisor()
    supervisor.register("controle", job, max_silence=None, gates_watchdog=True)
    supervisor.start()
    try:
        await wait_until(lambda: len(starts) >= 4, timeout=0.3)
        intervals = [starts[index + 1] - starts[index] for index in range(3)]
        assert intervals[0] >= 0.007
        assert intervals[1] >= 0.017
        assert intervals[2] >= 0.017
        assert intervals[1] < 0.08
        assert intervals[2] < 0.08
    finally:
        await stop_supervisor(supervisor)


async def test_tache_bloquee_est_annulee_mise_en_securite_et_relancee(monkeypatch):
    fast_backoff(monkeypatch)
    starts = 0
    safe_calls = 0

    async def job():
        nonlocal starts
        starts += 1
        await asyncio.Event().wait()

    def safe():
        nonlocal safe_calls
        safe_calls += 1

    supervisor = TaskSupervisor()
    registered = supervisor.register(
        "controle", job, safe_state=safe, max_silence=0.01,
        gates_watchdog=True,
    )
    supervisor.start()
    try:
        await wait_until(lambda: starts == 1 and registered.inner is not None)
        registered.last_beat -= 1.0
        supervisor._cancel_stalled_jobs()
        await wait_until(lambda: starts == 2)
        assert registered.stalls == 1
        assert registered.restarts == 1
        assert safe_calls == 1
    finally:
        await stop_supervisor(supervisor)


async def test_reload_volontaire_ne_fait_pas_clignoter_etat_sur(monkeypatch):
    fast_backoff(monkeypatch)
    starts = 0
    safe_calls = 0

    async def job():
        nonlocal starts
        starts += 1
        beat()
        await asyncio.Event().wait()

    def safe():
        nonlocal safe_calls
        safe_calls += 1

    supervisor = TaskSupervisor()
    registered = supervisor.register(
        "controle", job, safe_state=safe, max_silence=None,
        gates_watchdog=True,
    )
    supervisor.start()
    try:
        await wait_until(lambda: starts == 1 and registered.inner is not None)
        registered.last_error = "ancienne erreur"
        assert supervisor.request_reload("controle") is True
        await wait_until(lambda: starts == 2)
        assert registered.reloads == 1
        assert registered.restarts == 0
        assert registered.last_error is None
        assert safe_calls == 0
        assert supervisor.request_reload("absent") is False
    finally:
        await stop_supervisor(supervisor)


def test_start_refuse_superviseur_sans_controle_watchdog():
    supervisor = TaskSupervisor()
    supervisor.register("auxiliaire", lambda: asyncio.sleep(1), gates_watchdog=False)
    with pytest.raises(RuntimeError, match="watchdog"):
        supervisor.start()
