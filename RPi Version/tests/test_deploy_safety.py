from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from param.config import AppConfig


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "scripts" / "deploy.sh"


def test_un_second_deploiement_est_refuse(tmp_path: Path):
    lock_path = tmp_path / ".phyto-deploy.lock"
    with lock_path.open("w", encoding="utf-8") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = subprocess.run(
            ["bash", str(DEPLOY), "master"],
            cwd=ROOT,
            env={
                **os.environ,
                "HOME": str(tmp_path),
                "PHYTO_DEPLOY_REEXEC": "1",
                "PHYTO_APP_DIR": str(ROOT),
                "PHYTO_DEPLOY_HEALTH_VALIDATOR": str(
                    ROOT / "utils" / "deployment_health.py"
                ),
            },
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 1
    assert "Un autre deploiement est deja en cours" in result.stderr
    assert not (tmp_path / "phyto-backups").exists()


def test_option_config_git_est_definitivement_refusee():
    result = subprocess.run(
        ["bash", str(DEPLOY), "--config-git"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "--config-git a ete supprime" in result.stderr


def test_checkout_ne_peut_plus_toucher_les_fichiers_vivants():
    script = DEPLOY.read_text(encoding="utf-8")

    assert 'git checkout -- "RPi Version/$f"' not in script
    assert "FICHIERS_CONFIG_REPO" in script
    assert 'git cat-file -e "$revision:$fichier"' in script
    assert 'git checkout --detach "$SHA_CIBLE"' in script
    assert script.index("Configuration locale valide") < script.index("git fetch origin")


def test_exemple_est_valide_et_neutre():
    example = ROOT / "param" / "param.example.json"
    config = AppConfig.model_validate(json.loads(example.read_text(encoding="utf-8")))

    assert not config.daily_timer1.enabled
    assert not config.daily_timer2.enabled
    assert not config.cyclic1.enabled
    assert not config.cyclic2.enabled
    assert not config.heater_settings.enabled
    assert config.motor.motor_mode == "manual"
    assert config.motor.motor_user_speed == 0
    assert config.motor.sensor_fallback_speed == 0
    assert config.motor.winter_default_speed == 0
    assert config.motor.winter_refresh_speed == 0
    assert not any(config.sensors.model_dump().values())


def test_configuration_et_metadonnees_locales_sont_ignorees():
    ignored = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "param/param.json" in ignored
    assert "param/equipment_metadata.json" in ignored
    assert "param/sensor_stats.json" in ignored

    docker_ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "param/param.json" in docker_ignored
    assert "param/param.json.bak" in docker_ignored
    assert "param/equipment_metadata.json" in docker_ignored

    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "param/param.json -diff" in attributes.splitlines()


# Les chemins vivants sont figés à l'import (ClassVar, constantes de module) :
# seul un interpréteur neuf, lancé avec la variable posée, dit la vérité.
_SONDE_CHEMINS = """
import json
from param.config import AppConfig
from param.equipment_metadata import EquipmentMetadataStore
from model.SensorStats import SensorStats
from utils.csrf import TOKEN_FILE
from utils.state_store import StateStore
from utils.operator_history import OperatorHistory
from utils.culture_store import CultureStore
from utils.pretty_console import PARAM_FILE

print(json.dumps([
    str(AppConfig.config_path()),
    str(EquipmentMetadataStore().path),
    str(SensorStats.FILE),
    str(TOKEN_FILE),
    str(StateStore.FILE),
    str(OperatorHistory.FILE),
    str(CultureStore.FILE),
    str(PARAM_FILE),
]))
"""


def test_aucun_fichier_vivant_dans_le_depot_avec_data_dir(tmp_path: Path):
    """
    L'incident du 08/09/2026 en un test : tant qu'un fichier écrit à l'exécution
    reste dans le répertoire de travail Git, un `git checkout` peut l'écraser.
    """
    donnees = tmp_path / "phyto-data"
    donnees.mkdir()

    result = subprocess.run(
        [sys.executable, "-c", _SONDE_CHEMINS],
        cwd=ROOT,
        env={**os.environ, "PHYTO_DATA_DIR": str(donnees)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    chemins = [Path(p) for p in json.loads(result.stdout) if p]
    assert len(chemins) == 8
    for chemin in chemins:
        assert chemin.parent == donnees, f"{chemin} reste dans le dépôt"


def test_unite_systemd_pose_le_repertoire_de_donnees():
    unite = (ROOT / "deploy" / "phyto.service").read_text(encoding="utf-8")
    assert "Environment=PHYTO_DATA_DIR=" in unite

    script = DEPLOY.read_text(encoding="utf-8")
    # Le script lit la variable dans l'unite, pas dans son propre environnement :
    # un `${PHYTO_DATA_DIR:-...}` du shell retomberait sur param/ apres migration.
    assert "systemctl show" in script and "PHYTO_DATA_DIR" in script
    assert '"$APP_DIR/param/param.json"' not in script
