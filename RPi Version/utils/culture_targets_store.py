"""Plages cibles pH/EC historisées (lot E) : squelette enregistré par la migration 4.

La table `culture_targets` existe dès le schéma 4 mais naît vide : aucune plage par
défaut n'est inventée. Le lot E ajoute ici la saisie, la correction, l'annulation et la
résolution du contexte (cibles directes, puis sujets alimentés, puis réservoir), toujours
sans rétroactivité de la plage courante sur les mesures anciennes.

Le validateur est déjà branché sur `_cycle_validate` et sur `restore_copy` : le lot E n'a
qu'à en remplir le corps, sans toucher au schéma ni aux points d'appel.
"""


class TargetsStoreMixin:
    def _validate_targets(self):
        """Invariants des plages cibles. Sans ligne à contrôler, il n'y a rien à refuser.

        Lot E : révisions 1..n sans trou, au moins une borne renseignée, `min <= max`,
        valeurs finies, fenêtres non chevauchantes par `(scope, cible)`.
        """
