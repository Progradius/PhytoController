"""Lot H : journal transversal filtrable et observations d'espace, sans matériel.

Aucun test ici n'accède au GPIO, à `param.json` ni à un capteur : le carnet reste
déclaratif et son indisponibilité ne dégrade jamais la régulation.
"""

import csv
import io
import json
import uuid
import zipfile
from pathlib import Path

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_journal import (JOURNAL_TYPES, journal_filters, journal_window,
                                   space_event_payload, validate_space_events)
from tests.test_cultures import NOW, create, cultures, event  # noqa: F401 (fixtures pytest)
from tests.test_culture_cycles import photo_bytes
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401 (fixture pytest)
from utils.culture_backup import restore_bundle
from utils.culture_store import CultureStore


async def observation(store, space="space_2", note="Espace nettoyé", **extra):
    command = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": space,
               "kind": "observation", "effective_at": "2026-09-01", "note": note, **extra}
    return await store.call("space_event_mutate", command)


async def mother(store, name):
    return await store.call("mutate", create(name, "mother", stage="maintien", origins=[]))


def test_regles_pures_du_journal_sans_base():
    assert space_event_payload("incident", {"note": "  Fuite  "}) == {"note": "Fuite"}
    for kind, raw in (("plante", {"note": "x"}), ("observation", {"note": ""}),
                      ("observation", {"note": "x" * 4001}), ("observation", {"autre": "x"})):
        with pytest.raises(CultureError):
            space_event_payload(kind, raw)
    assert journal_filters({"type": "solution:water", "start": ""}) == {"type": "solution:water"}
    with pytest.raises(CultureError):
        journal_filters({"inconnu": "1"})
    with pytest.raises(CultureError):
        journal_filters({"type": "event:inexistant"})
    # Borne haute calendaire exclusive : le dernier jour du filtre reste entier.
    start, end = journal_window({"start": "2026-09-01", "end": "2026-09-01"}, "Europe/Paris")
    assert start == "2026-08-31T22:00:00+00:00" and end == "2026-09-01T22:00:00+00:00"
    with pytest.raises(CultureError):
        journal_window({"start": "2026-09-02", "end": "2026-09-01"}, "Europe/Paris")
    with pytest.raises(CultureError):
        journal_window({"start": "01/09/2026"}, "Europe/Paris")
    assert JOURNAL_TYPES["space_event:observation"] == "Espace · Observation"


def test_validation_des_observations_rejette_revisions_et_contenus_incoherents():
    base = {"id": "a", "revision": 1, "space": "space_1", "kind": "observation",
            "precision": "date", "cancelled": 0, "clock_reliable": 1,
            "payload": json.dumps({"note": "ok"})}
    validate_space_events([base, {**base, "revision": 2, "cancelled": 1}])
    # Une observation entièrement annulée reste légitime : sa trace ne disparaît pas.
    validate_space_events([{**base, "cancelled": 1}])
    for broken in ({**base, "revision": 2}, {**base, "space": "serre"}, {**base, "kind": "note"},
                   {**base, "payload": "{"}, {**base, "payload": json.dumps({"note": ""})},
                   {**base, "cancelled": 2}, {**base, "precision": "vague"}):
        with pytest.raises(CultureError):
            validate_space_events([broken])


async def test_observation_d_un_espace_vide_reste_consultable(cultures):
    saved = await observation(cultures, "space_2", "Bac vide désinfecté")
    journal = await cultures.call("journal", {"target": "space_2"})
    assert journal["total"] == 1
    entry = journal["items"][0]
    assert entry["source"] == "space_event" and entry["entry_id"] == saved["id"]
    assert entry["target_label"] == "Espace 2" and entry["note"] == "Bac vide désinfecté"
    assert entry["type_label"] == "Espace · Observation" and entry["editable"]
    # Aucune fausse plante n'a été créée pour porter la note.
    assert (await cultures.call("overview"))["total"] == 0
    assert (await cultures.call("journal", {"target": "space_1"}))["total"] == 0


