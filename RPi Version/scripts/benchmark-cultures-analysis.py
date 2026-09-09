#!/usr/bin/env python3
"""Mesure reproductible du lot UI 4 sur un carnet synthétique temporaire, sans GPIO.

À lancer depuis la racine avec l'interpréteur du venv. Aucune base existante n'est
ouverte : les insertions massives ne concernent que le répertoire temporaire créé ici.
"""
import asyncio
import json
import statistics
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model.culture import SPACES, STAGES
from model.culture_cycle import CHECKLIST, REMINDER_STATES
from model.culture_solution import RESERVOIRS
from network.web.pages import env, ASSET_VERSIONS
from utils.culture_store import CultureStore


async def benchmark():
    now = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory(prefix="phyto-analysis-") as directory:
        store = CultureStore(Path(directory) / "cultures.sqlite3", now=lambda: now, reliable=lambda: True)
        try:
            subjects = []
            for index in range(44):
                result = await store.call("mutate", {"operation": "create", "request_id": str(uuid.uuid4()),
                    "kind": "mother", "name": f"Mère {index:02}", "variety": "Essai synthétique",
                    "origin_at": "2024-09-09", "space_at": "2024-09-09", "stage_at": "2024-09-09",
                    "stage": "maintien", "origins": []})
                subjects.append(result["subject_id"])
            await store.call("solution_mutate", {"operation": "entry", "request_id": str(uuid.uuid4()),
                "kind": "reading", "targets": [subjects[0]], "effective_at": "2024-09-10", "ph": 6.0})

            def seed():
                # Le carnet synthétique doit exercer les **deux** chemins d'attribution d'un
                # relevé, sans quoi la mesure ignore la branche la plus chère : la visée
                # directe (`solution_targets`) et l'alimentation datée (`solution_links`
                # jointes à `solution_periods`). Les renouvellements sont insérés en SQL
                # comme les relevés : aucune mutation n'est rejouée après ce semis, donc la
                # reconstruction des périodes ne les efface pas.
                row = dict(store._db.execute("SELECT * FROM solution_entries LIMIT 1").fetchone())
                row.pop("sequence")
                columns = tuple(row)
                sql = f"INSERT INTO solution_entries ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                start = now - timedelta(days=729)
                periods = []
                boundaries = [start + timedelta(days=30 * step) for step in range(25)]
                for step, opened in enumerate(boundaries):
                    closed = boundaries[step + 1] if step + 1 < len(boundaries) else None
                    periods.append((f"benchmark-periode-{step}", "reservoir_2", opened.isoformat(),
                                    closed.isoformat() if closed else None))
                with store._db:
                    store._db.executemany("INSERT INTO solution_periods VALUES (?,?,?,?)", periods)
                    # Les quatre cultures comparées sont alimentées sur tout le parcours :
                    # chaque période leur associe une ligne datée, comme une occupation
                    # continue de l'espace 2 en produirait.
                    store._db.executemany("INSERT INTO solution_links VALUES (?,?,?,?)",
                        [(period[0], subject, period[2], period[3]) for period in periods for subject in subjects[:4]])
                    for index in range(12000):
                        at = (start + timedelta(minutes=index * 80)).isoformat()
                        # Un relevé sur deux appartient au réservoir : il n'est rattaché à une
                        # culture que par l'association datée, l'autre moitié la vise.
                        fed = index % 2 == 0
                        values = {**row, "id": f"benchmark-{index}", "sort_at": at, "effective_at": at,
                                  "precision": "instant", "reservoir_id": "reservoir_2" if fed else None,
                                  "ph": None if index % 7 == 0 else 5.5 + index % 10 / 10,
                                  "ec": None if index % 5 == 0 else index % 20 / 10}
                        store._db.execute(sql, tuple(values[key] for key in columns))
                        if not fed:
                            store._db.execute("INSERT INTO solution_targets VALUES (?,1,?)", (values["id"], subjects[index % 4]))
                    first = int(start.timestamp()) // 3600 * 3600
                    for sensor, label, unit in (("BME280T", "Température", "°C"), ("BME280H", "Humidité", "%")):
                        store._db.executemany("INSERT INTO climate_hours VALUES (?,?,?,?,?,?,?,?,?)",
                            [(sensor, first + index * 3600, label, unit, 18, 24, 1260, 60, 60)
                             for index in range(729 * 24) if index % 11])

            def counts():
                # Volumétrie réellement insérée, comptée en base : les chiffres publiés ne
                # doivent pas être une reprise de la constante du semis.
                return {table: store._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in ("subjects", "solution_entries", "solution_targets",
                                      "solution_periods", "solution_links", "climate_hours")}
            store._seed_analysis = seed
            store._analysis_counts = counts
            await store.call("seed_analysis")
            volumes = await store.call("analysis_counts")
            results = {}
            for count in (1, 4):
                reads, renders = [], []
                for _ in range(5):
                    begin = time.perf_counter()
                    data = await store.call("cycle_data", subjects[:count])
                    reads.append((time.perf_counter() - begin) * 1000)
                    begin = time.perf_counter()
                    html = env.get_template("culture_cycles.html").render(asset_versions=ASSET_VERSIONS, page_title="Cycles et rappels", current_page="cultures",
                        csrf_token="benchmark", data=data, error=None, selected=subjects[:count], states=REMINDER_STATES,
                        checklist=CHECKLIST, reservoirs=RESERVOIRS, stages=STAGES, spaces=SPACES)
                    renders.append((time.perf_counter() - begin) * 1000)
                results[str(count)] = {"lecture_mediane_ms": round(statistics.median(reads), 1),
                    "lecture_max_ms": round(max(reads), 1), "rendu_jinja_mediane_ms": round(statistics.median(renders), 1),
                    "rendu_jinja_max_ms": round(max(renders), 1), "html_octets": len(html.encode()),
                    "points_climat": sum(len(s["climate"]["points"]) for s in data["summaries"]),
                    "choix_affiches": len(data["comparison_choices"])}
            sys.stdout.write(json.dumps({"cultures": volumes["subjects"], "releves": volumes["solution_entries"],
                "releves_vises": volumes["solution_targets"], "solution_periods": volumes["solution_periods"],
                "solution_links": volumes["solution_links"], "agregats_horaires": volumes["climate_hours"],
                "jours": 729, "mesures": results}, indent=2) + "\n")
        finally:
            await store.close()


if __name__ == "__main__":
    asyncio.run(benchmark())
