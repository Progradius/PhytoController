from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "scripts" / "observe-jalon2-operator-quality.sh"

# Unité systemd simulée : seules les propriétés lues par l'observateur.
_FAUX_SYSTEMCTL = """#!/usr/bin/env bash
prop=""
while (( $# )); do
    if [[ "$1" == "-p" ]]; then prop="$2"; shift; fi
    shift
done
case "$prop" in
    MainPID) echo 4242 ;;
    NRestarts) echo 0 ;;
    WatchdogUSec) echo 10min ;;
    ActiveState) echo active ;;
    SubState) echo running ;;
    Environment) echo "PHYTO_RUN_MODE=service PHYTO_DATA_DIR=__DONNEES__" ;;
esac
"""

# Aucune API joignable : seule la sonde Influx, qui lit param.json, compte ici.
_FAUX_CURL = """#!/usr/bin/env bash
printf '000'
exit 7
"""


def _executable(path: Path, contenu: str) -> None:
    path.write_text(contenu, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_la_sonde_influx_lit_le_repertoire_de_donnees_de_l_unite(tmp_path: Path):
    """
    Après migration, la configuration vivante n'est plus dans param/ du checkout :
    l'observateur doit la chercher là où l'unité systemd la déclare.
    """
    donnees = tmp_path / "phyto-data"
    donnees.mkdir()
    # « offline » ne se lit que dans ce fichier : le checkout n'en a pas, ou
    # un autre. Une sonde qui lirait param/ répondrait autre chose.
    (donnees / "param.json").write_text(
        json.dumps({"Network_Settings": {"host_machine_state": "offline"}}),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(bin_dir / "systemctl", _FAUX_SYSTEMCTL.replace("__DONNEES__", str(donnees)))
    _executable(bin_dir / "curl", _FAUX_CURL)
    preuves = tmp_path / "observations"

    result = subprocess.run(
        ["bash", str(OBSERVER)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "PHYTO_OBSERVATION_DIR": str(preuves),
            # La fenêtre doit couvrir le démarrage (git sur un montage lent),
            # sinon aucun échantillon n'est pris ; l'intervalle égal à la durée
            # borne l'observation à un seul échantillon.
            "PHYTO_OBSERVATION_SECONDS": "8",
            "PHYTO_OBSERVATION_INTERVAL_SECONDS": "8",
            "PHYTO_OBSERVATION_EXPECTED_COMMIT": "0" * 40,
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    # API injoignable : l'échantillon échoue, c'est attendu et hors sujet ici ;
    # ce code prouve surtout qu'un échantillon a bien été pris.
    assert result.returncode == 1, result.stdout + result.stderr
    run_dir = Path((preuves / "latest-jalon2-operateur-qualite.txt").read_text().strip())
    assert f"donnees={donnees}\n" in (run_dir / "metadata.txt").read_text(encoding="utf-8")
    premier = json.loads((run_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert premier["influx_quality_probe"] == {"enabled": False, "ok": True, "sensors": {}}
