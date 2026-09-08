"""Bloc « Aujourd'hui » de l'accueil, seaux de rappels et identité de l'entrée écrite."""

import uuid

import pytest

from model.culture import CultureConflict
from model.culture_cycle import reminder_buckets
from model.culture_journal import TODAY_JOURNAL
from tests.test_culture_cycles import photo_bytes, reminder
from tests.test_cultures import create, cultures, event  # noqa: F401  (fixtures)
from tests.test_http_server import CSRF_TOKEN, web_context  # noqa: F401  (fixture)

HEADERS = {"X-CSRF-Token": CSRF_TOKEN}
REMINDER_KEYS = {"id", "revision", "title", "due_date", "state", "interval_days",
                 "completed_at", "target"}


def row(state="planned", due="2026-09-07", completed=None, recorded="2026-09-07T15:00:00+00:00"):
    return {"id": due + state, "state": state, "due_date": due,
            "completed_at": completed, "recorded_at": recorded}


def test_seaux_de_rappels_classent_sans_rien_inventer():
    rows = [row("planned", "2026-09-01"), row("postponed", "2026-09-07"),
            row("planned", "2026-09-20"), row("done", "2026-09-05", "2026-09-07T15:00:00+00:00"),
            row("cancelled", "2026-09-05", None, "2026-09-07T09:00:00+00:00"),
            row("done", "2026-09-04", "2026-09-05T15:00:00+00:00")]
    buckets = reminder_buckets(rows, "2026-09-07", "Europe/Paris")
    assert [r["due_date"] for r in buckets["overdue"]] == ["2026-09-01"]
    assert [r["due_date"] for r in buckets["due_today"]] == ["2026-09-07"]
    assert [r["due_date"] for r in buckets["upcoming"]] == ["2026-09-20"]
    # Deux clôtures du jour ; celle d'avant-hier reste hors du bloc.
    assert [r["due_date"] for r in buckets["done_today"]] == ["2026-09-05", "2026-09-05"]
    assert reminder_buckets([], "2026-09-07") == {"overdue": [], "due_today": [],
                                                  "upcoming": [], "done_today": []}


def test_bascule_de_jour_locale_des_cloture():
    # 22 h 30 UTC = 00 h 30 heure d'été à Paris : la clôture appartient au lendemain local.
    late = row("done", "2026-09-06", "2026-09-06T22:30:00+00:00")
    assert reminder_buckets([late], "2026-09-06", "Europe/Paris")["done_today"] == []
    assert reminder_buckets([late], "2026-09-07", "Europe/Paris")["done_today"] == [late]
    # En UTC, la même clôture reste celle du 6.
    assert reminder_buckets([late], "2026-09-06", "UTC")["done_today"] == [late]
    # Un horodatage absent ou illisible ne devient jamais « clos aujourd'hui ».
    assert reminder_buckets([row("done", "2026-09-06", None, "")], "2026-09-07")["done_today"] == []


async def seed_reminders(store, subject_id):
    for due in ("2026-09-01", "2026-09-07", "2026-09-20"):
        await store.call("cycle_mutate", reminder(subject_id, due_date=due))
    closed = await store.call("cycle_mutate", reminder("reservoir_2", due_date="2026-09-05",
                                                       interval_days=0, title="Rincer le bac"))
    await store.call("cycle_mutate", {"operation": "reminder_action", "request_id": str(uuid.uuid4()),
                                      "id": closed["id"], "version": closed["version"], "action": "done"})


async def test_agenda_absent_par_defaut_present_sur_demande(cultures):
    lot = await cultures.call("mutate", create())
    await seed_reminders(cultures, lot["subject_id"])
    assert "agenda" not in await cultures.call("overview")
    agenda = (await cultures.call("overview", False, 0, True))["agenda"]
    assert set(agenda) == {"reminders", "journal", "journal_truncated"}
    reminders = agenda["reminders"]
    assert set(reminders) == {"overdue", "due_today", "upcoming_count", "done_today"}
    assert [r["due_date"] for r in reminders["overdue"]] == ["2026-09-01"]
    assert [r["due_date"] for r in reminders["due_today"]] == ["2026-09-07"]
    assert reminders["upcoming_count"] == 1
    assert set(reminders["overdue"][0]) == REMINDER_KEYS
    assert reminders["overdue"][0]["target"] == {"kind": "culture", "id": lot["subject_id"],
                                                 "name": "Semis"}
    closed = reminders["done_today"][0]
    assert closed["state"] == "done" and closed["completed_at"]
    assert closed["target"] == {"kind": "reservoir", "id": "reservoir_2",
                                "name": "Réservoir de l’espace 2"}


async def test_agenda_vide_n_invente_aucun_zero(cultures):
    agenda = (await cultures.call("overview", False, 0, True))["agenda"]
    assert agenda == {"reminders": {"overdue": [], "due_today": [], "upcoming_count": 0,
                                    "done_today": []},
                      "journal": [], "journal_truncated": False}


async def test_agenda_journal_borne_et_enrichi(cultures):
    lot = await cultures.call("mutate", create())
    for day in range(2, 8):
        lot = await event(cultures, lot, "note", f"2026-09-0{day}", {"note": f"Observation {day}"})
    agenda = (await cultures.call("overview", False, 0, True))["agenda"]
    assert len(agenda["journal"]) == TODAY_JOURNAL and agenda["journal_truncated"] is True
    first = agenda["journal"][0]
    # Enrichissement identique à celui du journal complet : libellés et cible résolus.
    assert first["note"] == "Observation 7" and first["source_label"] == "Culture"
    assert first["targets"] == [{"kind": "subject", "id": lot["subject_id"], "name": "Semis"}]
    assert first["link"] == "/cultures/" + lot["subject_id"]


