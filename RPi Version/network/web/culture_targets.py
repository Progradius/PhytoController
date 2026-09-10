"""Plages cibles pH/EC (lot E) : page, données et mutations, sans commande du contrôleur.

Une plage saisie ici ne règle rien : elle sert de repère de lecture sur les relevés et les
courbes. Aucune valeur par défaut n'est proposée et aucune alarme de contrôle n'en découle.

La page résout la plage applicable à une cible et à une date consultées. La **règle** de
résolution reste entière dans `model/culture_targets.resolve_targets` — priorité stricte
cible directe → sujet alimenté → réservoir, sans fusion et sans rétroactivité ; cette vue
n'ajoute que le libellé court de la source et la période lisible.
"""

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError, STAGES, stamp
from model.culture_solution import RESERVOIRS
from network.web.cultures import error_response
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable

# Indications courtes affichées contre la valeur. Ce sont des libellés de présentation :
# l'ordre de priorité et la sélection restent ceux de `resolve_targets`.
SOURCE_SHORT = {"subject": "cible directe", "fed_subject": "sujet alimenté",
                "reservoir": "réservoir"}


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

    async def resolution(self, request, data):
        """Plage applicable à la cible et à la date consultées, ou son absence explicite.

        La cascade entière est jouée par le magasin (`target_resolution`), qui appelle la
        règle pure `resolve_targets` avec les associations d'alimentation réellement
        déclarées à cette date : la vue n'ajoute que le libellé court de la source.

        Sans cible choisie il n'y a rien à résoudre : la page le dit au lieu d'inventer une
        cible par défaut. La date reste vérifiée par `stamp`, la seule définition du carnet,
        pour qu'une date impossible soit refusée avec ou sans cible.
        """
        target = (request.query.get("target") or "").strip()
        at = (request.query.get("at") or data["today"]).strip()
        if not target:
            stamp(at, "date", self.store.zone, self.store.now(), field="at")
            return {"at": at, "target": "", "range": None, "fed_subjects": [],
                    "reservoirs": [], "ambiguous_reservoir": False}
        view = await self.store.call("target_resolution", target, at)
        if view["range"]:
            view["range"]["source_short"] = SOURCE_SHORT[view["range"]["source"]]
        return view

    async def page(self, request):
        data, error, status, resolution = None, None, 200, None
        try:
            data = await self.payload(request)
            resolution = await self.resolution(request, data)
        except CultureError as exc:
            data, error, status = None, str(exc), 400
        except CultureUnavailable as exc:
            data, error, status = None, str(exc), 503
        return self.server._html(render_template(
            "culture_targets.html", page_title="Plages cibles pH et EC",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            resolution=resolution,
            filters={**self.filters(request), "at": (request.query.get("at") or "").strip()},
            stages=STAGES, reservoirs=RESERVOIRS), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call("target_mutate", await request.json()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

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
