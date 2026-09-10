#!/usr/bin/env python3
"""Banc HTTP isolé, sans matériel : 30/90/365 jours, aucune base existante ouverte."""
import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from aiohttp import ClientSession, ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from tests import ui_server
from tests.test_cultures import create, event
from tests.test_culture_cycles import photo_bytes, reminder
from tests.test_culture_solutions import entry


class Elements(HTMLParser):
    """Compte les balises HTML ; le DOM après JavaScript est mesuré par measure_pages.js."""
    def __init__(self):
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag, attrs):
        self.count += 1

    def handle_startendtag(self, tag, attrs):
        self.count += 1


async def scenario(days, repetitions):
    stores = []
    original = ui_server.CultureStore

    def capture(*args, **kwargs):
        store = original(*args, **kwargs)
        stores.append(store)
        return store

    # Réutilise exactement le serveur/faux matériels de la suite, en capturant son
    # store temporaire. Aucun chemin de base ne peut être fourni par l'appelant.
    ui_server.CultureStore = capture
    try:
        app = ui_server.build_app()
    finally:
        ui_server.CultureStore = original
    store = stores[0]
    client = TestClient(TestServer(app), timeout=ClientTimeout(total=20))
    try:
        start = datetime.now(timezone.utc).date() - timedelta(days=days)
        first = start.isoformat()
        # Trois mères actives donnent des listes, sélecteurs et séries moins artificiels
        # qu'une unique fiche, tout en respectant l'espace 2 exclusif du carnet.
        subjects = [await store.call("mutate", create(f"Mère benchmark {index}", "mother",
                    origin_at=first, space_at=first, stage_at=first)) for index in range(1, 4)]
        counts = {"days": days, "subjects": len(subjects), "readings": 0, "reminders": 0, "photos": 0}
        for index in range(days):
            day = (start + timedelta(days=index)).isoformat()
            for subject_index, subject in enumerate(subjects):
                await store.call("solution_mutate", entry("reading", day, reservoir_id=None,
                    targets=[subject["subject_id"]], ph=None if (index + subject_index) % 7 == 0 else 5.8 + (index + subject_index) % 6 / 10,
                    ec=1.2 + (index + subject_index) % 4 / 10))
                counts["readings"] += 1
                if index % 7 == 0:
                    await store.call("cycle_mutate", reminder(subject["subject_id"], due_date=day, interval_days=0))
                    counts["reminders"] += 1
                    # Une observation de culture est une note ; les observations d'espace
                    # suivent une autre API et ne servent pas de support à une photo de fiche.
                    subjects[subject_index] = await event(store, subject, "note", day, {"note": "Observation synthétique"})
                    note = subjects[subject_index]
                    await store.call("media_add", {"request_id": str(uuid.uuid4()), "subject_id": note["subject_id"],
                        "event_id": note["event_id"], "event_revision": note["event_revision"], "caption": "Photo factice"}, photo_bytes(exif=False))
                    counts["photos"] += 1
        await client.start_server()
        rows = []
        for route in ROUTES + [f"/cultures/{subjects[0]['subject_id']}"]:
            elapsed = []
            for _ in range(repetitions):
                before = time.perf_counter()
                response = await client.get(route)
                body = await response.read()
                elapsed.append((time.perf_counter() - before) * 1000)
                if response.status != 200:
                    raise RuntimeError(f"{route}: HTTP {response.status}")
            parser = Elements()
            parser.feed(body.decode("utf-8"))
            rows.append({"route": route, "html_bytes": len(body), "html_elements": parser.count,
                "html_ms_median": round(statistics.median(elapsed), 2), "html_ms_max": round(max(elapsed), 2)})
        return {"fixture": counts, "pages": rows}
    finally:
        await client.close()
        await store.close()
        app["ui_test_temporary"].cleanup()


ROUTES = ["/", "/alarms", "/history", "/conf", "/console", "/cultures", "/cultures/solutions",
          "/cultures/cycles", "/cultures/targets", "/cultures/light", "/cultures/equipment",
          "/cultures/journal"]