async def test_agenda_seulement_sur_l_accueil_des_cultures_actives(web_context):
    client, server, *_ = web_context
    calls = []
    original = server.cultures.store.call
    async def spy(operation, *args):
        calls.append((operation, args))
        return await original(operation, *args)
    server.cultures.store.call = spy
    saved = await (await client.post("/api/v1/cultures", headers=HEADERS, json=create())).json()

    def last_overview():
        return next(args for operation, args in reversed(calls) if operation == "overview")

    assert (await client.get("/cultures")).status == 200
    assert last_overview()[2] is True
    assert (await client.get("/cultures?archives=1")).status == 200
    assert last_overview()[2] is False
    assert (await client.get("/cultures/" + saved["subject_id"])).status == 200
    assert last_overview()[2] is False
    assert "agenda" not in await (await client.get("/api/v1/cultures")).json()
    assert "agenda" in await (await client.get("/api/v1/cultures?agenda=1")).json()


async def test_detail_porte_ses_rappels_ses_photos_et_ses_actions(cultures):
    lot = await cultures.call("mutate", create(space="space_2"))
    await cultures.call("cycle_mutate", reminder(lot["subject_id"], due_date="2026-09-01"))
    detail = await cultures.call("detail", lot["subject_id"])
    assert set(detail["reminders"]) == {"overdue", "due_today", "upcoming", "done_today"}
    assert len(detail["reminders"]["overdue"]) == 1
    assert set(detail["reminders"]["overdue"][0]) == REMINDER_KEYS
    assert detail["media"] == []
    assert detail["actions"] == {"primary": ["reading", "observation", "stage"],
                                 "other": ["move", "loss", "harvest", "identity"]}
    added = await cultures.call("media_add", {"request_id": str(uuid.uuid4()),
        "subject_id": lot["subject_id"], "event_id": detail["events"][0]["id"],
        "event_revision": detail["events"][0]["revision"], "caption": "Bouture"}, photo_bytes())
    detail = await cultures.call("detail", lot["subject_id"])
    assert [photo["id"] for photo in detail["media"]] == [added["id"]]


async def test_cycle_data_inchange_par_les_seaux(cultures):
    lot = await cultures.call("mutate", create())
    await seed_reminders(cultures, lot["subject_id"])
    data = await cultures.call("cycle_data")
    today = data["today"]
    rows = data["reminders"]
    assert today == "2026-09-07" and len(rows) == 4
    for item in rows:
        # Règle d'origine rejouée telle quelle : déplacer le classement en pur ne
        # change ni les drapeaux, ni les révisions attachées à chaque rappel.
        assert "revisions" in item
        open_state = item["state"] in ("planned", "postponed")
        assert item["overdue"] is (open_state and item["due_date"] < today)
        assert item["due_today"] is (open_state and item["due_date"] == today)
    focused = await cultures.call("cycle_data", [lot["subject_id"]])
    assert len(focused["reminders"]) == 3 and focused["reminders"][0]["revisions"] == []


async def test_identite_de_l_entree_ecrite(cultures):
    lot = await cultures.call("mutate", create(origin_at="2026-07-01", space_at="2026-07-01"))
    # Une création écrit trois événements et n'en désigne aucun.
    assert "event_id" not in lot and "event_revision" not in lot
    command = {"request_id": str(uuid.uuid4()), "operation": "event", "subject_id": lot["subject_id"],
               "version": lot["version"], "kind": "note", "effective_at": "2026-08-05",
               "payload": {"note": "Observation"}}
    noted = await cultures.call("mutate", command)
    assert noted["event_revision"] == 1 and noted["event_id"]
    # Rejeu de la même clé : le même résultat, donc la même ancre et la même photo possible.
    assert await cultures.call("mutate", command) == noted
    with pytest.raises(CultureConflict):
        await cultures.call("mutate", {**command, "effective_at": "2026-08-06"})
    corrected = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "subject_id": lot["subject_id"], "version": noted["version"], "event_id": noted["event_id"],
        "effective_at": "2026-08-06", "payload": {"note": "Corrigée"}, "reason": "Date"})
    assert corrected["event_id"] == noted["event_id"] and corrected["event_revision"] == 2
    backfilled = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "backfill",
        "subject_id": lot["subject_id"], "version": corrected["version"],
        "steps": [{"kind": "move", "effective_at": "2026-07-15", "payload": {"space": "space_2"}}]})
    assert "event_id" not in backfilled


async def test_observation_puis_photo_puis_correction(cultures):
    lot = await cultures.call("mutate", create())
    noted = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "event",
        "subject_id": lot["subject_id"], "version": lot["version"], "kind": "note",
        "effective_at": "2026-08-05", "payload": {"note": "Observation"}})
    photo = {"request_id": str(uuid.uuid4()), "subject_id": lot["subject_id"],
             "event_id": noted["event_id"], "event_revision": noted["event_revision"],
             "caption": "Feuille"}
    assert (await cultures.call("media_add", photo, photo_bytes()))["saved"]
    corrected = await cultures.call("mutate", {"request_id": str(uuid.uuid4()), "operation": "correct",
        "subject_id": lot["subject_id"], "version": noted["version"], "event_id": noted["event_id"],
        "effective_at": "2026-08-06", "payload": {"note": "Corrigée"}, "reason": "Date"})
    # La révision a bougé : une photo envoyée sur l'ancienne version est refusée, pas rattachée
    # au hasard à la nouvelle.
    with pytest.raises(CultureConflict):
        await cultures.call("media_add", {**photo, "request_id": str(uuid.uuid4())}, photo_bytes())
    assert (await cultures.call("media_add", {**photo, "request_id": str(uuid.uuid4()),
        "event_revision": corrected["event_revision"]}, photo_bytes()))["saved"]
