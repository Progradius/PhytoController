"""Repères d'éclairage informatifs (lot F) : squelette enregistré par la migration 4.

`culture_light_targets` naît vide : 18 h / 6 h et 12 h / 12 h sont des préremplissages de
formulaire, jamais des données existantes. Un repère ne commande rien — le rapprochement
avec les horaires réellement configurés se fait en lecture depuis la configuration déjà
distribuée, sans calcul de régulation ni acquisition.

Le lot F remplit ce module ; le validateur est déjà appelé par `_cycle_validate`.
"""


class LightStoreMixin:
    def _validate_light(self):
        """Invariants des repères d'éclairage. Aucune ligne migrée, donc rien à refuser ici.

        Lot F : révisions 1..n sans trou, `on_minutes + off_minutes = 1440`,
        fenêtres non chevauchantes par `(scope, cible, stade)`.
        """