def base_origin(value):
    """Origine HTTP(S) nue : ni identifiant, ni chemin, ni requête, ni fragment."""
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise argparse.ArgumentTypeError("--base-url doit être une URL http(s) absolue.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise argparse.ArgumentTypeError("--base-url doit être une origine nue, sans identifiant ni chemin.")
    return f"{parsed.scheme}://{parsed.netloc}"


async def external(base_url, repetitions, subject_id):
    """Banc sur cible réelle (fiche R4.2) : **GET seulement**, aucune base générée.

    Le carnet représentatif ne peut pas être fabriqué depuis ici : le faire supposerait
    d'écrire dans la base visée, et la fiche interdit expressément la base vivante. La
    restauration sur une **copie isolée** est un geste opérateur, documenté par
    `scripts/restore-cultures.py` ; ce mode-ci se contente de lire ce qui est servi.
    """
    routes = list(ROUTES)
    if subject_id:
        routes.append(f"/cultures/{subject_id}")
    rows = []
    timeout = ClientTimeout(total=30)
    async with ClientSession(timeout=timeout) as session:
        for route in routes:
            elapsed = []
            body = b""
            for _ in range(repetitions):
                before = time.perf_counter()
                # `allow_redirects=False` : une redirection mesurerait deux pages et
                # masquerait le fait que la route visée n'est pas celle qui répond.
                async with session.get(f"{base_url}{route}", allow_redirects=False) as response:
                    body = await response.read()
                    elapsed.append((time.perf_counter() - before) * 1000)
                    if response.status != 200:
                        raise RuntimeError(f"{route}: HTTP {response.status}")
            parser = Elements()
            parser.feed(body.decode("utf-8", errors="replace"))
            rows.append({"route": route, "html_bytes": len(body), "html_elements": parser.count,
                "html_ms_median": round(statistics.median(elapsed), 2), "html_ms_max": round(max(elapsed), 2)})
    return {"fixture": {"days": None, "source": "cible externe, carnet non fabriqué ici"}, "pages": rows}


async def main(args):
    result = {"measured_at": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "python": platform.python_version(), "repetitions": args.repetitions, "scenarios": []}
    if args.base_url:
        result["base_url"] = args.base_url
        result["mode"] = "cible externe (lecture seule)"
        result["scenarios"].append(await external(args.base_url, args.repetitions, args.subject_id))
    else:
        result["mode"] = "base temporaire locale"
        for days in args.days:
            result["scenarios"].append(await scenario(days, args.repetitions))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, nargs="+", choices=(30, 90, 365), default=[30, 90, 365])
    parser.add_argument("--repetitions", type=int, choices=range(1, 21), default=5)
    parser.add_argument("--output", type=Path, default=Path("test-results/web-perf.json"))
    parser.add_argument("--base-url", type=base_origin,
                        help="origine du Pi de qualification ; lecture seule, aucune base générée")
    parser.add_argument("--subject-id", help="fiche de culture à mesurer en plus, en mode cible externe")
    parsed = parser.parse_args()
    # `PHYTO_UI_BASE_URL` sert de valeur par défaut, mais passe par la **même** validation
    # que l'option : une variable d'environnement n'est pas une origine de confiance.
    if not parsed.base_url and os.environ.get("PHYTO_UI_BASE_URL"):
        try:
            parsed.base_url = base_origin(os.environ["PHYTO_UI_BASE_URL"])
        except argparse.ArgumentTypeError as erreur:
            parser.error(f"PHYTO_UI_BASE_URL : {erreur}")
    if parsed.base_url:
        # Refus net plutôt que génération silencieuse : fabriquer le carnet supposerait
        # d'écrire dans la base visée, ce que la fiche R4.2 interdit.
        if parsed.days != [30, 90, 365]:
            parser.error("--days est sans effet sur une cible externe : le carnet doit y être "
                         "restauré au préalable sur une copie isolée (scripts/restore-cultures.py).")
    elif parsed.subject_id:
        parser.error("--subject-id n'a de sens qu'avec --base-url.")
    asyncio.run(main(parsed))
