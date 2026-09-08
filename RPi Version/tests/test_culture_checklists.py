"""Lot D : vérifications déclaratives corrigibles, annulables et confrontées au parcours.

Ces scénarios n'utilisent ni GPIO ni configuration machine : une case cochée reste une
déclaration datée. Ils exercent les révisions, le motif obligatoire, le conflit dérivé
d'une correction rétrospective du parcours et la restauration sur copie isolée.
"""

import sqlite3
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_checklist import context_at
from tests.test_cultures import NOW, create, cultures, event
from utils.culture_backup import restore_copy
from utils.culture_store import CultureStore

CHECKS = {"lighting": True, "pump": False, "ventilation": True}


def checklist(lot, day="2026-09-07", **extra):
    return {"operation": "checklist", "request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"],
            "version": lot["version"], "effective_at": day, "checks": dict(CHECKS), **extra}


async def only(store, subject_id):
    """Unique vérification courante d'un lot, telle que la page la restitue."""
    entries = (await store.call("cycle_data", [subject_id]))["summaries"][0]["checklists"]
    assert len(entries) == 1
    return entries[0]


async def test_correction_et_annulation_conservent_l_historique(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    saved = await cultures.call("cycle_mutate", checklist(lot))
    assert saved == {"saved": True, "id": saved["id"], "revision": 1}
    projection = (await cultures.call("detail", lot["subject_id"]))["subject"]

    correction = {"operation": "checklist_correct", "request_id": str(uuid.uuid4()), "id": saved["id"],
                  "version": 1, "checks": {"lighting": True, "pump": True, "ventilation": True},
                  "note": "Pompe finalement vérifiée", "reason": "Case oubliée à la saisie"}
    assert (await cultures.call("cycle_mutate", correction))["revision"] == 2
    entry = await only(cultures, lot["subject_id"])
    assert entry["revision"] == 2 and entry["pump"] == 1 and not entry["cancelled"]
    assert entry["reason"] == "Case oubliée à la saisie" and entry["note"] == "Pompe finalement vérifiée"
    # La révision d'origine reste lisible : rien n'est réécrit à sa place.
    assert [old["revision"] for old in entry["revisions"]] == [1]
    assert entry["revisions"][0]["pump"] == 0 and entry["revisions"][0]["reason"] == ""

    cancel = {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()), "id": saved["id"],
              "version": 2, "reason": "Vérification attribuée au mauvais lot"}
    assert (await cultures.call("cycle_mutate", cancel))["revision"] == 3
    entry = await only(cultures, lot["subject_id"])
    assert entry["cancelled"] == 1 and entry["reason"] == "Vérification attribuée au mauvais lot"
    assert [old["revision"] for old in entry["revisions"]] == [1, 2]
    # Une vérification annulée n'affirme plus rien et ne peut plus être révisée.
    assert entry["conflict"] is None and entry["conflict_unknown"] is False
    with pytest.raises(CultureError, match="déjà annulée"):
        await cultures.call("cycle_mutate", {**cancel, "request_id": str(uuid.uuid4()), "version": 3})
    # Le carnet reste déclaratif : ni le parcours ni la version du lot ne bougent.
    assert (await cultures.call("detail", lot["subject_id"]))["subject"] == projection


async def test_version_attendue_idempotence_et_motif_obligatoire(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    saved = await cultures.call("cycle_mutate", checklist(lot))
    command = {"operation": "checklist_correct", "request_id": str(uuid.uuid4()), "id": saved["id"],
               "version": 1, "checks": dict(CHECKS), "note": "", "reason": "Erreur de saisie"}
    first = await cultures.call("cycle_mutate", command)
    # Rejouer la même clé ne crée pas de deuxième révision.
    assert await cultures.call("cycle_mutate", command) == first
    entry = await only(cultures, lot["subject_id"])
    assert entry["revision"] == 2 and len(entry["revisions"]) == 1

    # Onglet périmé : la révision attendue n'est plus la révision courante.
    with pytest.raises(CultureConflict, match="actualiser"):
        await cultures.call("cycle_mutate", {**command, "request_id": str(uuid.uuid4()), "version": 1})
    with pytest.raises(CultureConflict):
        await cultures.call("cycle_mutate", {**command, "request_id": str(uuid.uuid4()), "version": "2"})
    with pytest.raises(CultureError, match="Motif"):
        await cultures.call("cycle_mutate", {**command, "request_id": str(uuid.uuid4()), "version": 2, "reason": " "})
    with pytest.raises(CultureError, match="Motif"):
        await cultures.call("cycle_mutate", {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()),
                                             "id": saved["id"], "version": 2, "reason": ""})
    with pytest.raises(CultureError, match="introuvable"):
        await cultures.call("cycle_mutate", {**command, "request_id": str(uuid.uuid4()), "id": str(uuid.uuid4())})
    # Une opération inconnue n'atteint aucun magasin : elle est refusée en amont.
    with pytest.raises(CultureError, match="invalide"):
        await cultures.call("cycle_mutate", {**command, "operation": "checklist_autre",
                                             "request_id": str(uuid.uuid4())})
    with pytest.raises(CultureError, match="qu'un motif"):
        await cultures.call("cycle_mutate", {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()),
                                             "id": saved["id"], "version": 2, "reason": "Motif",
                                             "note": "Interdit ici"})
    assert (await only(cultures, lot["subject_id"]))["revision"] == 2


