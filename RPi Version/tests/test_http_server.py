from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest
from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from controllers.sensor_catalog import SENSOR_CATALOG
from param.config_store import ConfigStore
from param.equipment_metadata import EQUIPMENT_IDS, default_catalog
from network.web import pages as pages_module
from network.web import server as server_module
from utils import overrides as overrides_module
from utils.overrides import OverrideStore
from utils.state_store import StateStore


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
                "freeze_epsilon": definition.freeze_epsilon,
                "freeze_after_seconds": definition.freeze_after_seconds,
                "freeze_min_samples": definition.freeze_min_samples,
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

    def save(self, candidate):
        self.current = dict(candidate)


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


async def test_graphiques_conservent_une_hauteur_logique_immuable(web_context):
    client, *_ = web_context
    page = await (await client.get("/")).text()
    script = await (await client.get("/static/js/history.js")).text()

    assert page.count('data-chart-height="240"') == 2
    assert page.count('data-chart-height="220"') == 1
    assert "canvas.dataset.chartHeight" in script
    assert 'canvas.getAttribute("height")' not in script


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
    assert temperature["freeze_epsilon"] == 0.0
    assert temperature["freeze_after_seconds"] == 1800.0
    assert temperature["freeze_min_samples"] == 30
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


async def test_saisie_refusee_est_reaffichee_sans_secret(web_context):
    """Un refus ne doit pas obliger à ressaisir la section (jalon 3, 3a)."""
    client, *_ = web_context
    response = await client.post(
        "/conf/influx",
        data={
            "csrf_token": CSRF_TOKEN,
            "host_machine_state": "online",
            "host_machine_address": "10.0.0.9",
            "influx_db_port": "pas-un-port",
            "influx_db_name": "serre",
            "influx_db_user": "operateur",
            "influx_db_password": "secret-refuse",
        },
    )
    assert response.status == 422
    body = await response.text()
    # La saisie ordinaire revient…
    assert 'value="10.0.0.9"' in body
    assert 'value="serre"' in body
    assert 'value="pas-un-port"' in body
    # …mais jamais un secret, refusé ou non.
    assert "secret-refuse" not in body
    assert "operateur" not in body


async def test_contrainte_croisee_est_rattachee_aux_deux_champs(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/temperature",
        data={
            "csrf_token": CSRF_TOKEN,
            "target_temp_min_day": "30",
            "target_temp_max_day": "10",
            "vent_step": "3.5",
        },
    )
    assert response.status == 422
    body = await response.text()
    assert 'aria-describedby="target_temp_min_day-error"' in body
    assert 'aria-describedby="target_temp_max_day-error"' in body
    assert "Le minimum de jour doit rester sous le maximum de jour." in body
    # Le reste de la section conserve sa saisie.
    assert 'value="3.5"' in body


async def test_message_pydantic_est_humanise_et_localise(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/daily-timer-1",
        data={"csrf_token": CSRF_TOKEN, "start_time": "25:00"},
    )
    assert response.status == 422
    body = await response.text()
    assert 'id="daily-1-start-error"' in body
    assert "Saisir une valeur inférieure ou égale à 23." in body
    assert "Input should be less than or equal to" not in body


async def test_valeur_non_numerique_reste_visible_et_expliquee(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/temperature",
        data={"csrf_token": CSRF_TOKEN, "hysteresis_offset": "abc"},
    )
    assert response.status == 422
    body = await response.text()
    assert 'value="abc"' in body
    assert "Saisir un nombre (séparateur décimal : le point)." in body


async def test_champ_inattendu_ne_perd_pas_la_saisie_valide(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/life",
        data={"csrf_token": CSRF_TOKEN, "stage": "floraison", "inconnu": "1"},
    )
    assert response.status == 422
    body = await response.text()
    assert 'value="floraison"' in body


async def test_registre_de_champs_couvre_chaque_section(web_context):
    """`SECTION_FIELDS` reste l'unique source des cibles et des libellés."""
    for section, fields in server_module.SECTION_FIELDS.items():
        for name, spec in fields.items():
            assert spec.label, f"{section}.{name} sans libellé"
            assert isinstance(spec.target, tuple) or spec.target in (
                server_module.TIME_TARGETS
                | {"equipment_metadata", "simple_intensity", "simple_season"}
            )
    index = server_module.PAYLOAD_INDEX
    assert index["daily-timer-2"]["DailyTimer2_Settings.start_hour"] == "start_time"
    assert index["day-night"]["Day_Night_Settings.stop_minute"] == "stop_time"
    assert index["motor"]["Motor_Settings.max_speed"] == "max_speed"


