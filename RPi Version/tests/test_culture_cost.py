"""Coût des lectures du carnet sur le thread unique : projections comptées, pas devinées.

Une projection complète relit tous les événements, toutes les origines et rejoue `project()`
pour chaque culture. Sur un Raspberry Pi et un carnet de deux ans, c'est la lecture la plus
chère du magasin, et les lots 2 et 3 en avaient ajouté trois par ouverture de fiche sans que
rien ne le mesure. Ces tests comptent les appels : une régression de coût devient un échec,
pas une lenteur constatée six mois plus tard.
"""

import uuid

import pytest

from tests.test_cultures import create, cultures, event  # noqa: F401  (fixtures)
from tests.test_culture_solutions import entry


class Counter:
    """Compteur d'appels à `_projections`, posé sur l'instance et non sur la classe."""

    def __init__(self, store):
        self.store = store
        self.original = store._projections
        self.calls = 0
        store._projections = self

    def __call__(self):
        self.calls += 1
        return self.original()


@pytest.fixture
def counted(cultures):
    counter = Counter(cultures)
    yield cultures, counter
    cultures._projections = counter.original


async def seeded(store):
    """Un lot alimenté par le réservoir de l'espace 2, avec un relevé mesuré."""
    lot = await store.call("mutate", create(space="space_2"))
    await store.call("solution_mutate", entry())
    await store.call("solution_mutate", entry("reading", "2026-08-05", ph=6.1, ec=1.4))
    return lot


async def test_accueil_fiche_et_assistance_ne_projettent_qu_une_fois(counted):
    store, counter = counted
    lot = await seeded(store)
    identifier = lot["subject_id"]

    for label, call in (("overview", ("overview",)),
                        ("overview+agenda", ("overview", False, 0, True)),
                        ("detail", ("detail", identifier)),
                        ("assistance", ("assistance", identifier))):
        counter.calls = 0
        await store.call(*call)
        assert counter.calls == 1, f"{label} : {counter.calls} projections"

    # Une page de fiche enchaîne l'accueil puis le détail : deux appels, donc au plus deux
    # projections — une par requête du magasin, jamais quatre comme avant le correctif.
    counter.calls = 0
    await store.call("overview", False, 0, False)
    await store.call("detail", identifier)
    assert counter.calls == 2


async def test_assistance_a_version_inchangee_ne_projette_rien(counted):
    store, counter = counted
    lot = await seeded(store)
    identifier = lot["subject_id"]

    counter.calls = 0
    first = await store.call("assistance", identifier, None)
    token = first["version"]
    assert "items" in first and counter.calls == 1

    counter.calls = 0
    fresh = await store.call("assistance", identifier, token)
    assert fresh == {"unchanged": True, "version": token, "valid_for_seconds": 30,
                     "generated_at": store.now().isoformat()}
    assert counter.calls == 0

    # Un jeton périmé refait le calcul complet : l'aide ne peut pas rester sur un parcours
    # qui a changé.
    counter.calls = 0
    stale = await store.call("assistance", identifier, "0:jeton-perime")
    assert "items" in stale and stale["version"] == token and counter.calls == 1

    # Un jeton absent aussi : c'est le cas d'un premier chargement.
    counter.calls = 0
    assert "items" in await store.call("assistance", identifier, None)
    assert counter.calls == 1

    # Après une mutation de parcours, le jeton que le client affichait ne vaut plus.
    await event(store, lot, "note", "2026-09-01", {"note": "Observation"})
    counter.calls = 0
    after = await store.call("assistance", identifier, token)
    assert "items" in after and after["version"] != token and counter.calls == 1
    counter.calls = 0
    assert (await store.call("assistance", identifier, after["version"]))["unchanged"]
    assert counter.calls == 0


