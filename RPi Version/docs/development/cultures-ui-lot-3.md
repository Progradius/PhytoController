# Lot UI 3 — Assistance contextuelle

Réalisation du lot 3 de l’[audit du 8 septembre 2026](audit-ui-cultures-2026-09-08.md).
Le carnet reste au schéma 4 ; aucune intervention matérielle ou en production.

## Parcours livrés

- Fiche : suggestions expliquées, bornées à quatre, avec faits datés et liens vers
  les rappels, vérifications du stade, étapes manquantes, relevés ou libération.
  Les rappels de l’accueil Aujourd’hui et de la fiche restent les actions du lot 2.
- Création et parcours : bouton de prévalidation ; état avant/après, date, effets
  déclaratifs d’une récolte ; erreurs métier identiques à celles de l’enregistrement.
  Un conflit d’occupation nomme désormais les deux cultures et leurs périodes.
- Solutions : prévalidation, repère antérieur de même cible/contexte, association
  déclarée à la date saisie et signalement prudent de relevés ressemblants. Une vraie
  seconde mesure reste possible après confirmation explicite dans l’interface.
- Fraîcheur : suggestions retirées hors ligne, à l’échec ou après 30 secondes ; panneau
  de vérification invalidé par la saisie et par expiration. Une modification pendant
  une requête préalable empêche l’envoi de l’ancien brouillon.

## Garanties et limites

La prévalidation partage les mutations finales et annule sa transaction, y compris les
reconstructions dérivées. Les règles pures du parcours restent autoritaires. Les tests
comparent l’export avant/après succès et refus, puis simulent une modification concurrente
et un rejeu après réponse perdue. Les suggestions ne sont ni des tâches persistantes ni
des notifications. Elles ne modifient aucune donnée ni commande du contrôleur.

Deux points relevés à l’audit sont **en cours de remédiation** et ne doivent pas être lus
comme un choix définitif : la prévalidation systématique avant chaque enregistrement, qui
fait deux requêtes serveur là où une suffit (R2.1), et le rejeu de l’assistance toutes les
30 secondes pour chaque fiche ouverte, qui reprojette le carnet sans qu’une saisie ait
changé (R2.2). Voir
[le plan de remédiation](remediation-ui-cultures-lots-2-3-2026-09-09.md).

La recherche de ressemblances porte sur 200 relevés courants, avec au plus trois
résultats. Elle peut ignorer une entrée plus ancienne et ne prétend pas détecter tout
doublon. Les associations d’alimentation viennent des périodes déclarées ; aucune
association matérielle ni mesure n’est inventée. Aucune fréquence de suivi ou préférence
persistante n’est introduite. Les suggestions n’offrent pas de conseil de dosage.

Les profils navigateur sont émulés sous Chromium. Les essais sur téléphone physique,
lecteur d’écran et Raspberry Pi avec un historique volumineux ne sont pas qualifiés
par cette livraison. Les performances des projections historiques existantes restent
une limite à mesurer sur le Pi.

## Validation locale

- Suite Python complète : **610 réussites**. Les avertissements de dépréciation
  Pydantic/aiohttp préexistants restent présents.
- Tests propres à l’assistance : transaction annulée au succès et au refus, état
  exporté inchangé, conflit concurrent final, rejeu d’une clé acceptée, conversion EC,
  annulation des relevés ressemblants, changement de jour local, absence distincte
  de zéro, sélection par date effective, retrait des aides après vérification/rappel
  accompli et suspension lorsque l’horloge n’est pas fiable.
- Contrôle `node --check` des scripts modifiés, `git diff --check` et miroir
  `AGENTS.md` / `CLAUDE.md` sans écart.
- Parcours navigateur du lot 3 : prévalidation sans écriture, confirmation explicite
  d’une seconde mesure, invalidation après modification pendant une requête, aides
  retirées hors ligne, contrôle axe et absence de débordement horizontal. Captures
  conservées dans les résultats Playwright locaux, dont le panneau à 320 px examiné.

Les essais ont conduit à corriger la disposition du panneau de vérification sur mobile
et à conserver un unique bouton de soumission : le bouton de vérification utilise la
validation native du formulaire, tout en restant une action distincte de l’enregistrement.

Bilan navigateur : **206 scénarios distincts validés**, 89 exclusions prévues selon
les profils, sur les 295 cas de la suite complète. L’exécution complète initiale
comptait 203 réussites et trois échecs liés à l’ajout du bouton ; la reprise finale
a porté sur `tests/ui/cultures_lot_c.spec.js`, `tests/ui/cultures.spec.js` et
`tests/ui/cultures_ui_lot_3.spec.js`, sans échec.

Le budget de temps est celui de `playwright.config.js` : `timeout: 20_000`, rallongé
scénario par scénario avec `test.setTimeout(...)` (45 s pour le lot C, 60 s à 180 s
ailleurs). Il n’existe pas de « limite de 60 secondes » globale ; la reprise ci-dessus
a été relancée avec `--timeout=60000` en ligne de commande, une surcharge ponctuelle
qui n’est pas la configuration du dépôt. Le scénario historique du lot C attend
maintenant le refus en prévalidation et vérifie explicitement qu’aucune mutation
finale n’est envoyée ; ses assertions de chronologie et de conservation de saisie
restent présentes.

Commandes de validation finales :

```bash
.venv/bin/python -m pytest -q
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --workers=2
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures_lot_c.spec.js tests/ui/cultures.spec.js tests/ui/cultures_ui_lot_3.spec.js --workers=2 --timeout=60000
```
