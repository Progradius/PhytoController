from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from controllers.sensor_catalog import SENSOR_CATALOG
from param.config_store import ConfigStore
from param.equipment_metadata import default_catalog
from network.web import server as server_module


CSRF_TOKEN = "T" * 43


class FakeStats:
    KEYS = ("BME280T", "BME280H", "DS18B#3")

    def __init__(self):
        self.cleared = []
        self.data = {
            key: {"min": None, "min_date": None, "max": None, "max_date": None}
            for key in self.KEYS
        }

    def get_all(self):
        return {key: dict(value) for key, value in self.data.items()}

    def clear_key(self, key):
        self.cleared.append(key)


class FakeSensors:
    def __init__(self, config):
        self.config = config
        self.stats = FakeStats()
        self.reconfigured = 0
        self.quality_resets = []

    def snapshot(self):
        return {
            definition.key: {
                "key": definition.key,
                "label": definition.label,
                "unit": definition.unit,
                "decimals": definition.decimals,
                "enabled": bool(getattr(self.config.sensors, definition.enabled_field)),
                "family": definition.family,
                "hardware_id": None,
                "status": "normal",
                "acquisition_status": "ok",
                "reason_codes": [],
                "value": 21.5,
                "observed_value": 21.5,
                "raw_value": 21.5,
                "last_trusted_value": 21.5,
                "control_usable": True,
                "would_block_control": False,
                "control_disposition": "trusted",
                "enforcement_mode": self.config.sensor_quality.mode,
                "last_attempt_at": "2026-08-26T10:00:00Z",
                "last_success_at": "2026-08-26T10:00:00Z",
                "last_trusted_at": "2026-08-26T10:00:00Z",
                "attempt_age_s": 1.0,
                "age_s": 1.0,
                "unchanged_for_s": 0.0,
                "freshness_threshold_s": definition.freshness_seconds,
                "plausible_range": {
                    "min": definition.plausible_min,
                    "max": definition.plausible_max,
                },
                "calibration": {
                    "offset": 0.0, "calibrated_at": None,
                    "valid_days": None, "overdue": False,
                },
                "failures": {
                    "consecutive": 0, "since_calibration": 0,
                    "incoherences_since_calibration": 0, "last_at": None,
                },
                "redundancy": {
                    "group": None, "status": "not_configured", "delta": None,
                },
            }
            for definition in SENSOR_CATALOG
        }

    def cached_value(self, _key, max_age=30.0):
        return 21.5

    async def reconfigure(self, config):
        self.reconfigured += 1
        self.config = config

    def discovered_ds18_ids(self):
        return ["28-000000000001", "28-000000000002"]

    def reset_quality(self, key):
        self.quality_resets.append(key)


class FakeStatus:
    def get_component_state(self):
        return "off"

    def get_motor_speed(self):
        return 0

    def get_dailytimer_current_start_time(self):
        return "19:00"

    def get_dailytimer_current_stop_time(self):
        return "07:00"


class FakeSupervisor:
    def __init__(self):
        self.reloads = []

    def is_healthy(self):
        return True

    def control_healthy(self):
        return True

    def unhealthy_names(self):
        return []

    def snapshot(self):
        return {"http_server": {"alive": True, "healthy": True}}

    def health_domains(self):
        return {"http": {"healthy": True, "tasks": ["http_server"], "unhealthy": []}}

    def request_reload(self, name):
        self.reloads.append(name)
        return True


@dataclass
class FakeEquipmentStore:
    current: dict

    def payload(self):
        return {key: value.model_dump() for key, value in self.current.items()}


@pytest.fixture
async def web_context(config_path, monkeypatch):
    store = ConfigStore(config_path)
    sensors = FakeSensors(store.current)
    supervisor = FakeSupervisor()
    equipment = FakeEquipmentStore(default_catalog())
    monkeypatch.setattr(server_module, "shared_config", lambda: store)
    monkeypatch.setattr(server_module, "load_or_create_token", lambda: CSRF_TOKEN)
    monkeypatch.setattr(
        server_module.influx_handler, "reload_sensor_handler", lambda *_args, **_kwargs: None
    )
    server = server_module.Server(
        FakeStatus(), sensors, store.current,
        supervisor=supervisor, equipment_store=equipment,
    )
    client = TestClient(TestServer(server.create_app()))
    await client.start_server()
    try:
        yield client, server, store, sensors, supervisor
    finally:
        await client.close()


async def test_pages_dynamiques_et_secrets_absents(web_context):
    client, _server, store, _sensors, _supervisor = web_context
    for path in ("/", "/conf", "/api/v1/state", "/health/live", "/health/ready"):
        response = await client.get(path)
        assert response.status == 200
        assert response.headers["Cache-Control"] == "no-store"

    response = await client.get("/conf")
    body = await response.text()
    assert store.current.network.wifi_password not in body
    assert store.current.network.influx_db_password not in body
    assert "Content-Security-Policy" in response.headers


