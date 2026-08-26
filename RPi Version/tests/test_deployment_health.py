from __future__ import annotations

import pytest

from utils.deployment_health import validation_error


VERSION = "a" * 40


def healthy_payloads():
    return (
        {"live": True, "version": VERSION},
        {"ready": True, "unhealthy": []},
        {
            "version": VERSION,
            "health": {"control_healthy": True},
            "alarms": {"critical_count": 0},
        },
    )


def test_sante_complete_acceptee():
    assert validation_error(VERSION, *healthy_payloads()) is None


@pytest.mark.parametrize(
    ("payload_index", "path", "value", "message"),
    [
        (0, ("live",), False, "live=true"),
        (1, ("ready",), False, "ready=true"),
        (2, ("health", "control_healthy"), False, "control_healthy"),
        (0, ("version",), "b" * 40, "version active"),
        (2, ("version",), "b" * 40, "version d'état"),
        (2, ("alarms", "critical_count"), 1, "alarme(s) critique(s)"),
    ],
)
def test_chaque_defaut_est_refuse(payload_index, path, value, message):
    payloads = healthy_payloads()
    target = payloads[payload_index]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    assert message in validation_error(VERSION, *payloads)


@pytest.mark.parametrize("value", [None, False, "0", 0.0])
def test_compteur_critique_doit_etre_un_entier_nul(value):
    payloads = healthy_payloads()
    payloads[2]["alarms"]["critical_count"] = value
    assert "alarme(s) critique(s)" in validation_error(VERSION, *payloads)
