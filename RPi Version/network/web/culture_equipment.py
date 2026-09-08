"""Affectations d'équipements (lot G) : module de vue réservé par la migration du schéma 4.

Déjà instancié et agrégé par `CultureViews.routes()`. Le lot G reste déclaratif : il décrit
des associations historiques, il ne modifie ni le catalogue `param/equipment_metadata.json`
ni un réglage d'équipement.
Un nouvel asset exige deux lignes ailleurs, à ajouter par le lot :
`network/web/pages.py` (entrée `culture_equipment` dans `_asset_versions`) et
`network/web/server.py` (accesseur `_asset` plus la route `/static/js/culture_equipment.js`).
"""


class EquipmentViews:
    def __init__(self, views):
        self.views = views
        self.store = views.store
        self.server = views.server

    def routes(self):
        return []