async def test_arrosage_partage_reste_une_operation_unique_dans_le_journal(cultures):
    first = await mother(cultures, "Mère A")
    second = await mother(cultures, "Mère B")
    third = await mother(cultures, "Mère C")
    targets = [first["subject_id"], second["subject_id"], third["subject_id"]]
    await cultures.call("solution_mutate", {"request_id": str(uuid.uuid4()), "operation": "entry",
        "kind": "water", "targets": targets, "effective_at": "2026-09-02", "volume_l": 5})
    watering = await cultures.call("journal", {"type": "solution:water"})
    assert watering["total"] == 1 and len(watering["items"]) == 1
    assert len(watering["items"][0]["targets"]) == 3
    # Chaque mère retrouve l'arrosage, sans que la ligne soit dupliquée pour autant.
    for subject_id in targets:
        page = await cultures.call("journal", {"target": subject_id, "type": "solution:water"})
        assert page["total"] == 1


async def test_journal_retrouve_les_evenements_d_un_lot_archive_sur_une_periode(cultures):
    lot = await cultures.call("mutate", create("Lot archivé", stage="vegetatif", space="space_2"))
    lot = await event(cultures, lot, "harvest", "2026-08-20")
    lot = await event(cultures, lot, "finish", "2026-08-25", {"release": True, "weight_g": 12.0})
    subject_id = lot["subject_id"]
    assert (await cultures.call("overview", True))["total"] == 1
    period = await cultures.call("journal", {"target": subject_id, "start": "2026-08-20", "end": "2026-08-25"})
    assert [item["kind"] for item in period["items"]] == ["finish", "harvest"]
    assert (await cultures.call("journal", {"target": subject_id, "start": "2026-08-26"}))["total"] == 0
    assert (await cultures.call("journal", {"target": subject_id, "end": "2026-08-19"}))["total"] == 3


async def test_pagination_stable_et_lien_focus_a_travers_les_pages(cultures):
    ordered = []
    for day in range(1, 46):
        saved = await observation(cultures, "space_1", f"Passage {day:02d}",
                                  effective_at=f"2026-07-{day:02d}" if day <= 31 else f"2026-08-{day - 31:02d}")
        ordered.append(saved["id"])
    first = await cultures.call("journal", {"target": "space_1"})
    second = await cultures.call("journal", {"target": "space_1"}, 40)
    assert first["total"] == 45 and len(first["items"]) == 40 and len(second["items"]) == 5
    # Aucune opération n'est perdue ni comptée deux fois entre deux pages.
    identifiers = [item["entry_id"] for item in first["items"] + second["items"]]
    assert len(set(identifiers)) == 45 and set(identifiers) == set(ordered)
    # Le repère ramène directement sur la page qui contient l'opération visée.
    focused = await cultures.call("journal", {"target": "space_1"}, 0, ordered[0])
    assert focused["offset"] == 40 and any(item["entry_id"] == ordered[0] for item in focused["items"])
    assert (await cultures.call("journal", {"target": "space_1"}, 0, str(uuid.uuid4())))["offset"] == 0


async def test_correction_et_annulation_d_observation_sont_tracables(cultures):
    saved = await observation(cultures, "space_1", "Ventilateur bruyant")
    correction = {"request_id": str(uuid.uuid4()), "operation": "correct", "id": saved["id"],
                  "version": 1, "note": "Ventilateur remplacé", "effective_at": "2026-09-01",
                  "reason": "Précision apportée"}
    corrected = await cultures.call("space_event_mutate", correction)
    assert corrected["version"] == 2
    # Idempotence : rejouer la même clé ne crée pas une seconde révision.
    assert await cultures.call("space_event_mutate", correction) == corrected
    with pytest.raises(CultureConflict):
        await cultures.call("space_event_mutate", {**correction, "request_id": str(uuid.uuid4())})
    entry = (await cultures.call("journal", {"target": "space_1"}))["items"][0]
    assert entry["note"] == "Ventilateur remplacé" and entry["revision"] == 2
    assert [old["note"] for old in entry["revisions"]] == ["Ventilateur bruyant"]
    assert entry["reason"] == "Précision apportée"
    cancelled = await cultures.call("space_event_mutate", {
        "request_id": str(uuid.uuid4()), "operation": "correct", "id": saved["id"], "version": 2,
        "note": "Ventilateur remplacé", "effective_at": "2026-09-01",
        "reason": "Saisie erronée", "cancelled": True})
    assert cancelled["version"] == 3
    entry = (await cultures.call("journal", {"target": "space_1"}))["items"][0]
    assert entry["cancelled"] and not entry["editable"] and len(entry["revisions"]) == 2
    # L'espace et le genre ne se corrigent pas : la trace ne change pas de cible.
    with pytest.raises(CultureError, match="ne se corrigent pas"):
        await cultures.call("space_event_mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
            "id": saved["id"], "version": 3, "space": "space_2", "note": "x", "reason": "y",
            "effective_at": "2026-09-01"})
    await cultures.call("cycle_validate")