async def test_previsualisation_montre_le_seuil_de_ventilation_effectif(web_context):
    """Le seuil relevé par la zone morte doit être visible avant la sauvegarde."""
    client, _server, store, *_ = web_context
    before = store.path.read_bytes()
    response = await client.post(
        "/api/v1/config/preview",
        json={
            "section": "temperature",
            "fields": {"target_temp_max_day": "21", "hysteresis_offset": "2", "vent_deadband": "1"},
        },
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["valid"] is True
    assert payload["climate_relevant"] is True
    day = payload["climate"]["phases"]["day"]
    # 20 (min) + 2 (hystérésis) + 1 (zone morte) = 23 : au-dessus du maximum saisi.
    assert day["vent_threshold"] == 23.0
    assert day["vent_threshold_raised"] is True
    assert day["temp_max"] == 21.0
    assert [rung["starts_at"] for rung in day["vent_ladder"]] == [23.0, 24.0, 25.0, 26.0]
    # Aucune écriture.
    assert store.path.read_bytes() == before


async def test_previsualisation_liste_les_ecarts_et_refuse_sans_ecrire(web_context):
    client, server, store, *_ = web_context
    before = store.path.read_bytes()
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "temperature", "fields": {"hysteresis_offset": "3.5"}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    payload = await response.json()
    assert payload["changes"] == [
        {"field": "hysteresis_offset", "label": "Hystérésis chauffage",
         "secret": False, "from": 1.0, "to": 3.5}
    ]

    server._preview_last_at = 0.0
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "temperature", "fields": {"target_temp_min_day": "30",
                                                   "target_temp_max_day": "10"}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    payload = await response.json()
    assert payload["valid"] is False
    assert payload["climate"] is None
    assert "target_temp_min_day" in payload["errors"]
    assert store.path.read_bytes() == before


async def test_previsualisation_ne_renvoie_jamais_un_secret(web_context):
    client, *_ = web_context
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "wifi", "fields": {"wifi_ssid": "serre", "wifi_password": "motdepasse"}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status == 200
    body = await response.text()
    assert "motdepasse" not in body
    payload = await response.json()
    assert payload["climate_relevant"] is False
    secrets = [item for item in payload["changes"] if item["secret"]]
    assert secrets and all("to" not in item for item in secrets)


async def test_previsualisation_est_protegee_et_bornee(web_context):
    client, server, *_ = web_context
    # Sans jeton : refusée comme toute mutation.
    response = await client.post(
        "/api/v1/config/preview", json={"section": "logs", "fields": {}}
    )
    assert response.status == 403

    # Section non projetable sur un candidat complet.
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "equipment", "fields": {}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status == 400

    # Intervalle minimum : la deuxième requête immédiate est repoussée.
    server._preview_last_at = 0.0
    first = await client.post(
        "/api/v1/config/preview", json={"section": "logs", "fields": {}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert first.status == 200
    second = await client.post(
        "/api/v1/config/preview", json={"section": "logs", "fields": {}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert second.status == 429


SIMPLE_FORM = {
    "csrf_token": CSRF_TOKEN,
    "source": "dailytimer1",
    "start_time": "08:00",
    "stop_time": "20:00",
    "target_temp_min_day": "20",
    "target_temp_max_day": "24",
    "target_temp_min_night": "18",
    "target_temp_max_night": "22",
    "humidity_max": "65",
    "intensity": "normale",
    "season": "hiver",
    "heater_enabled": "enabled",
    "daily1_enabled": "enabled",
    "daily1_start": "19:00",
    "daily1_stop": "07:00",
    "daily2_enabled": "disabled",
    "daily2_start": "10:00",
    "daily2_stop": "12:00",
}


async def test_mode_simple_ecrit_les_deux_minuteries_et_le_profil(web_context):
    client, _server, store, _sensors, supervisor = web_context
    response = await client.post("/conf/simple", data=SIMPLE_FORM, allow_redirects=False)
    assert response.status == 303
    config = store.current
    assert (config.daily_timer1.start_hour, config.daily_timer1.stop_hour) == (19, 7)
    assert (config.daily_timer2.start_hour, config.daily_timer2.stop_hour) == (10, 12)
    assert config.daily_timer2.enabled is False
    # Intensité « normale » → vitesse maximale et renouvellement à 3.
    assert (config.motor.max_speed, config.motor.winter_refresh_speed) == (3, 3)
    assert config.motor.motor_mode == "winter"
    # Profil de conduite imposé, aligné sur la configuration déployée.
    assert config.temperature.hysteresis_offset == 2.0
    assert config.temperature.min_dwell_seconds == 120
    assert config.motor.winter_refresh_minutes_per_hour == 5
    assert config.motor.winter_humidity_minutes_per_hour == 15
    assert "climate_control" in supervisor.reloads
    assert "daily_timer_2" in supervisor.reloads


async def test_mode_simple_exige_un_choix_explicite_de_saison(web_context):
    """Un moteur en manuel ne doit pas en sortir par le seul fait d'enregistrer."""
    client, _server, store, *_ = web_context
    before = store.path.read_bytes()
    incomplete = {key: value for key, value in SIMPLE_FORM.items() if key != "season"}
    response = await client.post("/conf/simple", data=incomplete)
    assert response.status == 422
    body = await response.text()
    assert "Choisir explicitement Été, Hiver, ou Manuel" in body
    assert store.path.read_bytes() == before


async def test_mode_simple_refuse_de_faire_entrer_en_manuel(web_context):
    client, _server, store, *_ = web_context
    payload = dict(SIMPLE_FORM, season="manuel")
    response = await client.post("/conf/simple", data=payload)
    assert response.status == 422
    assert "Le pilotage manuel se règle dans le mode avancé." in await response.text()
    assert store.current.motor.motor_mode != "manual"


async def test_previsualisation_simple_annonce_les_reglages_fins(web_context):
    client, *_ = web_context
    fields = {key: value for key, value in SIMPLE_FORM.items() if key != "csrf_token"}
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "simple", "fields": fields},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status == 200
    payload = await response.json()
    assert payload["valid"] is True
    labels = {item["label"]: item for item in payload["profile_changes"]}
    # La configuration de test porte une hystérésis de 1 °C : le profil la remonte.
    assert labels["Hystérésis chauffage"]["from"] == 1.0
    assert labels["Hystérésis chauffage"]["to"] == 2.0
    assert payload["climate_relevant"] is True
    assert "climate_control" in payload["apply_note"]


async def test_compte_rendu_est_opaque_et_a_usage_unique(web_context):
    client, *_ = web_context
    response = await client.post(
        "/conf/logs",
        data={"csrf_token": CSRF_TOKEN, "level": "WARNING", "retention_days": "21"},
        allow_redirects=False,
    )
    assert response.status == 303
    location = response.headers["Location"]
    assert location.startswith("/conf?flash=")
    # Le jeton ne porte aucune donnée : ni section lisible, ni valeur.
    token = location.split("flash=", 1)[1].split("#", 1)[0]
    assert "logs" not in token and "WARNING" not in token

    page = await client.get(f"/conf?flash={token}")
    body = await page.text()
    assert "Niveau" in body and "Rétention" in body
    assert "Appliqué à chaud : niveau et rétention de journalisation." in body

    # Usage unique : un rechargement ne rejoue pas le compte rendu.
    again = await client.get(f"/conf?flash={token}")
    assert "Appliqué à chaud : niveau et rétention" not in await again.text()


async def test_compte_rendu_equipement_ne_liste_que_les_ecarts(web_context):
    client, _server, _store, *_ = web_context
    catalog = default_catalog()
    data = {"csrf_token": CSRF_TOKEN}
    for equipment_id, item in catalog.items():
        data[f"{equipment_id}__display_name"] = (
            "Lampe de floraison" if equipment_id == "daily_1" else item.display_name
        )
        data[f"{equipment_id}__usage_type"] = item.usage_type
        data[f"{equipment_id}__zone"] = item.zone
        data[f"{equipment_id}__icon"] = item.icon
        data[f"{equipment_id}__wiring_note"] = item.wiring_note
        data[f"{equipment_id}__dashboard_visible"] = "true" if item.dashboard_visible else "false"
        data[f"{equipment_id}__out_of_service"] = "true" if item.out_of_service else "false"

    response = await client.post("/conf/equipment", data=data, allow_redirects=False)
    assert response.status == 303
    token = response.headers["Location"].split("flash=", 1)[1].split("#", 1)[0]
    body = await (await client.get(f"/conf?flash={token}")).text()
    assert "Champs modifiés : daily_1 · Nom affiché." in body


async def test_previsualisation_publie_les_deux_hysteresis(web_context):
    """Hystérésis chauffage **et** relâchement de palier doivent être lisibles."""
    client, *_ = web_context
    response = await client.post(
        "/api/v1/config/preview",
        json={"section": "temperature", "fields": {"hysteresis_offset": "2", "vent_release": "0.5"}},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    day = (await response.json())["climate"]["phases"]["day"]
    # Bande morte du chauffage : 20 °C → 22 °C.
    assert day["heater_hysteresis"] == 2.0
    assert (day["heater_on_at_or_below"], day["heater_off_above"]) == (20.0, 22.0)
    # Hystérésis des paliers : un cran engagé à 24 °C ne se relâche que sous 23,5 °C.
    assert day["vent_release"] == 0.5
    first = day["vent_ladder"][0]
    assert (first["starts_at"], first["releases_below"]) == (24.0, 23.5)


# ─────────────────────────────────────────────────────────────
#  Forçages « arrêt » (jalon 4)
# ─────────────────────────────────────────────────────────────
@pytest.fixture
def override_store(tmp_path, monkeypatch):
    """Magasin isolé : aucun test n'écrit dans le `runtime_state.json` vivant."""
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: _FakeReliability("synchronized"))
    magasin = OverrideStore(StateStore(tmp_path / "runtime_state.json"))
    monkeypatch.setattr(server_module, "shared_overrides", lambda: magasin)
    monkeypatch.setattr(pages_module, "shared_overrides", lambda: magasin)
    return magasin


class _FakeReliability:
    def __init__(self, state):
        self.state = state


async def test_forcage_cree_coupe_et_relance_la_minuterie(web_context, override_store):
    client, _server, _store, _sensors, supervisor = web_context
    response = await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "daily_1",
              "duration_minutes": "30", "reason": "changement de lampe"},
        allow_redirects=False,
    )
    assert response.status == 303
    assert override_store.is_forced_off("daily_1") is True
    # Sans relance, un cyclique en attente longue ignorerait l'ordre.
    assert supervisor.reloads == ["daily_timer_1"]

    state = await (await client.get("/api/v1/state")).json()
    assert state["overrides"]["active_count"] == 1
    assert state["overrides"]["items"][0]["target"] == "daily_1"
    assert state["overrides"]["items"][0]["reason"] == "changement de lampe"


async def test_forcage_climat_ne_relance_pas_la_regulation(web_context, override_store):
    client, _server, _store, _sensors, supervisor = web_context
    await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "heater", "duration_minutes": "30"},
        allow_redirects=False,
    )
    # Relancer le climat lui ferait relire ses budgets d'hiver pour rien.
    assert supervisor.reloads == []
    assert override_store.is_forced_off("heater") is True


