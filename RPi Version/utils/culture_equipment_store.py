"""Affectations d'équipements datées (lot G) : squelette enregistré par la migration 4.

`culture_equipment_links` naît vide : la migration n'invente aucune date de réaffectation
passée. Le contexte connu à la saisie reste porté par `equipment_context` (événements,
relevés, vérifications, observations d'espace) ; à défaut, l'interface doit dire
« association inconnue à cette date » plutôt que retomber sur le catalogue courant.

`equipment_id` est validé en Python contre `EQUIPMENT_IDS` : le catalogue est du code, pas
du schéma. Le lot G remplit ce module et son validateur, déjà appelé par `_cycle_validate`.
"""


class EquipmentStoreMixin:
    def _validate_equipment(self):
        """Invariants des affectations d'équipements. Table vide après migration.

        Lot G : révisions 1..n sans trou, `equipment_id` dans `EQUIPMENT_IDS`,
        fenêtres non chevauchantes par équipement.
        """