async def test_commandes_d_observation_refusees_sans_effet(cultures):
    for command in (
        {"request_id": "k1", "operation": "inconnue", "space": "space_1", "note": "x", "effective_at": "2026-09-01"},
        {"request_id": "k2", "operation": "space_event", "space": "serre", "note": "x", "effective_at": "2026-09-01"},
        {"request_id": "k3", "operation": "space_event", "space": "space_1", "note": "", "effective_at": "2026-09-01"},
        {"request_id": "k4", "operation": "space_event", "space": "space_1", "note": "x", "effective_at": "2099-01-01"},
        {"request_id": "k5", "operation": "space_event", "space": "space_1", "note": "x",
         "effective_at": "2026-09-01", "id": "imposé"},
        {"request_id": "k6", "operation": "correct", "id": "absent", "version": 1, "note": "x",
         "effective_at": "2026-09-01", "reason": "y"},
        {"request_id": "k7", "operation": "space_event", "space": "space_1", "note": "x",
         "effective_at": "2026-09-01", "champ": "inconnu"},
    ):
        with pytest.raises(CultureError):
            await cultures.call("space_event_mutate", command)
    assert (await cultures.call("journal", {}))["total"] == 0
    with pytest.raises(CultureError, match="Cible de filtre"):
        await cultures.call("journal", {"target": "inconnue"})
    with pytest.raises(CultureError, match="Filtre de journal"):
        await cultures.call("journal", {"inconnu": "1"})


async def test_export_csv_du_filtre_neutralise_les_textes(cultures):
    await observation(cultures, "space_1", "=cmd|' /c calc'!A1")
    await observation(cultures, "space_2", "Note ordinaire")
    export = await cultures.call("journal_csv", {"target": "space_1"})
    lines = export.strip().splitlines()
    assert lines[0].startswith("source,operation_id,revision,type")
    assert len(lines) == 2 and "'=cmd" in lines[1] and "Note ordinaire" not in export
    assert '"[{""kind"": ""space"", ""id"": ""space_1""' in lines[1]
    # Une opération multi-cibles reste une ligne unique, cibles sérialisées en JSON.
    first, second = await mother(cultures, "Mère X"), await mother(cultures, "Mère Y")
    await cultures.call("solution_mutate", {"request_id": str(uuid.uuid4()), "operation": "entry",
        "kind": "water", "targets": [first["subject_id"], second["subject_id"]],
        "effective_at": "2026-09-02", "volume_l": 4})
    rows = list(csv.DictReader(io.StringIO(await cultures.call("journal_csv", {"type": "solution:water"}))))
    assert len(rows) == 1 and len(json.loads(rows[0]["cibles"])) == 2


