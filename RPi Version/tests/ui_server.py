"""Serveur matériel-neutre ; les mutations du carnet restent dans une base temporaire.

`python3 tests/ui_server.py` sert l'application sur `PHYTO_UI_TEST_PORT` (38123 par défaut, `0`
pour un port libre choisi par le noyau) et annonce `PHYTO_UI_READY <port>` sur sa sortie standard
dès qu'il accepte des requêtes.
"""

from pathlib import Path
import asyncio
import os
import signal
import sys
import tempfile

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from network.web import server as server_module
from param.config import AppConfig
from param.config_store import ConfigStore
from param.equipment_metadata import default_catalog
from utils.culture_store import CultureStore
from utils.operational_state import publish as publish_state
from utils.time_reliability import time_reliability
from tests.fakes.http_server import (
    CSRF_TOKEN,
    FakeEquipmentStore,
    FakeSensors,
    FakeStatus,
    FakeSupervisor,
)


class _FakeAlarmManager:
    @staticmethod
    def _critical():
        return os.environ.get("PHYTO_UI_MEASURE_SCENARIO") == "critical"

    @staticmethod
    def summary():
        if _FakeAlarmManager._critical():
            return {"active_count": 1, "unacknowledged_count": 1, "critical_count": 1,
                    "control_count": 1, "auxiliary_count": 0, "highest_severity": "critical"}
        return {
            "active_count": 0, "unacknowledged_count": 0, "critical_count": 0,
            "control_count": 0, "auxiliary_count": 0, "highest_severity": None,
        }

    @staticmethod
    def active_payloads():
        if _FakeAlarmManager._critical():
            return [{"id": "measure-critical", "severity": "critical", "category": "control",
                     "title": "Surchauffe simulée", "detail": "Fixture de mesure uniquement.",
                     "consequence": "Culture exposée à une température excessive.",
                     "advice": "Vérifier la ventilation et le chauffage.", "affects_control": True,
                     # Horodatage fixe et non nul : le résumé court de `/alarms` affiche la
                     # dernière occurrence, et un `0` y vaudrait « aucune occurrence datée ».
                     "link": "/alarms", "started_ts": 1788462000, "duration_seconds": 60,
                     "acknowledged_ts": None, "acknowledged_by": None, "status": "active"}]
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
        return _FakeAlarmManager.active_payloads()

    @staticmethod
    async def record_override_event(_action, _target, _seconds):
        """Trace opérateur d'une coupure : sans SQLite, il n'y a rien à écrire.

        Son absence faisait échouer `/actions/overrides/create` en 500 **après** la
        création du forçage : la coupure était bien posée côté serveur, mais le navigateur
        recevait une erreur et n'actualisait pas la ligne. Un parcours d'intervention n'était
        donc jouable qu'au hasard du sondage suivant.
        """
        return None


def publier_etat_nominal():
    """Publie l'état des six équipements, comme le feraient les boucles métier.

    Sans cette publication le registre d'observabilité est **vide** : chaque équipement
    est alors « demandé inconnu, non relu », `tracking` vaut `unknown`, et le tableau de
    bord ouvre les six lignes en application de la règle « une ligne en anomalie n'est
    jamais repliée ». Le serveur de référence décrivait donc une serre dont **aucun**
    équipement n'est relu — l'inverse du scénario nominal que son en-tête annonce, et une
    base de mesure trompeuse pour la hauteur de page.

    La règle d'ouverture n'est pas touchée : elle reste vérifiée par les deux scénarios
    dédiés de `tests/ui/dashboard.spec.js` (coupure réelle côté serveur, anomalie injectée
    côté flux vivant). Ici, la serre va bien.

    `stale_after` est volontairement très large : une session de navigation dure plusieurs
    minutes, et un état qui se périmerait en cours de route ferait rouvrir les lignes au
    milieu d'un test sans qu'aucune anomalie ne soit survenue.
    """
    jour = 24 * 3600
    for equipment_id in ("daily_1", "daily_2", "cyclic_1", "cyclic_2", "heater"):
        publish_state(equipment_id, stale_after=jour, requested="off", applied="off",
                      actual="off", tracking="ok", mode="automatique",
                      reason="Conduite normale : aucune condition d'activation.",
                      since_mono=None, next_transition={"type": "condition"})
    publish_state("motor", stale_after=jour, requested=0, applied=0, actual=0,
                  tracking="ok", mode="automatique",
                  reason="Conduite normale : température dans la cible.",
                  since_mono=None, next_transition={"type": "condition"})