async def test_jeton_d_assistance_suit_les_rappels_pas_seulement_le_parcours(counted):
    """Un rappel accompli invalide le jeton (D-3).

    La version du sujet ne bouge qu'aux événements de parcours : seule elle, l'aide
    « Ouvrir le rappel » restait affichée jusqu'au rechargement de la page, le serveur
    répondant « inchangé » alors que le rappel était clos. La comparaison porte donc sur un
    jeton opaque qui inclut aussi les rappels, vérifications, photos et dernier relevé du
    sujet — sans projection : c'est l'objet du compteur ci-dessous.
    """
    store, counter = counted
    lot = await seeded(store)
    identifier = lot["subject_id"]
    token = (await store.call("assistance", identifier, None))["version"]

    reminder = await store.call("cycle_mutate", {"operation": "reminder", "request_id": str(uuid.uuid4()),
        "target": identifier, "title": "Contrôler la solution", "due_date": "2026-08-10",
        "interval_days": 0, "note": ""})
    counter.calls = 0
    opened = await store.call("assistance", identifier, token)
    assert "items" in opened and opened["version"] != token
    assert any(item["id"] == "reminder-" + reminder["id"] for item in opened["items"])

    await store.call("cycle_mutate", {"operation": "reminder_action", "request_id": str(uuid.uuid4()),
        "id": reminder["id"], "version": reminder["version"], "action": "done", "note": ""})
    counter.calls = 0
    closed = await store.call("assistance", identifier, opened["version"])
    assert "items" in closed, "un rappel accompli doit invalider le jeton"
    assert not any(item["id"].startswith("reminder-") for item in closed["items"])
    # Le jeton reste inchangé tant que rien ne bouge, et sa vérification ne projette rien.
    counter.calls = 0
    assert (await store.call("assistance", identifier, closed["version"]))["unchanged"]
    assert counter.calls == 0


async def test_assistance_a_version_inchangee_refuse_une_fiche_inconnue(cultures):
    from model.culture import CultureError
    with pytest.raises(CultureError, match="introuvable"):
        await cultures.call("assistance", "inconnu", "1:0:0:0:0:0:-")


async def test_dernier_releve_d_un_sujet_egale_la_lecture_integrale(cultures):
    """Équivalence stricte entre la lecture bornée et l'export qu'elle remplace.

    C'est le seul garde-fou qui compte : la requête d'un seul sujet reproduit la règle de
    `_solution_data` — cible directe ou alimentation couvrant la date —, et un cas où les
    deux divergeraient serait un dernier relevé faux sur la fiche.
    """
    fed = await cultures.call("mutate", create("Alimenté", space="space_2"))
    direct = await cultures.call("mutate", create("Ciblé", space="space_1"))
    # Un lot de semis de l'espace 1 n'est alimenté par aucun réservoir : son dernier
    # relevé doit rester une absence, jamais le relevé d'un voisin.
    orphan = await cultures.call("mutate", create("Sans relevé", space="space_1"))

    async def compare():
        full = await cultures.call("latest_solution_readings")
        for subject in (fed, direct, orphan):
            identifier = subject["subject_id"]
            assert await cultures.call("latest_reading", identifier) == full.get(identifier), identifier
            rows = await cultures.call("solution_data", {"target": identifier}, 0, True)
            summary = await cultures.call("reading_summary", identifier)
            for metric in ("ph", "ec"):
                values = [row[metric] for row in rows if not row["cancelled"] and row[metric] is not None]
                assert summary[metric] == {"count": len(values), "minimum": min(values) if values else None,
                    "maximum": max(values) if values else None,
                    "mean": pytest.approx(sum(values) / len(values)) if values else None}


    await cultures.call("solution_mutate", entry())
    await compare()
    # Relevé du réservoir : il vaut pour le lot alimenté, pour personne d'autre.
    await cultures.call("solution_mutate", entry("reading", "2026-08-05", ph=6.0, ec=1.2))
    await compare()
    assert (await cultures.call("latest_reading", fed["subject_id"]))["ph"] == 6.0
    assert await cultures.call("latest_reading", direct["subject_id"]) is None
    # Relevé visant explicitement une culture, sans réservoir.
    await cultures.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
        "kind": "reading", "reservoir_id": None, "targets": [direct["subject_id"]],
        "effective_at": "2026-08-06", "ph": 5.9})
    await compare()
    assert (await cultures.call("latest_reading", direct["subject_id"]))["ph"] == 5.9
    # Un relevé plus récent l'emporte ; un renouvellement postérieur ouvre une seconde
    # période et une seconde association sans effacer la dernière mesure connue.
    await cultures.call("solution_mutate", entry("reading", "2026-08-07", ph=6.4))
    await cultures.call("solution_mutate", entry("renewal", "2026-08-08"))
    await compare()
    assert (await cultures.call("latest_reading", fed["subject_id"]))["ph"] == 6.4
    assert await cultures.call("latest_reading", orphan["subject_id"]) is None
    # Relevé « avant » horodaté à la seconde exacte d'un renouvellement : c'est la branche
    # spéciale de la requête (`]début ; fin]` au lieu de `[début ; fin[`), celle qui
    # rattache la mesure à la solution **précédente**. Sans elle, la période lue serait la
    # nouvelle et le dernier relevé d'une fiche pourrait diverger de l'export.
    renewal = await cultures.call("solution_mutate", entry("renewal", "2026-08-09"))
    await cultures.call("solution_mutate", entry("reading", "2026-08-09", ph=5.7,
                                                 intervention_id=renewal["id"], context="before"))
    await compare()
    assert (await cultures.call("latest_reading", fed["subject_id"]))["ph"] == 5.7


