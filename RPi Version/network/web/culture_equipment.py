"""Affectations d'équipements (lot G) : module de vue réservé par la migration du schéma 4.

Déjà instancié et agrégé par `CultureViews.routes()`. Le lot G reste déclaratif : il décrit
des associations historiques, il ne modifie ni le catalogue `param/equipment_metadata.json`
ni un réglage d'équipement.
L'asset `culture_equipment.js` est déjà déclaré dans `network/web/pages.py` et servi par
`network/web/server.py` : ce module n'a plus qu'à remplir ses routes.

Le catalogue courant est **passé** au magasin en lecture seule (`equipment_store.payload()`),
comme pour les événements de culture : il sert à figer un libellé au moment de la saisie,
jamais à réécrire une association passée.
"""

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable


class EquipmentViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return [web.get("/cultures/equipment", self.page),
                web.get("/api/v1/cultures/equipment", self.data),
                web.post("/api/v1/cultures/equipment", self.mutate)]

    @staticmethod
    def filters(request):
        """Filtres bornés : une date consultée et un équipement, rien d'autre."""
        return {key: request.query[key] for key in ("at", "equipment") if request.query.get(key)}

    async def payload(self, request):
        return await self.store.call("equipment_links", self.filters(request),
                                     self.server.equipment_store.payload())

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template(
            "culture_equipment.html", page_title="Affectations d'équipements",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            filters=self.filters(request)), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call(
                "equipment_mutate", await request.json(), self.server.equipment_store.payload()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)
