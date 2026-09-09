"""Solutions : attribution temporelle, révisions, unité, durabilité et HTTP isolé."""

import json
import sqlite3
import uuid

import pytest

from model.culture import CultureConflict, CultureError
from model.culture_solution import ingredients, measurements, number
from tests.test_cultures import NOW, create, cultures, event
from tests.test_http_server import CSRF_TOKEN, web_context
from utils.culture_backup import restore_copy
from utils.culture_store import CultureStore, CultureUnavailable
from utils.culture_solution_store import SOLUTION_TABLES
from utils.culture_cycle_store import CYCLE_TABLES


def entry(kind="renewal", day="2026-08-01", **extra):
    return {"operation": "entry", "request_id": str(uuid.uuid4()), "kind": kind,
            "reservoir_id": "reservoir_2", "effective_at": day,
            **({"volume_l": 20} if kind == "renewal" else {}), **extra}


def recipe(**extra):
    return {"operation": "recipe", "request_id": str(uuid.uuid4()), "name": "Mélange A",
            "volume_l": 10, "ingredients": [{"product": "Produit A", "quantity": 2, "unit": "mL"}], **extra}


def correction(saved, original, **extra):
    return {**original, "operation": "correct", "request_id": str(uuid.uuid4()),
            "id": saved["id"], "version": saved["version"], **extra}


@pytest.mark.parametrize("value", ["NaN", "inf", float("inf"), float("nan"), True, [], {}, "1,2,3", -1])
def test_nombres_invalides(value):
    with pytest.raises(CultureError):
        number(value, "Valeur")


def test_mesures_decimales_unites_et_absences():
    data = measurements({"ph": "0", "ec": "1234,5", "ec_unit": "µS/cm"})
    assert data["ph"] == 0 and data["ec"] == 1.2345
    assert data["temperature_c"] is None and data["volume_l"] is None
    with pytest.raises(CultureError):
        measurements({"ec": 300, "ec_unit": "ppm"})
    with pytest.raises(CultureError):
        ingredients([{"product": "X", "quantity": 1, "unit": "cuillère"}])


async def test_recette_figee_arrosage_partage_et_restauration(cultures, tmp_path):
    a = await cultures.call("mutate", create("A", "mother"))
    b = await cultures.call("mutate", create("B", "mother"))
    saved_recipe = await cultures.call("solution_mutate", recipe())
    command = entry("water", "2026-08-02", reservoir_id=None, targets=[a["subject_id"], b["subject_id"]],
                    volume_l=5, recipe_id=saved_recipe["id"], recipe_revision=1,
                    ingredients=[{"product": "Produit A", "quantity": 1, "unit": "mL"}])
    saved = await cultures.call("solution_mutate", command)
    assert await cultures.call("solution_mutate", command) == saved
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", {**command, "volume_l": 6})
    await cultures.call("solution_mutate", recipe(id=saved_recipe["id"], version=1,
        ingredients=[{"product": "Nouveau", "quantity": 99, "unit": "g"}]))
    for subject in (a, b):
        rows = (await cultures.call("solution_data", {"target": subject["subject_id"]}))["items"]
        assert len(rows) == 1 and rows[0]["volume_l"] == 5
        assert len(rows[0]["targets"]) == 2
        assert rows[0]["ingredients"][0] == {"product": "Produit A", "quantity": 1, "unit": "mL"}
    assert len((await cultures.call("export"))["tables"]["solution_entries"]) == 1
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", {**command, "request_id": str(uuid.uuid4()), "ingredients": []})
    backup = tmp_path / "backup.sqlite3"
    backup.write_bytes(await cultures.call("backup"))
    destination = tmp_path / "copy.sqlite3"
    restore_copy(backup, destination)
    other = CultureStore(destination, now=lambda: NOW)
    try:
        assert (await other.call("export"))["tables"] == (await cultures.call("export"))["tables"]
    finally:
        await other.close()