def build_app():
    # Horloge du scénario nominal. Le moniteur réel sonde des fichiers de `systemd-timesyncd`
    # qui n'existent pas sur un poste de développement : l'état y reste « unknown », et
    # `utils/overrides.create()` refuse alors toute coupure (« heure non fiable : impossible
    # de borner un forçage »). Aucun parcours d'intervention n'était donc jouable au
    # navigateur. La serre de référence a une horloge synchronisée ; le serveur de test la
    # représente, sans toucher au moniteur lui-même — la règle de refus reste intacte et
    # reste couverte par `tests/test_http_server.py`.
    monitor = time_reliability()
    monitor.ever_synchronized = True
    monitor.state = "synchronized"
    publier_etat_nominal()

    temporary = tempfile.TemporaryDirectory(prefix="phyto-ui-")
    config_path = Path(temporary.name) / "param.json"
    config_path.write_text(
        AppConfig.load(Path("param/param.example.json")).to_json(), encoding="utf-8"
    )
    store = ConfigStore(config_path)
    # Le scénario par défaut représente une serre nominale : les états vides
    # restent exercés explicitement dans les tests qui en ont besoin.
    store.current.sensors.bme280_state = True
    sensors = FakeSensors(store.current)
    server_module.shared_config = lambda: store
    server_module.load_or_create_token = lambda: CSRF_TOKEN
    server_module.influx_handler.reload_sensor_handler = lambda *_args, **_kwargs: None
    server = server_module.Server(
        FakeStatus(), sensors, store.current,
        supervisor=FakeSupervisor(),
        equipment_store=FakeEquipmentStore(default_catalog()),
        operator_service=_FakeOperatorService(),
        # Horloge système volontairement conservée ici, contrairement à `tests/test_http_server.py` :
        # les specs navigateur saisissent des dates du jour (échéances de rappels, « aujourd'hui »
        # de l'accueil, occupation en cours). Une horloge figée les rendrait futures ou trop
        # anciennes selon le jour d'exécution, et le carnet refuserait des saisies légitimes.
        culture_store=CultureStore(Path(temporary.name) / "cultures.sqlite3", reliable=lambda: True),
    )
    app = server.create_app()
    # La référence garde le répertoire temporaire vivant pendant le serveur.
    app["ui_test_temporary"] = temporary
    return app


# Ligne de disponibilité, lue par `tests/ui/serveurs.js`. Elle est écrite **après** l'ouverture de
# l'écoute et le démarrage de l'application (`on_startup`) : qui la lit peut envoyer une requête.
# C'est un protocole entre processus, pas un journal — elle ne passe donc pas par `pretty_console`,
# dont la mise en forme (couleurs, préfixes) la rendrait illisible pour la fixture.
READY_PREFIX = "PHYTO_UI_READY"


def annoncer(port: int) -> None:
    """Écrit la ligne de disponibilité d'un seul `write`, pour qu'aucun journal ne s'y intercale."""
    os.write(sys.stdout.fileno(), f"{READY_PREFIX} {port}\n".encode())


async def servir(port: int) -> None:
    """Sert l'application jusqu'à SIGTERM/SIGINT, puis l'arrête proprement.

    `port=0` laisse le noyau choisir un port libre. C'est la seule façon d'exclure toute collision :
    les anciens ports fixes (38123, 39123 + rang du worker…) tombent dans la plage éphémère de Linux
    (32768–60999), où n'importe quelle connexion sortante peut les occuper au hasard — un
    `EADDRINUSE` constaté le 11 septembre 2026 sans qu'aucun serveur n'écoute sur le port.
    """
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        arret = asyncio.Event()
        loop = asyncio.get_running_loop()
        for signum in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(signum, arret.set)
        annoncer(runner.addresses[0][1])
        await arret.wait()
    finally:
        # `on_cleanup` ferme le carnet ; le répertoire temporaire ne disparaît qu'ensuite.
        await runner.cleanup()
        app["ui_test_temporary"].cleanup()


if __name__ == "__main__":
    asyncio.run(servir(int(os.environ.get("PHYTO_UI_TEST_PORT", "38123"))))
