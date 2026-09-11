"""Serveur des specs navigateur (`tests/ui_server.py`) : démarrage, disponibilité, arrêt.

Ces tests lancent le **vrai** processus, comme le font les fixtures Playwright, et ne parlent qu'à
la boucle locale. Ils fixent le contrat dont dépend `tests/ui/serveurs.js` : un port libre choisi
par le noyau, une ligne `PHYTO_UI_READY <port>` écrite quand le serveur accepte des requêtes, et un
arrêt propre sur SIGTERM qui ne laisse rien dans le répertoire temporaire imposé.
"""

from __future__ import annotations

import os
import re
import selectors
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

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
