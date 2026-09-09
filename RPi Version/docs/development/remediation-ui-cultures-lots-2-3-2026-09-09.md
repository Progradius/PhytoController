# Plan de remédiation — lots UI 2 et 3 du carnet de cultures

État des lieux du 9 septembre 2026, après livraison des lots 2 (`62e29e7..c879d51`) et 3
(`d9d3dfd..0665d80`) de l'[audit du 8 septembre 2026](audit-ui-cultures-2026-09-08.md).
Ce document liste les écarts constatés et le correctif attendu pour chacun. Il ne modifie rien
et n'ajoute aucune fonctionnalité hors audit ; le lot 4 (comparaison alignée, courbes tactiles,
galerie, bilan, recherche) reste hors périmètre.

Méthode : quatre revues indépendantes (conformité lot 2, conformité lot 3, revue technique du
diff `2597e8f..HEAD`, exécution réelle des suites), chaque constat retenu ayant été relu dans le
code par l'orchestrateur. Résultats mesurés sur l'arbre `0665d80` :

| Suite | Annoncé | Mesuré |
| --- | --- | --- |
| pytest | 610 réussites | 610 réussites, 0 échec, 0 exclusion, 34 s |
| Playwright, 5 profils, 295 cas | 206 validés, 89 exclusions | 206 réussites, 0 échec, 89 exclusions déclarées, 36 min |
| Lot 2 par profil (36/31/26/24/10) | idem | idem, recalculé en excluant le lot 3 |
| Contrôles statiques | tous verts | `diff CLAUDE.md AGENTS.md`, `git diff --check`, `node --check`, absence d'inline et de `print` : verts ; pyflakes : 2 imports inutilisés dans `culture_cycle_store.py` |

Les chiffres des bilans sont exacts. Les écarts ci-dessous viennent de la lecture du code, pas
des suites, qui ne les couvrent pas.

## Ordre de traitement

| Priorité | Contenu | Taille |
| --- | --- | --- |
| P0 | Garde de sécurité des tests navigateur | petite |
| P1 | Bugs fonctionnels visibles | petite à moyenne |
| P2 | Coût sur le Raspberry Pi introduit par les lots | moyenne |
| P3 | Non-conformités à l'audit | moyenne |
| P4 | Dette, tests d'infrastructure et documentation | petite |

Chaque correctif garde les invariants de `CLAUDE.md` : règles pures dans `model/`, SQLite sur le
thread unique du magasin, aucune persistance nouvelle sans schéma 5, aucune mesure préremplie,
aucune mutation rejouée hors ligne.

## P0 — sécurité des tests

### R0.1 Garde « cible externe » inopérante au-delà du premier fichier de spec

- **Constat, reproduit.** `tests/ui/culture_fixtures.js:39-41` déclare `test.beforeEach(test.skip(…PHYTO_UI_BASE_URL…))` dans un module partagé. Le cache CommonJS n'attache le hook qu'au premier fichier chargé par worker. Avec `PHYTO_UI_BASE_URL=http://127.0.0.1:9` et trois fichiers dans une commande : 13 exclusions, 2 tentatives réelles de `page.goto` (`cultures_ui_lot_2.spec.js:55`, `cultures_ui_lot_3.spec.js:4`), arrêtées seulement parce que le port 9 est interdit par Chromium. Sur un Pi réel, `createMother()` aurait créé un pied mère dans le carnet de production.
- **Correctif.** Refuser dans la fixture `cultureBaseURL` elle-même : si `PHYTO_UI_BASE_URL` est défini, `throw new Error(...)` ou `test.skip()` à l'intérieur de la fixture, jamais un hook au niveau du module. Retirer le `beforeEach` de module.
- **Validation.** Relancer la commande ci-dessus avec les douze specs du carnet en une seule invocation : 100 % exclusions, zéro requête sortante. Ajouter cette commande à `docs/development/verification.md`.

## P1 — bugs