async def test_renouvellement_avant_apres_recolte_et_changement_lot(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    old = await cultures.call("solution_mutate", entry())
    new_command = entry(day="2026-08-10", ph="5,8", context="after")
    new = await cultures.call("solution_mutate", new_command)
    before = await cultures.call("solution_mutate", entry("reading", "2026-08-10", ph=6.5,
                  intervention_id=new["id"], context="before"))
    after = await cultures.call("solution_mutate", entry("reading", "2026-08-10", ec="1200", ec_unit="µS/cm",
                  intervention_id=new["id"], context="after"))
    rows = {e["id"]: e for e in (await cultures.call("solution_data"))["items"]}
    assert rows[before["id"]]["period_id"] == old["id"]
    assert rows[after["id"]]["period_id"] == new["id"] and rows[after["id"]]["ec"] == 1.2
    await cultures.call("solution_mutate", entry("reading", "2026-08-12", ph=6))
    await cultures.call("solution_mutate", entry("reading", "2026-08-16", ph=7))
    await event(cultures, lot, "harvest", "2026-08-11")
    assert len((await cultures.call("solution_data", {"target": lot["subject_id"]}))["items"]) == 4
    current = (await cultures.call("detail", lot["subject_id"]))["subject"]
    await event(cultures, {"subject_id": lot["subject_id"], "version": current["version"]}, "finish", "2026-08-15", {"release": True})
    second = await cultures.call("mutate", create("Suivant", space="space_2", space_at="2026-08-15"))
    data = await cultures.call("solution_data", {"target": second["subject_id"]})
    assert [e["ph"] for e in data["items"]] == [7]
    assert data["items"][0]["period_id"] == new["id"]
    # Une correction qui casserait le lien avant/après est atomiquement refusée.
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", correction(new, new_command, effective_at="2026-08-11"))
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", correction(new, new_command, cancelled=True))
    assert len((await cultures.call("solution_data"))["periods"]) == 2


async def test_correction_retroactive_rejoue_attribution_et_conflits(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    await cultures.call("solution_mutate", entry())
    renewal_command = entry(day="2026-08-10")
    renewal = await cultures.call("solution_mutate", renewal_command)
    reading_command = entry("reading", "2026-08-11", ph=6)
    reading = await cultures.call("solution_mutate", reading_command)
    await cultures.call("solution_mutate", correction(renewal, renewal_command, effective_at="2026-08-12"))
    row = next(e for e in (await cultures.call("solution_data"))["items"] if e["id"] == reading["id"])
    assert row["period_id"] != renewal["id"]
    await cultures.call("solution_mutate", correction(reading, reading_command, ph=0, note="Corrigé"))
    row = next(e for e in (await cultures.call("solution_data"))["items"] if e["id"] == reading["id"])
    assert row["ph"] == 0 and row["revisions"][0]["ph"] == 6
    with pytest.raises(CultureConflict):
        await cultures.call("solution_mutate", correction(reading, reading_command, ph=7))
    await event(cultures, lot, "harvest", "2026-08-10")
    assert all(e["kind"] != "reading" for e in (await cultures.call("solution_data", {"target": lot["subject_id"]}))["items"])


async def test_erreurs_atomicite_horloge_et_csv(cultures):
    with pytest.raises(CultureError):
        await cultures.call("solution_mutate", entry("reading", ph=6))
    await cultures.call("solution_mutate", entry())
    before = await cultures.call("export")
    for command in [entry(), entry("reading"), entry("reading", ph=15), entry("topup", volume_l=0),
                    entry("ph"), entry("reading", ph=6, context="before"), entry("water"),
                    entry("reading", ph=6, reservoir_id="absent"), entry("reading", ph=6, targets=[{}])]:
        with pytest.raises(CultureError):
            await cultures.call("solution_mutate", command)
    assert before == await cultures.call("export")
    cultures.reliable = lambda: False
    command = entry("reading", ph=6, note="=HYPERLINK(\"x\")\nNote,français")
    with pytest.raises(CultureError, match="Horloge"):
        await cultures.call("solution_mutate", command)
    await cultures.call("solution_mutate", {**command, "confirm_date": True})
    exported = await cultures.call("solution_csv")
    assert "EC_mS_cm" in exported and "'=HYPERLINK" in exported
    assert (await cultures.call("solution_data"))["items"][0]["clock_reliable"] == 0


async def test_migration_v1_sauvegarde_et_schema_futur(cultures, tmp_path):
    from tests.test_culture_schema_v4 import strip_v4
    lot = await cultures.call("mutate", create())
    source = cultures.path
    await cultures.close()
    with sqlite3.connect(source) as db:
        strip_v4(db)
        for table in reversed(SOLUTION_TABLES + CYCLE_TABLES):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=1")
    assert (await cultures.call("detail", lot["subject_id"]))["subject"]["initial_count"] == 8
    backup = source.with_name(source.name + ".before-v2.sqlite3")
    with sqlite3.connect(backup) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 1
    restore_copy(backup, tmp_path / "old-restored.sqlite3")
    await cultures.close()
    assert (await cultures.call("solution_data"))["items"] == []


async def test_stockage_refuse_et_reprise(cultures):
    await cultures.call("overview")
    cultures._read_only = lambda: cultures._db.execute("PRAGMA query_only=ON").fetchall()
    cultures._writable = lambda: cultures._db.execute("PRAGMA query_only=OFF").fetchall()
    await cultures.call("read_only")
    command = entry()
    with pytest.raises(CultureUnavailable):
        await cultures.call("solution_mutate", command)
    await cultures.call("writable")
    assert (await cultures.call("solution_data"))["periods"] == []
    assert (await cultures.call("solution_mutate", command))["saved"]


async def test_solutions_http_securite_et_rendu(web_context, monkeypatch):
    client, server, config, sensors, supervisor = web_context
    original = config.current.to_json()
    writes = []
    monkeypatch.setattr(config, "save", lambda *_: writes.append("save"))
    command = entry(note='<script>alert("x")</script>')
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    assert (await client.post("/api/v1/cultures/solutions", json=command)).status == 403
    assert (await client.post("/api/v1/cultures/solutions", json=command, headers={**headers, "Origin": "http://evil.example"})).status == 403
    response = await client.post("/api/v1/cultures/solutions", json=command, headers=headers)
    assert response.status == 200, await response.text()
    response = await client.get("/cultures/solutions")
    assert response.status == 200, await response.text()
    html = await response.text()
    assert '&lt;script&gt;' in html and '<script>alert' not in html
    assert response.headers["Cache-Control"] == "no-store"
    assert (await client.get("/static/js/culture_solutions.js")).status == 200
    assert (await client.get("/api/v1/cultures/solutions?target=absent")).status == 400
    assert (await client.get("/api/v1/cultures/solutions/export")).status == 200
    lookup = await client.get("/api/v1/cultures/solutions?interventions=renouvellement")
    assert lookup.status == 200 and "items" not in await lookup.json()
    assert (await client.get("/api/v1/cultures/solutions?interventions=x&interventions_offset=-1")).status == 400
    assert (await client.get("/api/v1/cultures/solutions?interventions=" + "x" * 200)).status == 400
    assert (await client.post("/api/v1/cultures/solutions", json=[], headers=headers)).status == 400
    assert (await client.post("/api/v1/cultures/solutions", json={"note": "x"*70000}, headers=headers)).status == 413
    assert config.current.to_json() == original and not writes and not sensors.reconfigured
    assert (await client.get("/health/ready")).status == 200


async def test_courbes_longues_pagination_et_preparation_sans_rupture(cultures):
    first = await cultures.call("solution_mutate", entry())
    second = await cultures.call("solution_mutate", entry(day="2026-08-02"))
    # Charge représentative insérée dans le thread propriétaire : deux solutions,
    # même journée civile, pour vérifier que l'agrégation ne mélange pas leurs valeurs.
    def populate():
        with cultures._db:
            columns = [r[1] for r in cultures._db.execute("PRAGMA table_info(solution_entries)") if r[1] != "sequence"]
            template = dict(cultures._db.execute("SELECT * FROM solution_entries LIMIT 1").fetchone())
            for i in range(1002):
                row = {**template, "id": str(uuid.uuid4()), "kind": "reading", "ph": 5 if i < 501 else 7,
                       "volume_l": None, "effective_at": "2026-08-01" if i < 501 else "2026-08-02",
                       "sort_at": "2026-07-31T22:00:00+00:00" if i < 501 else "2026-08-01T22:00:00+00:00"}
                cultures._db.execute(f"INSERT INTO solution_entries ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])
    cultures._populate = populate
    await cultures.call("populate")
    data = await cultures.call("solution_data", {"target": "reservoir_2"}, 40)
    assert data["total"] == 1004 and len(data["items"]) == 40
    assert data["chart_aggregated"] and len(data["chart"]) == 2
    assert [(p["ph"], p["ph_count"], p["ph_min"], p["ph_max"]) for p in data["chart"]] == [(5, 501, 5, 5), (7, 501, 7, 7)]
    assert data["chart"][0]["period"] == first["id"] and data["chart"][1]["period"] == second["id"]
    focused = await cultures.call("solution_data", {}, 0, False, first["id"])
    assert any(e["id"] == first["id"] for e in focused["items"])
    assert len((await cultures.call("solution_data", {"start": "2026-08-02", "end": "2026-08-02"}, 0, True))) == 502


async def test_intentions_visibles_et_type_par_defaut_de_la_saisie(web_context):
    """Lot UI 2 : les quatre intentions conservent le filtre et arment la saisie neuve."""
    client, *_ = web_context
    headers = {"X-CSRF-Token": CSRF_TOKEN}
    assert (await client.post("/api/v1/cultures/solutions", json=entry(), headers=headers)).status == 200

    response = await client.get("/cultures/solutions?target=reservoir_2&kind=water&start=2026-07-01&end=2026-09-01")
    assert response.status == 200, await response.text()
    html = await response.text()
    # Cible et période suivent l'intention ; seul le type change, et la saisie s'ouvre.
    # Les séparateurs de la requête sont échappés : `&` nu dans un attribut HTML est une
    # référence d'entité mal formée, que les analyseurs ne toléreront pas toujours.
    for kind in ("reading", "water", "renewal", "topup"):
        assert f'href="?target=reservoir_2&amp;start=2026-07-01&amp;end=2026-09-01&amp;kind={kind}#saisie"' in html
    assert 'data-intention="water" aria-current="true"' in html
    assert html.count('aria-current="true"') == 1
    assert "Saisir : Arrosage" in html
    # Les deux types restants ne sont pas des intentions ; ils demeurent dans le choix « Action ».
    assert 'data-intention="nutrient"' not in html and 'data-intention="ph"' not in html
    saisie = html.split('<details id="saisie"')[1].split('id="journal-solutions"')[0]
    assert '<option value="water" selected>Arrosage</option>' in saisie
    assert 'name="ph" inputmode="decimal" value=""' in saisie

    # Sans intention, la saisie neuve retombe sur le relevé ; aucun lien n'est marqué courant.
    plain = await (await client.get("/cultures/solutions?target=reservoir_2")).text()
    assert 'aria-current="true"' not in plain and "Saisir : Relevé" in plain
    assert '<option value="reading" selected>Relevé</option>' in plain.split('<details id="saisie"')[1]
    # Un type inconnu est déjà refusé par le magasin : la page ne l'invente pas.
    assert (await client.get("/cultures/solutions?kind=invalide")).status == 400
    # Ancres locales : courbes et journal restent atteignables sans traverser la saisie.
    for anchor in ("#saisie", "#reservoirs", "#courbes", "#journal-solutions", "#recettes"):
        assert f'href="{anchor}"' in html
    assert 'id="courbes"' in html and 'id="reservoirs"' in html


async def test_correction_ignore_le_filtre_de_type(cultures):
    """Lot UI 2 : une correction reste verrouillée sur le type de l'entrée corrigée."""
    from network.web.pages import render_template
    from model.culture_solution import SOLUTION_KINDS

    await cultures.call("solution_mutate", entry())
    data = await cultures.call("solution_data", {}, 0)
    html = render_template("culture_solutions.html", page_title="Solutions et relevés",
                           current_page="cultures", csrf_token=CSRF_TOKEN, data=data, error=None,
                           filters={"kind": "water"}, kinds=SOLUTION_KINDS,
                           override_summary=None, pwa_url="", pwa_https_configured=False)
    saisie, journal = html.split('id="journal-solutions"')
    assert '<option value="water" selected>Arrosage</option>' in saisie
    # Le formulaire de correction porte l'identifiant de l'entrée et son type d'origine.
    correction = journal.split('data-solution-entry data-id=')[1]
    assert '<option value="renewal" selected>Renouvellement</option>' in correction
    assert 'value="water" selected' not in correction
    # L'entrée du journal est une cible de retour focalisable après enregistrement.
    assert 'tabindex="-1" data-point=' in journal


async def test_intervention_ancienne_reste_liee_et_retrouvable(cultures):
    """Lot A : une correction de pH ou de note conserve un lien devenu ancien."""
    lot = await cultures.call("mutate", create(space="space_2"))
    renewal = await cultures.call("solution_mutate", entry(day="2026-08-01"))
    await cultures.call("solution_mutate", entry(day="2026-08-01", reservoir_id="cuttings_1"))
    reading_command = entry("reading", "2026-08-01", ph=6, intervention_id=renewal["id"], context="after")
    reading = await cultures.call("solution_mutate", reading_command)
    # Plus de 200 interventions ultérieures, sur deux cibles, repoussent le renouvellement hors fenêtre.
    for index in range(201):
        day = f"2026-08-{index % 28 + 1:02d}"
        target = "reservoir_2" if index % 2 else "cuttings_1"
        await cultures.call("solution_mutate", entry("topup", day, reservoir_id=target, volume_l=1))
    data = await cultures.call("solution_data", {}, 0, False, reading["id"])
    proposed = {item["id"] for item in data["interventions"]}
    assert data["interventions_total"] == 203 and len(data["interventions"]) == 201
    assert renewal["id"] in proposed and any(item["linked"] for item in data["interventions"])
    # Correction « pH seul » : l'association n'est ni mentionnée, ni perdue, ni changée.
    partial = {"operation": "correct", "request_id": str(uuid.uuid4()), "id": reading["id"], "version": 1,
               "kind": "reading", "reservoir_id": "reservoir_2", "effective_at": "2026-08-01", "ph": 6.5}
    saved = await cultures.call("solution_mutate", partial)
    row = next(e for e in (await cultures.call("solution_data", {}, 0, False, reading["id"]))["items"] if e["id"] == reading["id"])
    assert row["ph"] == 6.5 and row["intervention_id"] == renewal["id"] and row["context"] == "after"
    # Correction « note seule », depuis la version issue de la précédente.
    await cultures.call("solution_mutate", {**partial, "request_id": str(uuid.uuid4()), "version": saved["version"],
                                            "ph": 6.5, "note": "Relevé revérifié"})
    row = next(e for e in (await cultures.call("solution_data", {}, 0, False, reading["id"]))["items"] if e["id"] == reading["id"])
    assert row["note"] == "Relevé revérifié" and row["intervention_id"] == renewal["id"] and row["revision"] == 3
    # Recherche bornée : l'intervention ancienne reste sélectionnable pour une saisie rétrospective.
    found = await cultures.call("solution_data", None, 0, False, None, renewal["id"][:8])
    assert [item["id"] for item in found["interventions"]] == [renewal["id"]] and "items" not in found
    assert found["interventions"][0]["target_label"] == "Réservoir de l’espace 2"
    page = await cultures.call("solution_data", None, 0, False, None, "", 200)
    assert page["interventions_offset"] == 200 and len(page["interventions"]) == 3
    assert (await cultures.call("solution_data", None, 0, False, None, "appoint"))["interventions_total"] == 201
    # Association incohérente : refus atomique, sans doublon à la nouvelle tentative identique.
    before = await cultures.call("export")
    broken = {**reading_command, "request_id": str(uuid.uuid4()), "operation": "correct", "id": reading["id"],
              "version": 3, "targets": [lot["subject_id"]], "reservoir_id": None}
    for _ in range(2):
        with pytest.raises(CultureError):
            await cultures.call("solution_mutate", broken)
    assert before == await cultures.call("export")


async def test_migration_interrompue_ne_publie_pas_un_schema_partiel(cultures):
    await cultures.call("mutate", create())
    path = cultures.path
    await cultures.close()
    with sqlite3.connect(path) as db:
        from tests.test_culture_schema_v4 import strip_v4
        strip_v4(db)
        for table in reversed(SOLUTION_TABLES + CYCLE_TABLES):
            db.execute(f"DROP TABLE {table}")
        db.execute("CREATE TABLE recipes (incompatible TEXT)")
        db.execute("PRAGMA user_version=1")
    with pytest.raises(CultureUnavailable):
        await cultures.call("overview")
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='reservoirs'").fetchone()
        assert db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] == 1
    assert path.with_name(path.name + ".before-v2.sqlite3").exists()
    with pytest.raises(CultureUnavailable, match="Sauvegarde"):
        await cultures.call("overview")


# Lot C de la remédiation UI 4 : légende (R3.1) et synthèse textuelle (R3.3) des courbes.


def test_repere_par_source_borne_et_repli_annonce():
    """Une variante par couple (cible, période), dans l'ordre d'apparition, jamais fondue.

    Au-delà de la borne, les sources restantes partagent la variante de repli, et la légende
    le dit au lieu de laisser croire à un repère propre à chacune.
    """
    from model.culture_solution import CHART_SOURCE_VARIANTS, chart_sources
    names = {"reservoir_2": "Réservoir de l’espace 2", "lot-a": "Épinard", "lot-b": "Basilic"}
    points = [{"target": "reservoir_2", "period": "abcdefgh1234"},
              {"target": "reservoir_2", "period": "abcdefgh1234"},
              {"target": "reservoir_2", "period": "zzzzzzzz9999"},
              {"target": "lot-a,lot-b", "period": None}]
    sources = chart_sources(points, names)
    assert sources["variants"] == [0, 0, 1, 2]
    assert [entry["label"] for entry in sources["legend"]] == [
        "Réservoir de l’espace 2 · solution abcdefgh",
        "Réservoir de l’espace 2 · solution zzzzzzzz",
        "Épinard et Basilic · solution manuelle"]
    # `target` nomme les seules cibles : c'est ce que la colonne « Cible ou capteur » du
    # tableau équivalent affiche, la période ayant déjà sa propre colonne.
    assert [entry["target"] for entry in sources["legend"]] == [
        "Réservoir de l’espace 2", "Réservoir de l’espace 2", "Épinard et Basilic"]
    crowd = [{"target": f"cible-{i}", "period": None} for i in range(CHART_SOURCE_VARIANTS + 3)]
    crowded = chart_sources(crowd, {})
    assert crowded["variants"][-3:] == [CHART_SOURCE_VARIANTS] * 3
    assert crowded["legend"][-1] == {"variant": CHART_SOURCE_VARIANTS, "target": "",
                                     "label": "3 autres sources · même repère, faute de variantes distinctes"}


def test_repli_de_repere_ne_nomme_aucune_cible_et_reste_distinct():
    """Huit sources : six repères propres, un repli partagé et annoncé (P2.4).

    Aucun scénario n'exerçait la borne à huit sources, celle du carnet réel quand un filtre
    réunit plusieurs réservoirs et plusieurs solutions. L'entrée de repli n'est la désignation
    d'aucune source : son `target` est vide, ce qui interdit au script de nommer un point avec
    elle — il retomberait sinon sur « 2 autres sources » comme sur un nom de cible.
    """
    from model.culture_solution import CHART_SOURCE_VARIANTS, chart_sources
    names = {f"cible-{index}": f"Culture {index}" for index in range(8)}
    points = [{"target": f"cible-{index}", "period": None} for index in range(8)]
    sources = chart_sources(points, names)

    assert CHART_SOURCE_VARIANTS == 6
    assert sources["variants"] == [0, 1, 2, 3, 4, 5, 6, 6]
    # Six variantes distinctes, donc six repères distincts : aucune fusion silencieuse.
    assert len(set(sources["variants"][:CHART_SOURCE_VARIANTS])) == CHART_SOURCE_VARIANTS
    assert len(sources["legend"]) == CHART_SOURCE_VARIANTS + 1
    assert sources["legend"][-1] == {"variant": 6, "target": "",
                                     "label": "2 autres sources · même repère, faute de variantes distinctes"}
    assert all(entry["target"] for entry in sources["legend"][:-1])


def test_synthese_de_courbe_compte_les_mesures_sans_inventer_de_zero():
    """Période, mesures, min/moyenne/max, lacunes et cibles ; une absence reste une absence.

    La moyenne est pondérée par le nombre de mesures de chaque point : un agrégat journalier
    de trois mesures ne pèse pas comme une mesure isolée, et une lacune n'entre nulle part.
    """
    from model.culture_solution import chart_summary
    names = {"reservoir_2": "Réservoir de l’espace 2", "lot-a": "Épinard"}
    points = [{"at": "2026-08-01T22:00:00+00:00", "target": "reservoir_2", "period": "p1", "ph": 6.0, "ec": None},
              {"at": "2026-08-02T22:00:00+00:00", "target": "reservoir_2", "period": "p1", "ph": None, "ec": None},
              {"at": "2026-08-03T22:00:00+00:00", "target": "lot-a", "period": None, "ph": 6.4, "ec": None,
               "ph_count": 3, "ph_min": 6.2, "ph_max": 6.6}]
    # Les clés sont UTC : minuit local du 2 août en heure d'été, pas le 1er.
    assert chart_summary(points, "ph", "pH", "", "Europe/Paris", names) == (
        "pH · du 02/08/2026 au 04/08/2026 · 4 mesures · minimum 6.00, moyenne 6.30, maximum 6.60"
        " · 1 lacune · cibles : Réservoir de l’espace 2, Épinard.")
    # Aucune mesure d'EC : c'est « aucune mesure », jamais une moyenne de 0.
    absent = chart_summary(points, "ec", "EC", "mS/cm", "Europe/Paris", names)
    assert "aucune mesure · 3 lacunes" in absent and "0.00" not in absent
    assert chart_summary([], "ph", "pH", "", "Europe/Paris", names) == "pH · aucune mesure sur ce filtre."


async def test_courbes_portent_leur_synthese_et_leurs_reperes(cultures):
    """Le magasin livre variantes, légende et synthèses : le gabarit et le script les rendent."""
    lot = await cultures.call("mutate", create("Lot repère"))
    await cultures.call("solution_mutate", entry("renewal", "2026-08-01"))
    await cultures.call("solution_mutate", entry("reading", "2026-08-02", ph=6.1))
    await cultures.call("solution_mutate", entry("reading", "2026-08-03", reservoir_id=None,
                                                 targets=[lot["subject_id"]], ph=6.5))
    data = await cultures.call("solution_data")
    assert {point["variant"] for point in data["chart"]} == {0, 1}
    labels = [source["label"] for source in data["chart_sources"]]
    assert any(label.startswith("Réservoir de l’espace 2 · solution ") for label in labels)
    assert "Lot repère · solution manuelle" in labels
    assert "2 mesures" in data["chart_summaries"]["ph"]
    assert "minimum 6.10" in data["chart_summaries"]["ph"] and "maximum 6.50" in data["chart_summaries"]["ph"]
    assert data["chart_summaries"]["ec"].startswith("EC · ") and "aucune mesure" in data["chart_summaries"]["ec"]