async def test_conflit_derive_d_une_correction_retrospective_du_parcours(cultures):
    lot = await cultures.call("mutate", create(space="space_1"))
    saved = await cultures.call("cycle_mutate", checklist(lot))
    entry = await only(cultures, lot["subject_id"])
    assert entry["stage"] == "germination" and entry["space"] == "space_1"
    assert entry["conflict"] is None and entry["conflict_unknown"] is False

    # Étapes connues ajoutées après coup, à des dates antérieures à la vérification :
    # le contexte enregistré devient contradictoire avec le parcours d'aujourd'hui.
    lot = await event(cultures, lot, "stage", "2026-09-02", {"stage": "vegetatif"})
    lot = await event(cultures, lot, "move", "2026-09-03", {"space": "space_2"})
    entry = await only(cultures, lot["subject_id"])
    assert entry["conflict"] == {"expected_stage": "vegetatif", "expected_space": "space_2",
                                 "recorded_stage": "germination", "recorded_space": "space_1"}
    assert entry["conflict_unknown"] is False
    # Le stade affiché aujourd'hui reste distinct du contexte enregistré à la saisie.
    assert entry["stage_at"] == "2026-08-01"

    # Le conflit ne se lève que par une révision explicite de l'opérateur.
    await cultures.call("cycle_mutate", {"operation": "checklist_correct", "request_id": str(uuid.uuid4()),
                                         "id": saved["id"], "version": 1, "checks": dict(CHECKS),
                                         "note": "", "reason": "Contexte réaligné sur le parcours corrigé"})
    entry = await only(cultures, lot["subject_id"])
    assert entry["conflict"] is None and entry["stage"] == "vegetatif" and entry["space"] == "space_2"
    assert entry["stage_at"] == "2026-09-02" and entry["stage_precision"] == "date"
    # L'ancienne version garde le contexte tel qu'il était déclaré.
    assert entry["revisions"][0]["stage"] == "germination" and entry["revisions"][0]["space"] == "space_1"