async def test_photos_d_observation_partagent_limites_sauvegarde_et_restauration(cultures, tmp_path):
    saved = await observation(cultures, "space_2", "Traces d’humidité")
    command = {"request_id": str(uuid.uuid4()), "space_event_id": saved["id"],
               "space_event_revision": 1, "caption": "Coin nord"}
    raw = photo_bytes()
    photo = await cultures.call("media_add", command, raw)
    assert photo["space"] == "space_2"
    assert await cultures.call("media_add", command, raw) == photo
    with pytest.raises(CultureConflict):
        await cultures.call("media_add", {**command, "caption": "Autre"}, raw)
    for _ in range(3):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    with pytest.raises(CultureError, match="Quatre"):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4())}, raw)
    # Exclusivité du propriétaire : jamais une photo à la fois de culture et d'espace.
    with pytest.raises(CultureError, match="jamais aux deux"):
        await cultures.call("media_add", {**command, "request_id": str(uuid.uuid4()),
                                          "event_id": "x", "subject_id": "y"}, raw)
    entry = (await cultures.call("journal", {"target": "space_2"}))["items"][0]
    assert len(entry["photos"]) == 4 and entry["photos"][0]["owner_kind"] == "space_event"
    # La galerie des cycles ne mélange pas les propriétaires : son lien de fiche resterait vide.
    assert (await cultures.call("media_list")) == []
    assert (await cultures.call("media_storage"))["count"] == 4
    bundle = Path(await cultures.call("bundle"))
    try:
        with zipfile.ZipFile(bundle) as archive:
            assert len(json.loads(archive.read("manifest.json"))["files"]) == 5
        destination = tmp_path / "restauration"
        restore_bundle(bundle, destination)
        assert len(list((destination / "culture_media").glob("*.jpg"))) == 4
        other = CultureStore(destination / "cultures.sqlite3", now=lambda: NOW)
        try:
            restored = await other.call("journal", {"target": "space_2"})
            assert restored["total"] == 1 and len(restored["items"][0]["photos"]) == 4
            assert await other.call("media_get", photo["id"]) == await cultures.call("media_get", photo["id"])
        finally:
            await other.close()
    finally:
        bundle.unlink()


async def test_photo_refusee_sur_observation_annulee(cultures):
    saved = await observation(cultures, "space_1", "À supprimer")
    await cultures.call("space_event_mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "id": saved["id"], "version": 1, "note": "À supprimer", "effective_at": "2026-09-01",
        "reason": "Doublon", "cancelled": True})
    with pytest.raises(CultureError, match="annulée"):
        await cultures.call("media_add", {"request_id": str(uuid.uuid4()), "space_event_id": saved["id"],
                                          "space_event_revision": 2, "caption": ""}, photo_bytes())


async def test_journal_http_expose_page_donnees_mutation_et_export(web_context):
    client, server, config, *_ = web_context
    original = config.current.to_json()
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": "space_2",
            "kind": "incident", "effective_at": "2026-09-01", "note": "<script>alert(1)</script>"}
    assert (await client.post("/api/v1/cultures/journal", json=body)).status == 403
    response = await client.post("/api/v1/cultures/journal", json=body, headers=headers)
    assert response.status == 200, await response.text()
    saved = await response.json()
    assert (await client.post("/api/v1/cultures/journal", json={**body, "request_id": str(uuid.uuid4()),
                                                                "note": ""}, headers=headers)).status == 400
    page = await client.get("/cultures/journal?target=space_2&type=space_event:incident")
    assert page.status == 200
    html = await page.text()
    assert "Journal du carnet" in html and "<script>alert" not in html and "&lt;script&gt;" in html
    assert 'value="space_2" selected' in html
    data = await (await client.get("/api/v1/cultures/journal?target=space_2")).json()
    assert data["total"] == 1 and data["items"][0]["entry_id"] == saved["id"]
    # Un filtre refusé conserve les champs saisis au lieu de vider le formulaire.
    refused = await client.get("/cultures/journal?start=2026-09-05&end=2026-09-01")
    assert refused.status == 400 and 'value="2026-09-05"' in await refused.text()
    assert (await client.get("/api/v1/cultures/journal?start=2026-09-05&end=2026-09-01")).status == 400
    assert (await client.get("/api/v1/cultures/journal?offset=-1")).status == 400
    export = await client.get("/api/v1/cultures/journal/export?target=space_2")
    assert export.status == 200 and "attachment" in export.headers["Content-Disposition"]
    assert "space_event:incident" in await export.text()
    assert (await client.get("/api/v1/cultures/journal/export?format=json")).status == 400
    # Le carnet reste déclaratif : aucune écriture de configuration, aucune commande.
    assert config.current.to_json() == original
    assert (await client.get("/health/ready")).status == 200


