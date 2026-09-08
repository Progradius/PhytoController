"""Journal transversal et observations d'espace (lot H) : module de vue réservé.

Déjà instancié et agrégé par `CultureViews.routes()`. Le lot H pagine la vue
`culture_journal` (une ligne par opération, jamais une ligne par cible) et ajoute les
observations d'espace et leurs photos.
Un nouvel asset exige deux lignes ailleurs, à ajouter par le lot :
`network/web/pages.py` (entrée `culture_journal` dans `_asset_versions`) et
`network/web/server.py` (accesseur `_asset` plus la route `/static/js/culture_journal.js`).
"""


class JournalViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return []