async def test_dernier_releve_annule_ou_corrige_suit_la_revision_courante(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    await cultures.call("solution_mutate", entry())
    command = entry("reading", "2026-08-05", ph=6.0)
    saved = await cultures.call("solution_mutate", command)
    assert (await cultures.call("latest_reading", lot["subject_id"]))["ph"] == 6.0
    corrected = await cultures.call("solution_mutate", {**command, "operation": "correct",
        "request_id": str(uuid.uuid4()), "id": saved["id"], "version": saved["version"],
        "ph": 6.3, "reason": "Sonde relue"})
    assert (await cultures.call("latest_reading", lot["subject_id"]))["ph"] == 6.3
    await cultures.call("solution_mutate", {**command, "operation": "correct",
        "request_id": str(uuid.uuid4()), "id": corrected["id"], "version": corrected["version"],
        "cancelled": True, "reason": "Mesure saisie par erreur"})
    assert await cultures.call("latest_reading", lot["subject_id"]) is None
    assert (await cultures.call("latest_solution_readings")).get(lot["subject_id"]) is None


async def test_comparaison_agrege_sans_export_ni_projection_repetee(counted):
    store, counter = counted
    lot = await seeded(store)
    identifier = lot["subject_id"]
    command = entry("reading", "2026-08-06", ph=0, ec=0)
    saved = await store.call("solution_mutate", command)
    await store.call("solution_mutate", {**command, "operation": "correct", "request_id": str(uuid.uuid4()),
        "id": saved["id"], "version": saved["version"], "ph": 6.3, "reason": "Correction"})
    expected = await store.call("solution_data", {"target": identifier}, 0, True)
    expected = [row for row in expected if not row["cancelled"]]
    original = store._solution_data
    def forbidden(*args, **kwargs):
        raise AssertionError("La comparaison ne doit pas exporter les relevés")
    store._solution_data = forbidden
    counter.calls = 0
    try:
        summary = (await store.call("cycle_data", [identifier]))["summaries"][0]
        assert counter.calls == 1
        for metric in ("ph", "ec"):
            values = [row[metric] for row in expected if row[metric] is not None]
            assert summary["measures"][metric] == {"count": len(values), "minimum": min(values),
                "maximum": max(values), "mean": pytest.approx(sum(values) / len(values))}
    finally:
        store._solution_data = original


async def test_recherche_comparaison_bornee_conserve_selection(cultures):
    for i in range(43):
        await cultures.call("mutate", create(f"Mère {i:02}", "mother"))
    first = await cultures.call("cycle_data")
    assert len(first["comparison_choices"]) == 40
    chosen = first["comparison_choices"][0]["id"]
    second = await cultures.call("cycle_data", [chosen], 0, None, 0, None, "", 40)
    assert len(second["comparison_choices"]) == 4
    assert second["comparison_choices"][0]["id"] == chosen
    filtered = await cultures.call("cycle_data", [chosen], 0, None, 0, None, "introuvable")
    assert filtered["selection_total"] == 0
    assert [s["id"] for s in filtered["comparison_choices"]] == [chosen]
