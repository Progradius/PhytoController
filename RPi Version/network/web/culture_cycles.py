"""Cycles, rappels, photos et export complet, sans commande du contrôleur."""

import asyncio
import json
from pathlib import Path
from urllib.parse import unquote

from aiohttp import web

from model.culture import CultureConflict, CultureError, SPACES, STAGES
from model.culture_cycle import CHECKLIST, MAX_PHOTO_BYTES, REMINDER_STATES
from model.culture_solution import RESERVOIRS
from network.web.cultures import error_response
from network.web.pages import render_template
from utils.culture_store import CultureUnavailable


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
                                     self.bounded(request, "climate_at", 4102444800))

    async def page(self, request):
        data, error, status = None, None, 200
        try:
            data = await self.payload(request)
        except CultureError as exc:
            error, status = str(exc), 400
        except CultureUnavailable as exc:
            error, status = str(exc), 503
        return self.server._html(render_template("culture_cycles.html", page_title="Cycles et rappels",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            selected=request.query.getall("subject", []), states=REMINDER_STATES, checklist=CHECKLIST,
            reservoirs=RESERVOIRS, stages=STAGES, spaces=SPACES), status)

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
