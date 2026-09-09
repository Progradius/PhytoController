# Plan de remédiation — lot UI 4 du carnet de cultures

État des lieux du 9 septembre 2026, après livraison du lot 4 (`183189b`, rapport
[cultures-ui-lot-4.md](cultures-ui-lot-4.md)) de l'[audit du 8 septembre 2026](audit-ui-cultures-2026-09-08.md).
Ce document liste les écarts constatés et le correctif attendu pour chacun. Il ne modifie rien et
n'ajoute aucune fonctionnalité hors audit.

Méthode : quatre revues indépendantes (dorsale SQL et magasin, front et accessibilité, analyse
d'écart contre le périmètre du lot 4, exécution réelle des suites), chaque constat retenu ayant
été relu dans le code par l'orchestrateur. Une mutation de code hors dépôt a servi à qualifier
le pouvoir discriminant des tests dorsaux. Résultats mesurés sur l'arbre `183189b` :

| Suite | Annoncé | Mesuré |
| --- | --- | --- |
| pytest | 800 réussites | 800 réussites, 0 échec, 0 exclusion, 24 s |
| Playwright `cultures_ui_lot_4.spec.js`, un worker | 12 réussites, 3 exclusions PWA | 12 réussites, 0 échec, 3 exclusions, 2,5 min |
| Garde cible externe, deux specs en une invocation | — | 55 exclusions, 0 réussite, 0 échec, aucune requête sortante |
| Banc `benchmark-cultures-analysis.py`, 4 cultures | lecture 167 ms WSL, 759 ms Pi | lecture 529 ms médiane sur ce poste ; HTML 438 973 octets ; base temporaire supprimée |
| Contrôles statiques | — | `git status` vide, `diff CLAUDE.md AGENTS.md` vide, `node --check` vert |

Les chiffres du rapport de livraison sont exacts. Les écarts de temps de lecture entre postes ne
remettent pas en cause le banc, mais R2.1 à R2.3 montrent que sa répartition et sa représentativité
sont discutables. Les écarts ci-dessous viennent de la lecture du code, pas des suites, qui ne les
couvrent pas.

## Bilan par exigence du lot 4

| Exigence de l'audit | Statut | Renvoi |
| --- | --- | --- |
| Comparaison alignée par indicateur | livrée (tableau `th scope`, absences en texte, unités) | — |
| Comparaison alignée par âge du stade | non livrée ; l'audit dit « par indicateur **ou** par âge du stade » | écart assumé, voir fin |
| Sélection par recherche et cases, maximum quatre visible | livrée ; plafond annoncé mais pas motivé ; bugs de pagination | R1.2, R3.6 |
| Courbes : détail au toucher et au clavier | livrée | R1.1, R1.7, R2.4 |
| Courbes : taille de texte stable | acquise depuis le lot 1 (`viewBox` à la largeur rendue, 14 px) | — |
| Courbes : tableau équivalent | livré sous forme d'une colonne de texte concaténé | R3.2 |
| Courbes : légende explicite, par source et période | **absente** sur les courbes de solutions ; présente sur le climat | R3.1 |
| Courbes : synthèse textuelle | absente sur les courbes de solutions ; présente sur le climat | R3.3 |
| Lacunes et bandes datées préservées, jamais reliées | livrée | R1.3 |
| Galerie précédent/suivant, légendes, retour au contexte | livrée ; lien de contexte inexistant dans le journal, focus volé | R1.5, R3.6 |
| Bilan des archives : variété, dates, poids, enseignements, comparaison | livrée ; durée par stade absente des cartes ; occupation persistante non signalée sur la page Archives | R3.5 |
| Recherche | sélecteur de comparaison livré ; recherche du journal transversal absente | R3.4 |
| Requêtes bornées, une projection par requête | livrée et testée | — |
| Temps de rendu sur Pi | mesuré ; coût dominé par un recalcul évitable | R2.1 à R2.3 |
| Invariants : pas de zéro inventé, prédicat partagé, pas de SQLite dans l'event loop, aucune règle métier en Jinja ou JS | respectés, vérifiés par lecture et par mutation | R4.1 |

## Ordre de traitement

| Priorité | Contenu | Taille |
| --- | --- | --- |
| P0 | aucun : garde des tests prouvée, aucun accès GPIO, aucune mutation nouvelle | — |
| P1 | Bugs fonctionnels et d'accessibilité visibles | petite |
| P2 | Coût sur le Raspberry Pi et dans le navigateur | petite à moyenne |
| P3 | Non-conformités à l'audit et état de l'art | moyenne |
| P4 | Tests, documentation, méthode | petite |

Chaque correctif garde les invariants de `CLAUDE.md` : règles pures dans `model/`, SQLite sur le
thread unique du magasin, DDL du schéma 4 figé, aucune acquisition ni commande, aucune mutation
rejouée hors ligne. Aucun correctif ne demande de nouvelle persistance.

## P1 — bugs

### R1.1 Bouton désactivé sous le focus : perte de position au clavier

- **Constat.** `culture_analysis.js:29` désactive « Point précédent » quand l'index atteint 0 et
  « Point suivant » en fin de série ; `:74` fait de même pour la galerie. Le bouton qui porte le
  focus devient `disabled` au moment où l'utilisateur l'active : le focus retombe sur `body` ou sur
  le dialogue, et un lecteur d'écran n'annonce plus rien.
- **Correctif.** Ne jamais désactiver le bouton actif : garder les deux boutons activés et borner
  dans `select()` / `show()`, ou déplacer le focus vers le bouton opposé avant de désactiver.
  Annoncer la butée dans le texte du point (« premier point », « dernière photo »).
- **Validation.** Spec : focus sur « Point précédent », activations jusqu'à l'index 0,
  `toBeFocused()` reste vrai ; même scénario sur « Photo précédente ».

### R1.2 Pagination du sélecteur de comparaison

- **Constat.** Trois défauts liés. (a) `culture_cycle_store.py:266` découpe `matches` avec un
  `selection_offset` jamais borné, alors que `_climate_detail` (`:226`) clampe le sien ; la vue
  accepte jusqu'à 10⁷ (`culture_cycles.py:57`), et le gabarit rend alors « Choix précédents » vers
  `offset − 40` depuis n'importe quelle valeur. (b) Le formulaire `data-comparison-selection`
  (`culture_cycles.html:43-49`) reconduit `q` mais pas `selection_offset` : valider depuis la page
  2 ramène à la page 1. (c) Le champ « Filtrer les choix affichés » est dans ce formulaire sans
  `name` : Entrée soumet « Afficher les cycles » au lieu de filtrer.
- **Correctif.** Clamper `selection_offset` sur `len(matches)` comme le détail climatique et
  renvoyer l'offset normalisé ; ajouter le `hidden` manquant ; sortir le champ de filtre du
  formulaire ou intercepter `submit` quand il vient de ce champ.
- **Validation.** Test magasin : `selection_offset=10**7` sur 44 cultures renvoie l'offset 40 et
  40 choix ; spec : page 2, coche, « Afficher les cycles », la page reste 2 ; Entrée dans le
  filtre ne navigue pas.

### R1.3 Lacune climatique sélectionnée sans retour visuel

- **Constat.** `culture_cycles.js:167` pose `data-analysis-index` sur les tics de lacune
  (`path.climate-gap`), donc le curseur les atteint, mais la seule règle de surbrillance est
  `.solution-dot.culture-selected-point` (`cultures.css:215`) : le dessin ne bouge pas.
- **Correctif.** Règle `.culture-selected-point` non scopée, avec un traitement propre au `path`
  (épaisseur et couleur), et poser aussi l'attribut `r` en JS pour ne pas dépendre de la propriété
  CSS `r`, absente des Firefox antérieurs à 128.
- **Validation.** Spec sur la courbe climatique des cycles : curseur sur une lacune, le `path`
  porte la classe et un style calculé distinct.

### R1.4 Dépendance non gardée à `PhytoCultureAnalysis`

- **Constat.** `culture_solutions.js:247` et `culture_cycles.js:147` appellent
  `window.PhytoCultureAnalysis.chart(...)` avant `draw()`. Si l'asset manque (précache PWA partiel
  après déploiement, 404), le `TypeError` interrompt le script hôte : plus aucune courbe n'est
  dessinée, et la suite du script des cycles ne s'exécute pas.
