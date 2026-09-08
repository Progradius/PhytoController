"""Repères d'éclairage (lot F) : rapprochement en lecture seule, sans aucun ordre.

Cette vue lit la configuration déjà distribuée (`self.server.config`), le catalogue
d'équipements et le registre d'observabilité déjà publiés par les boucles métier. Elle
n'écrit jamais `param.json`, ne commande aucune sortie, ne relit aucun capteur et ne crée
aucune alarme : l'écart entre un repère et les horaires configurés reste une information.
"""

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError, SPACES, STAGES
from model.culture_light import (LIGHT_PRESETS, LIGHT_SCOPES, compare_light, duration_label,
                                 schedule_crosses_midnight, schedule_on_minutes)
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable
from utils.operational_state import snapshot as operational_snapshot
from utils.schedule import day_night_times

# Convention déjà portée par la page des cultures et la liste de vérification :
# l'espace 1 est éclairé par la minuterie quotidienne 1, l'espace 2 par la 2.
SPACE_TIMERS = {"space_1": 1, "space_2": 2}
# Libellés de l'état déjà publié ; aucune interprétation nouvelle n'est produite ici.
STATE_LABELS = {"on": "marche", "off": "arrêt", "unknown": "inconnu"}
TRACKING_LABELS = {"ok": "consigne et état relu concordants",
                   "mismatch": "écart entre la consigne et l’état relu",
                   "known_hardware_fault": "panne matérielle déjà déclarée",
                   "unknown": "non vérifiable"}


class LightViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return [web.get("/cultures/light", self.page),
                web.get("/api/v1/cultures/light", self.data),
                web.post("/api/v1/cultures/light", self.mutate)]

    @staticmethod
    def filters(request):
        return {key: request.query[key] for key in ("scope", "target", "stage") if request.query.get(key)}

    def _actuators(self):
        """Photographie déjà produite pour le tableau de bord ; aucune lecture neuve ici."""
        service = getattr(self.server, "operator_service", None)
        try:
            return service.actuator_snapshot() if service is not None else operational_snapshot()
        except Exception:
            # L'état opérationnel est un diagnostic : son absence se présente,
            # elle ne fait jamais échouer la lecture du carnet.
            return {}

    def _state(self, entries, equipment_id):
        """État opérationnel d'un équipement, ou son indisponibilité explicite."""
        catalog = self.server.equipment_store.payload().get(equipment_id, {})
        entry = entries.get(equipment_id)
        state = {"equipment_id": equipment_id,
                 "name": catalog.get("display_name", equipment_id),
                 "out_of_service": bool(catalog.get("out_of_service")),
                 "available": entry is not None}
        for key in ("requested", "applied", "actual", "tracking", "reason", "mode",
                    "stale", "age_seconds", "since_seconds", "actual_status"):
            state[key] = entry.get(key) if entry else None
        return state

    def _lighting(self, entries):
        config = self.server.config
        timers = {}
        for space, number in SPACE_TIMERS.items():
            settings = config.daily_timer1 if number == 1 else config.daily_timer2
            schedule = {"start_hour": settings.start_hour, "start_minute": settings.start_minute,
                        "stop_hour": settings.stop_hour, "stop_minute": settings.stop_minute}
            minutes = schedule_on_minutes(schedule)
            timers[space] = {
                "number": number, "equipment_id": f"daily_{number}",
                "space_label": SPACES[space], "enabled": bool(settings.enabled),
                "schedule": schedule,
                "start": f"{schedule['start_hour']:02d}:{schedule['start_minute']:02d}",
                "stop": f"{schedule['stop_hour']:02d}:{schedule['stop_minute']:02d}",
                "on_minutes": minutes, "on_label": duration_label(minutes),
                "off_label": duration_label(1440 - minutes),
                "crosses_midnight": schedule_crosses_midnight(schedule),
                "empty": minutes == 0, "settings_url": f"/conf#daily-timer-{number}",
                "state": self._state(entries, f"daily_{number}")}
        return timers

    def _operational(self):
        """Sources existantes rassemblées : horaires, jour/nuit, ventilation commune."""
        config = self.server.config
        entries = self._actuators()
        start_h, start_m, stop_h, stop_m = day_night_times(config)
        return {"timers": self._lighting(entries),
                "ventilation": self._state(entries, "motor"),
                "day_night": {"source": config.day_night.source,
                              "start": f"{start_h:02d}:{start_m:02d}",
                              "stop": f"{stop_h:02d}:{stop_m:02d}",
                              "empty": (start_h, start_m) == (stop_h, stop_m)}}

    async def payload(self, request):
        data = await self.store.call("light_data", self.filters(request))
        operational = self._operational()
        for occupant in data["occupants"]:
            timer = operational["timers"].get(occupant["space"])
            occupant["timer"] = timer
            # Aucun repère résolu ⇒ aucun écart : jamais un repère standard implicite.
            occupant["comparison"] = compare_light(occupant["reference"], timer["schedule"]) if timer else None
        data["operational"] = operational
        return data

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template(
            "culture_light.html", page_title="Repères d’éclairage", current_page="cultures", culture_subjects=request.query.getall("subject", []),
            csrf_token=self.server.csrf_token, data=data, error=error,
            filters=self.filters(request), scopes=LIGHT_SCOPES, stages=STAGES, spaces=SPACES,
            presets=LIGHT_PRESETS, state_labels=STATE_LABELS,
            tracking_labels=TRACKING_LABELS), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call("light_mutate", await request.json()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)
