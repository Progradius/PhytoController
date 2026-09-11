# Contribuer

## Avant toute modification

1. Lire `AGENTS.md` et le document du domaine concerné.
2. Vérifier `git status` et préserver les changements existants.
3. Identifier les risques liés dans `docs/risk-register.md`.
4. Définir l'état sûr, le rollback et la preuve attendue.
5. Ne jamais lire ou publier les valeurs sensibles de `param/param.json`.

## Validation automatisée

Installer les dépendances de développement puis exécuter la suite avant de proposer un changement
Python :

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

Une fixture ne doit jamais copier les valeurs du `param.json` vivant. Toute persistance de test reste
sous `tmp_path`, tout GPIO est un faux explicite et toute commande système est remplacée par un double.
Une modification matérielle exige en plus le protocole de
[`hardware-validation.md`](hardware-validation.md).

### Suite navigateur (Playwright)

Un test choisit ses profils **à sa déclaration**, jamais dans son corps :

```js
const {pour, sauf} = require("./profils");

test("titre", pour("Deux formats suffisent.", "desktop-chromium", "mobile-chromium"), async ({page}) => {…});
test("titre", sauf("Parcours hors service worker.", "pwa-chromium"), async ({page}) => {…});
```

`tests/ui/profils.js` pose des étiquettes que le `grepInvert` de chaque projet évalue avant toute
fixture : un test exclu d'un profil n'y est ni planifié ni instancié. Un
`test.skip(testInfo.project.name …)` dans le corps arrive au contraire **après** les fixtures — le
navigateur et, pour le carnet, un serveur Python complet ont déjà été démarrés pour rien. La raison
du choix est conservée en annotation `profils`. `test.skip` reste réservé à ce qui dépend d'une
donnée d'exécution (largeur de fenêtre, variable d'environnement) et à la garde « cible externe »
du carnet. Les noms de profils n'existent qu'une fois, dans `PROFILS` : un nom inconnu casse le
chargement de la spec (`npm run test:js` couvre ces règles).

## Style

- Code, commentaires, messages et logs en français.
- `utils.pretty_console` uniquement, jamais de `print` applicatif.
- Transitions à INFO, ticks à DEBUG, échecs répétés via `StateLogger`.
- Une tâche supervisée reçoit une fabrique, un état sûr si elle pilote une sortie et des heartbeats.
- Une attente avec sortie ON utilise `Component.energized()`.
- Les temps de sécurité utilisent `time.monotonic()`.
- Une lecture capteur peut renvoyer `None`.

## Documentation liée

Mettre à jour dans le même changement :

- référence si une interface ou configuration change ;
- runbook si l'exploitation change ;
- matrice GPIO et modèle de sûreté si le matériel change ;
- ADR si une décision structurelle change ;
- registre des risques et roadmap ;
- changelog pour un comportement livré.

`AGENTS.md` et `CLAUDE.md` sont des miroirs exacts : toute modification doit être identique et `diff -u CLAUDE.md AGENTS.md` doit rester vide.

## Périmètre

Cette arborescence est le port Raspberry Pi. Ne pas reporter automatiquement les changements dans la version ESP32. Le code mort apparent doit être confirmé comme non importé avant suppression.

## Mesures web et composants partagés (remédiation septembre 2026)

`PHYTO_TEST_PYTHON=.venv/bin/python npm run measure:ui` démarre un serveur neutre isolé,
crée une mère et six relevés via les fabriques navigateur puis mesure douze pages à 320,
390 et 1440 px en sombre et plein jour.

**Le JSON reprend exactement les clés de l'audit** — `route`, `width`, `status`, `height`,
`scrollWidth`, `dom`, `headings`, `smallTargets`, `resources`, `axe`, `errors` — et n'ajoute
que des clés supplémentaires : `state`, `theme`, `mainVisibleMs`, `memory`, `actions`,
`wcagTargets`, `namedTargets`, `timings`. Ne renommez aucune clé de l'audit : c'est ce qui
permet à `scripts/compare-measures.py` de comparer les deux fichiers sans conversion.
`smallTargets` garde le critère de l'audit (une dimension sous 44 px, repère de confort) ;
`wcagTargets` applique le minimum WCAG 2.2 AA de 24 px, qui est autre chose. `resources`
vient de `performance.getEntriesByType("resource")`, `errors` des erreurs de console et des
exceptions de page.