async def test_arret_general_applique_le_plafond_de_chaque_cible(web_context, override_store):
    client, *_ = web_context
    await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "all", "duration_minutes": "1440"},
        allow_redirects=False,
    )
    actifs = override_store.active()
    assert set(actifs) == set(EQUIPMENT_IDS)
    assert actifs["heater"].remaining_seconds(time.time(), time.monotonic()) <= 4 * 3600
    assert actifs["motor"].remaining_seconds(time.time(), time.monotonic()) <= 4 * 3600
    assert actifs["daily_1"].remaining_seconds(time.time(), time.monotonic()) > 4 * 3600


async def test_annulation_groupee_leve_tout(web_context, override_store):
    client, *_ = web_context
    await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "all", "duration_minutes": "10"},
        allow_redirects=False,
    )
    response = await client.post(
        "/actions/overrides/cancel",
        data={"csrf_token": CSRF_TOKEN, "target": "all"},
        allow_redirects=False,
    )
    assert response.status == 303
    assert override_store.active() == {}


async def test_cible_libre_ou_broche_refusee(web_context, override_store):
    client, *_ = web_context
    for cible in ("gpio_17", "17", "", "../heater"):
        response = await client.post(
            "/actions/overrides/create",
            data={"csrf_token": CSRF_TOKEN, "target": cible, "duration_minutes": "10"},
        )
        assert response.status == 400
    assert override_store.active() == {}


