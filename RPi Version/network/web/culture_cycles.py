"""Cycles, rappels, photos et export complet, sans commande du contrôleur."""

import asyncio
import json
from pathlib import Path
from urllib.parse import unquote

from aiohttp import web

from model.culture import CultureConflict, CultureError, SPACES, STAGES
from model.culture_cycle import CHECKLIST, MAX_PHOTO_BYTES, REMINDER_STATES, reminder_buckets
from model.culture_solution import RESERVOIRS
from network.web.cultures import error_response
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable

# Vues de la page. La liste est ici, à côté de la seule route qui la lit : un `view` inconnu
# ne doit jamais masquer les deux panneaux à la fois.
CYCLE_VIEWS = ("faire", "comparer")


def split_reminders(data):
    """Sépare les rappels déjà dus du reste, avec la règle pure du bloc « Aujourd'hui ».

    « Du jour » veut dire *échéance atteinte* : un rappel en retard reste à faire
    aujourd'hui, et le laisser plus bas dans une liste paginée revient à le perdre. Le
    classement est celui de `reminder_buckets`, déjà employé par `/cultures` — écrire ici
    une seconde comparaison de dates ferait deux définitions du même mot, qui finiraient
    par diverger sur le passage de minuit ou de fuseau.

    Aucune projection ni lecture neuve : seules les lignes déjà servies par `cycle_data`
    sont classées, dans l'ordre où elles arrivent (échéance croissante), et le reste est
    rendu tel quel. Un rappel dû qui tomberait sur une page suivante n'est pas inventé
    ici : le gabarit renvoie alors à la première page, où le classement le place.
    """
    buckets = reminder_buckets(data["reminders"], data["today"], data["timezone"])
    due = buckets["overdue"] + buckets["due_today"]
    keys = {(row["id"], row["revision"]) for row in due}
    return due, [row for row in data["reminders"] if (row["id"], row["revision"]) not in keys]


class BundleResponse(web.FileResponse):
    async def prepare(self, request):
        try:
            return await super().prepare(request)
        finally:
            await asyncio.to_thread(self._path.unlink, missing_ok=True)


class CycleViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return [web.get("/cultures/cycles", self.page), web.get("/api/v1/cultures/cycles", self.data),
                web.post("/api/v1/cultures/cycles", self.mutate),
                web.post("/api/v1/cultures/photos", self.upload),
                web.get("/cultures/photos/{photo_id}", self.photo),
                web.get("/api/v1/cultures/bundle", self.bundle)]

    @staticmethod
    def bounded(request, name, limit):
        """Pagination climatique bornée : aucune requête ne peut demander un décalage arbitraire."""
        raw = request.query.get(name)
        if raw is None:
            return None
        try:
            value = int(raw)
            if not 0 <= value <= limit:
                raise ValueError()
            return value
        except ValueError:
            raise web.HTTPBadRequest(text="Pagination invalide.") from None

    async def payload(self, request):
        return await self.store.call("cycle_data", request.query.getall("subject", []), self.views.offset(request),
                                     request.query.get("reminder"), self.bounded(request, "climate_offset", 10 ** 7) or 0,
                                     self.bounded(request, "climate_at", 4102444800), request.query.get("q", ""),
                                     self.bounded(request, "selection_offset", 10 ** 7) or 0)

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        requested_view = request.query.get("view", CYCLE_VIEWS[0])
        cycle_view = requested_view if requested_view in CYCLE_VIEWS else CYCLE_VIEWS[0]
        due_reminders, later_reminders = split_reminders(data) if data else ([], [])
        return self.server._html(render_template("culture_cycles.html", page_title="Cycles et rappels",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            selected=request.query.getall("subject", []), states=REMINDER_STATES, checklist=CHECKLIST,
            reservoirs=RESERVOIRS, stages=STAGES, spaces=SPACES, cycle_view=cycle_view,
            due_reminders=due_reminders, later_reminders=later_reminders), status)

    async def data(self, request):
        try:
            return web.json_response(await self.payload(request))
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def mutate(self, request):
        try:
            return web.json_response(await self.store.call("cycle_mutate", await request.json()))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    async def upload(self, request):
        # Corps binaire dédié : aucun relèvement de la limite JSON globale de 64 Kio.
        if request.content_type != "application/octet-stream":
            raise web.HTTPUnsupportedMediaType(text="Envoyer une photo binaire avec ses métadonnées dédiées.")
        if request.content_length is not None and request.content_length > MAX_PHOTO_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_PHOTO_BYTES, actual_size=request.content_length)
        try:
            header = request.headers.get("X-Culture-Metadata", "")
            if len(header) > 7000:
                raise CultureError("Métadonnées de photo trop longues.")
            command = json.loads(unquote(header))
            raw = bytearray()
            async def receive():
                async for chunk in request.content.iter_chunked(65536):
                    if len(raw) + len(chunk) > MAX_PHOTO_BYTES:
                        raise web.HTTPRequestEntityTooLarge(max_size=MAX_PHOTO_BYTES, actual_size=len(raw) + len(chunk))
                    raw.extend(chunk)
            await asyncio.wait_for(receive(), timeout=30)
            return web.json_response(await self.store.call("media_add", command, bytes(raw)))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "Métadonnées de photo invalides."}, status=400)
        except CultureConflict as exc:
            return error_response(exc, 409)
        except CultureError as exc:
            return error_response(exc, 400)
        except CultureUnavailable as exc:
            return error_response(exc, 503)
        except asyncio.TimeoutError:
            raise web.HTTPRequestTimeout(text="Envoi de photo trop lent ; aucune photo confirmée.") from None

    async def photo(self, request):
        try:
            raw = await self.store.call("media_get", request.match_info["photo_id"])
            return web.Response(body=raw, content_type="image/jpeg")
        except CultureError as exc:
            raise web.HTTPNotFound(text=str(exc)) from None
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None

    async def bundle(self, request):
        try:
            filename = await self.store.call("bundle")
            return BundleResponse(Path(filename), headers={"Content-Disposition": 'attachment; filename="cultures-complet.zip"', "Content-Type": "application/zip"})
        except CultureError as exc:
            raise web.HTTPBadRequest(text=str(exc)) from None
        except CultureUnavailable as exc:
            raise web.HTTPServiceUnavailable(text=str(exc)) from None
