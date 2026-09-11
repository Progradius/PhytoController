"""Serveur des specs navigateur (`tests/ui_server.py`) : démarrage, disponibilité, arrêt, zygote.

Ces tests lancent le **vrai** processus, comme le font les fixtures Playwright, et ne parlent qu'à
la boucle locale. Ils fixent le contrat dont dépend `tests/ui/serveurs.js` : un port libre choisi
par le noyau, une annonce écrite quand le serveur accepte des requêtes, un arrêt propre sur SIGTERM
qui ne laisse rien dans le répertoire temporaire imposé et, en mode zygote, un processus neuf et
isolé par demande, sans orphelin quelle que soit la façon dont le zygote disparaît.
"""

from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READY = re.compile(rb"^PHYTO_UI_READY (\d+)$", re.MULTILINE)


def _lire_jusqua(process: subprocess.Popen, motif: re.Pattern, delai: float = 30.0) -> re.Match:
    """Lit la sortie standard sans bloquer au-delà du délai ; échoue avec la sortie reçue."""
    tampon = b""
    selecteur = selectors.DefaultSelector()
    selecteur.register(process.stdout, selectors.EVENT_READ)
    fin = time.monotonic() + delai
    try:
        while time.monotonic() < fin:
            if not selecteur.select(timeout=max(0.0, fin - time.monotonic())):
                break
            morceau = os.read(process.stdout.fileno(), 65536)
            if not morceau:
                break
            tampon += morceau
            trouve = motif.search(tampon)
            if trouve:
                return trouve
    finally:
        selecteur.close()
    raise AssertionError(f"motif {motif.pattern!r} absent ; sortie reçue :\n{tampon.decode(errors='replace')}")


def _get(url: str) -> int:
    with urllib.request.urlopen(url, timeout=5) as reponse:
        return reponse.status


