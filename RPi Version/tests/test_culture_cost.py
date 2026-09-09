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
    identifier, version = lot["subject_id"], lot["version"]

    counter.calls = 0
    fresh = await store.call("assistance", identifier, version)
    assert fresh == {"unchanged": True, "version": version, "valid_for_seconds": 30,
                     "generated_at": store.now().isoformat()}
    assert counter.calls == 0

    # Une version périmée refait le calcul complet : l'aide ne peut pas rester sur un
    # parcours qui a changé.
    counter.calls = 0
    stale = await store.call("assistance", identifier, version - 1)
    assert "items" in stale and stale["version"] == version and counter.calls == 1

    # Une version absente aussi : c'est le cas d'un premier chargement.
    counter.calls = 0
    assert "items" in await store.call("assistance", identifier, None)
    assert counter.calls == 1

    # Après une mutation, la version que le client affichait ne vaut plus.
    saved = await event(store, lot, "note", "2026-09-01", {"note": "Observation"})
    counter.calls = 0
    assert "items" in await store.call("assistance", identifier, version)
    assert counter.calls == 1
    counter.calls = 0
    assert (await store.call("assistance", identifier, saved["version"]))["unchanged"]
    assert counter.calls == 0


async def test_assistance_a_version_inchangee_refuse_une_fiche_inconnue(cultures):
    from model.culture import CultureError
    with pytest.raises(CultureError, match="introuvable"):
        await cultures.call("assistance", "inconnu", 1)


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