async def test_ligne_migree_sans_contexte_reste_sans_verdict(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    saved = await cultures.call("cycle_mutate", checklist(lot))

    def strip():
        with cultures._db:
            cultures._db.execute("UPDATE culture_checklists SET subject_version=NULL, stage_at=NULL,"
                                 " stage_precision=NULL WHERE id=?", (saved["id"],))
        return True
    cultures._strip = strip
    await cultures.call("strip")
    entry = await only(cultures, lot["subject_id"])
    assert entry["conflict"] is None and entry["conflict_unknown"] is True
    assert entry["stage_at"] is None
    # Une correction réenregistre un contexte connu : le verdict redevient possible.
    await cultures.call("cycle_mutate", {"operation": "checklist_correct", "request_id": str(uuid.uuid4()),
                                         "id": saved["id"], "version": 1, "checks": dict(CHECKS),
                                         "note": "", "reason": "Contexte enregistré après migration"})
    entry = await only(cultures, lot["subject_id"])
    assert entry["conflict_unknown"] is False and entry["stage_at"] == "2026-08-01"


async def test_correction_apres_progression_et_refus_avant_l_origine(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    saved = await cultures.call("cycle_mutate", checklist(lot, "2026-09-06"))
    # Le lot progresse : une saisie neuve à l'ancienne date est refusée…
    lot = await event(cultures, lot, "stage", "2026-09-07", {"stage": "vegetatif"})
    with pytest.raises(CultureError, match="précède le début du stade"):
        await cultures.call("cycle_mutate", checklist(lot, "2026-09-06"))
    # … mais la case déjà cochée par erreur reste corrigeable à sa propre date.
    assert (await cultures.call("cycle_mutate", {
        "operation": "checklist_correct", "request_id": str(uuid.uuid4()), "id": saved["id"], "version": 1,
        "checks": {"lighting": False, "pump": False, "ventilation": False},
        "note": "", "reason": "Aucune vérification n'avait été faite"}))["revision"] == 2
    entry = await only(cultures, lot["subject_id"])
    assert entry["lighting"] == 0 and entry["stage"] == "germination" and entry["conflict"] is None
    with pytest.raises(CultureError, match="précède l'origine"):
        await cultures.call("cycle_mutate", {
            "operation": "checklist_correct", "request_id": str(uuid.uuid4()), "id": saved["id"], "version": 2,
            "effective_at": "2026-07-01", "checks": dict(CHECKS), "note": "", "reason": "Date fausse"})


async def test_contexte_au_jour_de_bascule_et_espace_libere(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    lot = await event(cultures, lot, "harvest", "2026-09-02", {})
    lot = await event(cultures, lot, "finish", "2026-09-05", {"weight_g": 12, "release": True})
    subject = (await cultures.call("detail", lot["subject_id"]))["subject"]
    # Le jour d'un changement appartient à la période qui commence ; l'espace libéré
    # ce jour-là compte encore, mais plus le lendemain.
    assert context_at(subject, "2026-09-02", cultures.zone)["stage"] == "sechage"
    assert context_at(subject, "2026-09-01", cultures.zone)["stage"] == "germination"
    assert context_at(subject, "2026-09-05", cultures.zone)["space"] == "space_2"
    assert context_at(subject, "2026-09-06", cultures.zone)["space"] is None
    assert context_at(subject, "2026-07-31", cultures.zone) is None


async def test_validation_des_revisions_de_verification(cultures, tmp_path):
    lot = await cultures.call("mutate", create(space="space_2"))
    saved = await cultures.call("cycle_mutate", checklist(lot))
    await cultures.call("cycle_mutate", {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()),
                                         "id": saved["id"], "version": 1, "reason": "Doublon"})
    reference = await cultures.call("backup")
    counter = iter(range(100))

    def probe(sql):
        """Relit les invariants sur une copie altérée ; le carnet d'origine n'est pas touché."""
        path = tmp_path / f"probe-{next(counter)}.sqlite3"
        path.write_bytes(reference)
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        checker = CultureStore(path)
        checker._db = db
        try:
            with db:
                db.execute(sql)
            checker._validate_checklists()
            return None
        except CultureError as exc:
            return str(exc)
        finally:
            db.close()

    assert "manquantes" in probe("DELETE FROM culture_checklists WHERE revision=1")
    assert "redevenir active" in probe(
        "INSERT INTO culture_checklists SELECT id,3,subject_id,space,stage,stage_at,stage_precision,"
        "subject_version,effective_at,precision,recorded_at,clock_reliable,lighting,pump,ventilation,"
        "note,reason,0,equipment_context FROM culture_checklists WHERE revision=2")
    # Cases hors 0/1 et précisions inconnues sont déjà refusées par les contraintes du
    # schéma 4 ; le validateur reste la seconde barrière d'une base fabriquée hors du magasin.
    for damage in ("UPDATE culture_checklists SET lighting=2 WHERE revision=1",
                   "UPDATE culture_checklists SET stage_precision='approx' WHERE revision=1",
                   "UPDATE culture_checklists SET precision='approx' WHERE revision=1"):
        with pytest.raises(sqlite3.IntegrityError):
            probe(damage)
    # La copie intacte reste valide.
    assert probe("SELECT 1") is None


async def test_export_et_restauration_des_revisions_de_verification(cultures, tmp_path):
    lot = await cultures.call("mutate", create(space="space_2"))
    kept = await cultures.call("cycle_mutate", checklist(lot))
    await cultures.call("cycle_mutate", {"operation": "checklist_correct", "request_id": str(uuid.uuid4()),
                                         "id": kept["id"], "version": 1, "checks": dict(CHECKS),
                                         "note": "Relecture", "reason": "Note manquante"})
    removed = await cultures.call("cycle_mutate", checklist(lot, "2026-09-06"))
    await cultures.call("cycle_mutate", {"operation": "checklist_cancel", "request_id": str(uuid.uuid4()),
                                         "id": removed["id"], "version": 1, "reason": "Saisie en double"})

    exported = await cultures.call("export")
    rows = exported["tables"]["culture_checklists"]
    assert len(rows) == 4 and {row["revision"] for row in rows} == {1, 2}
    assert [row["reason"] for row in rows if row["cancelled"]] == ["Saisie en double"]

    backup = tmp_path / "download.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    restored = tmp_path / "restored.sqlite3"
    restore_copy(backup, restored)
    copy_store = CultureStore(restored, now=lambda: NOW)
    try:
        entries = (await copy_store.call("cycle_data", [lot["subject_id"]]))["summaries"][0]["checklists"]
        assert {entry["id"]: entry["revision"] for entry in entries} == {kept["id"]: 2, removed["id"]: 2}
        assert sum(len(entry["revisions"]) for entry in entries) == 2
        assert (await copy_store.call("export"))["tables"]["culture_checklists"] == rows
    finally:
        await copy_store.close()

    # Une sauvegarde dont les révisions sont trouées est refusée sur copie isolée.
    broken = tmp_path / "broken.sqlite3"
    broken.write_bytes(backup.read_bytes())
    db = sqlite3.connect(broken)
    with db:
        db.execute("DELETE FROM culture_checklists WHERE revision=1")
    db.close()
    with pytest.raises(CultureError, match="Révisions"):
        restore_copy(broken, tmp_path / "refused.sqlite3")


__all__ = ["cultures"]