async def test_sondes_publient_la_version_chargee(web_context):
    client, *_ = web_context
    live = await (await client.get("/health/live")).json()
    state = await (await client.get("/api/v1/state")).json()

    assert live == {"live": True, "version": server_module.DEPLOYED_VERSION}
    assert state["version"] == server_module.DEPLOYED_VERSION
    assert state["schema_version"] == 2
    assert state["health"]["control_healthy"] is True
    assert state["alarms"]["critical_count"] == 0
    temperature = next(item for item in state["sensors"] if item["key"] == "BME280T")
    assert temperature["status"] == "normal"
    assert temperature["control_usable"] is True
    assert temperature["calibration"]["offset"] == 0.0


async def test_armement_qualite_exige_confirmation_et_recharge_le_climat(web_context):
    client, _server, store, _sensors, supervisor = web_context
    refused = await client.post(
        "/conf/sensor-quality",
        data={"csrf_token": CSRF_TOKEN, "sensor_key": "__mode__", "mode": "enforce"},
    )
    assert refused.status == 422
    assert store.current.sensor_quality.mode == "observe"
    assert supervisor.reloads == []

    accepted = await client.post(
        "/conf/sensor-quality",
        data={
            "csrf_token": CSRF_TOKEN, "sensor_key": "__mode__",
            "mode": "enforce", "confirm_enforce": "ARMER",
        },
        allow_redirects=False,
    )
    assert accepted.status == 303
    assert store.current.sensor_quality.mode == "enforce"
    assert supervisor.reloads == ["climate_control"]


async def test_calibration_sauvegardee_rearme_qualite_et_statistiques(web_context):
    client, _server, store, sensors, supervisor = web_context
    response = await client.post(
        "/conf/sensor-quality",
        data={
            "csrf_token": CSRF_TOKEN,
            "sensor_key": "BME280T",
            "offset": "0.4",
            "calibrated_at": "2026-08-27",
            "calibration_valid_days": "365",
            "freshness_seconds": "20",
            "plausible_min": "-20",
            "plausible_max": "60",
            "freeze_epsilon": "0.02",
            "freeze_after_seconds": "1800",
            "freeze_min_samples": "10",
        },
        allow_redirects=False,
    )
    assert response.status == 303
    assert store.current.sensor_quality.profiles["BME280T"].offset == 0.4
    assert sensors.quality_resets == ["BME280T"]
    assert sensors.stats.cleared == ["BME280T"]
    assert supervisor.reloads == ["climate_control"]


async def test_reset_diagnostic_qualite_est_protege_par_csrf(web_context):
    client, _server, _store, sensors, _supervisor = web_context
    refused = await client.post(
        "/actions/sensors/reset-quality", data={"key": "BME280T"}
    )
    assert refused.status == 403
    accepted = await client.post(
        "/actions/sensors/reset-quality",
        data={"csrf_token": CSRF_TOKEN, "key": "BME280T"},
        allow_redirects=False,
    )
    assert accepted.status == 303
    assert sensors.quality_resets == ["BME280T"]


@pytest.mark.parametrize("host", ["evil.example.com", "public.example.net", "mal formé"])
async def test_host_etranger_est_refuse(web_context, host):
    client, *_ = web_context
    response = await client.get("/", headers={"Host": host})
    assert response.status == 421


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "192.168.1.20", "169.254.1.2"])
async def test_host_local_est_accepte(web_context, host):
    client, *_ = web_context
    response = await client.get("/health/live", headers={"Host": host})
    assert response.status == 200


async def test_host_explicitement_autorise(web_context, monkeypatch):
    client, server, *_ = web_context
    monkeypatch.setenv("PHYTO_ALLOWED_HOSTS", "serre.test")
    server._allowed_names = server._build_allowed_names()
    response = await client.get("/health/live", headers={"Host": "serre.test"})
    assert response.status == 200


async def test_csrf_absent_invalide_et_origine_tierce(web_context):
    client, *_ = web_context
    response = await client.post("/conf/life", data={"stage": "test"})
    assert response.status == 403

    response = await client.post(
        "/conf/life", data={"csrf_token": "mauvais", "stage": "test"}
    )
    assert response.status == 403

    response = await client.post(
        "/conf/life",
        data={"csrf_token": CSRF_TOKEN, "stage": "test"},
        headers={"Origin": "http://evil.example.com"},
    )
    assert response.status == 403