- **Correctif.** `window.PhytoCultureAnalysis?.chart?.(...) ?? (() => {})`, le dessin des courbes
  ne dépendant jamais de l'explorateur.
- **Validation.** Spec : `page.route` renvoie 404 sur `culture_analysis.js`, les courbes se
  dessinent quand même.

### R1.5 Lien de contexte de la galerie : focus volé et lien absent dans le journal

- **Constat.** (a) `culture_analysis.js:85` ferme le dialogue au clic sur « Ouvrir l'entrée
  liée », ce qui déclenche `:83` et ramène le focus sur la vignette d'origine alors que la page
  défile vers `#event-…` : la convention du lot 2 (« l'élément focalisé est la confirmation ») est
  contredite. (b) Le script cherche `figcaption a` ; `culture_journal.html:41` et
  `cultures.html:301` n'ont aucun lien dans la légende, donc le bouton reste caché précisément là
  où le rapport le revendique (« même dans le journal »).
- **Correctif.** Distinguer la fermeture par le lien (pas de re-focalisation, l'ancre
  `tabindex="-1"` reçoit le focus) de la fermeture par Échap ou par le bouton ; ajouter dans les
  deux légendes le lien vers l'entrée ou la fiche, comme `culture_cycles.html:103`.
- **Validation.** Spec sur `/cultures/journal` avec photo réelle : le bouton est visible, son
  `href` pointe sur l'entrée, après activation l'ancre est focalisée.

### R1.6 Tap sans distance maximale

- **Constat.** `culture_analysis.js:34-43` retient le point le plus proche sans seuil : un tap sur
  une zone vide, une bande ou le titre d'axe remplace la sélection courante par un point
  potentiellement à l'autre bout de la série.
- **Correctif.** Ignorer le tap au-delà d'un rayon de 44 px CSS et laisser la sélection en place.
- **Validation.** Spec : tap à 200 px de tout point, le texte de sélection est inchangé ; tap à
  10 px d'un point, le point est sélectionné (voir aussi R4.2).

## P2 — coût sur le Pi et dans le navigateur

### R2.1 Synthèse climatique recalculée à l'identique pour chaque culture

- **Constat, mesuré.** `culture_cycle_store.py:248` appelle `_climate_summary(start_hour,
  end_hour)` dans la boucle des cultures sans mémoïsation. Sur le carnet du banc, 105 ms sur
  154 ms de lecture pour quatre agrégations identiques (≈ 31 800 lignes `climate_hours` balayées
  chacune). C'est la source dominante des 759 ms mesurés sur le Pi, pas les statistiques pH/EC.
- **Correctif.** Mémoïser `_climate_summary` par `(start_hour, end_hour)` dans la portée de
  `_cycle_data`. Aucune persistance, aucun schéma.
- **Validation.** Compteur d'appels dans `test_culture_cost.py` : quatre cultures de même fenêtre,
  une seule exécution SQL ; rejouer le banc sur le Pi et reporter le tableau.

### R2.2 Statistiques pH/EC pilotées par un balayage complet de `solution_entries`

- **Constat, mesuré.** `EXPLAIN QUERY PLAN` sur `_subject_readings_sql()` donne `SCAN e` puis, en
  sous-requête corrélée, `SCAN l` : `solution_links` n'a pas d'index sur `subject_id` (clé
  `(period_id, subject_id, start_at)`). Environ 10 ms par culture sur 12 001 relevés ici, soit
  ~190 ms sur Pi pour quatre cultures, proportionnels au journal entier. Pas une régression
  (l'ancien chemin exportait tout), mais « agrégé en SQL » n'enlève pas le O(relevés × sujets).
- **Correctif.** Réécrire la requête en `UNION ALL` pilotée par `solution_targets` (index
  `solution_targets_subject`) et par `solution_links` joint à `solution_periods`, sans toucher au
  DDL : un index nouveau serait un schéma 5, ce que rien ici ne justifie. Conserver l'unique
  source du prédicat, partagée avec `_latest_reading`.
- **Validation.** `EXPLAIN QUERY PLAN` sans `SCAN e` ; les tests d'équivalence avec l'export et
  les mutations `revision`, `cancelled` et « avant » (R4.1) restent discriminants.

### R2.3 Banc de mesure non représentatif de la branche coûteuse

- **Constat.** `benchmark-cultures-analysis.py:59-60` sème 12 000 relevés en SQL brut avec
  `solution_targets` seul : aucun renouvellement, `solution_periods` et `solution_links` vides.
  L'`EXISTS` d'alimentation datée porte donc sur zéro ligne, et les 759 ms Pi sont un plancher.
  Les compteurs publiés (`:78`) sont codés en dur, pas comptés.
- **Correctif.** Semer des renouvellements et des associations datées sur une partie des
  réservoirs ; compter les entrées réellement insérées ; remesurer sur le Pi et mettre
  `cultures-ui-lot-4.md` et le JSON à jour.
- **Validation.** Le banc affiche `solution_links > 0` ; les deux tableaux du rapport sont
  régénérés.

### R2.4 Coût quadratique et balayages DOM dans le navigateur

- **Constat.** À la borne réelle de 2 000 points (`culture_solution_store.py:390`) :
  `points.indexOf(p)` dans la boucle de dessin (`culture_solutions.js:299`, `culture_cycles.js:162`
  et `:167`) soit jusqu'à 4 × 10⁶ comparaisons par redessin ; `select()` fait un
  `querySelectorAll` puis un `toggle` sur tous les nœuds à chaque pas du curseur
  (`culture_analysis.js:30`) ; un `getBoundingClientRect()` par point à chaque tap (`:38-40`).
- **Correctif.** Index de boucle (`forEach((p, i) =>`) ; mémoriser le nœud sélectionné et ne
  toucher que lui ; pour le tap, calculer en coordonnées du `viewBox` à partir des données
  (`x(p)`, `y(p)`) plutôt qu'en lisant le DOM.
- **Validation.** La mesure déjà attachée par la spec à 2 000 points devient une assertion
  (seuil sur le temps de `End` puis d'ouverture du tableau, voir R4.2).

## P3 — non-conformités à l'audit et état de l'art

### R3.1 Légende explicite des courbes de solutions, par source et par période

- **Constat.** Le constat P1 de l'audit sur les graphiques énumère quatre attendus ; trois sont
  livrés, la légende ne l'est pas. `culture_solutions.js:284-300` trace bandes cibles, tirets de
  renouvellement, marqueurs de stade, barres min/max et points sans aucune clé de lecture ; tous
  les points portent la même classe `solution-dot` quelle que soit la cible ou la période
  (`:297`), donc deux cultures ou deux solutions d'un même filtre sont indiscernables. Les deux
  `<details>` du gabarit listent des dates et des valeurs, pas le sens des tracés. Le climat, lui,
  a un `figcaption` complet (`culture_cycles.js:145`).
- **Correctif.** Sous chaque figure, une légende texte des encodages (bande = plage cible, tiret
  long = renouvellement, tiret composé = stade, barre = min/max journalier, point = mesure) ; une
  forme ou une teinte par cible ou période de solution, reprise dans la légende et dans le texte
  du curseur. Aucune courbe reliant des sources différentes.
- **Validation.** Spec : deux cibles dans le filtre, la légende nomme les deux, les points portent
  deux classes distinctes ; axe sans violation en sombre et plein jour.

### R3.2 Tableau équivalent réduit à une colonne de texte

- **Constat.** `culture_analysis.js:49-51` construit un tableau à un `th scope="row"` (le rang) et
  un unique `td` contenant la chaîne concaténée (`describe()`, `culture_solutions.js:246`) ; ni
  `thead` ni `th scope="col"`. C'est une liste numérotée, pas le tableau de données demandé par
  l'audit (réf. WAI, alternatives aux graphiques complexes).
- **Correctif.** Passer des lignes structurées (`date`, `valeur`, `unité`, `cible ou capteur`,
  `période`, `agrégats`, `lacune`) et émettre `thead` avec un `th scope="col"` par champ ; garder la
  construction différée et la borne au même jeu de points.
- **Validation.** Spec : `thead th` ≥ 4, une cellule « mesure absente » dans la colonne valeur ;
  axe.

### R3.3 Synthèse textuelle des courbes de solutions

- **Constat.** Les figures pH/EC n'ont pour texte que « pH » et « EC (mS/cm) »
  (`culture_solutions.html:94`) ; le curseur décrit un point, jamais la série. Le climat annonce
  périodes fiables, lacunes et granularité (`culture_cycles.js:141`).
- **Correctif.** Un paragraphe par figure, calculé côté serveur à partir des points déjà bornés :
  période couverte, nombre de mesures, min / moyenne / max, nombre de lacunes, cibles présentes.
  Aucune interprétation agronomique.
- **Validation.** Test Python sur le rendu ; spec vérifiant le texte avec une absence.

### R3.4 Recherche du journal transversal et filtres rapides

- **Constat.** Le lot 4 s'intitule « … et recherche » ; `culture_journal.html:12-28` n'offre que
  dates, cible et type. L'audit (ligne « Journal transversal ») demande aussi des filtres rapides
  7 / 30 jours. Aucun des quatre lots ne les a livrés, et le rapport ne le dit pas.
- **Correctif.** Champ `q` sur la vue SQL `culture_journal` (note, cible, type), borné à
  120 caractères, paginé comme aujourd'hui ; deux liens GET « 7 jours » et « 30 jours » qui
  remplissent `start`/`end` à partir de `overview["today"]`. Aucune persistance.
- **Validation.** Test magasin sur la borne et l'échappement ; spec : recherche d'un mot d'une
  note, un résultat ; « 7 jours » renseigne les deux dates.

### R3.5 Archives : occupation persistante non signalée, durée par stade absente

- **Constat.** Le marqueur « Espace encore occupé · à libérer » existe (`cultures.html:141`) mais
  son bloc est sous `{% if not archives %}` (`:139`) : la page Archives, où l'audit place
  l'exigence, ne le montre pas. Les cartes d'archives (`:154`) donnent origine, stade, poids et
  enseignements, pas la durée par stade ; il faut ouvrir chaque bilan.
- **Correctif.** Rendre le signalement sur la carte d'archive concernée ; ajouter une ligne
  compacte des durées par stade à partir de `subject.periods`, déjà projetées (aucune projection
  neuve).
- **Validation.** Spec sur `/cultures?archives=1` avec une archive occupant l'espace 2 : le
  signalement et les durées sont présents.

### R3.6 Finitions d'accessibilité de l'explorateur, de la galerie et du sélecteur

- **Constat.** (a) `role="status"` sur la sortie du curseur **et** `aria-valuetext`
  (`culture_analysis.js:21`, `:28`) : double annonce ; `refreshSelection()` réécrit le texte à
  chaque redessin, donc une rotation annonce un point, et la page en annonce deux au chargement.
  (b) Deux régions live dans le dialogue (`:64`) et l'image cassée reste affichée. (c) Plafond de
  quatre imposé par `disabled` (`:97`) sans lien programmatique avec l'explication, et jamais
  motivé (`culture_cycles.html:40`). (d) Pas de fermeture au clic sur le voile. (e) Dialogue sur
  `var(--bg)` sans bordure ni ombre (`cultures.css:216`) : quasi indiscernable du voile en thème
  sombre, contrairement à `.confirm-dialog` (`style.css:121`). (f) Consigne d'usage présente sur
  les solutions seulement (`culture_solutions.html:93`), pas sur le climat. (g) `min-height: 44px`
  seulement : pas de largeur minimale.
- **Correctif.** Retirer `role="status"` de la sortie du curseur et n'annoncer que par
  `aria-valuetext` ; ne réécrire le texte au redessin que si l'index a changé ; une seule région
  live dans le dialogue et `image.hidden` sur `error` ; `aria-describedby` des cases vers la
  sortie et une phrase motivant le plafond (lisibilité d'un tableau à quatre colonnes sur
  téléphone) ; fermeture sur clic hors contenu ; reprendre les jetons de `.confirm-dialog` ;
  générer la consigne dans le fragment de `PhytoCultureAnalysis.chart` ; `min-width: 44px` sur
  les boutons de l'explorateur et de la galerie.
- **Validation.** Spec : après rotation, le texte de statut n'a pas changé ; quatre cases cochées,
  la cinquième porte `aria-describedby` vers l'explication ; capture galerie en thème sombre ;
  mesure des boîtes ≥ 44 × 44.

### R3.7 Recherche insensible aux diacritiques

- **Constat.** Client `toLocaleLowerCase("fr")` (`culture_analysis.js:97`) et serveur
  `casefold()` (`culture_cycle_store.py:264`) sont cohérents mais aucun ne normalise : « epinard »
  ne trouve pas « Épinard ». L'ordre des résultats est `rowid DESC`, ni documenté ni utile pour une
  recherche par nom.
- **Correctif.** Normalisation NFD sans marques diacritiques des deux côtés, appliquée aussi à la
  recherche des cultures et des archives du lot 2 pour rester homogène ; trier les résultats par
  nom puis identifiant et le documenter dans `cultures-api.md`.
- **Validation.** Test magasin « epinard » → « Épinard » ; spec sur le filtre client.

### Reliquats des lignes « Photos » et « Cycles » hors lot 4, à arbitrer

- Aperçu local avant envoi présent sur la fiche seulement (`cultures.js:442`), absent des
  formulaires photo du journal et des cycles ; progression d'envoi réduite à un texte d'état
  (`submitBinary` utilise `fetch`, sans progression). Ce sont des attendus de la ligne « Photos »
  de l'audit, non repris par le lot 2 ni le lot 4 ; une progression réelle demande `XMLHttpRequest`
  dans le socle. À traiter dans une passe photos dédiée, pas ici.
- Alignement par âge du stade : l'audit propose « par indicateur ou par âge du stade » ; le lot
  a choisi l'indicateur et le dit. Comparer deux cycles décalés dans le temps reste impossible.
  C'est le plafond fonctionnel de la livraison ; toute suite est une décision produit, pas une
  remédiation.

## P4 — tests, documentation, méthode

### R4.1 La branche « relevé avant un renouvellement à la même seconde » n'est pas discriminée

- **Constat, prouvé par mutation.** `culture_solution_store.py:456-465` porte un `CASE` dont la
  seule fonction est de basculer la fenêtre d'association en `]début ; fin]`. Rendre ses deux
  branches identiques laisse **64 tests verts** (`test_culture_cost.py`,
  `test_culture_solutions.py`, `test_culture_cycles.py`, `test_cultures.py`), alors que les
  mutations sur `revision` et `cancelled` font bien échouer la suite. Le scénario existant garde
  le lot alimenté avant et après le renouvellement : le changement de période n'est pas
  observable. La branche ne l'est que si l'association se ferme à la seconde du renouvellement
  (récolte le jour du renouvellement).
- **Correctif.** Ajouter ce cas au test d'équivalence, pour l'agrégat et pour `_latest_reading`.
- **Validation.** Rejouer la mutation : au moins un échec.

### R4.2 Couverture de la spec du lot 4

- **Constat.** Annoncé par le rapport mais non asséré : plafond de quatre côté client (la spec ne
  coche jamais plus de deux cases) ; le filtre client (`fill("inconnue")` n'est suivi d'aucune
  assertion sur les libellés masqués, le test passe si le filtre ne fait rien) ; sélection
  conservée au redessin (aucun redimensionnement) ; « un seul arrêt de tabulation » ; point le
  plus proche (le tap vise exactement le cercle, un écouteur par point passerait) ; explorateur de
  la courbe climatique ; lien de contexte réel ; cartes d'archives ; pagination du sélecteur en
  navigateur ; bandes de référence en texte ; seuil de 2 000 points mesuré mais jamais asséré.
- **Correctif.** Une assertion par affirmation du rapport, dans la même spec ; les seuils de temps
  deviennent des `expect` avec une marge documentée.
- **Validation.** `npx playwright test tests/ui/cultures_ui_lot_4.spec.js --workers=1`, tous
  profils ; garde externe rejouée avec plusieurs specs.

### R4.3 Documentation et rédaction

- `docs/reference/cultures-api.md` : volumétrie de la page des cycles périmée (258 217 octets
  contre 438 973 mesurés à quatre cultures) ; ordre des choix non documenté.
- `docs/operations/cultures.md` : « nombre de relevés » alors que `COUNT(e.ph)` compte des
  valeurs ; écrire « nombre de mesures ».
- `cultures-ui-lot-4.md` : « boutons de 44 px » (hauteur seule), « lien vers le contexte quand il
  existe » (préciser où), « un seul arrêt de tabulation par curseur » (aucun arrêt par point,
  trois arrêts par zone), et absence de toute mention de la ligne « Journal transversal » et du
  signalement d'occupation sur la page Archives : un lecteur du seul rapport conclut à un lot
  complet.
- Constantes `4` et `40` dupliquées entre magasin, gabarit (six occurrences) et JS : les exposer
  dans `data` et les lire.
- `culture_analysis.js` : plusieurs instructions par ligne, lignes de 190 caractères mêlant règle
  de plafond et règle de filtrage (`:97`) ; une instruction par ligne dans le rendu et les
  gestionnaires.

### R4.4 Méthode

- Le hook RTK filtre la sortie de `npx playwright` et fait disparaître le compte d'exclusions ;
  passer par `rtk proxy npx …` ou par `--reporter=json` quand le chiffre importe.
- La fixture navigateur laisse un répertoire `/tmp/phyto-ui-*` vide par exécution (≈ 160
  accumulés) ; défaut préexistant au lot, à corriger dans `tests/ui/culture_fixtures.js`.

## Lots de correction proposés

| Lot | Contenu | Fichiers principaux |
| --- | --- | --- |
| A | R1.1, R1.3, R1.4, R1.6, R2.4, R3.2, R3.6 | `culture_analysis.js`, `culture_solutions.js`, `culture_cycles.js`, `cultures.css` |
| B | R1.2, R2.1, R2.2, R2.3, R3.7, R4.1 | `culture_cycle_store.py`, `culture_solution_store.py`, `culture_cycles.py`, `culture_cycles.html`, `benchmark-cultures-analysis.py`, `tests/test_culture_cost.py` |
| C | R1.5, R3.1, R3.3, R3.5 | `culture_solutions.html`, `culture_journal.html`, `cultures.html`, `culture_solution_store.py` (synthèse), `culture_solutions.js` |
| D | R3.4 | `culture_journal_store.py`, `network/web/cultures.py`, `culture_journal.html`, `culture_journal.js` |
| E | R4.2, R4.3, R4.4 | `tests/ui/cultures_ui_lot_4.spec.js`, `culture_fixtures.js`, docs |

Les lots A à D travaillent sur des fichiers disjoints, sauf `culture_solutions.js` partagé entre
A et C et `culture_solution_store.py` partagé entre B et C : ces deux fichiers se commitent en
deux fois ou se mentionnent dans le message. Le lot E suit les quatre autres. Validation de
sortie : pytest complet, spec du lot 4 sur tous les profils, garde externe multi-specs, banc
rejoué sur le Pi et rapport mis à jour.

## Bilan de la remédiation (9 septembre 2026)

| Exigence | Commit | Statut |
| --- | --- | --- |
| R1.1 bouton désactivé sous le focus | `2ff0180` (A) | livré |
| R1.2 pagination du sélecteur de comparaison | `1dc848d` (B) | livré ; le constat « 40 choix » est **démenti**, voir plus bas |
| R1.3 lacune sélectionnée visible | `2ff0180` (A) | livré |
| R1.4 dessin sans l'explorateur | `2ff0180` (A) | livré |
| R1.5 lien de contexte de la galerie | `932b2fc` (C) | livré ; le constat (a) est **nuancé**, voir plus bas |
| R1.6 point le plus proche | `2ff0180` (A) | livré |
| R1.7 curseur et boutons | `2ff0180` (A) | livré |
| R2.1 synthèse climatique mémoïsée | `1dc848d` (B) | livré ; −55 % de lecture à quatre cultures sur le Pi |
| R2.2 statistiques pH/EC sans balayage complet | `1dc848d` (B) | livré |
| R2.3 banc représentatif | `1dc848d` (B), mesures `017605b` | livré ; le repère « 759 ms Pi » est **démenti**, voir plus bas |
| R2.4 coût quadratique dans le navigateur | `2ff0180` (A) | livré ; seuils devenus des `expect` |
| R3.1 légende des courbes de solutions | `932b2fc` (C) | livré |
| R3.2 tableau équivalent structuré | `2ff0180` (A) | livré, sept colonnes |
| R3.3 synthèse textuelle des courbes | `932b2fc` (C) | livré |
| R3.4 recherche du journal transversal | `c7ddf8c` (D) | livré, avec les raccourcis 7 / 30 jours |
| R3.5 bilan des cartes d'archives | `932b2fc` (C) | livré |
| R3.6 défauts d'accessibilité groupés | `2ff0180` (A), `932b2fc` (C) | livré |
| R3.7 bornage serveur | `1dc848d` (B) | livré |
| R4.1 branche « relevé avant renouvellement » | `1dc848d` (B) | livré, mutation rejouée |
| R4.2 couverture de la spec | lot E | livré : 9 scénarios au lieu de 8, assertions ajoutées sur le plafond de quatre, le filtre local, la pagination en navigateur, la sélection au redessin, l'arrêt de tabulation unique et l'explorateur climatique ; trois mutations temporaires prouvent leur pouvoir discriminant |
| R4.3 documentation et rédaction | lot E | livré : `cultures-api.md`, `cultures.md`, `cultures-ui-lot-4.md`, `docs/index.md` |
| R4.4 méthode | lot E | **partiellement** : la fixture supprime son répertoire ; le `webServer` de `playwright.config.js` en laisse toujours un par exécution (fichier hors périmètre du lot) |
| Comparaison alignée par âge du stade | — | **non livrée**, écart assumé du lot 4, à arbitrer |

### Constats démentis ou nuancés

- **R1.2, « 40 choix affichés ».** Le sélecteur n'en affichait pas 40 mais 4 sur la dernière
  page d'un carnet de 44 cultures : le découpage n'était pas borné, mais la page réellement
  servie restait celle des résultats restants. Le défaut de pagination était bien réel ; sa
  formulation, non.
- **R1.5 (a), « focus volé ».** Le vol de focus n'existait que pour une destination **non
  focalisable** (`#photos`, une section sans `tabindex`). Vers une ancre `tabindex="-1"`,
  Chromium focalisait déjà la destination, et le retour à la vignette ne se produisait pas.
  Le correctif reste juste, son constat était trop large.
- **R2.3, « les 759 ms Pi ».** Ce chiffre était un **plancher** : le semis ne créait ni
  `solution_periods` ni `solution_links`, donc l'`EXISTS` d'alimentation datée portait sur
  zéro ligne. Le vrai « avant » du semis représentatif est **1 720,9 ms** à quatre cultures
  (485,4 ms à une), contre 721,0 ms (288,0 ms) après R2.1 et R2.2. Le repère historique est
  conservé dans le JSON sous `pi_lot_4_semis_initial`, étiqueté non comparable.
- **R4.4, « répertoire vide ».** Les `/tmp/phyto-ui-*` abandonnés ne sont **pas** vides :
  188 répertoires y occupent 16,5 Mio, chacun avec un `param.json` recopié de
  `param.example.json` et, pour une partie d'entre eux, la base `cultures.sqlite3` du test et
  son journal WAL. La fuite est donc plus lourde que décrite. Aucun n'étant vide, aucun n'a
  été supprimé par le lot E : leur nettoyage reste une décision de l'exploitant.

### Revue indépendante et corrections

Une revue indépendante des cinq lots a relevé douze écarts, tous corrigés ici. Aucun ne
touche la régulation, aucune persistance ni route nouvelle.

| Point | Écart relevé | Correctif appliqué |
| --- | --- | --- |
| P1.1 | colonne « Cible ou capteur » et phrase du curseur affichant l'identifiant technique | `chart_sources` publie `target` (cibles nommées) à côté de `label` ; `culture_solutions.js` nomme la source dans la cellule, le curseur et l'infobulle, et retombe sur `p.target` seulement pour le repli |
| P1.2 | plafond de quatre imposé par `disabled`, donc explication jamais annoncée | `aria-disabled="true"` et refus au gestionnaire `change` (la cinquième case se décoche aussitôt) ; la case reste focalisable, opacité réduite dans `cultures.css` |
| P1.3 | boutons et tap silencieux, seul `aria-valuetext` annonçait | région live masquée (`visually-hidden`, `role="status"`) propre à l'explorateur, alimentée par `select(index, {announce})` et uniquement pour un bouton ou un tap |
| P2.1 | docstring affirmant un balayage borné par les dates | texte corrigé (dates facultatives, ×4,5 mesuré sur 12 000 relevés) ; aucune fenêtre par défaut ajoutée, le conseil passe dans `cultures-api.md` |
| P2.2 | commentaire attribuant le gain aux bornes et à l'index `solution_date` | commentaire refait sur le plan réellement retenu (`SCAN l`, `solution_periods` par clé primaire, index automatique sur `reservoir_id`) ; le gain vient de la sous-requête corrélée supprimée |
| P2.3 | aucune assertion sur le plan de requête | `test_bilan_ph_ec_ne_balaie_plus_solution_entries` : `EXPLAIN QUERY PLAN` du bilan, aucune ligne `SCAN e` |
| P2.4 | variante de repli 6 indiscernable de la 5 (deux points évidés pointillés) | repli plein, contour continu épais, teinte en retrait et opacité `.55` ; les variantes 0 à 5 restent distinctes par la forme et le motif ; `test_repli_de_repere_ne_nomme_aucune_cible_et_reste_distinct` couvre huit sources |
| P2.5 | `casefold()` côté serveur contre `toLowerCase()` côté navigateur | `search_key` plie par `lower()`, docstring expliquant « ß » ; deux tests (clé pure et recherche des choix) |
| P2.6 | rembourrage du `dialog` fermant la galerie au clic | rembourrage porté par `.culture-gallery-body`, créé en JS ; `event.target === dialog` redevient exact |
| P2.7 | retour de focus neutralisé même sans destination atteinte | `followed` reste faux pour la page courante sans fragment |
| P2.8 | consigne d'usage répétée sous chaque figure | rendue au premier appel de `chart` de la page (drapeau de module) |
| P2.9 | bloc de sélection sans `output` ni champ | garde `if (!output || !query) return;`, dans l'esprit de R1.4 |
| P3 | `stages[period.stage]` sur les cartes d'archives ; `phyto_norm` réinscrite à chaque requête | `stages.get(period.stage, period.stage)` ; fonction inscrite une fois à l'ouverture de la connexion (`CultureStore._open`) |

### Reliquats

- La légende des courbes de solutions reste calculée sur **tous** les points de la figure et
  non métrique par métrique : une source qui n'apporte que de l'EC figure encore dans la
  légende du pH. Le doute du lot C reste ouvert ; seule la seconde moitié du constat (les
  deux vocabulaires de la colonne « Cible ou capteur ») est corrigée par P1.1.
- Hors lot, à arbitrer : aperçu de photo avant envoi, progression d'envoi, alignement de la
  comparaison par âge du stade.
- Méthode : le `webServer` de `playwright.config.js` reste le dernier producteur de
  `/tmp/phyto-ui-*` (un par exécution non externe).

### Validation de sortie (9 septembre 2026)

| Contrôle | Résultat |
| --- | --- |
| pytest complet, arbre final | 820 réussites, 0 échec |
| Suite Playwright complète, un worker, avant fusion des corrections de revue (`d78f805`) | 284 réussites, 111 exclusions prévues, 0 échec, 47 min |
| Specs du lot 4 après fusion (`fc2a222` + spec corrigée), `desktop-chromium`, `mobile-chromium`, `mobile-etroit`, `mobile-paysage` | 11 / 11 sur chaque profil |
| Garde cible externe, `tests/ui/cultures*.spec.js` en une invocation | 61 exclusions, 0 réussite, 0 échec (lot E) |
| Banc sur le Pi, même semis, 4 cultures | 1 720,9 ms → 721,0 ms (lecture médiane) |

Une assertion de la spec du sélecteur (`toBeEnabled()` sur une case `aria-disabled`) était
fausse : Playwright lit `aria-disabled` comme une désactivation, pour `toBeEnabled` comme pour
l'actionnabilité d'un clic. La preuve porte désormais sur la propriété DOM `disabled` et le
clic de refus contourne la vérification d'actionnabilité.
