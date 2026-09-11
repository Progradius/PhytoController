"""Comparateur de mesures web (`scripts/compare-measures.py`, fiche R0.1).

Le comparateur décide seul si deux relevés de hauteur se valent : il doit donc refuser de
confronter deux protocoles différents (carnet, fenêtre) au lieu de produire un écart
trompeur, et continuer à lire le fichier de l'audit, qui ne consigne ni l'un ni l'autre.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare-measures.py"
_spec = importlib.util.spec_from_file_location("compare_measures", SCRIPT)
compare_measures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_measures)


def _audit(route, width, height):
    """Entrée au format exact de l'audit : ni `state`, ni `theme`, ni `carnet`, ni `viewport`."""
    return {"route": route, "width": width, "status": 200, "height": height, "scrollWidth": width,
            "dom": 100, "headings": [], "smallTargets": [], "resources": [], "axe": [], "errors": []}


def _mesure(route, width, height, carnet="vide", theme="dark", viewport_height=844):
    return {**_audit(route, width, height), "state": "page", "theme": theme, "carnet": carnet,
            "viewport": {"width": width, "height": viewport_height}}


def _write(tmp_path, name, entries):
    path = tmp_path / name
    path.write_text(json.dumps(entries), encoding="utf-8")
    return str(path)


def test_rejeu_dans_la_tolerance_sort_a_zero(tmp_path, capsys):
    before = _write(tmp_path, "avant.json", [_audit("/", 390, 1000), _audit("/alarms", 390, 1414)])
    after = _write(tmp_path, "apres.json", [_mesure("/", 390, 1000), _mesure("/alarms", 390, 1410)])
    assert compare_measures.main([before, after]) == 0
    sortie = capsys.readouterr().out
    assert "| `/alarms` | 390 | 1414 | 1410 | -0.28 % | ok |" in sortie
    # L'audit ne consigne ni carnet ni fenêtre : le rapport le dit au lieu de le supposer.
    assert "Avant : 2 entrée(s) sans carnet consigné" in sortie
    assert "Avant : 2 entrée(s) sans fenêtre consignée" in sortie
    assert "Après :" not in sortie


def test_ecart_hors_tolerance_sort_en_echec(tmp_path, capsys):
    before = _write(tmp_path, "avant.json", [_audit("/", 390, 1000)])
    after = _write(tmp_path, "apres.json", [_mesure("/", 390, 1021)])
    assert compare_measures.main([before, after]) == 1
    assert "+2.10 % | HORS TOLÉRANCE" in capsys.readouterr().out


def test_route_disparue_est_un_echec(tmp_path, capsys):
    before = _write(tmp_path, "avant.json", [_audit("/", 390, 1000), _audit("/console", 390, 900)])
    after = _write(tmp_path, "apres.json", [_mesure("/", 390, 1000)])
    assert compare_measures.main([before, after]) == 1
    assert "ABSENTE APRÈS" in capsys.readouterr().out


def test_la_passe_comparee_est_choisie_par_le_carnet(tmp_path, capsys):
    """Un fichier complet porte deux passes nominales : elles ne sont pas des doublons."""
    before = _write(tmp_path, "avant.json", [_audit("/cultures", 390, 2159)])
    after = _write(tmp_path, "apres.json", [
        _mesure("/cultures", 390, 2159, carnet="vide"),
        _mesure("/cultures", 390, 2866, carnet="rempli"),
        _mesure("/cultures", 390, 2866, carnet="rempli", theme="daylight"),
    ])
    assert compare_measures.main([before, after]) == 0
    assert "+0.00 % | ok" in capsys.readouterr().out
    assert compare_measures.main([before, after, "--carnet", "rempli"]) == 1
    assert "HORS TOLÉRANCE" in capsys.readouterr().out


def test_deux_fenetres_differentes_ne_se_comparent_pas(tmp_path, capsys):
    before = _write(tmp_path, "avant.json", [_mesure("/history", 320, 844, viewport_height=844)])
    after = _write(tmp_path, "apres.json", [_mesure("/history", 320, 844, viewport_height=568)])
    # Même hauteur, et pourtant un échec : la ligne n'a pas de sens, elle ne vaut pas « ok ».
    assert compare_measures.main([before, after]) == 1
    assert "NON COMPARABLE : fenêtres 320×844 et 320×568" in capsys.readouterr().out


def test_doublon_dans_une_meme_passe_est_refuse(tmp_path):
    before = _write(tmp_path, "avant.json", [_audit("/", 390, 1000)])
    after = _write(tmp_path, "apres.json", [_mesure("/", 390, 1000), _mesure("/", 390, 1001)])
    with pytest.raises(SystemExit, match="mesurée deux fois"):
        compare_measures.main([before, after])


def test_carnet_absent_du_fichier_est_signale(tmp_path):
    before = _write(tmp_path, "avant.json", [_mesure("/", 390, 1000, carnet="rempli")])
    after = _write(tmp_path, "apres.json", [_mesure("/", 390, 1000, carnet="rempli")])
    with pytest.raises(SystemExit, match="carnet « vide »"):
        compare_measures.main([before, after])
