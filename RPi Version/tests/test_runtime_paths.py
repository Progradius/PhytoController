from __future__ import annotations

import os
import stat

import pytest

from utils import runtime_paths


@pytest.fixture(autouse=True)
def resolution_neuve():
    """La résolution est mémorisée pour tout le processus : on la remet à zéro."""
    runtime_paths._reset_for_tests()
    yield
    runtime_paths._reset_for_tests()


def test_defaut_reste_le_param_du_depot(monkeypatch):
    """Sans variable, rien ne bouge : dev, tests et Docker gardent param/."""
    monkeypatch.delenv(runtime_paths.ENV_VAR, raising=False)
    assert runtime_paths.data_dir() == runtime_paths.REPO_DEFAULT
    assert runtime_paths.data_file("param.json").name == "param.json"


def test_variable_deplace_les_fichiers_vivants(monkeypatch, tmp_path):
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(tmp_path))
    assert runtime_paths.data_dir() == tmp_path
    assert runtime_paths.data_file("cultures.sqlite3") == tmp_path / "cultures.sqlite3"


def test_variable_vide_vaut_absence(monkeypatch):
    """Une variable posée mais vide ne doit pas donner le répertoire courant."""
    monkeypatch.setenv(runtime_paths.ENV_VAR, "   ")
    assert runtime_paths.data_dir() == runtime_paths.REPO_DEFAULT


def test_chemin_relatif_est_rendu_absolu(monkeypatch, tmp_path):
    """L'unité systemd fait un `cd` : un chemin relatif désignerait deux endroits."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(runtime_paths.ENV_VAR, "donnees")
    resolu = runtime_paths.data_dir()
    assert resolu.is_absolute()
    assert resolu == (tmp_path / "donnees").resolve()


def test_resolution_memorisee(monkeypatch, tmp_path):
    """Une modification tardive de l'environnement ne crée pas une seconde vérité."""
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(tmp_path))
    premier = runtime_paths.data_dir()
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(tmp_path / "ailleurs"))
    assert runtime_paths.data_dir() == premier


def test_data_file_ne_cree_rien(monkeypatch, tmp_path):
    cible = tmp_path / "absent"
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(cible))
    chemin = runtime_paths.data_file("param.json")
    assert not cible.exists()
    assert not chemin.exists()


def test_ensure_cree_le_repertoire_prive(monkeypatch, tmp_path):
    cible = tmp_path / "phyto-data"
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(cible))
    assert runtime_paths.ensure_data_dir() == cible
    assert cible.is_dir()
    assert stat.S_IMODE(cible.stat().st_mode) == runtime_paths.DIR_MODE


def test_ensure_est_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(tmp_path / "phyto-data"))
    runtime_paths.ensure_data_dir()
    runtime_paths.ensure_data_dir()


def test_repertoire_inutilisable_echoue_sans_repli(monkeypatch, tmp_path):
    """
    Le point dur : jamais de repli silencieux sur `param/`.

    Un repli remettrait les écritures dans le répertoire de travail Git, c'est-à-dire
    exactement l'incident du 08/09/2026, et personne ne le verrait.
    """
    obstacle = tmp_path / "occupe"
    obstacle.write_text("je ne suis pas un répertoire", encoding="utf-8")
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(obstacle))

    with pytest.raises(RuntimeError) as refus:
        runtime_paths.ensure_data_dir()

    assert str(obstacle) in str(refus.value)
    assert runtime_paths.ENV_VAR in str(refus.value)
    assert runtime_paths.data_dir() != runtime_paths.REPO_DEFAULT


@pytest.mark.skipif(os.geteuid() == 0, reason="root écrit malgré le mode 0500")
def test_repertoire_non_ecrivable_echoue(monkeypatch, tmp_path):
    cible = tmp_path / "lecture-seule"
    cible.mkdir(mode=0o500)
    monkeypatch.setenv(runtime_paths.ENV_VAR, str(cible))

    with pytest.raises(RuntimeError):
        runtime_paths.ensure_data_dir()
