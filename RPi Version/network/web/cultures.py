"""Interface du carnet, indépendante des commandes du contrôleur."""

from __future__ import annotations

import json

from aiohttp import web

from model.culture import CultureConflict, CultureError, KINDS, SPACES, STAGES
from network.web.pages import render_template
from utils.culture_store import CultureStore, CultureUnavailable
from utils.time_reliability import time_reliability


class CultureViews:
    def __init__(self, server, store=None):
        self.server = server
        self.store = store or CultureStore(reliable=lambda: time_reliability().state == "synchronized")

    def routes(self):
        return [web.get("/cultures", self.page), web.get("/cultures/{subject_id}", self.page),
                web.get("/api/v1/cultures", self.overview),
                web.get("/api/v1/cultures/export", self.export),
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
            return web.json_response(await self.store.call("overview", request.query.get("archives") == "1", self.offset(request)))
        except CultureUnavailable as exc:
            return web.json_response({"available": False, "error": str(exc)}, status=503)

    async def detail(self, request):
        try:
            return web.json_response(await self.store.call("detail", request.match_info["subject_id"], self.offset(request)))
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=404)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

    async def mutate(self, request):
        try:
            command = await request.json()
            result = await self.store.call("mutate", command, self.server.equipment_store.payload())
            return web.json_response(result)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": "JSON invalide."}, status=400)
        except CultureConflict as exc:
            return web.json_response({"error": str(exc)}, status=409)
        except CultureError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except CultureUnavailable as exc:
            return web.json_response({"error": str(exc)}, status=503)

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
        try:
            overview = await self.store.call("overview", archived, 0 if subject_id else offset)
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
            # Lecture de la configuration distribuée, aucune relecture ou écriture disque.
            lighting=[self.server.config.daily_timer1, self.server.config.daily_timer2],
        ), status)
