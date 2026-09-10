"""Interface du carnet, indépendante des commandes du contrôleur."""

from __future__ import annotations

import json
import posixpath
from urllib.parse import urlencode, urlsplit

from aiohttp import web

from model.culture_solution import SOLUTION_KINDS
from model.culture import (CultureConflict, CultureError, KINDS, SPACES, STAGES, creation_stages,
                           first_stage)
from network.web.pages import render_template
from utils.culture_store import CultureStore, CultureUnavailable
from utils.time_reliability import time_reliability

# Les trois vues de « Solutions et relevés ». Un simple choix d'affichage servi par la même
# route : les trois blocs sont rendus, deux sont `hidden`. Aucune persistance, aucune route.
SOLUTION_VIEWS = ("saisir", "releves", "analyser")


def error_response(exc, status):
    """Réponse d'erreur unique de tout le carnet.

    `error` reste premier et inchangé ; `field` et `index` ne sont ajoutés que lorsque
    l'erreur désigne un contrôle précis. Une indisponibilité (503) n'en porte jamais :
    aucun champ n'est en cause, et en inventer un ferait chercher une faute de saisie
    là où c'est le carnet qui est absent.
    """
    payload = {"error": str(exc)}
    # Le refus d'un champ n'a de sens que si un champ est en cause : une indisponibilité
    # n'en désigne aucun, et l'exception qui la porte peut en traîner un d'un autre lot.
    if status == 503:
        return web.json_response(payload, status=status)
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

    @staticmethod
    def search(request):
        """Recherche libre de l'accueil : une chaîne courte, jamais un motif.

        Elle voyage telle quelle jusqu'au magasin, qui compare des noms déjà projetés :
        aucun caractère n'y est spécial, il n'y a donc rien à échapper ici. Seule sa
        longueur est bornée, comme toute entrée de requête.

        Le refus est un `CultureError`, donc le contrat JSON du carnet (`{"error": …}`) :
        une réponse en texte brut obligeait le socle des formulaires à traiter à part le
        seul refus qui ne ressemble pas aux autres.
        """
        needle = (request.query.get("q") or "").strip()
        if len(needle) > 120:
            raise CultureError("Recherche trop longue.", "q")
        return needle

    async def overview(self, request):
        try:
            return web.json_response(await self.store.call(
                "overview", request.query.get("archives") == "1", self.offset(request),
                request.query.get("agenda") == "1", self.search(request)))
        except CultureUnavailable as exc:
            return web.json_response({"available": False, "error": str(exc)}, status=503)
        except CultureError as exc:
            return error_response(exc, 400)

    async def detail(self, request):
        try:
            return web.json_response(await self.store.call("detail", request.match_info["subject_id"], self.offset(request)))
        except CultureError as exc:
            return error_response(exc, 404)
        except CultureUnavailable as exc:
            return error_response(exc, 503)

    @staticmethod
    def version(request):
        """Jeton de fraîcheur que le client affiche déjà, ou None s'il est absent.

        C'est une **chaîne opaque** produite par le magasin : le client la renvoie telle
        quelle et personne d'autre ne la lit. Une valeur inconnue ou tronquée n'est pas un
        refus : elle vaut « je n'en ai pas », et le serveur recalcule. Refuser la requête ne
        rendrait service à personne — l'aide n'est pas une écriture et le jeton n'est qu'un
        moyen d'éviter un calcul. Sa longueur reste bornée, comme toute entrée de requête.
        """
        token = request.query.get("version")
        return token if token and len(token) <= 200 else None

    async def assistance(self, request):
        try:
            return web.json_response(await self.store.call(
                "assistance", request.match_info["subject_id"], self.version(request)))
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

    @staticmethod
    def return_link(request, return_query, subject_id):
        """Lien de retour d'une fiche : adresse **et** libellé, décidés ici, pas en Jinja.

        Retour contextualisé (R2.8) : une page du carnet qui a ses propres filtres — le
        journal — passe sa vue courante en `retour=`, qui prime alors sur le calcul
        q/archives/offset, incapable de la reconstituer. Le paramètre vient de la requête :
        il n'est accepté que s'il désigne une adresse **locale du carnet**, c'est-à-dire un
        chemin absolu sous `/cultures`, sans schéma ni hôte (`urlsplit` les isole, ce qui
        écarte `https://…`, `//evil.example` et `javascript:`), sans `\\` — qu'un navigateur
        normalise en `/`, d'où un `/\\evil.example` qui repartirait en `//evil.example` —, et
        **normalisé** : `/cultures/../conf` ne commence sous `/cultures` qu'en apparence.
        Un `retour` refusé est ignoré, jamais une erreur : le lien existe toujours,
        simplement non contextualisé.

        L'ancre `#culture-{id}` n'est ajoutée qu'au retour vers la **liste**, qui la porte ;
        l'ajouter à un retour vers le journal désignerait un élément inexistant, et écraserait
        au passage l'ancre que ce retour porte peut-être déjà.
        """
        retour = request.query.get("retour", "")
        parts = urlsplit(retour)
        chemin = posixpath.normpath(parts.path) if parts.path else ""
        if (retour and not parts.scheme and not parts.netloc and "\\" not in retour
                and (chemin == "/cultures" or chemin.startswith("/cultures/"))):
            libelle = "Retour au journal" if chemin.startswith("/cultures/journal") else "Retour au carnet"
            return retour, libelle
        # Retour à la liste : les filtres sont rejoués, et la position est portée par l'ancre
        # `#culture-{id}` posée sur une carte `tabindex="-1"`, que le navigateur focalise
        # lui-même. Un paramètre `focus=` n'aurait rien focalisé — il n'était lu nulle part.
        url = "/cultures" + ("?" + urlencode(return_query) if return_query else "")
        return (url + "#culture-" + subject_id) if subject_id else url, "Retour aux cultures"

    async def page(self, request):
        archived = request.query.get("archives") == "1"
        subject_id = request.match_info.get("subject_id")
        offset = self.offset(request)
        detail, overview, error = None, None, None
        status = 200
        # Le bloc « Aujourd'hui » n'a de sens que sur l'accueil des cultures actives : une
        # fiche a le sien, et les archives n'ont ni rappel ni prochaine action.
        agenda = not subject_id and not archived
        # La recherche est validée à part : son refus est une saisie trop longue (400),
        # jamais une fiche introuvable (404).
        needle = ""
        try:
            needle = "" if subject_id else self.search(request)
        except CultureError as exc:
            error, status = str(exc), 400
        if error is None:
            try:
                overview = await self.store.call("overview", archived, 0 if subject_id else offset,
                                                 agenda, needle)
                if subject_id:
                    detail = await self.store.call("detail", subject_id, offset)
            except CultureError as exc:
                error, status = str(exc), 404
            except CultureUnavailable as exc:
                error, status = str(exc), 503
        return_query = {}
        if subject_id:
            for key in ("q", "archives", "offset"):
                if request.query.get(key):
                    return_query[key] = request.query[key]
        return_url, return_label = self.return_link(request, return_query, subject_id)
        return self.server._html(render_template(
            "cultures.html", page_title=detail["subject"]["name"] if detail else "Cultures",
            current_page="cultures", csrf_token=self.server.csrf_token,
            overview=overview, detail=detail, error=error, archives=archived,
            return_url=return_url, return_label=return_label,
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
        # Vue demandée, sinon défaut : une cible choisie mais encore sans relevé appelle la
        # saisie ; partout ailleurs on montre les relevés. Une valeur inconnue retombe sur le
        # défaut plutôt que de refuser la page — le paramètre n'est qu'un choix d'affichage.
        requested_view = request.query.get("view")
        if requested_view in SOLUTION_VIEWS:
            solution_view = requested_view
        elif request.query.get("entry"):
            # Un lien qui désigne une entrée précise vise le journal, où elle est rendue.
            solution_view = "releves"
        elif filters.get("kind"):
            # Une intention de saisie (`kind=`) ouvre la saisie, même si la cible a déjà
            # des relevés : le lien dit ce que l'opérateur vient faire.
            solution_view = "saisir"
        elif filters.get("target") and data and not data.get("latest"):
            solution_view = "saisir"
        else:
            solution_view = "releves"
        return self.server._html(render_template("culture_solutions.html", page_title="Solutions et relevés",
            current_page="cultures", csrf_token=self.server.csrf_token, data=data, error=error,
            filters=filters, kinds=SOLUTION_KINDS, solution_view=solution_view), status)
