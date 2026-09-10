"""Affectations d'équipements (lot G) : module de vue réservé par la migration du schéma 4.

Déjà instancié et agrégé par `CultureViews.routes()`. Le lot G reste déclaratif : il décrit
des associations historiques, il ne modifie ni le catalogue `param/equipment_metadata.json`
ni un réglage d'équipement.
L'asset `culture_equipment.js` est déjà déclaré dans `network/web/pages.py` et servi par
`network/web/server.py` : ce module n'a plus qu'à remplir ses routes.

Le catalogue courant est **passé** au magasin en lecture seule (`equipment_store.payload()`),
comme pour les événements de culture : il sert à figer un libellé au moment de la saisie,
jamais à réécrire une association passée. Il sert aussi, ici, à peupler les deux sélecteurs
de la page — choisir l'équipement que l'on consulte ou que l'on déclare n'est pas une
résolution : la cascade datée reste entière dans `model/culture_equipment.py`.
"""

import json
from zoneinfo import ZoneInfo

from aiohttp import web

from model.culture import CultureConflict, CultureError
from network.web.cultures import error_response
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

    def page_filters(self, request):
        """Filtres de la page : sans date consultée, c'est celle d'aujourd'hui.

        L'API garde `filters()` telle quelle — sans `at`, elle ne résout aucun contexte.
        La page, elle, doit montrer « Appliqué maintenant » dès son ouverture, sans que
        l'opérateur ait à valider le sélecteur. L'horloge et le fuseau sont ceux du carnet,
        lus sur le magasin sans requête SQLite ; aucune horloge propre n'est introduite.
        """
        filters = self.filters(request)
        filters.setdefault(
            "at", self.store.now().astimezone(ZoneInfo(self.store.zone)).date().isoformat())
        return filters

    async def payload(self, request, filters=None):
        return await self.store.call("equipment_links",
                                     self.filters(request) if filters is None else filters,
                                     self.server.equipment_store.payload())

    async def page(self, request):
        data, error, status = None, None, 200
        # Une seule lecture de l'horloge pour la requête : le sélecteur réaffiché et la
        # résolution doivent porter la même date, y compris à cheval sur minuit.
        filters = self.page_filters(request)
        try:
            data = await self.payload(request, filters)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template(
            "culture_equipment.html", page_title="Affectations d'équipements",
            current_page="cultures", culture_subjects=request.query.getall("subject", []),
            csrf_token=self.server.csrf_token, data=data, error=error,
            catalog=self.server.equipment_store.payload(),
            filters=filters), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call(
                "equipment_mutate", await request.json(), self.server.equipment_store.payload()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)
