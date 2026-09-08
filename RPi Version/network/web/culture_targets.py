"""Plages cibles pH/EC (lot E) : page, données et mutations, sans commande du contrôleur.

Une plage saisie ici ne règle rien : elle sert de repère de lecture sur les relevés et les
courbes. Aucune valeur par défaut n'est proposée et aucune alarme de contrôle n'en découle.
"""

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError, STAGES
from model.culture_solution import RESERVOIRS
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable


class TargetsViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return [web.get("/cultures/targets", self.page),
                web.get("/api/v1/cultures/targets", self.data),
                web.post("/api/v1/cultures/targets", self.mutate),
                web.get("/api/v1/cultures/targets/export", self.export)]

    @staticmethod
    def filters(request):
        return {key: request.query[key] for key in ("target", "scope") if request.query.get(key)}

    async def payload(self, request):
        return await self.store.call("targets", self.filters(request), self.views.offset(request))

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template(
            "culture_targets.html", page_title="Plages cibles pH et EC",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            filters=self.filters(request), stages=STAGES, reservoirs=RESERVOIRS), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call("target_mutate", await request.json()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

    async def export(self, request):
        if request.query.get("format", "csv") != "csv":
            raise web.HTTPBadRequest(text="Format attendu : csv.")
        try:
            body = "\ufeff" + await self.store.call("targets_csv", self.filters(request))
            return web.Response(body=body.encode(), content_type="text/csv",
                                headers={"Content-Disposition": 'attachment; filename="plages-cibles.csv"'})
        except CultureError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from None
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None
