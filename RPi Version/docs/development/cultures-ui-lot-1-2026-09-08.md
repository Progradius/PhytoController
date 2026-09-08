# Carnet de cultures — lot UI 1, cohérence et défauts

Réalisation du lot 1 de l’audit UI du 8 septembre 2026. Le périmètre est celui de
la navigation et de la présentation ; aucune migration, règle de culture,
commande d’équipement ou donnée de production n’est modifiée.

## Comportement livré

- Les sept rubriques partagent le même fragment de navigation, les mêmes intitulés
  et une rubrique active (`aria-current="page"`). Les ancres locales restent séparées.
- Une culture sélectionnée suit le parcours fiche → solutions/relevés → cycles →
  plages/journal → fiche. Les pages éclairage et équipements conservent un contexte
  de retour, sans prétendre filtrer leur vue globale. Les formulaires GET de ces
  deux pages et leurs actualisations après saisie gardent ce contexte.
- « Vue globale » permet de quitter explicitement la sélection. Un réservoir reste
  transmis aux solutions, plages et journal ; un espace du journal ne devient pas
  arbitrairement une culture ou un réservoir. Les destinations incompatibles sont
  marquées « vue globale ». Une comparaison de plusieurs cultures ne choisit jamais
  silencieusement la première pour un filtre à cible unique.
- Les relevés et plages se créent à la demande, les filtres du journal et la sélection
  de comparaison sont repliés. Les opérations du journal précèdent la création
  d’une observation d’espace ; les rappels précèdent comparaison et climat.
- Un changement de stade ne modifie jamais la durée d’un repère, y compris une
  valeur existante de 960 minutes. « Utiliser 12 h / 12 h » ou « Utiliser 18 h / 6 h »
  est une action explicite. L’aperçu sans JavaScript décrit aussi la durée enregistrée.
- Les SVG des relevés et du climat adaptent leur repère de coordonnées à leur
  largeur réelle, y compris après redimensionnement. Les graduations conservent
  leur taille de 14 px ; points, bandes et lacunes gardent leur signification.
- Les textes d’introduction sont raccourcis et l’export SQLite est nommé
  « Base SQLite seule (sans photos) ».

La refonte « Aujourd’hui », les formulaires guidés, les suggestions, les erreurs
associées aux champs, les points de courbe interactifs et la galerie restent dans
les lots suivants de l’audit.

## Validation

Validation locale sur les bases temporaires du serveur sans matériel ; les tests
mutateurs refusent une cible `PHYTO_UI_BASE_URL` externe.

- Python : `357 passed` ; avertissements existants de dépréciation Pydantic/aiohttp.
- Playwright : résultat de la suite du carnet consigné après exécution complète.
- Scénarios dédiés : conservation du contexte après un relevé enregistré, navigation
  entre rubriques et retour ; correction du stade enregistrée avec durée conservée ;
  préréglage explicite ; espaces/réservoirs et vues globales ; lecture compacte.
- Graduations mesurées aux largeurs 320, 393 et 1 440 px après redimensionnement.
- Sept rubriques à 393 px en thème normal et plein jour : contrôles axe et absence
  de débordement horizontal de page. Captures produites par le scénario dédié.
- `diff -u CLAUDE.md AGENTS.md` : aucun écart. Vérification Git des espaces en fin de ligne.

Les captures utilisent des données fictives. Leur barre mobile fixe peut apparaître
au milieu d’une capture pleine page : elle correspond au viewport initial.
Les vérifications sur téléphone physique, lecteur d’écran et Safari/iOS ne sont pas
couvertes par ces tests Chromium. Aucun essai ni déploiement sur le Pi.