`mainVisibleMs` est relevé **avant** axe — sans quoi il mesurerait la durée d'`analyze()`,
pas la visibilité du contenu. Il mesure une visibilité DOM, jamais un LCP ni un INP.

Le fichier est écrit **une seule fois**, en fin d'exécution.

`PHYTO_MEASURE_DIR` choisit le répertoire, `PHYTO_MEASURE_SCREENSHOTS=1` conserve les
captures, `PHYTO_MEASURE_WIDTHS=390` permet un diagnostic court et `PHYTO_UI_MEASURE_PORT`
fixe le port du serveur de mesure (40123 par défaut, plus 40124 pour le scénario d'alarme). Ce
port reste fixe parce qu'un arbre ancien servi par `PHYTO_MEASURE_ROOT` ne sait pas annoncer un
port choisi par le noyau ; les serveurs dédiés de la suite Playwright, eux, n'en réservent
aucun (`PHYTO_UI_TEST_PORT=0`). Avec `PHYTO_UI_BASE_URL=http://adresse-du-pi:8123`, seules les lectures sont
autorisées : aucune création, aucun POST. Cette variable doit être une origine HTTP(S) nue
(sans identifiant, chemin ni query) ; toutes les requêtes vers une autre origine sont
bloquées, y compris les redirections et sous-ressources.

États mesurés en plus des pages : `menu_plus_ouvert`, `formulaire_releve_ouvert`,
`formulaire_releve_refuse`, `zoom_200_police` (police à 200 %), `zoom_200_echelle`
(`deviceScaleFactor: 2` sur un viewport de largeur divisée par deux, ce qu'impose un zoom de
page à 200 %), `banniere_hors_ligne` (contexte à `serviceWorkers: "allow"`, page précachée
puis `context.setOffline(true)`), `alarme_critique` (scénario `PHYTO_UI_MEASURE_SCENARIO=critical`
de `tests/ui_server.py`, sur `/` et `/alarms`), `cibles_nommees` (liste d'actions fréquentes
de R5.3, confrontée à 44 px et à 24 px) et `temps_locaux`. Un état qu'on ne peut pas
atteindre est écrit `skipped` avec sa raison ; une mesure manquante porte sa raison dans
`timings.raisons`. Ne remplacez jamais une mesure absente par un zéro.

Le refus de formulaire mesuré est un refus **du serveur** : vider un champ `required` ferait
intervenir la validation native du navigateur, qui bloque l'envoi — l'état observé serait une
bulle du navigateur, pas le refus de l'application.

Un seul serveur sert toute l'exécution, alors que la fixture du carnet
(`tests/ui/culture_fixtures.js`) impose un serveur par test. Ce n'est pas une entorse : cette
règle protège des tests **parallèles**, l'espace 2 du carnet étant exclusif et une occupation
ouverte n'ayant pas de fin, donc deux workers qui partagent une base se la disputent. Ici tout
est séquentiel dans un seul processus et une seule mère est créée. Le scénario d'alarme
critique, lui, demande un second serveur — `PHYTO_UI_MEASURE_SCENARIO` est lu au démarrage du
processus —, et il n'est lancé qu'**après** l'arrêt du premier.

`npm run measure:compare -- <avant.json> <après.json>` (`scripts/compare-measures.py`) rejoue
l'acceptation de R0.1 : il compare les entrées nominales (`state` absent ou `page`) en thème
sombre (`theme` absent ou `dark`), rend un tableau Markdown et **sort avec un code non nul
au-delà de ±2 %**. `--metric` accepte `height`, `scrollWidth` ou `dom`. Une route mesurée
avant et absente après est un échec, jamais un silence.

`.venv/bin/python scripts/benchmark-web-pages.py --output test-results/web-perf.json`
mesure cinq lectures HTTP de chaque page sur trois carnets temporaires : 30, 90 et
365 jours, trois mères actives, un relevé quotidien par mère, un rappel et une photo
synthétique hebdomadaires par mère.
Le serveur est celui des tests, sans matériel. Chaque scénario ferme et efface sa
propre base. `html_elements` compte les balises du HTML initial ; `dom` du script
navigateur compte le DOM exécuté : ne pas confondre ces deux nombres.

`--base-url http://adresse-du-pi:8123` (ou `PHYTO_UI_BASE_URL`) vise une cible réelle : le
banc n'émet alors que des `GET`, ne fabrique aucun carnet et **refuse** `--days`, parce que
générer les 30/90/365 jours supposerait d'écrire dans la base visée. Le carnet représentatif
se prépare avant, sur une **copie isolée**, avec `scripts/restore-cultures.py` — jamais sur la
base vivante. `--subject-id` ajoute la fiche d'une culture à la liste des pages lues.

Les budgets provisoires et leur règle de dérivation sont dans
`docs/development/web-perf-baseline-2026-09-10.md`. Ils viennent de la mesure WSL et
**attendent la confirmation Pi/téléphone** de R4.2 ; les chiffres WSL ne la remplacent pas.

Les huit macros de `network/web/templates/macros/ui.html` n'évaluent aucune règle
métier, restent autoéchappées et n'émettent aucun script/style inline. Les actions
passées sous forme `{href, label}` sont des liens de navigation GET ; placer les
commandes POST existantes, avec leurs confirmations/CSRF, dans le bloc `caller`.
Importer avec `{% import 'macros/ui.html' as ui %}`. Exemples :

```jinja
{{ ui.compact_header('Serre', ['Données fraîches'], {'href': '#equipements', 'label': 'Équipements'}, []) }}
{{ ui.empty_state('Aucun relevé', 'Choisissez une cible pour commencer.', {'href': '#saisie', 'label': 'Saisir un relevé'}) }}
{{ ui.alarm_summary({'problem': 'Capteur absent', 'consequence': 'Mesure indisponible', 'action': 'Vérifier la connexion'}) }}
{% call ui.equipment_row({'id': 'heater', 'name': 'Chauffage', 'state': 'Arrêt', 'next_transition': 'Non prévue'}, true) %}<p>Motif de l’arrêt</p>{% endcall %}
{% call ui.journal_entry({'id': 'exemple', 'date': '10/09/2026', 'operation': 'Observation', 'target': 'Mère A', 'summary': 'Feuillage observé'}) %}<p>Révision 1</p>{% endcall %}
{% call ui.field_group('Observation', 'Déclaration dans le carnet') %}<label>Texte<textarea name="text"></textarea></label>{% endcall %}
{{ ui.chart_detail({'label': 'Relevé du jour', 'cells': [{'label': 'pH', 'value': none}]}) }}
{% call ui.network_state() %}Connexion en cours de vérification{% endcall %}
```

`compact_header` accepte aussi un bloc `caller`. `equipment_row` n'ouvre pas de
lui-même une anomalie : le serveur fournit `expanded` à partir de son état, et le
rafraîchissement maintient les ancres existantes. `network_state` fournit une seule
région de statut : ne pas l'ajouter à une bannière déjà annoncée. `chart_detail`
affiche les absences comme « Non renseigné », jamais comme zéro.

Les clés **facultatives** — `row.id`, `row.photo`, `equipment.next_transition`,
`equipment.reason` — sont lues avec `is defined and`. L'environnement de production
(`network/web/pages.py`) est en `Undefined` permissif, donc une clé manquante n'y casse
rien et le manque passerait inaperçu ; `tests/test_ui_macros.py` rend les huit macros sous
`StrictUndefined`, avec des données minimales **et** complètes, ce qui transforme cet oubli
en échec de test. Toute nouvelle clé facultative doit suivre la même garde.

Ce test vérifie aussi que chaque exemple du bloc ci-dessus **compile** : un exemple faux
dans cette page serait recopié tel quel dans la page suivante. En ajouter un ici, c'est
donc s'engager à ce qu'il rende. Le contrat de balisage (attributs `data-*`, ancre
`event-{id}` en `tabindex="-1"`, absence de `<script`/`style=`/`on*=`) y est vérifié macro
par macro ; l'axe « une page témoin par macro » est dans `tests/ui/qualification.spec.js`.

## Glossaire des libellés visibles (R5.3)

Sept mots portent des distinctions que l'opérateur doit pouvoir faire **sans lire la
documentation**. Ce glossaire fixe le mot rendu à l'écran : titre, bouton, badge, message,
libellé de champ, texte annoncé par un lecteur d'écran. Il ne contraint **ni** les
identifiants techniques (`data-*`, classes CSS, noms de champs, clés d'API, `severity-override`
ou `data-override-form` restent tels quels), **ni** les commentaires de code.

Un synonyme n'est pas une variante de style : deux mots pour une chose obligent l'opérateur
à vérifier s'il s'agit bien de la même, et un mot pour deux choses lui fait confondre un
rappel avec une panne.

| Terme | Ce que c'est | Ce que ce n'est pas | Termes proscrits à l'écran |
| --- | --- | --- | --- |
| **Coupure** | Arrêt temporaire d'un équipement demandé par l'opérateur, qui se lève seul à l'échéance et n'allume jamais rien. | Ni un réglage, ni une panne, ni un arrêt définitif : la conduite normale reprend seule. | « forçage », « override », « forcé », « intervention » employé seul pour désigner une coupure |
| **Rappel du carnet** | Échéance déclarative que l'opérateur s'est fixée dans le carnet de cultures. | **Pas une alarme** : le carnet ne surveille rien, ne commande aucun équipement et n'émet aucune notification. | « alerte », « alarme », « notification » pour un rappel |
| **Alarme** | Anomalie détectée par le contrôleur sur la serre, avec une sévérité et une catégorie. | Pas un rappel, pas un simple message d'information, pas une erreur de saisie. | « alerte » (réservée à rien : ne pas l'employer), « warning », « erreur » pour une alarme |
| **Copie datée** | Page ou données conservées sur cet appareil, relues **après un échec réseau**, avec leur date. | Pas l'état courant de la serre, et jamais une base de secours : aucune commande n'est possible dessus. | « snapshot », « cache », « instantané », « hors ligne » employé seul sans la date |
| **Brouillon** | Saisie non enregistrée conservée sur cet appareil, restaurée **explicitement** par l'opérateur. | Pas un enregistrement : rien n'est parti au contrôleur, rien ne sera rejoué tout seul. | « sauvegarde automatique », « enregistré localement », « en attente » |
| **Acquitter** | Signaler qu'on a **vu** l'alarme. | **≠ Résoudre.** Acquitter ne corrige pas la panne et n'éteint pas la cause ; l'alarme reste active. | « valider », « traiter », « fermer », « résoudre » pour un acquittement |
| **Résolue** | La cause a disparu : c'est le **contrôleur** qui le constate. | Pas une action de l'opérateur, et pas la conséquence d'un acquittement. | « corrigée », « fermée », « acquittée » pour une alarme résolue |

**Dans un résumé**, en tête de page ou dans une carte, on nomme ce que l'opérateur observe,
jamais le moyen technique de l'observer : pas d'« état GPIO relu », de « broche », de
« registre » ni de « transition GPIO ». Ces termes restent justes et utiles dans un bloc
« Comment cette valeur est choisie » ou « Couverture et méthode », où ils expliquent
précisément la limite de ce qui est mesuré — c'est leur place, pas le chapeau d'une page.

De même, une page ne dit pas « vivant » ou « production » pour distinguer la serre de sa
copie : elle dit **la serre** d'un côté, **copie datée du …** de l'autre.

Les écarts relevés sur les gabarits existants sont suivis hors dépôt ; toute nouvelle page
adopte le glossaire, et une page retouchée aligne les libellés qu'elle touche.
