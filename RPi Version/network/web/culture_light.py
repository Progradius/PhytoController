"""Repères d'éclairage (lot F) : module de vue réservé par la migration du schéma 4.

Déjà instancié et agrégé par `CultureViews.routes()`. Le lot F lit les horaires configurés
depuis `self.server.config` déjà distribuée — aucune relecture disque, aucune écriture de
`param.json`, aucun ordre d'équipement.
Un nouvel asset exige deux lignes ailleurs, à ajouter par le lot :
`network/web/pages.py` (entrée `culture_light` dans `_asset_versions`) et
`network/web/server.py` (accesseur `_asset` plus la route `/static/js/culture_light.js`).
"""


class LightViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return []
