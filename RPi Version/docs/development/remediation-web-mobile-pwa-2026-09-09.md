# Plan de remédiation — audit UI/UX web, mobile et PWA du 9 septembre 2026

Réponse à l'[audit du 9 septembre 2026](audit-web-mobile-pwa-2026-09-09.md) (point de départ `641a7ef`,
preuves dans `docs/images/audit-web-mobile-pwa-2026-09-09/`). Ce plan traite **la totalité** des
constats remontés : les 19 entrées du backlog priorisé (UX-01 à UX-19) et les recommandations du corps
de l'audit qui n'y figurent pas en propre (pages d'erreur, console mobile, cycles, plages, éclairage,
équipements, journal, composants réutilisables, budgets de performance, validation produit). La matrice
de couverture ci-dessous garantit qu'aucun constat n'est perdu ; chaque fiche R-x.y porte le constat,
la cible, les fichiers, les garde-fous et le critère d'acceptation repris de l'audit.

Il ne modifie rien par lui-même. Il ne demande aucune migration SPA ni aucun framework, conformément à
la conclusion de l'audit : le socle (rendu serveur, ressources locales, CSP sans `unsafe-inline`,
service worker à fraîcheur dominante, formulaires du carnet sur `culture_forms.js`) est conservé et
étendu.

## Méthode et baseline

- **Baseline à figer avant le lot 1.** L'arbre porte des modifications non commitées (lot F photos,
  documentation, `cultures.css`, `culture_forms.js`, `tests/ui/cultures_ui_photos.spec.js`). Le plan
  démarre après leur commit ; le commit de départ, le nombre de tests pytest et Playwright par profil
  sont notés dans la section « Suivi — remédiation web, mobile et PWA » de `tasks/todo.md`.
- **Orchestration.** Un agent par lot, une seule tâche par agent ; l'orchestrateur relit chaque
  changement, lance les vérifications et commite. Playwright s'exécute **un profil à la fois**.
- **Vérification de chaque lot** (aucune exception) :

  ```bash
  set -o pipefail
  python3 -m pytest | tee /tmp/pytest-lot.txt | tail -5
  npx playwright test --project=desktop-chromium | tee /tmp/pw-desktop.txt | tail -5
  npx playwright test --project=mobile-chromium  | tee /tmp/pw-mobile.txt  | tail -5
  npx playwright test --project=mobile-etroit    | tee /tmp/pw-etroit.txt  | tail -5
  npx playwright test --project=mobile-paysage   | tee /tmp/pw-paysage.txt | tail -5
  npx playwright test --project=pwa-chromium     | tee /tmp/pw-pwa.txt     | tail -5
  npx playwright test --project=mobile-zoom      | tee /tmp/pw-zoom.txt    | tail -5
  npm run test:js                                                            # service worker exécuté dans node:vm (R3.1)
  python -m pyflakes $(git ls-files '*.py')
  for f in $(git ls-files '*.js'); do node --check "$f"; done
  python3 -c "import pathlib,sys; [print('NUL:',f) for f in sys.argv[1:] if b'\0' in pathlib.Path(f).read_bytes()]" $(git ls-files '*.py' '*.js' '*.css' '*.html' '*.md')
  diff -u CLAUDE.md AGENTS.md
  git diff --check
  ```

  Les specs du carnet démarrent un serveur par test (`tests/ui/culture_fixtures.js`) : elles se
  jouent avec `--workers=1`, deux workers se disputant le port du carnet sur une machine chargée.
