"""Interface du carnet, indépendante des commandes du contrôleur."""

from __future__ import annotations

import json

from aiohttp import web

from model.culture_solution import SOLUTION_KINDS
from model.culture import (CultureConflict, CultureError, KINDS, SPACES, STAGES, creation_stages,
                           first_stage)
from network.web.pages import render_template
from utils.culture_store import CultureStore, CultureUnavailable
from utils.time_reliability import time_reliability


def error_response(exc, status):
    """Réponse d'erreur unique de tout le carnet.

    `error` reste premier et inchangé ; `field` et `index` ne sont ajoutés que lorsque
    l'erreur désigne un contrôle précis. Une indisponibilité (503) n'en porte jamais :
    aucun champ n'est en cause, et en inventer un ferait chercher une faute de saisie
    là où c'est le carnet qui est absent.
    """
    payload = {"error": str(exc)}
    field = getattr(exc, "field", None)
    if field:
        payload["field"] = field
        index = getattr(exc, "index", None)
        if index is not None:
            payload["index"] = index
    return web.json_response(payload, status=status)


class CultureViews:
    def __init__(self, server, store=None):
        self.server = server
        self.store = store or CultureStore(reliable=lambda: time_reliability().state == "synchronized")

    def routes(self):
        from network.web.culture_cycles import CycleViews
        from network.web.culture_equipment import EquipmentViews
        from network.web.culture_journal import JournalViews
        from network.web.culture_light import LightViews
        from network.web.culture_targets import TargetsViews
        # Les quatre vues des lots E à H sont déjà agrégées ici : chaque lot remplit son
        # module sans revenir sur ce fichier partagé.
        sections = (CycleViews(self), TargetsViews(self), LightViews(self),
                    EquipmentViews(self), JournalViews(self))
        return [route for section in sections for route in section.routes()] + [
                web.get("/cultures/solutions", self.solutions_page),
                web.get("/api/v1/cultures/solutions", self.solutions),
                web.post("/api/v1/cultures/solutions", self.solution_mutate),
                web.get("/api/v1/cultures/solutions/export", self.solution_export),
                web.get("/cultures", self.page), web.get("/cultures/{subject_id}", self.page),
                web.get("/api/v1/cultures", self.overview),
                web.get("/api/v1/cultures/export", self.export),
                web.get("/api/v1/cultures/assistance/{subject_id}", self.assistance),
                web.post("/api/v1/cultures/preview/{domain}", self.preview),
                web.get("/api/v1/cultures/{subject_id}", self.detail),
                web.post("/api/v1/cultures", self.mutate)]

    async def close(self, _app):
        await self.store.close()

    @staticmethod
    def offset(request):
        try:
            offset = int(request.query.get("offset", "0"))
            if not 0 <= offset <= 1000000:
                raise ValueError()
            return offset
        except ValueError:
            raise web.HTTPBadRequest(text="Pagination invalide.") from None

    async def overview(self, request):
        try:
            return web.json_response(await self.store.call(
                "overview", request.query.get("archives") == "1", self.offset(request),
                request.query.get("agenda") == "1"))
        except CultureUnavailable as exc:
            return web.json_response({"available": False, "error": str(exc)}, status=503)

    async def detail(self, request):
        try:
            return web.json_response(await self.store.call("detail", request.match_info["subject_id"], self.offset(request)))
        except CultureError as exc:
            return error_response(exc, 404)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def assistance(self, request):
        try:
            return web.json_response(await self.store.call("assistance", request.match_info["subject_id"]))
        except CultureError as exc:
            return error_response(exc, 404)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def preview(self, request):
        try:
            return web.json_response(await self.store.call("preview", request.match_info["domain"],
                await request.json(), self.server.equipment_store.payload()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def mutate(self, request):
        try:
            command = await request.json()
            result = await self.store.call("mutate", command, self.server.equipment_store.payload())
            return web.json_response(result)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def export(self, request):
        format_name = request.query.get("format", "json")
        if format_name not in ("json", "csv", "sqlite3"):
            raise web.HTTPBadRequest(text="Format attendu : json, csv ou sqlite3.")
        try:
            if format_name == "json":
                body = json.dumps(await self.store.call("export"), ensure_ascii=False, indent=2).encode()
                mime = "application/json"
            elif format_name == "csv":
                body = ("\ufeff" + await self.store.call("csv")).encode()
                mime = "text/csv"
            else:
                body = await self.store.call("backup")
                mime = "application/octet-stream"
            return web.Response(body=body, content_type=mime,
                                headers={"Content-Disposition": f'attachment; filename="cultures.{format_name}"'})
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None

    async def page(self, request):
        archived = request.query.get("archives") == "1"
        subject_id = request.match_info.get("subject_id")
        offset = self.offset(request)
        detail, overview, error = None, None, None
        status = 200
        # Le bloc « Aujourd'hui » n'a de sens que sur l'accueil des cultures actives : une
        # fiche a le sien, et les archives n'ont ni rappel ni prochaine action.
        agenda = not subject_id and not archived
        try:
            overview = await self.store.call("overview", archived, 0 if subject_id else offset, agenda)
            if subject_id:
                detail = await self.store.call("detail", subject_id, offset)
        except CultureError as exc:
            error, status = str(exc), 404
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template(
            "cultures.html", page_title=detail["subject"]["name"] if detail else "Cultures",
            current_page="cultures", csrf_token=self.server.csrf_token,
            overview=overview, detail=detail, error=error, archives=archived,
            stages=STAGES, spaces=SPACES, event_kinds=KINDS,
            # Stades de départ et stades acceptés à la création, par type et origine : le
            # formulaire les lit en attributs de données, le script ne décide de rien.
            creation={"mother": {"first": first_stage("mother", None),
                                 "stages": creation_stages("mother", None)},
                      "seed": {"first": first_stage("lot", "seed"),
                               "stages": creation_stages("lot", "seed")},
                      "cutting": {"first": first_stage("lot", "cutting"),
                                  "stages": creation_stages("lot", "cutting")}},
            # Lecture de la configuration distribuée, aucune relecture ou écriture disque.
            lighting=[self.server.config.daily_timer1, self.server.config.daily_timer2],
        ), status)

    @staticmethod
    def solution_filters(request):
        return {key: request.query[key] for key in ("target", "kind", "start", "end") if request.query.get(key)}

    @staticmethod
    def solution_lookup(request):
        """Recherche bornée d'intervention : paramètres distincts des filtres du journal."""
        if "interventions" not in request.query:
            return None, 0
        try:
            offset = int(request.query.get("interventions_offset", "0"))
            if not 0 <= offset <= 1000000:
                raise ValueError()
        except ValueError:
            raise web.HTTPBadRequest(text="Pagination des interventions invalide.") from None
        return request.query["interventions"], offset

    async def solutions(self, request):
        search, search_offset = self.solution_lookup(request)
        try:
            return web.json_response(await self.store.call("solution_data", self.solution_filters(request),
                                                           self.offset(request), False, request.query.get("entry"),
                                                           search, search_offset))
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def solution_mutate(self, request):
        try:
            return web.json_response(await self.store.call("solution_mutate", await request.json(),
                                                           self.server.equipment_store.payload()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def solution_export(self, request):
        try:
            body = "\ufeff" + await self.store.call("solution_csv", self.solution_filters(request))
            return web.Response(body=body.encode(), content_type="text/csv",
                                headers={"Content-Disposition": 'attachment; filename="releves-interventions.csv"'})
        except CultureError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from None
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None

    async def solutions_page(self, request):
        data, error, status = None, None, 200
        filters = self.solution_filters(request)
        try:
            data = await self.store.call("solution_data", filters, self.offset(request), False, request.query.get("entry"))
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template("culture_solutions.html", page_title="Solutions et relevés",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            filters=filters, kinds=SOLUTION_KINDS), status)
