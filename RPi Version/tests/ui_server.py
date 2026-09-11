"""Serveur matériel-neutre ; les mutations du carnet restent dans une base temporaire.

`python3 tests/ui_server.py` sert l'application sur `PHYTO_UI_TEST_PORT` (38123 par défaut, `0`
pour un port libre choisi par le noyau) et annonce `PHYTO_UI_READY <port>` sur sa sortie standard
dès qu'il accepte des requêtes.

`python3 tests/ui_server.py --zygote` est le mode des specs navigateur : un processus par worker
Playwright, qui duplique un serveur neuf par test (voir `zygote()` et `tests/ui/serveurs.js`).
"""

from pathlib import Path
import asyncio
import json
import os
import selectors
import signal
import sys
import tempfile
import threading
import time
import traceback

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


# Ligne de disponibilité du mode autonome. Elle est écrite **après** l'ouverture de l'écoute et le
# démarrage de l'application (`on_startup`) : qui la lit peut envoyer une requête. C'est un
# protocole entre processus, pas un journal — elle ne passe donc pas par `pretty_console`, dont la
# mise en forme (couleurs, préfixes) la rendrait illisible pour l'appelant.
READY_PREFIX = "PHYTO_UI_READY"


def _ecrire_ligne(ligne: str) -> None:
    """Un seul `write` par ligne : aucun journal ne peut s'y intercaler."""
    os.write(sys.stdout.fileno(), f"{ligne}\n".encode())


def annoncer(port: int) -> None:
    _ecrire_ligne(f"{READY_PREFIX} {port}")


async def servir(port: int, annonce=annoncer) -> None:
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
        annonce(runner.addresses[0][1])
        await arret.wait()
    finally:
        # `on_cleanup` ferme le carnet ; le répertoire temporaire ne disparaît qu'ensuite.
        await runner.cleanup()
        app["ui_test_temporary"].cleanup()


# ---------------------------------------------------------------------------------------------
# Zygote : un processus par worker Playwright, un `fork()` par test.
#
# Chaque test garde **son** processus serveur, donc aucun état partagé : espace 2 exclusif du
# carnet, overrides, registre d'état et `ConfigStore` sont des singletons de module, et seul un
# processus neuf les isole sans dépendre d'une remise à zéro. Ce qui change, c'est le prix : l'import
# de l'applicatif (0,3 s sur ext4, 3 à 8 s depuis `/mnt/c`) n'est payé qu'une fois par worker, et
# chaque serveur ne coûte plus que `fork()` + `build_app()`, ≈ 20 ms.
#
# Protocole, une ligne JSON par message, préfixée pour la distinguer des journaux :
#   stdin  {"op": "demarrer", "id": n, "env": {...}}   → stdout {"id": n, "pid": p} puis, de l'enfant,
#                                                          {"id": n, "port": x}
#   stdin  {"op": "arreter", "id": n, "pid": p}        → stdout {"id": n, "code": c}
#   un enfant mort sans qu'on l'ait arrêté              → stdout {"id": n, "mort": c}
#   fin de stdin (worker terminé, même tué)             → tous les enfants arrêtés, puis sortie.
#
# Le zygote n'appelle **jamais** `build_app()` et ne crée ni boucle asyncio ni thread : chaque enfant
# part de l'état d'un processus qui vient d'importer ses modules, exactement comme un interpréteur
# neuf. Un thread présent au moment du `fork()` pourrait détenir un verrou (journalisation,
# allocation) que l'enfant hériterait verrouillé à jamais ; le zygote refuse donc de dupliquer un
# processus qui en a plus d'un.
# ---------------------------------------------------------------------------------------------
ZYGOTE_PREFIX = "PHYTO_UI_ZYGOTE"
ARRET_DELAI_SECONDES = 10.0


def _repondre(message: dict) -> None:
    _ecrire_ligne(f"{ZYGOTE_PREFIX} {json.dumps(message)}")


def _verifier_fork_sur() -> None:
    if threading.active_count() != 1:
        raise RuntimeError(
            f"zygote : {threading.active_count()} threads actifs, fork() refusé "
            f"({[thread.name for thread in threading.enumerate()]})"
        )