- **Mesures reproductibles.** Le lot 0 versionne le script de mesure (hauteurs, positions des titres,
  nombre d'éléments DOM, axe) qui a produit `measures.json`, pour que chaque critère « visible dans le
  premier écran à 390 × 844 » soit **mesuré**, pas apprécié. Les captures de l'audit sont la référence
  « avant » ; chaque lot dépose ses captures « après » dans `docs/images/remediation-web-mobile-pwa-2026-09-09/`.
- **Invariants du dépôt qui bornent ce plan** (rappel, voir `CLAUDE.md`) : aucune commande de contrôle
  derrière un GET ; aucune mutation mise en attente ou rejouée hors ligne ; aucune notification issue
  d'une copie ; aucun script ni style inline ; nouveaux assets ajoutés à l'allow-list statique **et** au
  précache haché ; règles d'action du carnet pures dans `model/culture.py` ; navigation du carnet
  uniquement via `templates/culture_navigation.html` ; formulaires du carnet uniquement via
  `culture_forms.js` ; pas de SQLite dans l'event loop ; drivers et handlers ne s'arrondissent jamais,
  l'arrondi est une affaire de présentation.

## Matrice de couverture de l'audit

| Constat de l'audit | Fiche(s) du plan | Lot |
| --- | --- | --- |
| UX-01 Occurrences avant notifications/filtres (Alarmes) | R1.1 | 1 |
| UX-02 Haut de tableau compact, équipements normaux compacts | R1.2 | 1 |
| UX-03 Cultures dans la barre mobile | R1.3 | 1 |
| UX-04 Nom accessible de Console (`aria-prohibited-attr`) | R1.4 | 1 |
| UX-05 Installation guidée Android/iPhone | R2.4 | 2 |
| UX-06 Promesse exacte des notifications | R1.5 | 1 |
| UX-07 États vides et relevés de Solutions | R1.6 | 1 |
| UX-08 Formatage des nombres affichés | R1.7 | 1 |
| UX-09 Actions et contexte en tête de fiche | R1.8 | 1 |
| UX-10 Lecture de Configuration | R2.1 | 2 |
| UX-11 Analyse tactile harmonisée (Historique et carnet) | R2.2 | 2 |
| UX-12 Lecture hors ligne et index des copies | R2.5 | 2 |
| UX-13 Délais de navigation du service worker, initialisation PWA indépendante | R3.1, R3.2 | 3 |
| UX-14 Cycle explicite de mise à jour PWA | R3.3 | 3 |
| UX-15 Brouillons déclaratifs à restauration explicite | R3.4 | 3 |
| UX-16 Qualification Safari/iOS et aides techniques | R4.1 | 4 |
| UX-17 Mesures de performance terrain | R0.2, R4.2 | 0, 4 |
| UX-18 Lisibilité, cibles tactiles, vocabulaire | R5.1, R5.2, R5.3 | 5 |
| UX-19 Parcours photo mobile homogène | R5.4 | 5 |
| Historique : indicateurs résumés, détail sous le graphique, axes lisibles, légendes dépliables | R2.2 | 2 |
| Cycles : rappels du jour, « À faire » / « Comparer », espace de sauvegarde, distinction rappels/alarmes | R2.6 | 2 |
| Plages cibles, éclairage, équipements : sélection d'abord, déclaré/appliqué, affectations en vue principale | R2.7 | 2 |
| Journal : chronologie lisible, détails au second niveau, recherche visible, contexte au retour | R2.8 | 2 |
| Console mobile : actions secondaires groupées, hauteur du journal, erreurs de presse-papiers | R1.4 | 1 |
| Pages d'erreur : reprise contextuelle et réessai ; « état GPIO relu » / « sonde de vie » en détail | R1.9 | 1 |
| Rubriques du carnet sous 480 px : onglet actif visible, défilement signalé | R1.3 | 1 |
| Police Visitor réservée à la marque, chiffres tabulaires, moins de majuscules | R5.1 | 5 |
| Plein jour dehors, séries distinguables sans la couleur seule | R5.2 | 5 |
| Qualification étendue : formulaires ouverts/refusés, dialogues, hors ligne, zoom, focus sous barres fixes | R0.1, R4.1 | 0, 4 |
| Certificat local, changement d'adresse, renouvellement TLS | R2.4, R4.1 | 2, 4 |
| Réponses HTTP 500 distinctes d'une panne réseau | R3.1 | 3 |
| Installation incomplète, stockage refusé | R3.2 | 3 |
| Composants réutilisables et harmonisation CSS | R0.3 | 0 (puis chaque lot) |
| Budgets Pi/téléphone, carnet 30/90/365 jours, instrumentation locale | R0.2, R4.2 | 0, 4 |
| Validation produit avec opérateurs, objectifs chiffrés | R4.3 | 4 |
| Non qualifiés par l'audit (iPhone physique, VoiceOver/TalkBack, clavier virtuel, encoches, certificat, faible mémoire, mise à jour pendant saisie, plusieurs fenêtres, perte de stockage) | R4.1 | 4 |

## Ordre de traitement

Il suit la séquence recommandée par l'audit, précédée d'un lot d'outillage sans lequel les critères
d'acceptation ne sont pas mesurables.

| Lot | Contenu | Dépend de |
| --- | --- | --- |
| 0 — Outillage | script de mesure versionné, banc de performance, macros de composants | baseline commitée |
| 1 — Lecture et urgence | Alarmes, Tableau, barre mobile, Console, notifications, Solutions, nombres, fiche, erreurs | 0 |
| 2 — Application mobile quotidienne | Configuration, exploration tactile, page PWA et installation, hors ligne, cycles, plages/éclairage/équipements, journal | 1 |
| 3 — Cycle de vie et robustesse | délais du service worker, initialisation indépendante, mise à jour explicite, brouillons | 2 |
| 4 — Qualification | appareils réels et aides techniques, performance terrain, validation produit | 1 à 3 |
| 5 — Finitions | typographie, contrastes et séries, cibles tactiles, vocabulaire, photo mobile | 1 |

Le lot 5 peut s'intercaler après le lot 1 : il ne dépend d'aucun changement de structure. Les brouillons
(R3.4) sont un chantier explicite séparé, précédé d'une décision produit (voir « Arbitrages »).

---

## Lot 0 — Outillage de mesure et socle de composants

### R0.1 Script de mesure versionné

**Constat.** Les mesures de l'audit (`measures.json`, `scenarios.json`, `finalchecks.json`) viennent
d'un script non versionné. Sans lui, « visible dans le premier écran » ne peut pas être vérifié après
correction, et la qualification des états ouverts (formulaires refusés, dialogues, hors ligne, zoom)
n'existe pas.

**Cible.** `tests/ui/measure_pages.js` (Playwright, hors suite par défaut, lancé par
`npm run measure:ui`) qui, pour les 12 pages à 320, 390 et 1440 px : mesure la hauteur du document,
la position `y` des titres `h1`/`h2`, le nombre d'éléments DOM, la largeur de défilement horizontal,
exécute axe (tags `wcag2a`, `wcag2aa`, `wcag22aa`) en sombre et en plein jour, et écrit un JSON au
format de `measures.json`. Scénarios avec données réutilisant `tests/ui/culture_fixtures.js` (une
mère, six relevés). États ouverts : formulaire de relevé ouvert, formulaire refusé (erreur au champ),
menu « Plus » ouvert, bannière hors ligne, zoom 200 % (`deviceScaleFactor` et taille de police).

**Garde-fous.** Un serveur par test pour le carnet (espace 2 exclusif). Aucune requête sortante ; refus
d'une cible `PHYTO_UI_BASE_URL` externe pour les scénarios mutateurs.

**Acceptation.** Rejouer le script sur la baseline reproduit les hauteurs de `measures.json` à ±2 %.
Le JSON de chaque lot est déposé avec ses captures.

### R0.2 Banc de performance page + carnet représentatif

**Constat.** L'audit ne qualifie pas la performance terrain et rappelle que 343 Ko d'assets n'est pas
un poids de page, que ~2 120 éléments DOM en configuration ne disparaissent pas en repliant, et que
la longueur ne prouve pas la lenteur. Il demande de **mesurer avant** de décider d'un chargement à la
demande.

**Cible.** `scripts/benchmark-web-pages.py` : génère une base de carnet temporaire à 30, 90 et
365 jours (relevés, rappels, photos factices) à partir des fabriques de `tests/`, sert le site via
`tests/ui_server.py`, et mesure par page : temps de réponse HTML, taille HTML, nombre d'éléments DOM.
`tests/ui/measure_pages.js` ajoute côté navigateur, sur cible `PHYTO_UI_BASE_URL` (le Pi) : contenu
principal visible, première interaction sur graphique, ouverture d'un formulaire, retour après
enregistrement, mémoire JS (`performance.measureUserAgentSpecificMemory` si disponible, sinon
`performance.memory` en Chromium). Aucune dépendance à un service public d'analytics.

**Acceptation.** Un fichier `docs/development/web-perf-baseline-<date>.md` avec la baseline WSL et la
baseline Pi (R4.2), et des budgets fixés à partir de la mesure, pas à partir des repères Web Vitals
seuls (LCP ≤ 2,5 s, INP ≤ 200 ms, CLS ≤ 0,1 restent les repères, non des résultats).

### R0.3 Macros de composants partagés

**Constat.** L'audit demande quelques composants réutilisables plutôt que des exceptions CSS par page :
en-tête compact, état vide, résumé d'alarme, ligne d'équipement, entrée de journal, groupe de champs,
détail de graphique, état réseau.

**Cible.** `network/web/templates/macros/ui.html` (Jinja2, autoescape conservé) avec
`compact_header(title, facts, primary_action, secondary_actions)`, `empty_state(title, text, action)`,
`alarm_summary(alarm)`, `equipment_row(equipment, expanded)`, `journal_entry(row)`,
`field_group(legend, help)`, `chart_detail(point)`, `network_state()`. Styles correspondants dans
`style.css` (préfixe `.ui-`), sans supprimer les classes existantes tant qu'une page les utilise.
Chaque lot suivant remplace le balisage ad hoc par ces macros **dans les pages qu'il touche**, jamais
au-delà.

**Garde-fous.** Pas de script inline ; les macros ne posent que des attributs `data-*` lus par les JS
existants. `tests/test_culture_actions.py` (équivalence des actions) s'adapte au nouveau balisage, ne
se supprime pas.

**Acceptation.** Les huit macros sont documentées dans `docs/development/contributing.md` avec un
exemple chacune ; axe vert sur une page témoin par macro.

---

## Lot 1 — Lecture et urgence

### R1.1 Alarmes : occurrences avant notifications et filtres (UX-01, P1)

**Constat mesuré.** `alarms.html` enchaîne héros → panneau « Notifications locales » (y=429) → quatre
filtres verticaux → liste (y=1 131). Le même ordre s'applique avec des alarmes.

**Cible.** Ordre : résumé court (nombre d'actives, plus haute gravité, dernière occurrence) →
alarme la plus importante développée → liste → `<details>` « Filtres avancés » → `<details>`
« Préférences de notification ». Chaque occurrence expose immédiatement **problème, conséquence,
action conseillée** (trois lignes, macro `alarm_summary`) avant les détails techniques. Sous le bouton
d'acquittement : « Acquitter = signaler que vous avez vu l'alarme ; cela ne corrige pas la panne ».
Les états « Active », « Active, acquittée » et « Résolue » restent trois libellés distincts. Quand la
vue filtrée est statique (`data-live-refresh="false"`), un bouton explicite « Actualiser » (lien GET
vers la même URL) accompagne la mention existante.

**Fichiers.** `network/web/templates/alarms.html`, `network/web/static/css/style.css`,
`utils/alarm_manager.py` uniquement si les champs problème/conséquence/action n'existent pas déjà dans
le catalogue d'alarmes (les y ajouter comme texte statique, pas de logique nouvelle), `pwa.js`
(`updateAlarmChrome` doit retrouver ses ancres après réordonnancement).

**Acceptation (audit).** Sur le scénario mobile défini (390 × 844, une alarme critique de la fixture),
la première alarme critique et son action sont visibles **sans défilement** ; mesuré par R0.1. Axe
vert. `dashboard.spec.js` ajoute le scénario « alarme critique en tête ».

### R1.2 Tableau de bord : haut compact et équipements normaux repliés (UX-02, P1)

**Constat mesuré.** 5 035 px à 390 px : « Climat actuel » à y=514, « Actionneurs » à y=941,
« Capteurs actifs » à y=2 803, « Cultures en cours » à y=4 329. Les cartes d'équipements répètent état,
motif, prochaine transition et conduite normale.

**Cible.** `main.html` :
1. En tête, une seule bande compacte (macro `compact_header`) : état de la serre, fraîcheur des
   données, T/RH et cible, alarme active éventuelle. Le héros et `#control-overview` fusionnent dans
   cette bande ; leurs textes d'explication passent sous un `<details>` « Comprendre cet état ».
2. Ensuite « Anomalies et interventions prioritaires » : alarmes actives, coupures (overrides) en
   cours, rappels du jour du carnet (`overview["today"]`, sans projection neuve), avec liens directs.
3. « Équipements » : une ligne compacte par équipement (macro `equipment_row`) : nom, état, prochaine
   transition, bouton de coupure ; développement au toucher (`<details>`) pour motif et conduite
   normale. Une ligne dont l'équipement est en coupure, en anomalie ou en état non relu est rendue
   **ouverte** côté serveur : un défaut n'est jamais caché par un repli.
4. Liens visibles « Voir les équipements » (ancre) et « Toutes les mesures » (ancre) dans la bande
   compacte.
5. Les cartes capteurs et l'aperçu d'historique restent, après les tâches du jour.

**Garde-fous.** Les distinctions état demandé / appliqué / relu, l'affichage des absences et la
confirmation des commandes critiques (POST, CSRF, confirmation navigateur) sont conservés à
l'identique. Aucune route nouvelle. Le rafraîchissement 5 s (`dashboard.js` ou équivalent) doit
mettre à jour les lignes compactes **et** rouvrir une ligne qui passe en anomalie.

**Acceptation (audit).** À 390 × 844 : état, fraîcheur, T/RH et alarme visibles sans défilement, accès
aux équipements en un geste ; hauteur du document de la fixture divisée par deux au moins ; aucun
défaut masqué (test Playwright : une coupure active rend sa ligne ouverte, un rafraîchissement qui
apporte une anomalie l'ouvre).

### R1.3 Navigation mobile : Cultures en un geste, rubriques du carnet (UX-03, P1)

**Constat.** `base.html` (lignes 67-71) : Tableau, Alarmes, Historique, Plus ; Cultures est dans
« Plus ». Les sept rubriques du carnet défilent horizontalement sous 480 px.

**Cible.** Barre basse **Serre · Cultures · Alarmes · Plus** ; Historique reste dans la bande compacte
du tableau (R1.2) et dans « Plus ». Une variante à cinq destinations (avec Historique) est activée
par `@media (min-width: 400px)` seulement si R0.1 montre qu'elle tient à 320 px sans troncature ;
sinon quatre. Le compteur d'alarmes actives reste sur l'onglet Alarmes. `aria-current="page"` sur
Cultures pour toute page `/cultures…`. Dans `culture_navigation.html` : l'onglet actif est amené
dans la zone visible au chargement et au retour (`scrollIntoView({inline:"nearest"})` dans le JS
du carnet, pas inline), un dégradé de bord signale le défilement, et un `<select>` de rubrique
compact est **préparé mais non activé** tant que R4.3 n'a pas montré que les derniers onglets sont
ignorés.

**Garde-fous.** Pas de barre fixe haute supplémentaire : la somme barre de saisie + barre basse est
mesurée à 320 × 568 et 568 × 320 (profil paysage) et ne doit pas laisser moins de 50 % de hauteur
utile. La navigation du carnet ne se réécrit **que** dans le fragment partagé.

**Acceptation (audit).** Depuis toute page, le carnet en un geste ; focus, état actif et retour
préservés à 320 px (test Playwright sur `mobile-etroit` : aller-retour Tableau → Cultures →
Solutions → retour, `aria-current` correct, focus sur l'onglet au retour).

### R1.4 Console : nom accessible, actions mobiles, presse-papiers (UX-04, P1)

**Défaut vérifié.** `console.html:36` pose `aria-label` sur un `<pre>` sans rôle : axe
`aria-prohibited-attr`, impact « serious », absent de la liste des pages du test axe
(`dashboard.spec.js`, qui ne couvre que `/`, `/alarms`, `/history`, `/conf#life`).

**Cible.**
- Envelopper le `<pre>` dans une région nommée : `<section role="region"
  aria-labelledby="console-output-title">` avec un titre visuellement masqué « Journal système en
  direct » ; le `<pre>` garde `tabindex="0"` (défilement clavier) et perd `aria-label`. **Pas** de
  `role="log"` ni d'`aria-live` sur le flux : un journal en continu ne doit pas devenir une annonce
  permanente. Les changements d'état (pause, suivi, filtre) sont annoncés par l'`<output
  role="status">` existant ou à créer.
- Sur mobile, les actions secondaires (niveau, composant, recherche, copie, export) passent dans un
  `<details>` « Filtres et outils » ; le journal récupère la hauteur (`min-height` en `dvh`).
- Copie : `navigator.clipboard` est absent en HTTP non sécurisé. Repli : sélection du texte et message
  « Copie indisponible sur cette connexion, utilisez Exporter » dans l'`<output>`.

**Acceptation (audit).** Axe sans `aria-prohibited-attr` ; région lisible au lecteur d'écran sans
annonces continues ; `/console` ajouté à la liste des pages du test axe ; test Playwright du repli de
copie (contexte non sécurisé simulé par suppression de `navigator.clipboard`).

### R1.5 Notifications : promesse exacte (UX-06, P1)

**Constat.** `pwa.js:451` : « Notifications actives sur ce terminal tant que la PWA reste active » ;
`pwa.js:445` : aide de refus qui cite Chrome sur tous les navigateurs. Le poller ne travaille que
document visible.

**Cible.** Texte : « Notifications actives lorsque l'application est ouverte au premier plan et
connectée au contrôleur. Le système peut les suspendre en arrière-plan ; ce n'est pas une alerte à
distance. » Aide de refus adaptée par détection de plateforme (Chromium/Android, Safari/iOS, Firefox,
autre) avec un libellé générique en dernier recours ; aucune promesse de Web Push. Même précision dans
`docs/operations/pwa-local-tls.md` et `docs/reference/http-interface.md`.

**Acceptation (audit).** Premier plan et connexion explicités ; aide adaptée au navigateur (test unitaire
JS de la fonction de libellé via Playwright `page.evaluate`, trois agents utilisateur).

### R1.6 Solutions : états vides et relevés allégés (UX-07, P1)

**Constat mesuré.** 3 259 px à vide, 7 001 px avec six relevés : saisie, réservoirs, filtres, deux
graphiques, légendes, export, journal, contexte et recettes sur une seule page.

**Cible.** Trois vues nommées **Saisir · Relevés · Analyser**, rendues par la même route
`/cultures/solutions` avec un paramètre `view` (défaut `saisir` si cible sélectionnée sans relevé,
`releves` sinon), sous forme d'onglets `role="tablist"` **sans** chargement dynamique : les trois
blocs sont servis, les deux inactifs sont `hidden` ; le lien de chaque onglet est un vrai lien
(`?view=`) pour rester lisible hors ligne et sans JS.
- Cible sélectionnée : d'abord la cible et son **dernier relevé** ; réservoirs globaux repliés.
- À vide : macro `empty_state` avec une phrase et « Saisir le premier relevé » ; les graphiques et
  leurs légendes ne sont pas rendus (le gabarit teste `data.entries`).
- Chaque relevé compacté en une ligne : date, cible, pH, EC, anomalie éventuelle ; contexte
  historique, traçabilité et références techniques dans un `<details>` « Détails ».

**Garde-fous.** `culture_forms.js` reste le socle (identifiants stables, `register` rejouable) ;
l'explorateur reste `culture_analysis.js` ; la légende par mesure (`9136e40`) est conservée dans la
vue Analyser ; la navigation reste dans `culture_navigation.html` (`culture_section='solutions'`,
`view` conservé dans le contexte). Aucune route ni persistance nouvelle.

**Acceptation (audit).** À vide, une action claire ; six relevés lisibles sans répétition systématique
de la traçabilité ; hauteur avec six relevés réduite d'au moins 40 % à 390 px (R0.1) ; specs
`cultures_ui_lot_4.spec.js` et `cultures_ui_photos.spec.js` adaptées au balisage, pas supprimées.

### R1.7 Formatage des nombres affichés (UX-08, P1)

**Constat.** `culture_solutions.html:118` (et lignes 83, 97, 129) affiche `entry.ph` / `entry.ec`
bruts : `1.4 + 0.05` sort en décimales binaires longues. Les valeurs persistées sont correctes.

**Cible.** Un filtre Jinja `nombre(value, decimals, unit=None)` dans `network/web/pages.py`, à côté
de `mesure` : virgule française, décimales bornées par une précision métier explicite (pH 2, EC 2,
volumes 1, températures selon le catalogue), `—` pour `None`, `0` affiché comme `0,00` et jamais
comme une absence. Réplique JS `formatNombre` dans `culture_analysis.js` pour les détails d'exploration
et dans `history.js` pour l'infobulle. Les données `data-chart` (JSON), les `value` des champs de
saisie et l'export CSV restent **bruts**.

**Garde-fous.** Aucun arrondi côté magasin, modèle ou API (`/api/v1/cultures/…` inchangé). La saisie
avec virgule est déjà acceptée pour les relevés (`model/culture_solution.py:28`) ; un test pytest le
fige. La même tolérance est à vérifier pour `/conf` (R2.1).

**Acceptation (audit).** Décimales françaises bornées, zéro distinct de l'absence, précision persistée
inchangée (test pytest du filtre et d'un aller-retour saisie → API ; test Playwright sur la fixture
`1.4 + 0.05`).

### R1.8 Fiche culture : synthèse et actions en tête (UX-09, P2, avancé au lot 1 par l'audit)

**Constat mesuré.** Fiche d'une mère avec six relevés : 4 325 px, nom à y=412, « Que faire
maintenant ? » à y=983, après introduction, navigations, métadonnées et aides.

**Cible.** En tête (macro `compact_header`) : nom, espace, stade, âge ; puis les deux actions
principales « Saisir un relevé » et « Observation / photo » ; puis les aides utiles. Règles de calcul
d'âge dans `<details>` « Comprendre ces dates » ; corrections et backfill derrière un accès
secondaire explicite « Corriger l'historique ». Le bilan et les archives restent accessibles en bas
de page. Retour à la liste avec position et filtres conservés (ancre `culture-{id}` sur la liste,
`tabindex="-1"`, paramètres de filtre rejoués dans le lien de retour, comme les ancres
`event-{id}`).

**Garde-fous.** `allowed_actions`, `stage_options`, `first_stage`, `creation_stages`,
`fiche_actions` restent la seule source des conditions d'action ; `tests/test_culture_actions.py`
s'adapte. Aucune projection neuve ; `overview["today"]` reste l'unique date.

**Acceptation (audit).** Nom/espace/stade et première action dans le premier écran du scénario
nominal (390 × 844, mesuré) ; retour à la liste sur l'élément d'origine (test Playwright).

### R1.9 Pages d'erreur et actions système

**Constat.** `error.html` propose uniquement « Retour au tableau de bord ». `system_action.html`
emploie « état GPIO relu » et « sonde de vie » dans le résumé.

**Cible.**
- `error.html` : conserver le retour au tableau ; ajouter « Revenir à la page précédente » quand le
  `Referer` est de même origine et passe la validation d'hôte privée existante (lien serveur, pas de
  `history.back()` inline) ; pour 502/503/504 et pour une 500 sur un GET, ajouter « Réessayer » (lien
  vers l'URL demandée). Jamais de réessai proposé sur un POST.
- `system_action.html` : résumé immédiat compréhensible (« Le redémarrage est en cours, la page se
  reconnectera d'elle-même ») ; « état GPIO relu », « sonde de vie » et le détail du suivi dans un
  `<details>` « Détails techniques ».

**Garde-fous.** Les redirections restent des `HTTPException` hors du rendu d'erreur ; les erreurs
restent texte brut pour un client non navigateur.

**Acceptation.** Tests pytest des trois variantes de liens (referer absent, externe, interne) et du
réessai limité aux GET ; axe vert sur `/inexistant`.

---

## Lot 2 — Application mobile quotidienne

### R2.1 Configuration lisible (UX-10, P2)

**Constat.** Mode simple de 3 662 px ; horaires en champs séparés ; la normalisation peut annoncer des
changements additionnels importants ; ~2 120 éléments DOM.

**Cible.**
- Regrouper « Jour/nuit », « Éclairage », « Climat » (macro `field_group`) avec un résumé compact en
  tête de groupe (« 06:00 → 22:00 · 24 °C / 18 °C ») mis à jour par `config.js`.
- Horaires : un champ `type="time"` par borne quand le navigateur le supporte, repli sur les champs
  actuels ; la valeur envoyée reste celle du schéma `AppConfig`.
- Avant sauvegarde, tableau « valeur modifiée → valeur appliquée » incluant les **normalisations**
  (le bloc existant est transformé en tableau à deux colonnes, chaque ligne nommant le champ).
- La barre de saisie mobile (`#config-dirty-bar`) ne masque jamais le dernier champ ni son erreur :
  `scroll-padding-bottom` et `padding-bottom` du formulaire égaux à la hauteur de la barre plus la
  zone sûre ; le focus programmatique sur un champ en erreur utilise `scrollIntoView({block:"center"})`.
- Recherche de réglage en mode avancé : **préparée** (index des libellés côté serveur), activée
  seulement si R4.3 confirme la difficulté d'orientation.
- Décimales : les champs numériques acceptent virgule et point (validation `AppConfig` ou conversion
  dans `/conf/{section}` avant `model_validate`), message d'erreur explicite.

**Garde-fous.** L'unité de sauvegarde par section et le candidat `AppConfig` complet sont conservés ;
GPIO reste en lecture seule ; les secrets vides signifient « inchangé » ; aucune réduction du DOM
par chargement à la demande avant la mesure R0.2/R4.2.

**Acceptation (audit).** Sections compréhensibles, changements induits explicites, dernier champ et
sauvegarde accessibles au clavier virtuel (test Playwright : focus sur le dernier champ d'une section
avec barre visible, le champ n'est pas recouvert, mesuré par `getBoundingClientRect`).

### R2.2 Exploration tactile harmonisée : Historique et carnet (UX-11, P2)

**Constat.** `history.js` : textes canvas de 10 px (l. 58) et 11 px (l. 153, 169) contre 14 px dans le
carnet ; infobulle fixe proche du toucher ; légendes nombreuses. 3 903 px rempli sur mobile.

**Cible.**
- Trois ou quatre indicateurs résumés avant les tracés (T min/max/moy, RH, part de lacunes) à partir
  des données déjà envoyées par `/api/v1/history`.
- Sélection claire d'un indicateur (`role="tablist"` ou `<select>`), un tracé à la fois sur mobile.
- Détail du point choisi affiché **sous** le graphique sur téléphone (macro `chart_detail`, région
  `aria-live="polite"` atomique), infobulle conservée au bureau.
- Texte des axes à 13 px minimum (`history.js`), taille stable par `devicePixelRatio`.
- Explications techniques (couvertures, lacunes, méthode) dans `<details>`.
- Gestes et vocabulaire alignés sur `culture_analysis.js` : tap avec distance maximale, flèches et
  Début/Fin au clavier, même libellé « Point sélectionné », **sans** fusion canvas/SVG.
- Le défilement vertical reste possible pendant un toucher sur le graphique (`touch-action: pan-y`) ;
  le point choisi est conservé au changement de taille (index conservé, pas la position en pixels).

**Acceptation (audit).** Point choisi lisible hors du doigt, axes lisibles, défilement vertical
possible, tableau accessible (tests Playwright sur `mobile-chromium` : sélection d'un point puis
redimensionnement, le détail affiche le même horodatage ; `touch-action` vérifié).

### R2.3 Séries et légendes des graphiques du carnet

**Constat.** Les légendes détaillées des deux graphiques de Solutions et de l'historique alourdissent
la lecture (audit, sections Historique et Solutions).

**Cible.** Légende courte par défaut (nom de série et unité), légende détaillée (source, période)
dans `<details>` « Légende complète » ; conservation de la légende par mesure de `9136e40`. Cette
fiche est réalisée avec R1.6 (vue Analyser) et R2.2.

**Acceptation.** Hauteur de la vue Analyser avec six relevés inférieure à 2 000 px à 390 px ; axe vert.

### R2.4 Page « Application sur ce téléphone » et installation guidée (UX-05, P1)

**Constat.** Le bouton d'installation n'apparaît qu'après `beforeinstallprompt` (`pwa.js:249`) et
seulement sur le tableau ; la documentation TLS ne décrit qu'Android ; l'interface ne guide ni iPhone
ni certificat local ; l'index des pages conservées n'est visible que sur Cycles.

**Cible.** Route GET `/app` (`server.py`, allow-list, page lisible mise en cache par le service worker
comme les autres pages de lecture), gabarit `pwa.html`, entrée « Application sur ce téléphone » dans
« Plus » et dans la barre mobile via Plus. Contenu, tout rendu par le serveur puis complété par
`pwa.js` :
1. **Connexion** : HTTPS ou HTTP, adresse à utiliser, état du certificat (contexte sécurisé ou non),
   lien vers la procédure d'approbation du certificat (`docs/operations/pwa-local-tls.md`, section
   par plateforme). L'interface ne peut pas installer une autorité : elle guide et identifie la
   bonne adresse.
2. **Installation** : état installé (`display-mode: standalone`, `navigator.standalone`), bouton
   d'installation si l'invite existe, sinon **aide par plateforme** : Android/Chromium (menu →
   « Installer l'application »), iOS/iPadOS Safari (Partager → « Sur l'écran d'accueil », mention
   que les sites ajoutés s'ouvrent comme web apps depuis iOS 26), Firefox, autre. Les textes
   affichent la version système testée et sont vérifiés en R4.1 sur appareils réels.
3. **Lecture hors ligne** : index des copies conservées (date, limite de 20 pages et 40 photos,
   liste des vues disponibles, lien vers le carnet), repris de l'index existant de Cycles et
   partagé avec R2.5.
4. **Notifications** : les contrôles et le texte de R1.5.
5. **Version** : `PWA_CACHE_VERSION`, version du service worker actif, et l'état « Mise à jour
   disponible » de R3.3.

**Garde-fous.** Aucune information sensible (pas de secret, pas de mot de passe Wi-Fi) ; aucune
commande. La page est utilisable sans service worker et sans JS (états « inconnus » explicites).

**Acceptation (audit).** Aucun cul-de-sac quand l'invite est absente (test Playwright sans
`beforeinstallprompt` : l'aide de la plateforme simulée est visible) ; parcours testé sur appareils
avec certificat approuvé en R4.1 ; qualification du changement d'adresse réseau et du renouvellement
TLS documentée.

### R2.5 Hors ligne : outils locaux, index des copies, `/offline` (UX-12, P2)

**Constat vérifié.** `pwa.js:144` `setControlsDisabled()` désactive **tous** les contrôles des
formulaires, y compris les filtres GET et les curseurs. `offline.html` ne propose que Tableau, Alarmes,
Historique.

**Cible.**
- Trois classes de contrôles, par attribut :
  * `data-offline-local` : outils de lecture locale (recherche dans les lignes chargées, explorateur
    de graphique, sélection de série, onglets de vue) — **restent actifs** hors ligne ;
  * formulaires GET serveur (filtres) — restent désactivés, avec un message à côté du formulaire :
    « Filtre indisponible hors ligne : seules les données conservées sont affichées » ; si un filtrage
    local est ajouté (journal, relevés), il annonce « Filtre limité aux données conservées » ;
  * mutations — bloquées comme aujourd'hui.
  `setControlsDisabled` ne touche plus aux `data-offline-local` ; les explorateurs SVG/canvas ne sont
  pas dans un `<form>` ou portent l'attribut.
- `/offline` : ajout de « Carnet de cultures (copies conservées) » avec date de la copie la plus
  récente et lien vers l'index de `/app` ; formulation qui ne laisse pas croire que toutes les pages
  sont disponibles.
- L'index des copies devient un fragment partagé (`templates/offline_index.html`), rendu sur `/app`,
  `/offline` et Cycles.

**Garde-fous.** Ne pas réactiver aveuglément les GET ; aucune file, aucun rejeu ; la bannière
« HORS LIGNE — données datant de… — lecture seule » est conservée ; le service worker ne cache
toujours ni `/api/`, ni `/health/`, ni `/status`, ni le SSE.

**Acceptation (audit).** Recherche locale utilisable si proposée, couverture annoncée, mutations
bloquées, accès carnet depuis `/offline` (tests sur `pwa-chromium` : hors ligne, l'explorateur de
Solutions répond au clavier, le filtre GET est désactivé avec son message, un POST est refusé).

### R2.6 Cycles et rappels

**Constat.** Rappels, comparaisons, climats, vérifications, photos et sauvegardes cohabitent ;
2 275 px à vide, 3 705 px avec une culture.

**Cible.** En tête, « Rappels du jour » (gestes Fait/Reporter existants) ; puis deux blocs distincts
« À faire » et « Comparer » (onglets liens comme R1.6) ; l'export complet dans une section
« Sauvegarde » nommée et repérable (icône et libellé identiques à ceux de `/app`). Le libellé des
rappels précise « rappel du carnet », jamais « alarme » ; aucune notification système issue d'un rappel.

**Garde-fous.** Plafond de comparaison et absences explicites conservés ; sélecteur borné à 200 ;
`data-cycle-return="agenda"` conservé.

**Acceptation.** Rappels du jour dans le premier écran à 390 × 844 avec une culture (R0.1) ; specs
lot 4 adaptées.

### R2.7 Plages cibles, éclairage, équipements

**Constat.** Éclairage 2 762 px, Équipements 3 313 px à vide ; sur Équipements le catalogue précède le
contexte à une date (y=1 170) et les affectations (y=1 548).

**Cible.** Sur les trois pages : d'abord le sélecteur espace/culture et date (formulaire GET, valeurs
conservées), puis deux colonnes ou deux blocs « Déclaré dans le carnet » et « Appliqué maintenant »
avec ces libellés exacts ; règles de résolution dans `<details>` « Comment cette valeur est choisie »
avec une indication courte près de la valeur (« cible directe », « sujet alimenté », « réservoir »
pour les plages ; « affectation du 12/08 », « contexte copié à la saisie », « inconnu » pour les
équipements). Équipements : les affectations deviennent la vue principale, le catalogue de référence
est replié. Plages : la plage actuellement applicable, sa source et sa période en tête.

**Garde-fous.** Résolution cible directe → sujet alimenté → réservoir **sans fusion** et **sans
rétroactivité** ; contexte d'équipement affectation datée → copie à la saisie → inconnu, **jamais** le
catalogue courant ; ces règles restent dans `model/culture_*.py`, le gabarit n'affiche que le résultat
et sa source.

**Acceptation.** Sur Équipements, les affectations sont le premier bloc après le sélecteur ; sur
Plages, la plage applicable et sa source sont visibles dans le premier écran ; specs lots E, F, G
adaptées ; tests pytest de résolution inchangés et verts.

### R2.8 Journal

**Constat.** Recherche, filtre par cible, raccourcis 7/30 jours et export existent. La chronologie
mêle résolution et révision aux lignes.

**Cible.** Une ligne par opération (macro `journal_entry`) : date, opération, cible, résumé, vignette
de photo éventuelle ; détails de résolution et de révision dans `<details>`. Accès visible à la
recherche sur les carnets volumineux (champ en tête, pas seulement dans les filtres) ; filtres et
contexte conservés au retour depuis une fiche (mêmes paramètres rejoués dans le lien de retour).

**Garde-fous.** La vue SQL `culture_journal` reste la source ; `search_key` reste l'unique définition
de l'équivalence de recherche, réplique JS alignée.

**Acceptation.** Hauteur du journal à 20 lignes réduite d'un tiers à 390 px ; recherche visible sans
défilement ; `cultures_ui_lot_4_journal.spec.js` adaptée.

---

## Lot 3 — Cycle de vie et robustesse PWA

### R3.1 Budget d'attente du service worker et réponses 5xx (UX-13, P2)

**Risque identifié par lecture.** `service-worker.js` appelle `fetch()` sans délai applicatif dans les
navigations (l. 53, 64, 82), `networkOnly` (l. 48) et le préchargement (`warmReadablePages`). Un Wi-Fi
qui garde la connexion sans répondre laisse la navigation attendre avant le repli daté.

**Cible.**
- `fetchWithBudget(request, ms)` avec `AbortController` : navigations de pages 8 s, préchargement
  15 s, API et SSE inchangés (délais applicatifs déjà en place côté client, `networkOnly`).
- Repli sur la copie datée **seulement** après échec de transport (exception réseau ou `AbortError`).
- Une réponse HTTP 5xx est une **vraie réponse** : `navigationFallback` la sert déjà telle quelle
  (seul `response.ok` est mis en cache). Ce comportement est **conservé** et, désormais, testé : la
  page d'erreur du serveur (R1.9) s'affiche, jamais la copie datée.
- Le budget est publié dans `/app` (« repli après 8 s sans réponse »).

**Garde-fous.** Aucune mise en cache des méthodes mutantes ni des réponses non `ok` ; la bannière
distingue « hors ligne » (transport) de « service dégradé » (le contrôleur répond).

**Acceptation (audit).** Réseau sans réponse : repli daté dans le budget défini (test `pwa-chromium`
avec `page.route` qui ne répond jamais : la page datée s'affiche entre 8 et 10 s) ; réponse 500 :
la page d'erreur s'affiche, pas la copie.

### R3.2 Initialisation PWA indépendante (UX-13, P2)

**Constat.** `pwa.js:507` attend `navigator.serviceWorker.ready` avant `configureNotificationControls`
et le démarrage du poller global ; un worker qui tarde retient ces capacités.

**Cible.** Ordre d'initialisation : préférences → poller → bannière → contrôles de notification
(fonctionnels sans worker, le worker n'étant requis que pour l'affichage d'une notification) →
enregistrement du worker **sans attente** ; `ready.then(...)` branche ensuite ce qui en dépend. Un
`register()` en échec, une installation incomplète (`installing` sans `activated`) ou un stockage
refusé (IndexedDB indisponible, quota) donnent un état lisible sur `/app` (« lecture hors ligne
indisponible : stockage refusé ») sans bloquer l'interface connectée.

**Acceptation (audit).** Worker défaillant : interface connectée utilisable (test `pwa-chromium` :
`/service-worker.js` renvoyé en 500 par `page.route`, le poller d'alarmes tourne et les contrôles
sont actifs) ; IndexedDB neutralisée (`page.addInitScript`) : pas d'exception, état explicite.

### R3.3 Cycle explicite de mise à jour (UX-14, P2)

**Risque de cycle de vie.** `service-worker.js` : `skipWaiting()` à l'installation (l. 29),
`clients.claim()` et suppression des anciens caches à l'activation (l. 43-44). `pwa.js` n'offre pas
de « version disponible / activation ». Une page ouverte sur l'ancienne version, une nouvelle version et
le retrait des caches n'ont pas été testés ensemble.

**Cible.**
- Le worker n'appelle plus `skipWaiting()` de lui-même ; il attend un message `{type:"activer"}`.
- `pwa.js` écoute `updatefound` → `statechange: installed` (avec un contrôleur déjà présent) et affiche
  « Mise à jour disponible » (bannière discrète + état sur `/app`) avec un bouton « Mettre à jour ».
- Activation à la demande : `postMessage({type:"activer"})` puis, sur `controllerchange`, rechargement
  **uniquement si aucun formulaire n'est modifié** (état « sale » de `config.js` et de
  `culture_forms.js` exposé par une fonction commune `window.PhytoForms.isDirty()`) ; sinon message
  « La mise à jour s'appliquera à la prochaine ouverture » et aucun rechargement.
- Suppression des anciens caches uniquement à l'activation de la nouvelle version, après `claim`.
- Une ancienne page ouverte hors ligne continue de fonctionner sur ses caches tant que la nouvelle
  version n'est pas activée.

**Acceptation (audit).** Saisie ouverte + mise à jour + deux fenêtres + hors ligne : aucun rechargement
destructeur implicite (tests `pwa-chromium` : deux contextes, `PWA_CACHE_VERSION` changé par
redémarrage du serveur de test, formulaire modifié dans la première fenêtre, activation depuis la
seconde ; la première conserve sa saisie et affiche le message ; retour de veille simulé par
`visibilitychange`).

### R3.4 Brouillons déclaratifs à restauration explicite (UX-15, P2 — chantier séparé)

**Constat.** Les gardes de sortie existent, mais `beforeunload` n'est pas garanti sur mobile à la
fermeture du processus ; les saisies sont en mémoire de page.

**Cible (à concevoir après arbitrage, voir plus bas).** Module `drafts` dans `culture_forms.js` :
- portée : notes, observations d'espace, champs texte et sélections (cible, date) des formulaires du
  carnet inscrits explicitement (`data-culture-draft="<clé stable>"`) ;
- **exclus** : mesures numériques (pH, EC, volumes, températures), confirmations (`ARMER` et
  équivalents), vérifications cochées, secrets, tout formulaire de `/conf`, toute commande de
  contrôle, photos (stratégie distincte de taille et de confidentialité, hors de ce lot) ;
- stockage IndexedDB local, clé = clé du formulaire + cible + version de la fiche, expiration 24 h,
  suppression à l'enregistrement réussi et sur demande ;
- restauration **uniquement** par le bouton « Restaurer le brouillon » d'une bannière « Brouillon
  sur cet appareil, non enregistré (il y a 12 min) », après revalidation de cible, date et version
  (une fiche modifiée entre-temps invalide le brouillon avec un message) ; jamais de soumission
  automatique, jamais de rejeu.

**Garde-fous.** Ce n'est pas une réactivation des mutations hors ligne : un brouillon n'est jamais
envoyé sans action de l'opérateur en ligne ; la clé d'idempotence est régénérée à la restauration.

**Acceptation (audit).** Arrêt du navigateur : note récupérable ; aucun rejeu, aucune confirmation ni
mesure inventée (tests `pwa-chromium` : saisie d'une note, fermeture du contexte, réouverture,
restauration explicite ; une mesure saisie n'est pas restaurée ; un brouillon d'une fiche dont la
version a changé est refusé).

---

## Lot 4 — Qualification

### R4.1 Appareils réels, aides techniques, cas non qualifiés (UX-16, P2)

**Constat.** Non qualifiés par l'audit : iPhone/iPad physiques, VoiceOver/TalkBack, clavier virtuel
réel, encoches, installation avec certificat local, faible mémoire, performance Pi et Wi-Fi de serre,
mise à jour PWA pendant une saisie, plusieurs fenêtres, perte du stockage navigateur. Axe ne couvre
ni les états ouverts ni les aides techniques.

**Cible.** `docs/development/qualification-mobile-pwa.md` : protocole et grille de résultats, une
ligne par scénario × appareil, à remplir par l'opérateur (l'agent prépare, ne peut pas exécuter) :
- matrice : Android/Chromium, iPhone Safari (iOS courant et iOS 26), iPad, tablette Android ; portrait
  et paysage ; zoom 200 % et grande police système ;
- scénarios : les dix tâches de R4.3, plus installation avec certificat approuvé, changement
  d'adresse du Pi, renouvellement TLS, mise à jour pendant une saisie (R3.3), deux fenêtres,
  effacement du stockage du site, retour de veille, réseau sans réponse (R3.1), clavier virtuel sur
  `/conf` et sur un relevé, focus sous les barres fixes (critère WCAG 2.2 « focus non masqué ») ;
- aides techniques : VoiceOver et TalkBack sur Tableau, Alarmes, Console, fiche, relevé, explorateur.
Ce qui est reproductible en Playwright est ajouté à la suite (états ouverts, refusés, dialogues, hors
ligne, zoom via `deviceScaleFactor`, focus sous barres fixes par mesure de recouvrement).

**Acceptation (audit).** Scénarios critiques sur appareils, VoiceOver/TalkBack, zoom, paysage et clavier
virtuel : grille remplie, écarts reversés en fiches R-x.y complémentaires dans ce plan.

### R4.2 Performance terrain (UX-17, P2)

**Cible.** Exécuter R0.2 sur le Pi (`PHYTO_UI_BASE_URL`, carnet 30/90/365 jours restauré sur une
**copie isolée** via `scripts/restore-cultures.py`, jamais sur la base de production) depuis un
téléphone sur le Wi-Fi de la serre. Publier `docs/development/web-perf-baseline-<date>.md` : baseline
et budgets par page (réponse HTML, contenu principal visible, interaction graphique, ouverture de
formulaire, retour après enregistrement, DOM, mémoire). Décision sur le chargement à la demande de
`/conf` **après** cette mesure seulement.

**Acceptation (audit).** Baseline et budgets reproductibles sur Pi/téléphone/carnet représentatifs ;
la commande et la fixture sont versionnées.

### R4.3 Validation produit avec opérateurs

**Constat.** L'audit est une revue experte, pas une étude utilisateurs. Il fixe des objectifs : état de
la serre compris en moins de 5 s ; tâche principale en un geste depuis le bon contexte ; 90 % de
réussite sans aide sur les tâches fréquentes ; zéro ambiguïté enregistré/brouillon, vivant/copie,
acquittement/résolution.

**Cible.** `docs/development/validation-produit-protocole.md` : les dix tâches de l'audit (comprendre
l'état de la serre ; diagnostiquer une alarme ; couper temporairement un équipement et comprendre sa
reprise ; modifier une consigne ; saisir pH/EC sur la bonne cible ; observer et joindre une photo ;
marquer/reporter un rappel ; comparer deux cultures ; retrouver une intervention ; consulter une copie
hors ligne puis revenir en ligne), sur simulateur (`tests/ui_server.py`) ou selon
`docs/development/hardware-validation.md` pour le contrôle physique ; au moins deux opérateurs dont un
peu familier ; relevé de durées, erreurs, abandons et compréhension. Les résultats tranchent les
options « préparées mais non activées » (barre à cinq destinations, sélecteur de rubrique, recherche
de réglage).

**Acceptation.** Protocole écrit, résultats consignés, décisions reportées dans ce plan.

---

## Lot 5 — Finitions (P3)

### R5.1 Typographie : Visitor à la marque, chiffres tabulaires, moins de majuscules (UX-18)

**Constat.** `style.css` emploie Visitor sur `.brand` (l. 42) mais aussi `.eyebrow` (l. 58),
`.card-kicker` (l. 86), `.metadata-fieldset legend` (l. 173), `.actuator-group-title` (l. 211) et la
bannière de connexion (l. 250) : petits libellés, badges et groupes d'équipements.

**Cible.** Visitor réservée à `.brand` (et au titre du héros du tableau si souhaité) ; les cinq autres
règles passent en police système, casse normale, `letter-spacing` normal, taille ≥ 0,85 rem. Valeurs,
dates et durées en `font-variant-numeric: tabular-nums` (classe `.num` posée par les macros et le
filtre `nombre`). Réduction des microtextes et des répétitions relevées en R1.2 et R1.6.

**Acceptation (audit).** Textes métier lisibles ; le test « police de marque réellement décodable »
reste vert ; captures avant/après.

### R5.2 Plein jour dehors et séries sans la couleur seule (UX-18)

**Cible.** Contrôle des contrastes du thème plein jour sur toutes les paires texte/fond utilisées
(script dans R0.1, seuil 4,5:1 texte, 3:1 composants) ; séries des graphiques (`history.js`,
`culture_analysis.js`) distinguées par tracé (plein, tirets, pointillés) et marqueur en plus de la
couleur ; palette de séries vérifiée pour deutéranopie et protanopie. Mode « Système » : option non
prioritaire, non planifiée.

**Acceptation.** Rapport de contrastes joint ; deux séries superposées restent distinguables en
niveaux de gris (capture).

### R5.3 Cibles tactiles et vocabulaire (UX-18)

**Constat.** Liens secondaires de 18 à 25 px : « Saisir un relevé », raccourcis locaux, liens de
réglage, exports. WCAG 2.2 AA exige 24 × 24 px avec exceptions ; la cible produit est 44–48 px pour
les actions autonomes fréquentes.

**Cible.** Classe `.action-link` (`min-height: 44px`, `display: inline-flex`, `align-items: center`,
`padding-inline`) appliquée aux actions autonomes fréquentes ; les liens dans le texte courant restent
des liens. Glossaire de libellés dans `docs/development/contributing.md` (« Coupure », « Rappel du
carnet », « Alarme », « Copie datée », « Brouillon », « Acquitter », « Résolue ») et passage des
gabarits pour l'aligner ; suppression du jargon dans les résumés (R1.9).

**Acceptation (audit).** Actions fréquentes 44–48 px (mesure R0.1 sur une liste nommée d'actions),
libellés cohérents.

### R5.4 Parcours photo mobile homogène (UX-19)

**Cible.** Sur tous les champs photo du carnet : `accept="image/*"` et `capture="environment"` proposé
en option (prise de vue **ou** choix existant, jamais imposé) ; aperçu local existant du socle
(`data-culture-photo-preview`) ; messages de refus compréhensibles (taille, dimensions, nombre,
espace disque) nommant la limite ; « Reprendre la photo » remplace le fichier sans créer une seconde
note ni dupliquer l'observation (même clé d'idempotence tant que le texte ne change pas).

**Garde-fous.** Conventions du socle : indexation par contrôle, `submitBinary` → `sendUpload`,
`Content-Type: application/octet-stream`, barre de progression unique dans l'`<output>` atomique ;
réencodage sans métadonnées côté serveur inchangé.

**Acceptation (audit).** Prise de vue ou choix existant, aperçu, taille et refus compréhensibles,
reprise sans doublon (`cultures_ui_photos.spec.js` étendu).

---

## Documentation à tenir à jour par lot

- `CLAUDE.md` **et** `AGENTS.md` (miroirs, `diff -u` vide) : macros de composants (R0.3), classes
  `data-offline-local` (R2.5), cycle de mise à jour du service worker (R3.3), brouillons (R3.4),
  filtre `nombre` (R1.7), route `/app` (R2.4).
- `docs/reference/http-interface.md` : `/app`, `/offline`, `view` de Solutions, liens des pages
  d'erreur.
- `docs/operations/pwa-local-tls.md` : sections iOS/iPadOS et Firefox, changement d'adresse,
  renouvellement, texte exact des notifications.
- `docs/operations/cultures.md` et `docs/reference/cultures-api.md` : vues de Solutions, journal,
  brouillons (aucun changement d'API attendu ; le dire explicitement).
- `docs/development/contributing.md` : macros, glossaire, script de mesure.
- `tasks/todo.md` : cases par fiche ; `tasks/lessons.md` après toute correction.

## Arbitrages demandés avant les lots concernés

1. **Barre mobile (R1.3, lot 1)** : recommandation **Serre · Cultures · Alarmes · Plus** à quatre, la
   variante à cinq restant conditionnée à la mesure à 320 px. À confirmer.
2. **Vues de Solutions (R1.6, lot 1)** : recommandation d'onglets-liens `?view=` sur une seule route,
   sans routes nouvelles. À confirmer.
3. **Brouillons (R3.4, lot 3)** : périmètre recommandé « texte et sélections seulement, mesures
   exclues », expiration 24 h. C'est une évolution produit : à valider avant conception.
4. **Cycle de mise à jour (R3.3, lot 3)** : recommandation « pas de `skipWaiting` automatique, activation
   sur action ou à la prochaine ouverture ». Le comportement actuel (activation immédiate) disparaît :
   à confirmer.
5. **Page `/app` (R2.4, lot 2)** : nom de la route et de l'entrée de menu (« Application sur ce
   téléphone »). À confirmer.

Sans réponse, les recommandations ci-dessus sont appliquées telles quelles et signalées dans le rapport
du lot.

## Hors périmètre de ce plan

- Migration SPA ou framework : écartée par l'audit.
- Web Push distant, notifications application fermée : non implémentés, non promis (R1.5).
- Mutations hors ligne, file ou rejeu : interdits par le dépôt, non remis en cause.
- Qualification électrique : procédure `hardware-validation.md`, jamais depuis l'interface.
- Mode de thème « Système » : option facultative, non planifiée.

---

## État d'avancement — livraison du 11 septembre 2026

Section écrite avec le plan (`ada577f`) avant la remesure finale, puis **revérifiée le 11 septembre 2026
contre les commits de livraison** (`e29bf96`) : chiffres réalignés, statuts des fiches dont
l'acceptation n'était pas démontrée corrigés, onze écarts résiduels E1–E11 relevés. Tous sont
**corrigés** le même jour (tableau en fin de section), l'outil de mesure a été remis au protocole
de l'audit, et une revue indépendante du diff complet (code, documentation) a été traitée. Seuls
restent les gestes opérateur de R4.1 à R4.3.

Une première implémentation avait couvert **tous les lots en surface** (deux salves d'écriture, 10 h 19
à 10 h 24 puis 15 h 50 à 16 h 00, arrêtée en plein milieu, rien de commité) : gabarits compressés,
tests écrits par expressions régulières sur le texte source, légende par mesure de `9136e40`
remplacée par une légende générique, 3 tests pytest rouges, aucune case cochée. L'état a été rétabli
fiche par fiche par cinq relectures indépendantes (une par lot), contre-vérifié par l'orchestrateur,
puis chaque fiche entamée a été **terminée** par des agents à périmètre de fichiers disjoint, relue
par trois revues adversariales (Python et gabarits ; JavaScript, PWA et CSS ; tests, outillage et
documentation), et corrigée une seconde fois. Point de départ inchangé : `8023123`.

**Arbitrages** : aucune réponse n'ayant été apportée, les cinq recommandations (barre à quatre,
`?view=`, brouillons texte/sélections 24 h, pas de `skipWaiting` automatique, route `/app` et entrée
« Application sur ce téléphone ») sont appliquées telles quelles, comme le prévoyait la clause de
repli. Un sixième arbitrage a été pris en cours de route : les vues de Solutions et de Cycles sont des
**listes de liens** avec `aria-current="page"`, pas des onglets ARIA (`role="tablist"` sur des liens
qui rechargent masquait le rôle « lien » et n'offrait aucune navigation par flèches).

**Preuves** : `docs/images/remediation-web-mobile-pwa-2026-09-09/` (mesures « après » au format de
l'audit, comparateur `scripts/compare-measures.py`, rapport de contrastes et simulation
deutéranopie/protanopie, captures) ; `docs/development/web-perf-baseline-2026-09-10.md` (banc HTTP
30/90/365 jours, temps navigateur, budgets provisoires). Les chiffres qui font foi sont ceux du
`README.md` de ce dossier et de `measures-apres-final.json`, mesurés sur l'arbre final.

**Protocole de mesure corrigé.** Jusqu'au 11 septembre au matin, l'outil mesurait un carnet
rempli en 320 × 568 et 1440 × 844 alors que l'audit avait mesuré un carnet **vide** en
320 × 844, 390 × 844 et 1440 × 900 ; les écarts qu'on attribuait à « deux carnets différents »
venaient de l'outil. Il mesure désormais deux passes (`vide`, seule comparable à l'audit ;
`rempli`, pour les acceptations portant sur des données) aux fenêtres de l'audit, et rejoué sur
`8023123` il retrouve les 36 hauteurs de l'audit à ±2 % (33 au pixel près) :
`rejeu-baseline-8023123.md`. Tous les chiffres antérieurs de ce plan sont remplacés.

À 390 × 844, thème sombre : tableau de bord **2 517 px** sur carnet rempli et 2 493 px sur carnet
vide (R1.2, plafond 5 035 / 2 = 2 517,5 px : tenu, **marge 0,5 px**, et ce plafond dérive d'un
« avant » mesuré sur un autre carnet — une croissance normative future demandera de le rebaser,
en le disant) ; relevés de Solutions **1 754 px** sur `?view=releves` contre 7 001 px pour la page
à six relevés de l'audit (R1.6) ; vue Analyser **1 779 px** (R2.3, < 2 000) ; journal 115 px par
entrée, la réduction d'un tiers restant **non vérifiable** faute d'un « avant » à 20 lignes
(R2.8). Premier écran mesuré (boîte entière dans la zone utile, barres fixes retranchées,
défilement d'arrivée nul exigé) : R1.1, R1.2, R1.8 et R2.7 complets ; « Opérations du carnet »
dans le premier écran, mais la **première entrée du journal commence 50 px sous la zone utile**,
fait consigné, qu'aucune acceptation n'exige. Zoom 200 % de la police : aucun défilement
horizontal du corps sur les 14 pages. 0 violation axe sur les 202 relevés qui portent une analyse,
0 paire de contraste sous les seuils 4,5:1 / 3:1 (138 paires en sombre, 135 en plein jour).
Pages plus hautes qu'à l'audit, à carnet égal, par contenu ajouté et sans plafond de fiche :
Plages cibles +65,6 %, Éclairage +33,7 %, Journal +15,5 %, Configuration +4,6 %.

Suites : `python3 -m pytest` 969 réussis, `npm run test:js` 11 réussis (11 septembre 2026).

| Fiche | État | Ce qui a été fait, ce qui reste hors de portée ici |
| --- | --- | --- |
| R0.1 | **Fait** | `measure_pages.js` au format de `measures.json` (clés de l'audit conservées, `carnet` et `viewport` en plus), 12 pages sur deux passes + 2 vues de Solutions × 3 largeurs × 2 thèmes, états ouverts, refusé, menu, zoom police et `deviceScaleFactor`, bannière hors ligne réellement mesurée, alarme critique, premier écran des acceptations ; comparateur ±2 % `scripts/compare-measures.py`, qui refuse de comparer deux protocoles différents (`--fenetres-audit` rend explicite l'hypothèse des fenêtres de l'audit) ; port dédié 40123, aucune requête sortante, mutations refusées sur cible externe. **Rejeu de `8023123` : 36 hauteurs de l'audit à ±2 %** (E7). Un seul JSON final et non un par lot : les lots étaient commités avant que l'outil ne soit au protocole ; serveur unique assumé (`measure_pages.js:85`) |
| R0.2 | **Fait** (Pi : opérateur) | Banc HTTP 30/90/365 j, mode `--base-url` GET seul, temps navigateur (contenu visible, ouverture de formulaire, interaction graphique, retour après enregistrement, mémoire), budgets provisoires dérivés de la mesure et à confirmer sur Pi/téléphone (R4.2) |
| R0.3 | **Fait** | 8 macros, toutes employées par au moins une page, clés optionnelles gardées, `role="list"` ; 31 tests rendent chaque macro sous `StrictUndefined` et compilent les exemples de `contributing.md` ; axe vert sur une page témoin par macro (`qualification.spec.js`) |
| R1.1 | **Fait** | Résumé court (actives, gravité max, dernière occurrence), occurrence la plus grave développée, trois lignes via `alarm_summary`, phrase d'acquittement, `Actualiser` ; `alarms.js` reconstruit **exactement** le balisage du serveur (test d'équivalence lisant le HTML serveur avant tout sondage) ; première alarme critique et son action dans le premier écran à 390 × 844 (mesuré) |
| R1.2 | **Fait** | Bande compacte, priorités avec rappels du jour rendus côté serveur (`overview["today"]`, même chemin que l'API, lecture bornée à une par 60 s côté client), lignes d'équipement repliables ouvertes sur coupure/anomalie/état non relu (serveur **et** rafraîchissement), capteurs en liste, aperçu et maintenance repliés ; 2 517 px à 390 px (plafond 2 517,5, marge 0,5 px), état, fraîcheur, T/RH et alarmes dans le premier écran (mesuré) ; trois défauts du harnais de test corrigés (états d'actionneurs non publiés, méthode manquante, horloge non fiable) |
| R1.3 | **Fait** | Barre Serre · Cultures · Alarmes · Plus, `aria-current` sur toute page du carnet, onglet actif ramené à la vue, sélecteur de rubrique préparé non activé, focus rendu à l'onglet emprunté au retour ; tests 320 × 568 et 568 × 320 (aller-retour, ≥ 50 % de hauteur utile) |
| R1.4 | **Fait** | Région nommée sans `aria-live`, `<output role="status">`, outils repliés sur mobile seulement (`<details open>` servi, `summary` masqué au bureau, refermé sous 760 px par `matchMedia`), repli presse-papiers testé, `/console` dans la passe axe (deux thèmes) |
| R1.5 | **Fait** | Texte exact, `notificationDenialHelp(userAgent, platform, maxTouchPoints)` pure exposée et testée sur trois agents utilisateur + repli ; docs `pwa-local-tls.md` et `http-interface.md` |
| R1.6 | **Fait** | Trois vues `?view=` sur la même route (liens + `aria-current`, panneaux `hidden`, défaut `saisir`/`releves`, vue forcée par `kind`/`entry`), `view` conservé par `culture_navigation.html`, état vide, relevé compacté + `<details>`, légende par mesure rétablie dans `legende-{metric}` désignée par `aria-describedby` ; specs adaptées ; 1 754 px sur `?view=releves` contre 7 001 px pour la page à six relevés de l'audit |
| R1.7 | **Fait** | Règle unique côté serveur `model/nombre.nombre_texte` (arrondi à l'écart sur la représentation décimale courte, comme `Intl`), à laquelle délèguent les filtres `nombre` (`Markup` `.num`) et `nombre_texte`, les synthèses de graphique et les repères d'assistance ; `formatNombre` côté JS (`culture_analysis.js`, `history.js`, `useGrouping:false`) ; vecteurs partagés `tests/fixtures/nombre-vecteurs.json` rejoués par pytest **et** par Node ; plus aucun `:.Nf` ni `toFixed` d'affichage dans le carnet (E2, E9, E10) ; données `data-*`/`value`/CSV et API chiffrée brutes ; tests aller-retour saisie → API (`1.1 + 0.35` → « 1,45 », brut persisté). Le filtre `mesure` du tableau de bord et les durées « 1.5 h » de `pwa.js`/`alarms.js` gardent le point : hors du périmètre de la fiche, voir la fin de section |
| R1.8 | **Fait** | `compact_header` nom/espace/stade/âge, deux actions, « Comprendre ces dates », « Corriger l'historique », retour ancré `#culture-{id}` avec filtres rejoués, `retour` du journal validé (même origine, `/cultures…` normalisé) ; test Playwright du retour sur l'élément d'origine ; nom, espace, stade, âge et les deux actions dans le premier écran à 390 × 844 (mesuré, E6) |
| R1.9 | **Fait** | Liens décidés par le serveur (`Referer` même origine validé, réémis chemin seul ; « Réessayer » GET 5xx seulement), résumé + « Détails techniques » ; tests pytest, axe sur `/inexistant` |
| R2.1 | **Fait** | Groupes `field_group` avec résumés rendus serveur et tenus par JS, `type=time` avec repli, tableau modifié → appliqué incluant les normalisations, barre non masquante (`ResizeObserver` + `scroll-padding`), premier champ refusé focalisé et centré (défaut réel corrigé), virgule acceptée par une conversion unique (Qualité capteurs comprise, message cohérent), index de recherche préparé non activé ; `config.spec.js` (11 tests) |
| R2.2 | **Fait** | Indicateurs T/RH min-moy-max pondérés et part de lacunes, sélecteur d'indicateur, détail sous le graphique via `chart_detail` dans une région fixe annoncée sur sélection confirmée seulement, axes 13 px avec boîte de libellés mesurée, `touch-action: pan-y`, point conservé au redimensionnement, plus de rechargement réseau sur `resize` ; `history.spec.js` (10 tests) |
| R2.3 | **Fait** | Légende courte + « Légende complète » sur Solutions et Historique (définition CSS unique), légende par mesure conservée ; vue Analyser 1 779 px à 390 px (exploration repliée sous 48 rem, intentions de saisie ramenées dans la vue Saisir) |
| R2.4 | **Fait** | `/app` (allow-list, précache, préchauffé, page courante), cinq rubriques rendues serveur, aide par plateforme sans `beforeinstallprompt` (test asserte l'absence de l'autre plateforme), un seul bouton « Mettre à jour » (bannière de `base.html`), docs ; aide par la règle pure `installationHelp`, mention iOS/iPadOS 26 non qualifiée sur appareil (E4, R4.1) |
| R2.5 | **Fait** | `data-offline-local` (outils locaux) et `data-offline-filter` (filtres serveur, posé sur tous les formulaires GET de filtre, Portée/Stade de l'éclairage et de Plages compris — E3, E8), note exacte posée à côté du formulaire, fragment `offline_index.html` unique (`/app`, `/offline`, Cycles, Journal), inventaire propriétaire unique (`app.js`) ; test `pwa-chromium` hors ligne |
| R2.6 | **Fait** | Rappels du jour filtrés par la règle pure `reminder_buckets`, libellé « Rappel du carnet », vues `faire`/`comparer` en liens, section « Sauvegarde et carnet de cultures » (`#sauvegarde`, même libellé que `/app`), index des copies après les rappels |
| R2.7 | **Fait** | Trois pages : sélecteur → « Déclaré dans le carnet » → « Appliqué maintenant » sur Éclairage et Équipements, sélecteur → « Appliqué » → « Déclaré » sur Plages (conforme à la fiche) ; sur Plages **avec** une cible consultée, « Appliqué maintenant », la plage et sa source dans le premier écran (y = 684–763 pour une zone utile de 779, mesuré ; la portée affichée, qui ne filtre que la liste, est descendue dans « Déclaré » — E8) ; « Comment cette valeur est choisie », indications de source ; Équipements : affectations en premier, catalogue replié ; Plages : cascade **complète** via `target_resolution` (`_feeding_at`, lecture bornée du magasin), et la page annonce exactement ce qu'un relevé recevra (test d'équivalence) ; Éclairage : lecture dédiée `light_rows` |
| R2.8 | **Fait, acceptation non vérifiable** | Une ligne par opération via `journal_entry`, détails repliés, recherche visible dans un **seul** formulaire GET, `retour` rejoué ; 115 px par entrée (`.ui-journal-entry`) à 390 px, référence publiée pour toute comparaison future — la réduction d'un tiers ne peut pas être vérifiée, l'audit ne consignant pas le nombre de lignes. L'index des copies passe après les opérations (E5) : recherche et « Opérations du carnet » dans le premier écran ; la première entrée commence 50 px sous la zone utile (fait consigné, non exigé) |
| R3.1 | **Fait** | `fetchWithBudget` 8 s / 15 s, 5xx jamais mis en cache ni remplacé, précache parallèle et atomique, `Content-Length` assaini sur les copies réécrites ; tests Node exécutant le worker à minuteur simulé (`npm run test:js`) à la place du test `pwa-chromium` prévu (aucun navigateur ne vérifie l'affichage entre 8 et 10 s), docs |
| R3.2 | **Fait** | Rien de bloquant devant le poller, `observeRegistration` une seule fois, états lisibles (inscription échouée, installation incomplète, stockage refusé) ; tests `pwa-chromium` worker en 500 et IndexedDB neutralisée |
| R3.3 | **Fait** | Pas de `skipWaiting` automatique, message `activer`, bannière unique, rechargement conditionné à `PhytoForms.isDirty()`, purge après `claim`, `visibilitychange` → `update()` ; test avec vrai worker (deux fenêtres, saisie conservée, ancienne page hors ligne sur ses caches) |
| R3.4 | **Fait** | Brouillons IndexedDB (`data-culture-draft`, exclusions, 24 h, plafond 50, purge, anti-course, restauration explicite revalidée, clé d'idempotence régénérée) sur l'observation de fiche et l'observation d'espace, bannière hors du repli ; test par arrêt réel du navigateur (`launchPersistentContext`) |
| R4.1 | **Protocole livré** — grille à remplir (opérateur) | L'acceptation exige une grille remplie : `qualification-mobile-pwa.md` est entièrement « NE ». Protocole Q01–Q15 avec table de correspondance test automatisé / appareil réel ; `qualification.spec.js` (recouvrement du focus mesuré, dialogue piégeant le focus, hors ligne, zoom 200 % de page **et** de police sur profil `mobile-zoom`, 14 pages sans défilement horizontal — E11) ; VoiceOver/TalkBack, certificat, veille, mémoire restent à mener sur appareils |
| R4.2 | **Partiel** — baseline terrain : opérateur | Outils prêts (`--base-url`, `PHYTO_UI_BASE_URL`, copie isolée via `scripts/restore-cultures.py`) et baseline locale WSL publiée ; la baseline Pi/téléphone/Wi-Fi de serre, les budgets définitifs et la décision sur `/conf` sont un geste opérateur |
| R4.3 | **Protocole livré** — sessions à mener (opérateur) | L'acceptation exige des résultats consignés : `validation-produit-protocole.md` est « Non exécuté ». Protocole des dix tâches, mesures, objectifs chiffrés, options « préparées mais non activées » listées avec leur preuve attendue |
| R5.1 | **Fait** | Visitor réservée à `.brand` (coupable au zoom : `<wbr>`), `.num` posé par le filtre `nombre`, les macros et les gabarits/JS ; petits libellés ≥ 0,85 rem à toutes les largeurs (E1, test Playwright) ; captures dans `docs/images/remediation-…` |
| R5.2 | **Fait** | Rapport de contrastes (0 paire sous seuil, deux thèmes), bordures de champs et onglet courant corrigés, palette de séries de l'Historique remaniée (ΔE ≥ 15 en deutéranopie et protanopie ; les encres du carnet descendent à 6,6, distinguées par forme et tracé), marqueurs et tirets par série repris dans la légende, capture en niveaux de gris |
| R5.3 | **Fait** | `.action-link` 44 × 44 sur les actions autonomes (mesure d'une liste nommée : 0 échec), retirée des liens en phrase ; glossaire des sept termes et termes proscrits dans `contributing.md`, gabarits et JS alignés (« coupure », « copie datée », états traduits, pluriel français) |
| R5.4 | **Fait** | `capture` jamais dans le HTML servi (boutons « Prendre une photo » / « Choisir une image existante » du socle), aperçu par contrôle, refus nommant la limite (413/415 traduits), clé d'idempotence par destination (reprise sans doublon testée) |
| Docs | **Fait** | `CLAUDE.md`/`AGENTS.md` miroirs, `http-interface.md`, `cultures.md`, `cultures-api.md`, `contributing.md`, `pwa-local-tls.md`, `tasks/todo.md`, `tasks/lessons.md` |

**Commits de livraison** (11 septembre 2026, sur `8023123`) : `ada577f` (audit, plan, protocoles
`qualification-mobile-pwa.md` et `validation-produit-protocole.md`), `6f39986` (lot 0), `f93e8cb`
(lot 1), `d89c060` (R2.1–R2.3), `6562a2f` (carnet : R1.6, R1.8, R2.6–R2.8), `b801a8b` (PWA : R1.3,
R1.5, R2.4, R2.5, lot 3, R5.4), `366e1a5` (documentation, suivi, leçons), `08a4815` (preuves de
mesure).

**Écarts résiduels relevés par la revérification du 11 septembre, tous corrigés le même jour :**

| Réf. | Fiche | Écart | Correction | Commit |
| --- | --- | --- | --- | --- |
| E1 | R5.1 | `.actuator-group-title` à 0,78 rem sous 700 px | règle retirée, test des petits libellés ≥ 0,85 rem | `6955277` |
| E2 | R1.7 | Infobulle des points de Solutions en valeur brute (« undefined » possible) | infobulle, curseur, graduations et bornes par `formatNombre`, absence écrite « mesure absente » | `6955277` |
| E3 | R2.5 | Filtre Portée/Stade de l'éclairage sans `data-offline-filter` ; `value="None"` sur une date de fin absente | attribut posé, valeur vide | `6955277` |
| E4 | R2.4 | Aide d'installation sans iOS/iPadOS 26 | règle pure `installationHelp`, mention et doc `pwa-local-tls.md`, non qualifiée sur appareil | `6955277`, `99284f4` |
| E5 | R2.8 | Index des copies avant les opérations du journal | fragment déplacé après, hors du bloc `data` ; titre à y = 732 | `6955277` |
| E6 | R1.8, R2.7 | Premier écran non mesuré | mesure « boîte entière dans la zone utile », fiche et Plages avec cible | `7fb722b` |
| E7 | R0.1 | Rejeu de la baseline à ±2 % non démontré | outil remis au protocole de l'audit, 36 hauteurs à ±2 % | `7fb722b` |
| E8 | R2.7 | Sur Plages avec cible, « Appliqué maintenant » sous le premier écran (y = 857) | portée descendue dans « Déclaré », source en tête de ligne ; y = 684 | `99284f4` |
| E9 | R1.7 | Cycles en « 0.00 » (`'%.Nf'`, `toFixed`) | `nombre` / `nombre_texte` / `formatNombre` partout | `99284f4` |
| E10 | R1.7 | Synthèses de graphique et repères d'assistance avec leur propre arrondi | règle unique `model/nombre.py` | `28cc412` |
| E11 | R4.1, R5.1 | Défilement horizontal du corps au zoom 200 % de la police, sur les 14 pages | quatre causes corrigées à la racine, 14 tests `mobile-zoom` | `90d06c3`, `d9289e2` |

**Revue indépendante du diff complet** (`e29bf96..28cc412`, code puis documentation), défauts
réels corrigés :
- E10 affichait « écart : +0,00 » pour un écart réel sous 0,005 (EC saisie en µS/cm) : l'écart
  garde maintenant assez de décimales pour être non nul (`c0cd8f0`) ;
- Python et navigateur arrondissaient différemment les demi-valeurs (21,125 → 21,12 et 21,13),
  700 divergences sur 1 400 cas : Python aligné sur `Intl`, vecteurs partagés (`c0cd8f0`) ;
- la mesure du premier écran comptait un élément `visually-hidden` et ignorait un défilement
  d'arrivée, et le comparateur imputait un écart de protocole à la page (`b379e72`) ;
- la preuve de migration faisait un `git checkout` dans le checkout de production si on la
  collait à la suite ; les gardes « ARRÊT » n'arrêtaient rien ; une information de l'ancien
  fichier `notes` (BCM 17 HS, canal migré vers BCM 5) avait été perdue (`a3fc7ad`).

**Restent ouverts, hors fiches** : le filtre `mesure` du tableau de bord et les durées de
`pwa.js`/`alarms.js` (« 1.5 h ») gardent le point décimal. Le premier est un invariant
documenté, identique au `toFixed` de `dashboard.js` : le passer à la virgule touche le JS du
tableau et demande une décision. La sonde Influx de `scripts/observe-jalon2-operator-quality.sh`
lisait encore `param/` du checkout et ignorait `PHYTO_DATA_DIR` — **corrigé le 11/09/2026** :
elle lit le répertoire déclaré par l'unité systemd, comme `scripts/deploy.sh`
(`tests/test_observation_script.py`).

**Restent à mener par l'opérateur**, avec les protocoles livrés : R4.2 (baseline Pi, téléphone et
Wi-Fi de serre, budgets définitifs, décision sur `/conf`), la grille appareils réels de R4.1
(Q01–Q15, VoiceOver/TalkBack) et les sessions P01–P10 de R4.3 avec leurs décisions. Tant que ces
grilles ne sont pas remplies, R4.1 et R4.3 restent « protocole livré », pas « accepté ».