async def test_recherche_du_journal_ignore_accents_et_neutralise_les_jokers(cultures):
    plant = await cultures.call("mutate", create("Épinard géant", stage="vegetatif", space="space_2"))
    await event(cultures, plant, "note", "2026-09-03", {"note": "Feuillage dense"})
    await observation(cultures, "space_1", "Dosage à 100% du volume prévu")
    await observation(cultures, "space_1", "Bac rincé sans produit")
    complete = (await cultures.call("journal", {}))["total"]
    # « epinard » trouve « Épinard » : la normalisation retire les diacritiques des deux côtés.
    accents = await cultures.call("journal", {"q": "epinard"})
    assert accents["total"] == complete - 2 and {item["source"] for item in accents["items"]} == {"event"}
    assert all(item["subject_id"] == plant["subject_id"] for item in accents["items"])
    assert accents["filters"]["q"] == "epinard"
    # Le joker `%` du texte cherché est littéral : il ne balaie pas tout le journal.
    assert (await cultures.call("journal", {"q": "100%"}))["total"] == 1
    joker = await cultures.call("journal", {"q": "%"})
    assert joker["total"] == 1 and "100%" in joker["items"][0]["note"]
    assert (await cultures.call("journal", {"q": "_"}))["total"] == 0
    # La recherche porte aussi sur le libellé français du type d'opération.
    assert (await cultures.call("journal", {"q": "Espace · Observation"}))["total"] == 2
    # Un filtre vide ne filtre pas ; une saisie réduite à des accents non plus.
    assert (await cultures.call("journal", {"q": ""}))["total"] == complete
    assert (await cultures.call("journal", {"q": "́"}))["total"] == complete
    # La recherche se combine avec les autres filtres au lieu de les remplacer.
    assert (await cultures.call("journal", {"q": "bac", "target": "space_1"}))["total"] == 1
    assert (await cultures.call("journal", {"q": "bac", "target": "space_2"}))["total"] == 0


async def test_recherche_du_journal_est_bornee_a_120_caracteres_par_troncature(cultures):
    await observation(cultures, "space_1", "Repère " + "a" * 130)
    long = "a" * 121
    # Une saisie trop longue n'est ni une erreur ni une 500 : elle est tronquée, et c'est
    # la valeur tronquée qui est renvoyée au formulaire.
    page = await cultures.call("journal", {"q": long})
    assert page["total"] == 1 and page["filters"]["q"] == "a" * 120
    # Au-delà de la borne, deux saisies différentes cherchent la même chose.
    assert (await cultures.call("journal", {"q": "a" * 400}))["total"] == 1
    assert (await cultures.call("journal", {"q": "b" * 121}))["total"] == 0
    with pytest.raises(CultureError):
        await cultures.call("journal", {"q": 12})


async def test_recherche_du_journal_pagine_sur_le_compte_reellement_filtre(cultures):
    for day in range(1, 42):
        await observation(cultures, "space_1", f"Passage numéroté {day:02d}",
                          effective_at=f"2026-07-{day:02d}" if day <= 31 else f"2026-08-{day - 31:02d}")
    await observation(cultures, "space_1", "Hors recherche")
    first = await cultures.call("journal", {"q": "passage numerote"})
    assert first["total"] == 41 and len(first["items"]) == 40 and first["offset"] == 0
    second = await cultures.call("journal", {"q": "passage numerote"}, 40)
    # Le compte et la seconde page décrivent le filtre, pas la page : un post-filtrage
    # Python de la seule page affichée aurait annoncé 42 et rendu la page 2 vide.
    assert second["total"] == 41 and len(second["items"]) == 1 and second["offset"] == 40
    assert (await cultures.call("journal", {"q": "passage numerote"}, 10**7))["offset"] == 40
    # Le raccourci de période est calculé sur la date du carnet, sans en inventer une seconde.
    assert first["today"] == "2026-09-07"
    assert first["quick"] == [{"days": 7, "start": "2026-09-01", "end": "2026-09-07"},
                              {"days": 30, "start": "2026-08-09", "end": "2026-09-07"}]