def _mourir_avec_le_zygote(pid_zygote: int) -> None:
    """Un zygote tué par SIGKILL ne doit laisser aucun serveur orphelin (Linux : PR_SET_PDEATHSIG)."""
    try:
        import ctypes

        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass  # hors Linux, la fin de stdin reste le seul signal — elle couvre la fin normale
    if os.getppid() != pid_zygote:  # le zygote est mort avant le prctl
        os._exit(1)


def _enfant(identifiant: int, environnement: dict, pid_zygote: int) -> None:
    """Corps de l'enfant : ne rend jamais la main au zygote (`os._exit`)."""
    code = 1
    try:
        _mourir_avec_le_zygote(pid_zygote)
        # stdin porte le protocole du zygote : l'enfant ne doit ni le lire ni le garder ouvert.
        nul = os.open(os.devnull, os.O_RDONLY)
        os.dup2(nul, 0)
        os.close(nul)
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, signal.SIG_DFL)
        os.environ.update(environnement)
        # `tempfile` mémorise son répertoire au premier appel : sans cette remise à zéro, le
        # `TMPDIR` propre à ce test serait ignoré au profit de celui qu'a vu le zygote.
        tempfile.tempdir = None
        asyncio.run(servir(0, annonce=lambda port: _repondre({"id": identifiant, "port": port})))
        code = 0
    except BaseException:  # noqa: BLE001 — l'enfant rapporte tout, puis sort sans remonter
        traceback.print_exc()
    finally:
        # `os._exit` : ni les `atexit` hérités du zygote, ni un retour dans sa boucle.
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)


def _attendre_sortie(pid: int) -> int:
    """SIGTERM, puis SIGKILL passé le délai ; rend le code de sortie de l'enfant."""
    os.kill(pid, signal.SIGTERM)
    fin = time.monotonic() + ARRET_DELAI_SECONDES
    while True:
        termine, statut = os.waitpid(pid, os.WNOHANG)
        if termine:
            return os.waitstatus_to_exitcode(statut)
        if time.monotonic() >= fin:
            os.kill(pid, signal.SIGKILL)
            return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])
        time.sleep(0.01)


def zygote() -> None:
    _verifier_fork_sur()
    pid_zygote = os.getpid()
    enfants: dict[int, int] = {}  # pid → identifiant de la demande
    morts: dict[int, int] = {}  # pid récolté avant sa demande d'arrêt → code
    selecteur = selectors.DefaultSelector()
    selecteur.register(0, selectors.EVENT_READ)
    tampon = b""
    _repondre({"pret": True})
    try:
        while True:
            # Récolte des enfants morts d'eux-mêmes : la fixture l'apprend tout de suite, au lieu
            # d'attendre un port qui ne viendra jamais.
            while enfants:
                pid, statut = os.waitpid(-1, os.WNOHANG)
                if not pid:
                    break
                code = os.waitstatus_to_exitcode(statut)
                morts[pid] = code
                _repondre({"id": enfants.pop(pid), "mort": code})
            if not selecteur.select(timeout=0.2):
                continue
            morceau = os.read(0, 65536)
            if not morceau:
                return  # fin de stdin : le worker est parti
            tampon += morceau
            while b"\n" in tampon:
                ligne, tampon = tampon.split(b"\n", 1)
                if not ligne.strip():
                    continue
                demande = json.loads(ligne)
                if demande["op"] == "demarrer":
                    _verifier_fork_sur()
                    # Un tampon non vidé au moment du fork serait réécrit par l'enfant : un journal
                    # d'import apparaîtrait une fois par serveur dans les diagnostics.
                    sys.stdout.flush()
                    sys.stderr.flush()
                    pid = os.fork()
                    if pid == 0:
                        selecteur.close()
                        _enfant(demande["id"], demande.get("env") or {}, pid_zygote)
                    enfants[pid] = demande["id"]
                    _repondre({"id": demande["id"], "pid": pid})
                elif demande["op"] == "arreter":
                    pid = demande["pid"]
                    if pid in enfants:
                        del enfants[pid]
                        code = _attendre_sortie(pid)
                    else:
                        code = morts.pop(pid, None)
                    _repondre({"id": demande["id"], "code": code})
                else:
                    raise ValueError(f"zygote : opération inconnue {demande['op']!r}")
    finally:
        for pid in list(enfants):
            _attendre_sortie(pid)


if __name__ == "__main__":
    if sys.argv[1:] == ["--zygote"]:
        zygote()
    else:
        asyncio.run(servir(int(os.environ.get("PHYTO_UI_TEST_PORT", "38123"))))
