"""Journal transversal et observations d'espace (lot H) : squelette de la migration 4.

Le journal est une **vue** `culture_journal` (une ligne par opération, cibles jointes à la
demande), jamais une table matérialisée : une copie serait une seconde vérité à
resynchroniser après chaque correction rétrospective. La vue est donc exclue de l'export,
qui reprend déjà ses trois sources.

`space_events` porte les observations d'espace sans créer de fausse plante et sans entrer
dans l'historique opérateur purgé à 72 h. Le lot H remplit ce module et généralise
`utils/culture_media_store.py` aux photos d'observation ; son validateur est déjà appelé
par `_cycle_validate`.
"""


class JournalStoreMixin:
    def _validate_journal(self):
        """Invariants des observations d'espace. Table vide après migration.

        Lot H : révisions 1..n sans trou, `payload` JSON décodable et conforme, espace
        connu. Une observation entièrement annulée reste légitime.
        """