async def test_journal_http_reconduit_recherche_et_periodes_rapides(web_context):
    client, server, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    body = {"request_id": str(uuid.uuid4()), "operation": "space_event", "space": "space_2",
            "kind": "observation", "effective_at": "2026-09-01", "note": "Épinard tacheté"}
    assert (await client.post("/api/v1/cultures/journal", json=body, headers=headers)).status == 200
    data = await (await client.get("/api/v1/cultures/journal?q=epinard")).json()
    assert data["total"] == 1 and data["filters"]["q"] == "epinard"
    assert (await client.get("/api/v1/cultures/journal?q=" + "z" * 200)).status == 200
    page = await client.get("/cultures/journal?q=epinard&target=space_2")
    assert page.status == 200
    html = await page.text()
    # La saisie est réaffichée et les raccourcis de période reconduisent tous les filtres.
    assert 'name="q" maxlength="120" value="epinard"' in html
    assert 'href="?target=space_2&amp;q=epinard&amp;start=2026-09-01&amp;end=2026-09-07"' in html
    assert 'href="?target=space_2&amp;q=epinard&amp;start=2026-08-09&amp;end=2026-09-07"' in html
    assert 'href="?target=space_2&amp;q=epinard"' in html
    # L'export du filtre courant tient compte de la recherche comme la page.
    export = await client.get("/api/v1/cultures/journal/export?q=epinard")
    assert export.status == 200 and "tacheté" in await export.text()
    # Les liens de pagination reconduisent la recherche : sans elle, « plus anciennes »
    # ramènerait à un journal non filtré et perdrait le contexte de lecture.
    store = server.cultures.store
    for day in range(1, 42):
        await observation(store, "space_2", f"Épinard tacheté {day:02d}", effective_at=f"2026-07-{day:02d}"
                          if day <= 31 else f"2026-08-{day - 31:02d}")
    paginated = await (await client.get("/cultures/journal?q=epinard&target=space_2")).text()
    assert 'data-journal-offset="40" href="?target=space_2&amp;q=epinard&amp;offset=40"' in paginated
    assert '<span class="num">42</span> opération(s) pour ce filtre' in paginated


async def test_journal_rend_une_ligne_par_operation_avec_details_replies(web_context):
    """R2.8 : une opération = une ligne rendue par la macro partagée `journal_entry`.

    L'article extérieur reste le repère focalisable (`#entry-…`) visé par la galerie et par
    le retour après enregistrement ; la ligne porte date, opération, cible et résumé ; tout
    ce qui sert à *résoudre* l'entrée — version, contexte de saisie, motif, liens, galerie,
    versions antérieures — vit dans le `<details>` du `caller`, replié par défaut.
    """
    client, server, *_ = web_context
    store = server.cultures.store
    for index in range(3):
        await observation(store, "space_2", f"Bac {index} rincé")
    html = await (await client.get("/cultures/journal?target=space_2")).text()

    # Une ligne par opération : autant d'articles de macro que d'articles-repères.
    # R2.8 : l'entrée est une ligne, pas une carte — `.card` (remplissage + bordure) coûtait
    # 34 px par opération, soit une ligne de texte entière sur vingt entrées.
    assert html.count('<article class="culture-journal-entry"') == 3
    assert 'class="card culture-journal-entry"' not in html
    assert html.count('<article class="ui-journal-entry">') == 3
    assert html.count("<summary>Détails de l’opération</summary>") == 3
    ligne = html.split('<article class="ui-journal-entry">')[1].split("<details>")[0]
    assert '<time class="num">01/09/2026</time>' in ligne
    assert "<strong>Espace · Observation</strong> Espace 2" in ligne
    assert "Bac 2 rincé" in ligne
    # La résolution n'est plus sur la ligne : elle est derrière le repli.
    assert 'version <span class="num">1</span>' not in ligne
    assert "Ouvrir la fiche liée" not in ligne
    details = html.split("<summary>Détails de l’opération</summary>")[1].split("</details>")[0]
    assert 'version <span class="num">1</span> · saisie le' in details
    assert "Ouvrir la fiche liée" in details


