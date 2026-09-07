from __future__ import annotations

from collections import deque

from controllers.OperatorService import EVENT_QUEUE_LIMIT, OperatorService


class _Component:
    def __init__(self, state):
        self.state = state

    def get_state(self):
        return self.state


class _Motor:
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic

    def read_state(self):
        return dict(self.diagnostic)


def _service():
    service = object.__new__(OperatorService)
    service.components = {"heater": _Component(1)}
    service.motor = _Motor({"status": "ok", "speed": 3, "active_speeds": [3]})
    service._events = deque()
    service._queue_overflow = False
    service._session_id = "test-session"
    service._last_actual_states = {}
    return service


def test_transition_enregistre_la_relecture_gpio_ciblee():
    service = _service()

    service._on_output_transition(
        "heater", {"requested": "on", "applied": "on", "mode": "chauffage"},
    )

    event = service._events.pop()
    assert event["subject"] == "heater"
    assert isinstance(event["payload"].pop("monotonic_ts"), float)
    assert event["payload"] == {
        "requested": "on", "applied": "on", "mode": "chauffage",
        "actual": 1, "actual_status": "ok", "source": "transition",
        "session_id": "test-session",
    }


def test_transition_moteur_conserve_le_diagnostic_de_conflit():
    service = _service()
    service.motor.diagnostic = {
        "status": "conflict", "speed": None, "active_speeds": [2, 3],
    }

    service._on_output_transition("motor", {"requested": 3, "mode": "ventilation"})

    payload = service._events.pop()["payload"]
    assert payload["actual"] is None
    assert payload["actual_status"] == "conflict"
    assert payload["active_speeds"] == [2, 3]


def test_observation_minute_reutilise_le_snapshot_et_ne_duplique_pas_l_etat():
    service = _service()
    snapshot = {
        "heater": {
            "actual": "off", "actual_status": "ok",
            "requested": "off", "mode": "sécurité",
        },
    }

    service._observe_actual_transitions(snapshot, 100.0, 10.0)
    service._observe_actual_transitions(snapshot, 160.0, 70.0)
    snapshot["heater"]["actual"] = "on"
    service._observe_actual_transitions(snapshot, 220.0, 130.0)

    assert [event["payload"]["source"] for event in service._events] == [
        "baseline", "periodic_observation",
    ]
    assert [event["payload"]["actual"] for event in service._events] == [0, 1]


def test_debordement_ouvre_une_nouvelle_session_non_raccordee():
    service = _service()
    service._last_actual_states["heater"] = ("ok", 0)
    for index in range(EVENT_QUEUE_LIMIT):
        service._events.append({"index": index})
    previous_session = service._session_id

    service._on_output_transition("heater", {"requested": "on"})

    assert service._queue_overflow is True
    assert service._session_id != previous_session
    assert service._last_actual_states == {}