### R1.1 Clonage d'une ligne d'origine ou de produit qui recopie l'erreur

- **Constat.** `cultures.js:216` et `culture_solutions.js:152` font `cloneNode(true)` sur la première ligne. `mark()` (`culture_forms.js:112-136`) a pu y poser un `span.field-error` avec un `id`, `aria-invalid` et `data-describedby-base`. Le clone conserve tout : nouvelle ligne vide affichée en erreur, `id` dupliqué, et `clearField()` de la nouvelle ligne efface le message de l'ancienne.
- **Correctif.** Exposer `PhytoCultureForms.resetField(root)` qui retire `.field-error`, `aria-invalid`, `aria-describedby`, `data-describedby-base` et `field-invalid` ; l'appeler dans les deux gestionnaires avant `append`.
- **Validation.** Spec Playwright : refus sur la première origine, « Ajouter une origine », la nouvelle ligne est vierge et le document n'a qu'un seul `id` par erreur.

### R1.2 Index d'erreur non traduit quand les ingrédients viennent d'une recette

- **Constat.** `culture_solutions.js:188` vide `sentProducts`, puis `:203-206` retombe sur l'`index` serveur quand la table est vide : la n‑ième ligne de saisie libre est marquée alors que le refus porte sur un ingrédient de recette. Même fallback dans `cultures.js:102-104`.
- **Correctif.** Quand la table de traduction est vide, retirer la clé `index` du refus avant `showError`, et rattacher le message au sélecteur de recette (`field: "recipe_id"`).
- **Validation.** Test unitaire JS ou spec : recette choisie, quantité mise à l'échelle refusée, le sélecteur de recette porte l'erreur.

### R1.3 Refus côté client sans champ (fin de séchage)

- **Constat.** `cultures.js:127` et `:133` lèvent `new Error("Poids sec invalide.")` et « Poids par origine invalide. » ; le `catch` n'envoie que `{error}` : ni `aria-invalid`, ni lien, ni focus, contrairement au P1 de l'audit. `culture_solutions.js` a déjà `invalid(msg, field, index)`.
- **Correctif.** Utiliser le même helper avec `field: "weight_g"` et `field: "origin_weight", index: rank`.
- **Validation.** Spec : `abc` dans « Poids sec total » marque le champ et le focalise.

### R1.4 Message « hors ligne » alors que la note est déjà enregistrée

- **Constat.** `cultures.js:418` sort avant tout message quand la photo échoue en `offline`/`busy`/`preview` après une note acceptée ; le socle affiche « aucun envoi mis en attente » alors que la note est en base. Pas de doublon, mais l'annonce contredit l'état réel.
- **Correctif.** Après acceptation de la note, verrouiller l'observation (`lockObservation`) avant la requête photo et remplacer le message par « Note enregistrée ; photo non envoyée, réessayer quand le réseau revient ».
- **Validation.** Spec existante d'échec partiel étendue au cas hors ligne.

### R1.5 `reveal()` dévoile un bloc porteur d'une règle métier sans le refermer

- **Constat.** `culture_forms.js:171-176` met `hidden = false` sur tous les ancêtres ; `cultures.html:134` et `[data-creation-stage]` portent une règle (mode, semis/bouture) via `hidden`. Latent : aucun refus serveur ne vise aujourd'hui un champ masqué.
- **Correctif.** Ne dévoiler que les `<details>` et les conteneurs marqués `data-cf-collapsible`, jamais un `hidden` posé par une règle de page.
- **Validation.** Test unitaire du socle sur un champ dans un bloc `hidden` non repliable.

### R1.6 Ancre de la suggestion « Consulter le parcours »

- **Constat.** `model/culture_assistance.py:44` renvoie vers `#journal` alors que la section de rattrapage `culture-backfill` (`cultures.html:229`) n'a pas d'`id` : l'opérateur atterrit sous les formulaires à remplir.
- **Correctif.** Donner `id="backfill"` à la section et viser `#backfill`.
- **Validation.** Test Python sur le `href` de la suggestion `backfill`.