def test_port_libre_ligne_de_disponibilite_et_arret_propre(tmp_path):
    process = subprocess.Popen(
        [sys.executable, "tests/ui_server.py"], cwd=ROOT,
        env={**os.environ, "PHYTO_UI_TEST_PORT": "0", "TMPDIR": str(tmp_path)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        port = int(_lire_jusqua(process, READY).group(1))
        assert port > 0
        # La ligne n'est écrite qu'une fois l'écoute ouverte : aucune attente n'est nécessaire.
        assert _get(f"http://127.0.0.1:{port}/health/ready") == 200
        # Le serveur a bien posé sa base sous le TMPDIR imposé.
        assert any(tmp_path.iterdir())
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=15) == 0
        # SIGTERM est géré : le carnet est fermé puis le répertoire temporaire supprimé.
        assert list(tmp_path.iterdir()) == []
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


class _Zygote:
    """Pilote minimal du protocole de `tests/ui_server.py --zygote`."""

    PREFIXE = b"PHYTO_UI_ZYGOTE "

    def __init__(self):
        self.process = subprocess.Popen(
            [sys.executable, "tests/ui_server.py", "--zygote"], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.tampon = b""
        self.journal = b""
        # Messages reçus mais pas encore attendus : le zygote et l'enfant écrivent sans ordre garanti.
        self.recus: list[dict] = []
        assert self.attendre(lambda message: message.get("pret"))

    def envoyer(self, message: dict) -> None:
        self.process.stdin.write((json.dumps(message) + "\n").encode())
        self.process.stdin.flush()

    def attendre(self, condition, delai: float = 30.0) -> dict:
        fin = time.monotonic() + delai
        while True:
            while b"\n" in self.tampon:
                ligne, self.tampon = self.tampon.split(b"\n", 1)
                if ligne.startswith(self.PREFIXE):
                    self.recus.append(json.loads(ligne[len(self.PREFIXE):]))
                else:
                    self.journal += ligne + b"\n"
            for message in self.recus:
                if condition(message):
                    self.recus.remove(message)
                    return message
            reste = fin - time.monotonic()
            selecteur = selectors.DefaultSelector()
            selecteur.register(self.process.stdout, selectors.EVENT_READ)
            try:
                pret = reste > 0 and selecteur.select(timeout=reste)
            finally:
                selecteur.close()
            morceau = os.read(self.process.stdout.fileno(), 65536) if pret else b""
            if not morceau:
                raise AssertionError(f"message attendu absent ; sortie :\n{self.journal.decode(errors='replace')}")
            self.tampon += morceau

    def demarrer(self, identifiant: int, env: dict) -> tuple[int, int]:
        self.envoyer({"op": "demarrer", "id": identifiant, "env": env})
        fork = self.attendre(lambda m: m.get("id") == identifiant and "pid" in m and "port" not in m)
        pret = self.attendre(lambda m: m.get("id") == identifiant and ("port" in m or "mort" in m))
        assert "port" in pret, pret
        # L'annonce de l'enfant porte son propre PID : c'est le même que celui du fork.
        assert pret["pid"] == fork["pid"]
        return pret["pid"], pret["port"]

    def arreter(self, identifiant: int, pid: int) -> int:
        self.envoyer({"op": "arreter", "id": identifiant, "pid": pid})
        return self.attendre(lambda m: m.get("id") == identifiant and "code" in m)["code"]

    def fermer(self) -> int:
        self.process.stdin.close()
        return self.process.wait(timeout=30)

    def tuer(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


@pytest.fixture
def zygote():
    pilote = _Zygote()
    try:
        yield pilote
    finally:
        pilote.tuer()


def _json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as reponse:
        return json.load(reponse)


def _disparu(pid: int, delai: float = 10.0) -> bool:
    """Vrai quand le processus n'existe plus ou n'est plus qu'un zombie en attente de récolte."""
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            etat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return True
        if etat == "Z":
            return True
        time.sleep(0.05)
    return False


def test_zygote_deux_serveurs_neufs_et_isoles(zygote, tmp_path):
    carnet_a, carnet_b = tmp_path / "a", tmp_path / "b"
    carnet_a.mkdir()
    carnet_b.mkdir()
    pid_a, port_a = zygote.demarrer(1, {"TMPDIR": str(carnet_a)})
    pid_b, port_b = zygote.demarrer(2, {"TMPDIR": str(carnet_b), "PHYTO_UI_MEASURE_SCENARIO": "critical"})
    assert pid_a != pid_b and port_a != port_b
    for port in (port_a, port_b):
        assert _get(f"http://127.0.0.1:{port}/health/ready") == 200
    # L'environnement d'un enfant ne touche ni le zygote ni son voisin.
    assert _json(f"http://127.0.0.1:{port_a}/api/v1/alarms")["summary"]["critical_count"] == 0
    assert _json(f"http://127.0.0.1:{port_b}/api/v1/alarms")["summary"]["critical_count"] == 1
    # Chaque enfant a posé sa base sous SON TMPDIR (cache de `tempfile` remis à zéro).
    assert any(carnet_a.iterdir()) and any(carnet_b.iterdir())
    assert zygote.arreter(1, pid_a) == 0
    assert zygote.arreter(2, pid_b) == 0
    assert list(carnet_a.iterdir()) == [] and list(carnet_b.iterdir()) == []
    assert zygote.fermer() == 0


def test_zygote_signale_un_serveur_mort_de_lui_meme(zygote, tmp_path):
    pid, _port = zygote.demarrer(7, {"TMPDIR": str(tmp_path)})
    os.kill(pid, signal.SIGKILL)
    assert zygote.attendre(lambda m: m.get("id") == 7 and "mort" in m)["mort"] == -signal.SIGKILL
    # L'arrêt demandé ensuite rend le code déjà récolté, sans signal envoyé à un PID recyclé.
    assert zygote.arreter(7, pid) == -signal.SIGKILL


def test_fin_de_stdin_arrete_les_serveurs_restants(zygote, tmp_path):
    pid, _port = zygote.demarrer(3, {"TMPDIR": str(tmp_path)})
    assert zygote.fermer() == 0
    assert _disparu(pid)
    assert list(tmp_path.iterdir()) == []


def test_zygote_tue_sans_preavis_ne_laisse_aucun_orphelin(zygote, tmp_path):
    pid, port = zygote.demarrer(4, {"TMPDIR": str(tmp_path)})
    assert _get(f"http://127.0.0.1:{port}/health/ready") == 200
    zygote.tuer()  # SIGKILL : aucune fermeture de stdin, aucun nettoyage côté zygote
    assert _disparu(pid), "le serveur a survécu à son zygote"


def test_fork_refuse_des_quun_second_thread_existe():
    from tests import ui_server

    arret = threading.Event()
    thread = threading.Thread(target=arret.wait, name="temoin")
    thread.start()
    try:
        with pytest.raises(RuntimeError, match="fork"):
            ui_server._verifier_fork_sur()
    finally:
        arret.set()
        thread.join()


def test_arreter_un_pid_inconnu_est_refuse_explicitement(zygote):
    # Un « code: null » silencieux laissait croire à un arrêt réussi d'un serveur jamais arrêté.
    zygote.envoyer({"op": "arreter", "id": 9, "pid": 1})
    assert "PID inconnu" in zygote.attendre(lambda m: m.get("id") == 9)["erreur"]