async def test_jeton_entete_et_origine_locale_sont_acceptes(web_context):
    client, *_ = web_context
    origin = f"http://{client.server.host}:{client.server.port}"
    response = await client.post(
        "/conf/life", data={"stage": "test-entete"},
        headers={"X-CSRF-Token": CSRF_TOKEN, "Origin": origin},
        allow_redirects=False,
    )
    assert response.status == 303


async def test_formulaire_invalide_ne_change_ni_disque_ni_memoire(web_context):
    client, _server, store, _sensors, supervisor = web_context
    before = store.path.read_bytes()
    shared = store.current
    old_min = shared.temperature.target_temp_min_day

    response = await client.post(
        "/conf/temperature",
        data={
            "csrf_token": CSRF_TOKEN,
            "target_temp_min_day": "30",
            "target_temp_max_day": "10",
        },
    )
    assert response.status == 422
    assert store.path.read_bytes() == before
    assert store.current is shared
    assert shared.temperature.target_temp_min_day == old_min
    assert supervisor.reloads == []


async def test_champ_inattendu_et_duplique_sont_refuses(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/life", data={"csrf_token": CSRF_TOKEN, "inconnu": "1"}
    )
    assert response.status == 422

    form = FormData()
    form.add_field("csrf_token", CSRF_TOKEN)
    form.add_field("stage", "un")
    form.add_field("stage", "deux")
    response = await client.post("/conf/life", data=form)
    assert response.status == 422


async def test_formulaire_valide_sauvegarde_en_place_et_reload_climat(web_context):
    client, _server, store, _sensors, supervisor = web_context
    shared = store.current
    response = await client.post(
        "/conf/temperature",
        data={"csrf_token": CSRF_TOKEN, "hysteresis_offset": "2.5"},
        allow_redirects=False,
    )
    assert response.status == 303
    assert store.current is shared
    assert shared.temperature.hysteresis_offset == 2.5
    assert ConfigStore(store.path).current.temperature.hysteresis_offset == 2.5
    assert supervisor.reloads == ["climate_control"]


async def test_secret_vide_est_conserve(web_context):
    client, _server, store, *_ = web_context
    old_user = store.current.network.influx_db_user
    old_password = store.current.network.influx_db_password
    response = await client.post(
        "/conf/influx",
        data={
            "csrf_token": CSRF_TOKEN,
            "influx_db_user": "",
            "influx_db_password": "",
        },
        allow_redirects=False,
    )
    assert response.status == 303
    assert store.current.network.influx_db_user == old_user
    assert store.current.network.influx_db_password == old_password


@pytest.mark.parametrize("value", ["25:00", "heure", "07"])
async def test_horaire_invalide_est_refuse(web_context, value):
    client, *_ = web_context
    response = await client.post(
        "/conf/daily-timer-1",
        data={"csrf_token": CSRF_TOKEN, "start_time": value},
    )
    assert response.status == 422


async def test_horaire_avec_secondes_est_accepte(web_context):
    client, _server, store, *_ = web_context
    response = await client.post(
        "/conf/daily-timer-1",
        data={"csrf_token": CSRF_TOKEN, "start_time": "07:30:59"},
        allow_redirects=False,
    )
    assert response.status == 303
    assert (store.current.daily_timer1.start_hour, store.current.daily_timer1.start_minute) == (7, 30)


async def test_corps_trop_volumineux_est_refuse(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/life",
        data=b"stage=" + b"x" * (server_module.MAX_BODY_SIZE + 1),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRF-Token": CSRF_TOKEN,
        },
    )
    assert response.status == 413


@pytest.mark.parametrize(
    "path",
    [
        "/actions/stats/reset",
        "/actions/sensors/reset-quality",
        "/actions/system/reboot",
        "/actions/system/poweroff",
    ],
)
async def test_actions_sont_post_only(web_context, path):
    client, server, *_ = web_context
    server._system_command = AsyncMock()
    response = await client.get(path)
    assert response.status == 405
    server._system_command.assert_not_awaited()


async def test_action_post_sans_csrf_ne_lance_aucune_commande(web_context):
    client, server, *_ = web_context
    server._system_command = AsyncMock()
    response = await client.post("/actions/system/reboot")
    assert response.status == 403
    server._system_command.assert_not_awaited()


async def test_erreurs_html_texte_redirection_et_allow(web_context):
    client, *_ = web_context
    html = await client.get("/inexistante", headers={"Accept": "text/html"})
    assert html.status == 404
    assert "<html" in (await html.text())

    text = await client.get("/inexistante", headers={"Accept": "application/json"})
    assert text.status == 404
    assert "<html" not in (await text.text())

    redirect = await client.get("/monitor", allow_redirects=False)
    assert redirect.status == 303

    method = await client.get("/actions/system/reboot", headers={"Accept": "text/html"})
    assert method.status == 405
    assert "Allow" in method.headers