## P2 — coût sur le Pi

### R2.1 Prévalidation inconditionnelle à chaque enregistrement

- **Constat.** `culture_forms.js:295-311` : tout `submitJson` vers `/api/v1/cultures` ou `/api/v1/cultures/solutions` fait d'abord un POST `preview`, y compris pour « Enregistrer » et pour l'observation/photo qui n'a pas de bouton « Vérifier ». Serveur : deux `BEGIN IMMEDIATE`, deux `_projections()`, deux `_solution_rebuild()` par saisie, sur le thread unique. Un 503 transitoire de la prévalidation bloque l'enregistrement.
- **Correctif.** Prévalider seulement sur le bouton « Vérifier » et, pour un relevé de solution, une seule fois par signature de saisie (le rapprochement de ressemblance est la seule aide qui justifie un appel implicite). Un échec de prévalidation autre que 400/409 ne doit pas empêcher l'enregistrement, qui revalide de toute façon.
- **Validation.** Spec comptant les `POST` : un enregistrement nominal = une requête ; un relevé = au plus deux.

### R2.2 Assistance rejouée toutes les 30 s par fiche ouverte

- **Constat.** `cultures.js:82-84` : `setInterval(refresh, 30000)` + `focus` + `visibilitychange`. Serveur `_assistance()` (`culture_assistance_store.py:23-35`) : `_projections()` complet puis `_latest_solution_readings()`, qui refait `_solution_data(export=True)` avec une seconde projection complète. Une fiche laissée ouverte sur une tablette occupe le thread du magasin en continu et concourt avec les écritures (plafond 8 requêtes en vol, puis 503 « Carnet occupé »).
- **Correctif.** Côté client : rafraîchir au chargement, au retour de visibilité et après une mutation locale ; supprimer l'intervalle ou le porter à 5 min avec arrêt quand l'onglet est masqué. Côté serveur : renvoyer `304`/réponse vide quand `version` du sujet et `today` n'ont pas changé depuis la requête précédente (le client envoie `?version=`), et calculer `latest_reading` pour un seul sujet au lieu d'exporter tout le journal.
- **Validation.** Test Python : assistance avec `version` inchangée ne relance aucune projection (compteur sur `_projections`). Mesure sur Pi avec un carnet de 2 ans simulé, notée dans le bilan.

### R2.3 Ouverture d'une fiche : quatre projections complètes

- **Constat.** `cultures.py:156-158` appelle `overview` puis `detail` ; chacun fait `_projections()` et `_latest_solution_readings()`, qui rappelle `_projections()`. Le lot 2 a ajouté l'un de ces balayages (`culture_store.py:287`) pour le dernier relevé d'une fiche archivée.
- **Correctif.** Passer les projections déjà calculées à `_latest_solution_readings(subjects=…)` (le paramètre existe, `culture_solution_store.py:93`), et ne demander le dernier relevé que du sujet affiché.
- **Validation.** Compteur d'appels à `_projections()` dans un test HTTP de la fiche : au plus un.

### R2.4 Rappels de l'accueil non bornés

- **Constat.** `_agenda` (`culture_store.py:251`) charge tous les rappels courants sans `LIMIT` et `cultures.html:84-86` rend un formulaire par rappel en retard ou du jour, alors que le journal et les « à venir » sont bornés.
- **Correctif.** Borner `overdue` et `due_today` (par exemple 10 chacun) avec « … et N autres » vers `/cultures/cycles#rappels`, sur le modèle de `TODAY_JOURNAL`.
- **Validation.** Test d'agenda avec 30 rappels en retard : 10 cartes et un compteur.

### R2.5 Scintillement des aides

- **Constat.** `cultures.js:86-87` : l'expiration à ~30 s tombe juste avant l'intervalle de 30 s ; le panneau se vide puis se recharge. Disparaît avec R2.2 ; sinon, expirer à `valid_for_seconds + marge` ou remplacer plutôt que vider.

