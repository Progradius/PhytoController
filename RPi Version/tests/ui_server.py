"""Serveur matériel-neutre réservé aux contrôles Playwright en lecture seule."""

from pathlib import Path
import sys
import tempfile

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from network.web import server as server_module
from param.config import AppConfig
from param.config_store import ConfigStore
from param.equipment_metadata import default_catalog
from tests.test_http_server import (
    CSRF_TOKEN,
    FakeEquipmentStore,
    FakeSensors,
    FakeStatus,
    FakeSupervisor,
)


class _FakeAlarmManager:
    @staticmethod
    def summary():
        return {
            "active_count": 0, "unacknowledged_count": 0, "critical_count": 0,
            "control_count": 0, "auxiliary_count": 0, "highest_severity": None,
        }

    @staticmethod
    def active_payloads():
        return []


class _FakeHistory:
    available = False


class _FakeOperatorService:
    """Expose les vraies pages opérateur sans initialiser SQLite dans les tests UI."""

    alarms = _FakeAlarmManager()
    history = _FakeHistory()

    def snapshot(self):
        return {
            "alarms": self.alarms.summary(),
            "history": {"available": False},
            "network": {"status": "unknown"},
        }

    @staticmethod
    def actuator_snapshot():
        return server_module.operational_snapshot()

    @staticmethod
    async def list_alarm_payloads(_filters):
        return []


def build_app():
    temporary = tempfile.TemporaryDirectory(prefix="phyto-ui-")
    config_path = Path(temporary.name) / "param.json"
    config_path.write_text(
        AppConfig.load(Path("param/param.json")).to_json(), encoding="utf-8"
    )
    store = ConfigStore(config_path)
    sensors = FakeSensors(store.current)
    server_module.shared_config = lambda: store
    server_module.load_or_create_token = lambda: CSRF_TOKEN
    server_module.influx_handler.reload_sensor_handler = lambda *_args, **_kwargs: None
    server = server_module.Server(
        FakeStatus(), sensors, store.current,
        supervisor=FakeSupervisor(),
        equipment_store=FakeEquipmentStore(default_catalog()),
        operator_service=_FakeOperatorService(),
    )
    app = server.create_app()
    # La référence garde le répertoire temporaire vivant pendant le serveur.
    app["ui_test_temporary"] = temporary
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="127.0.0.1", port=38123, print=None)