async def test_journal_rejoue_ses_filtres_dans_les_liens_de_retour(web_context):
    """R2.8 : ouvrir une fiche depuis le journal doit ramener au journal **filtré**.

    Le paramètre `retour` porte l'adresse relative complète de la vue courante, filtres et
    page comprises, dans la forme normalisée par la route — pas celle de la requête brute.
    """
    client, server, *_ = web_context
    store = server.cultures.store
    mere = await mother(store, "Mère du retour")
    for day in range(1, 42):
        await observation(store, "space_2", f"Bac {day:02d} rincé",
                          effective_at=f"2026-07-{day:02d}" if day <= 31 else f"2026-08-{day - 31:02d}")

    html = await (await client.get("/cultures/journal?target=space_2&q=%20rinc%C3%A9%20")).text()
    # `q` est repris **borné et détouré** par la route, pas recopié de la requête brute :
    # le lien de retour rejoue exactement la page servie.
    assert "retour=/cultures/journal%3Ftarget%3Dspace_2%26q%3Drinc%25C3%25A9" in html
    assert "%26offset%3D40" not in html
    seconde = await (await client.get("/cultures/journal?target=space_2&q=%20rinc%C3%A9%20&offset=40")).text()
    assert "retour=/cultures/journal%3Ftarget%3Dspace_2%26q%3Drinc%25C3%25A9%26offset%3D40" in seconde
    # Sans filtre ni page, le retour reste l'adresse nue du journal.
    nu = await (await client.get(f"/cultures/journal?target={mere['subject_id']}")).text()
    assert f"retour=/cultures/journal%3Ftarget%3D{mere['subject_id']}" in nu
    # L'ancre du lien reste en dernier : `?retour=…#event-…`, jamais l'inverse.
    lien = nu.split('class="action-link" href="/cultures/' + mere["subject_id"], 1)[1]
    assert lien.startswith("?retour=") and "#event-" in lien.split('"', 1)[0]


async def test_journal_gabarit_photo_brouillon_et_inventaire_partage(web_context):
    """R5.4, R3.4 et R2.5 côté journal, vérifiés sur le HTML réellement servi."""
    client, server, *_ = web_context
    # Une observation existante : c'est elle qui porte le formulaire d'ajout de photo.
    await observation(server.cultures.store, "space_2", "Bac rincé")
    html = await (await client.get("/cultures/journal")).text()
    # R5.4 : `capture` n'est plus imposé par le gabarit ; `accept` reste.
    assert "capture=" not in html and 'type="file" name="photo" accept="image/*"' in html
    # R3.4 : l'observation d'espace est inscrite au dispositif de brouillon, bannière hors
    # du `<details>` replié, et chaque champ restaurable est marqué.
    assert '<div data-culture-draft-banner="space_event"></div>' in html
    banniere, reste = html.split('<div data-culture-draft-banner="space_event"></div>', 1)
    assert reste.lstrip().startswith("<details")
    formulaire = reste.split("</form>", 1)[0]
    assert 'data-culture-draft="space_event"' in formulaire
    assert 'data-draft-target="journal"' in formulaire and 'data-draft-version="' in formulaire
    for champ in ('name="space" data-draft-field', 'name="kind" data-draft-field',
                  'name="effective_at" data-draft-field', 'name="precision" data-draft-field',
                  'name="note" maxlength="4000" data-draft-field'):
        assert champ in formulaire, champ
    # R2.5 : un seul inventaire hors ligne, celui du fragment partagé, et la recherche du
    # journal n'est pas un outil local — elle interroge le serveur.
    assert html.count("data-culture-offline-index") == 1
    assert 'id="copies"' in html and "data-offline-latest" in html
    assert "data-offline-local" not in html
    # R2.8 : l'index des copies suit les opérations et l'observation d'espace ; placé avant,
    # il repoussait « Opérations du carnet » sous le premier écran d'un téléphone.
    assert html.index("<h2>Opérations du carnet</h2>") < html.index('id="observation"') < html.index('id="copies"')
