"""Journal transversal et observations d'espace (lot H), sans commande du contrôleur.

La page pagine la vue `culture_journal` : une ligne par opération, jamais une ligne par
cible, donc un arrosage de trois pieds mères reste une entrée et compte pour 1. Les
observations d'espace visent explicitement `space_1` ou `space_2` et n'entrent pas dans
l'historique opérateur purgé à 72 h.
"""

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError
from network.web.culture_cycles import CycleViews
from network.web.cultures import error_response
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable


class JournalViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return [web.get("/cultures/journal", self.page),
                web.get("/api/v1/cultures/journal", self.data),
                web.post("/api/v1/cultures/journal", self.mutate),
                web.post("/api/v1/cultures/journal/photos", self.upload),
                web.get("/api/v1/cultures/journal/export", self.export)]

    @staticmethod
    def filters(request):
        """Filtres repris tels quels : leur validation appartient au modèle, pas à la route."""
        return {key: request.query[key] for key in ("start", "end", "target", "type") if request.query.get(key)}

    async def payload(self, request):
        return await self.store.call("journal", self.filters(request), self.views.offset(request),
                                     request.query.get("focus"))

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        # Les filtres saisis sont renvoyés au gabarit même en erreur : une période refusée
        # ne doit pas vider le formulaire qui l'a produite.
        return self.server._html(render_template("culture_journal.html", page_title="Journal du carnet",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            filters=self.filters(request)), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call("space_event_mutate", await request.json()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def upload(self, request):
        """Photo d'observation d'espace : même chemin borné que les photos de culture.

        Déléguer plutôt que recopier garde une seule limite de corps binaire, un seul
        délai d'attente et une seule voie d'écriture vers `media_add`.
        """
        return await CycleViews.upload(self, request)

    async def export(self, request):
        if request.query.get("format", "csv") != "csv":
            raise web.HTTPBadRequest(text="Format attendu : csv.")
        try:
            body = "\ufeff" + await self.store.call("journal_csv", self.filters(request))
            return web.Response(body=body.encode(), content_type="text/csv",
                                headers={"Content-Disposition": 'attachment; filename="journal-carnet.csv"'})
        except CultureError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from None
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None