## P3 — non-conformités à l'audit

### R3.1 Vérifications de la fiche indépendantes du stade

- **Constat.** `cultures.html:202-210` : titre « Vérifications pertinentes à ce stade », mais la liste ne dépend que de `subject.space`, sous une condition d'état en Jinja, et recopie `model/culture_cycle.CHECKLIST` sans test d'équivalence.
- **Correctif.** Règle pure `stage_checks(subject)` dans `model/culture_cycle.py` renvoyant les vérifications et liens selon stade et espace ; le gabarit boucle sans condition ; test d'équivalence ajouté à `tests/test_culture_actions.py`.

### R3.2 Carte de rappel : « Fait » et « Reporter » en deux gestes

- **Constat.** `cultures.html:58-61` : un `<select>` à trois options plus un bouton « Enregistrer le suivi ». L'audit demande deux boutons.
- **Correctif.** Deux boutons `name="action" value="done|postponed"` dans le même formulaire ; la date n'apparaît qu'au clic « Reporter » (sans JS, un second écran ou la date visible comme aujourd'hui). Aucune route nouvelle.

### R3.3 « Toute API renvoie `field` » est faux

- **Constat.** Aucun `field` dans `culture_targets_store.py` et `culture_checklist_store.py` ; un seul dans light et equipment. Les refus de plages, éclairage, équipements, vérifications et photos s'affichent en résumé sans marquage. `cultures-api.md:51-62` le dit honnêtement ; le bilan du lot 2 non.
- **Correctif.** Compléter `field`/`index` sur ces magasins (mêmes règles : attribut `name`, rang 0-based) et faire adopter entièrement le socle à `culture_targets.js`, `culture_light.js`, `culture_journal.js`, `culture_equipment.js` (aujourd'hui `fetch`, clé et drapeau `busy` maison, `output` en cas de panne réseau). Corriger la phrase du bilan.
- **Validation.** Étendre `tests/test_culture_errors.py` à un cas par domaine ; `grep -L PhytoCultureForms` reste vide et `grep -c "fetch(" network/web/static/js/culture_*.js` ne compte que le socle.

### R3.4 Écart à la plage cible absent du relevé

- **Constat.** `culture_assistance_store.py:60-74` donne le relevé antérieur mais n'appelle jamais `resolve_targets`/`_current_targets` (`culture_solution_store.py:312,326`), pourtant disponibles et déjà affichés dans le journal. L'audit demande « le précédent à côté du champ et l'écart à la plage choisie ».
- **Correctif.** Dans `_preview` d'un relevé, résoudre la plage applicable à la cible et à la date saisie (ordre strict cible directe → sujet alimenté → réservoir, sans fusion) et ajouter une ligne « Plage applicable : pH 5,8–6,2 (source : …) ; écart : +0,3 ». Aucune valeur préremplie.
- **Validation.** Test Python sur une cible avec plage directe, une alimentée, une sans plage (absence explicite).

### R3.5 Réservoir non proposé, association sans action, cas 0 et ≥2 confondus

- **Constat.** `culture_assistance_store.py:66-74` : phrase informative après clic « Vérifier », sans lien ; `LIMIT 2` puis `len(links) == 1 … else` donne le même texte pour « aucune » et « plusieurs » associations.
- **Correctif.** Distinguer « aucune association déclarée » et « plusieurs associations » ; ajouter un lien vers `/cultures/solutions#reservoirs` ou l'affectation datée ; au chargement du formulaire ouvert depuis une fiche, afficher la source à côté du champ réservoir avec le choix laissé à l'opérateur (aucune sélection automatique).

### R3.6 Suggestions après récolte absentes

- **Constat.** `model/culture_assistance.py:29-50` : seul `release` existe, et seulement pour un sujet archivé. Poids, enseignements et photos finales ne sont jamais proposés.
- **Correctif.** Suggestion « Information manquante » pour un lot en séchage ou récolté sans poids ni photo finale, avec lien vers l'action `finish` existante ; poids facultatif, aucune libération implicite.

### R3.7 Catégorie « Information » hors nomenclature

- **Constat.** `model/culture_assistance.py:46` introduit une quatrième catégorie. L'audit en fixe trois.
- **Correctif.** Reclasser « Aucun relevé disponible » en « Information manquante » et « Dernier relevé saisi il y a N jours » en « À vérifier » ; afficher l'ancienneté en jours via `age()` plutôt que la date brute. Énumérer les valeurs de `category` dans `cultures-api.md`.

### R3.8 Transition guidée partielle

- **Constat.** Le résumé avant/après n'apparaît que sur « Vérifier » ; la date affichée est `effective_at` et jamais `payload.drying_at` ; aucune vérification n'est proposée après le passage en floraison ou séchage.
- **Correctif.** Pour les formulaires `data-culture-event`, afficher le résumé au premier clic « Enregistrer » avec confirmation (une requête de prévalidation, puis la mutation) ; inclure `drying_at` ; après succès, la fiche affiche les vérifications R3.1 du nouveau stade avec focus.

### R3.9 Raccourci « Noter une observation » et recherche

- **Constat.** `cultures.html:92` : le raccourci n'ouvre le formulaire qu'avec une seule culture, sinon renvoie à la liste ; la recherche (`cultures.js:487-505`) filtre les 40 cartes de la page.
- **Correctif.** Raccourci vers un sélecteur de culture (liste filtrable déjà présente) qui aboutit sur `#observation` de la fiche ; recherche serveur `?q=` bornée, en réutilisant la pagination existante. Tests ajoutés (aucun n'exerce `culture-search`).

### R3.10 Protection des saisies non terminées

- **Constat.** Aucun `beforeunload` dans le carnet alors que chaque enregistrement recharge la page.
- **Correctif.** Dans le socle : `beforeunload` armé quand un formulaire enregistré a une saisie différente de son état initial et n'est pas celui en cours de soumission.

### R3.11 Fonctionnement sans JavaScript

- **Constat.** Aucun formulaire de `cultures.html` n'a `method`/`action` ; sans script, « Créer un lot » fait un GET et perd la saisie. Le bilan du lot 2 laisse entendre le contraire.
- **Correctif.** Ne pas prétendre au fonctionnement sans script : corriger le bilan et la doc. Un vrai repli natif est un choix d'architecture à décider séparément.

## P4 — dette, tests, documentation

### R4.1 Tests d'infrastructure

- `tests/test_http_server.py:1262-1270` : ajouter `cultures.html`, `culture_solutions.html`, `culture_cycles.html` au test d'ordre de chargement du socle.
- `tests/ui_server.py:85` et `tests/test_http_server.py:185` : passer `now=` au `CultureStore` ; les dates en dur (relevé au 2026‑09‑02, archivage au 2026‑09‑03) ne sont vertes que depuis que ces dates sont passées.
- `tests/ui/cultures_ui_lot_3.spec.js` : ajouter l'exclusion `pwa-chromium` comme les parcours mutateurs du lot 2, ou documenter le choix ; prouver « sans écriture » en comptant les `POST` (méthode de `cultures_lot_c.spec.js:13-16`) ; ajouter `test.setTimeout` (12,8 s mesurées sous la limite de 20 s, marge faible).
- `tests/test_culture_actions.py` : exercer la vue `_detail` au lieu d'injecter `fiche_actions(item)` dans le contexte ; rendre réellement la branche `stage_options_full` (`:96-100` ne rend rien) ; faire échouer plutôt que skipper quand `allowed_actions` ne renvoie plus « stage ».
- Couverture manquante à ajouter : preview avec `domain` invalide et sous horloge non fiable, bornes `similar ≤ 3` et `items ≤ 4`, lignes d'association de réservoir, `transition_summary` récolte, GET assistance en HTTP (404, `no-store`), chemin 409 « Recharger la fiche », traduction `sentRanks`, restauration d'`aria-describedby`, `reveal()`, fiche au-delà de la 40ᵉ culture, expiration à 30 s.

### R4.2 Dette de code

- `_culture_transaction` vit dans `AssistanceStoreMixin` mais sert `_mutate` et `_solution_mutate` : la déplacer dans `CultureStore`.
- Pré‑`SELECT` de rejeu dans `_preview` (`culture_assistance_store.py:42`) redondant avec celui des mutations : supprimer.
- `self._equipment_context` écrasé par une prévalidation : le passer en paramètre plutôt qu'en attribut.
- `STAGE_RANKS` (`model/culture.py:164-166`) doublonne `stage_path` : dériver l'un de l'autre.
- `_prevalidate_create` et `_write_origins` dupliquent les contrôles d'origine : extraire `validate_origin(origin, origin_type, position)`.
- Message « Renseigner les origines du lot » envoyé à un pied mère avec origines : message dédié avec `field`.
- Deux `local_day` de sémantiques différentes (`culture_checklist.py:36`, `culture_cycle.py`) : n'en garder qu'une.
- `stage_options(current=…)` testé par véracité mais appelé avec une chaîne dans les tests : typer en booléen.
- `culture_cycles.js:5-8` : `decodeURIComponent` du fragment comme les autres scripts.
- `culture_cycle_store.py:72-74` : second classement des rappels avec une seconde horloge, drapeaux jamais lus : supprimer.
- `culture_journal_store.py:157` : lien du journal d'accueil vers `/cultures/{id}#event-{id}`.
- `culture_solutions.js:91-100` : règles d'intention dupliquées en JS ; les exposer depuis le serveur (`data-*`) comme les stades.
- `cultures.html:63` et `:117` : table `REMINDER_STATES` et pagination `40` recopiées ; les passer par le contexte.
- pyflakes : retirer `date` et `STAGES` inutilisés dans `utils/culture_cycle_store.py`.
- Accessibilité : `aria-live="polite"` sur la zone `[data-culture-assistance]` et sur `.culture-review` (apparition et retrait automatiques non annoncés).

### R4.3 Documentation

- `docs/index.md` : ajouter le bilan du lot 3 (leçon du lot 1 non appliquée).
- `cultures-ui-lot-2-2026-09-08.md` : corriger « Toute API du carnet renvoie `field` » et la mention du fonctionnement sans JavaScript.
- `cultures-ui-lot-3.md` : la « limite de 60 secondes » n'existe pas dans `playwright.config.js` (20 s, rallonges par spec) ; nommer les fichiers de la reprise « 32 réussites, 23 exclusions », non reproductible telle quelle ; documenter le polling de 30 s et la double requête, ou les retirer (R2.1, R2.2).
- `cultures-api.md` : énumérer les valeurs de `category` ; préciser que la prévalidation n'est pas appelée sur le chemin nominal une fois R2.1 fait.
- `tasks/lessons.md` : ajouter la leçon « un hook Playwright dans un module partagé ne protège que le premier fichier ».

## Validation de sortie

1. `.venv/bin/python -m pytest -q` : aucune régression, nouveaux tests listés en R4.1 verts.
2. Playwright un profil à la fois, un worker (`PATH="$PWD/.venv/bin:$PATH" PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --project=<profil> --workers=1`), puis la commande de R0.1 avec `PHYTO_UI_BASE_URL` factice : 100 % exclusions.
3. Compteurs de requêtes : un enregistrement nominal = un `POST` ; ouverture d'une fiche = une projection ; assistance à version inchangée = aucune projection.
4. Mesure sur Pi avec un carnet simulé de deux ans (fiche, accueil, assistance) consignée dans le bilan.
5. `diff -u CLAUDE.md AGENTS.md` vide, `git diff --check` vide, pyflakes sans alerte sur le carnet, `docs/index.md` à jour.
