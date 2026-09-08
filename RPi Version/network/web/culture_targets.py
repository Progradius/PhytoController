"""Plages cibles pH/EC (lot E) : module de vue réservé par la migration du schéma 4.

Déjà instancié et agrégé par `CultureViews.routes()` : le lot E ajoute ses routes ici,
son gabarit `culture_targets.html` et son script `static/js/culture_targets.js`.
Un nouvel asset exige deux lignes ailleurs, à ajouter par le lot :
`network/web/pages.py` (entrée `culture_targets` dans `_asset_versions`) et
`network/web/server.py` (accesseur `_asset` plus la route `/static/js/culture_targets.js`).
"""


class TargetsViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return []