async def test_duree_hors_bornes_refusee_en_http(web_context, override_store):
    client, *_ = web_context
    response = await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "heater", "duration_minutes": "0"},
    )
    assert response.status == 400
    assert override_store.active() == {}


async def test_heure_non_fiable_refuse_la_creation(web_context, override_store, monkeypatch):
    client, *_ = web_context
    monkeypatch.setattr(overrides_module, "time_reliability",
                        lambda: _FakeReliability("unknown"))
    response = await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "motor", "duration_minutes": "10"},
    )
    assert response.status == 400
    assert override_store.active() == {}


async def test_forcage_non_persiste_est_refuse(web_context, override_store, monkeypatch):
    client, *_ = web_context

    def _echec(*_args, **_kwargs):
        raise OSError("disque plein")

    monkeypatch.setattr("utils.state_store.write_text_atomic", _echec)
    response = await client.post(
        "/actions/overrides/create",
        data={"csrf_token": CSRF_TOKEN, "target": "motor", "duration_minutes": "10"},
    )
    assert response.status == 500
    assert override_store.active() == {}


async def test_forcages_exigent_le_jeton_csrf(web_context, override_store):
    client, *_ = web_context
    for route in ("/actions/overrides/create", "/actions/overrides/cancel"):
        response = await client.post(route, data={"target": "motor"})
        assert response.status == 403
    assert override_store.active() == {}


async def test_banniere_de_forcage_est_globale(web_context, override_store):
    client, *_ = web_context
    override_store.create("motor", 600, "")
    # La bannière n'est pas propre au tableau de bord : elle est calculée par
    # `render_template`, donc présente sur toutes les pages rendues.
    for chemin in ("/", "/console", "/conf"):
        page = await (await client.get(chemin)).text()
        assert 'id="override-banner"' in page
