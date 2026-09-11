# Carnet de cultures — lot UI 4 : analyse et confort

> Archivé le 11/09/2026 — bilan clos, conservé comme preuve ; ne plus le mettre à jour.

Implémentation du lot 4 de l’[audit du 8 septembre 2026](audit-ui-cultures-2026-09-08.md).

La comparaison présente désormais une colonne par culture et des lignes communes :
stade, durées par stade, minimum/moyenne/maximum pH et EC, nombre de mesures, poids
sec et enseignements. Chaque durée ouverte porte « à ce jour » ; les périodes
approximatives sont signalées. Les statistiques couvrent les parcours propres aux
cultures, sans prétendre comparer des périodes ou effectifs identiques. Un stade
absent, un poids absent ou une mesure absente reste explicitement non renseigné.
Les détails datés des parcours restent consultables sous le tableau.

La recherche nom/variété du sélecteur traverse le carnet, avec 40 résultats par page
et jusqu’à quatre cultures sélectionnées conservées en plus. Les cases remplacent
le sélecteur multiple ; les choix affichés se filtrent immédiatement et le plafond
de quatre se voit avant soumission. La validation serveur conserve son plafond.
La recherche des cultures et des archives existante est maintenue. Les archives
montrent leur bilan renseigné et permettent d’ouvrir directement le bilan ou la
comparaison. La fiche récapitule aussi les durées et les dates de son parcours.

Les courbes de solutions et de climat offrent un curseur natif, des boutons de
**44 × 44 px minimum** (hauteur *et* largeur déclarées) et un choix du point le plus
proche au toucher, ignoré au-delà de 44 px puisque le geste ne vise alors rien.
Aucun point n'est un arrêt de tabulation — à 2 000 points, ce serait 2 000 arrêts pour
traverser une figure —, et la zone d'exploration en compte **trois** : le curseur puis
les deux boutons. Aux extrémités, les boutons restent actifs et la butée est annoncée
dans le texte du point.
Le détail expose la date, la cible/période, les agrégations, les unités et les lacunes.
Un tableau équivalent, à sept colonnes, est construit seulement à son ouverture, sur le
même jeu de points borné ; les valeurs des bandes de référence sont aussi accessibles en
texte. Sous chaque courbe pH/EC, une synthèse textuelle et une légende des tracés sont
rendues par le serveur.
Les dessins ne relient toujours pas les périodes manquantes et la taille de leurs
graduations reste celle du lot 1. La sélection est conservée lors du redessin.

La galerie utilise un dialogue natif : précédent/suivant, flèches clavier, Échap,
légendes et lien vers le contexte. Ce lien existe là où le gabarit en rend un :
dans le **journal transversal**, dans la **fiche de culture** et sur la page des
**cycles**, chaque légende de photo portant le lien de son entrée. Échap, le bouton
« Fermer et revenir » et le clic sur le voile rendent le focus au lien d’origine ;
le lien de contexte, lui, **ne le rend pas** — il emmène ailleurs, et l'élément
focalisé à l'arrivée est la confirmation de l'endroit atteint.

## Livré par la remédiation du 9 septembre 2026

Le [plan de remédiation](remediation-ui-cultures-lot-4-2026-09-09.md) a complété ce lot,
sans nouvelle route ni nouvelle persistance :

- **Journal transversal** : recherche libre `q` (note, cibles, libellé de type), en SQL dans
  la même requête que les autres filtres, et raccourcis de période 7 / 30 jours calculés par
  le serveur sur l'unique date du carnet.
- **Signalement d'occupation sur la page Archives** : une culture archivée dont l'espace n'a
  pas été libéré le dit sur sa carte, à côté des durées par stade.
- Légende et synthèse textuelle des courbes de solutions, tableau équivalent structuré,
  bornage des boutons sans désactivation, pagination bornée du sélecteur de comparaison,
  mémoïsation de la synthèse climatique et sélection pH/EC pilotée par les deux chemins
  d'attribution. Une image indisponible laisse la navigation accessible. Sans support
du dialogue ou sans JavaScript, les liens directs aux images restent utilisables.
Les photos d’une comparaison sont désormais filtrées sur toutes les cultures
sélectionnées ; auparavant une sélection multiple ouvrait la galerie globale.
La borne existante de 100 photos et les limites PWA restent inchangées.

## Coût et invariants

Les statistiques pH/EC sont agrégées en SQL : une ligne retournée par culture, sans
export complet des relevés ni projection supplémentaire. Le prédicat d’association
est partagé avec le dernier relevé : cibles directes, alimentation datée, révision
courante non annulée et cas « avant » un renouvellement à la même seconde.
Les tests comparent ces résultats avec l’export de référence, y compris les absences
et les zéros, puis interdisent l’export sur le chemin de comparaison.

La page garde les projections globales et le catalogue des cibles de rappel qui
existaient déjà. Elle ne promet donc pas un coût constant pour un nombre illimité de
cultures. Les résultats du sélecteur, les graphiques, les photos et le détail horaire
sont bornés. Aucun schéma, acquisition, GPIO, régulation ou mécanisme de commande
n’est ajouté. Le nouveau script de consultation est versionné par empreinte et
inscrit dans l’allow-list des assets et dans le précache PWA.

## Banc de mesure

```bash
.venv/bin/python scripts/benchmark-cultures-analysis.py
```

Sur le Pi, utiliser `venv/bin/python3` à la place de `.venv/bin/python`.

Le script crée exclusivement une base temporaire synthétique, **redéfinie par la
remédiation R2.3** : 44 cultures, 12 001 relevés et 729 jours, avec deux séries
climatiques horaires lacunaires (31 810 agrégats), et surtout **25 renouvellements**
et **100 associations datées** — 6 001 relevés visés directement, un relevé sur deux
n'étant rattaché que par l'alimentation datée. Le semis d'origine ne semait ni
`solution_periods` ni `solution_links` : l'`EXISTS` d'alimentation portait sur zéro
ligne et la branche la plus chère n'était jamais parcourue, si bien que les temps
publiés au lot 4 étaient un **plancher**. Les volumétries ci-dessus sont maintenant
comptées en base, plus reprises des constantes du semis. Le script mesure cinq lectures
et rendus Jinja pour une puis quatre cultures, ferme et supprime sa base. Il n’ouvre
aucune base de production ni aucun serveur HTTP.

Mesures locales WSL du 9 septembre 2026, sous charge des tests navigateur, avec le
nouveau semis, avant puis après la remédiation (R2.1 et R2.2) :

| Sélection | Lecture médiane / maximum | Rendu Jinja médian / maximum | HTML | Points climatiques |
| --- | --- | --- | --- | --- |
| 1 culture, avant | 104,2 / 133,9 ms | 11,1 / 110,7 ms | 133 904 octets | 210 |
| 4 cultures, avant | 382,9 / 407,9 ms | 13,1 / 13,5 ms | 438 083 octets | 840 |
| 1 culture, après | 70,3 / 75,8 ms | 9,8 / 104,1 ms | 134 737 octets | 210 |
| 4 cultures, après | 172,0 / 173,2 ms | 12,4 / 14,6 ms | 438 415 octets | 840 |

Mesures sur le **Pi aarch64, Python 3.11.2**, même semis avant et après, l'arbre étant
transféré dans un répertoire temporaire de `/tmp` et la base synthétique temporaire
supprimée à la fermeture, service `phyto` actif et inchangé pendant la mesure :

| Sélection | Lecture médiane / maximum | Rendu Jinja médian / maximum | HTML | Points climatiques |
| --- | --- | --- | --- | --- |
| 1 culture, avant | 485,4 / 493,6 ms | 17,6 / 369,6 ms | 134 712 octets | 210 |
| 4 cultures, avant | 1 720,9 / 1 750,1 ms | 32,8 / 36,7 ms | 438 972 octets | 840 |
| 1 culture, après | 288,0 / 318,9 ms | 17,0 / 367,6 ms | 134 736 octets | 210 |
| 4 cultures, après | 721,0 / 722,0 ms | 31,4 / 31,5 ms | 438 414 octets | 840 |

Le repère de 759,3 ms publié au lot 4 pour quatre cultures **n'est pas comparable** à ces
chiffres : il vient du semis sans association, donc d'une branche non parcourue. Le vrai
« avant » du même semis est 1 720,9 ms, et le gain de la remédiation est un facteur 2,4
à quatre cultures comme à une seule. Ce repère historique reste dans le JSON sous
`pi_lot_4_semis_initial`, étiqueté comme non comparable.

Le premier rendu inclut la compilation du template, d’où son coût supérieur. Ces
mesures portent sur SQLite, les projections et Jinja, pas sur le transfert réseau
ni le navigateur. Les [mesures brutes](cultures-ui-lot-4-mesures.json) sont conservées.
Le service `phyto` est resté `active/running`, PID inchangé avant/après ; le
benchmark n’a chargé que sa base synthétique, supprimée à la fermeture.

Le téléphone physique et un lecteur d’écran réel restent des validations manuelles
distinctes des profils Chromium, du toucher/clavier automatisé et d’axe.

## Validation automatisée

- **800 tests Python réussis**, avec les avertissements de dépréciation existants.
- Suite navigateur complète : 250 réussites, 103 exclusions prévues, deux échecs
  initiaux. Le test PWA utilisait encore « Enregistrer le suivi » alors que les
  rappels proposent « Fait » et « Reporter » depuis les lots précédents : ses deux
  assertions, hors ligne puis en ligne, contrôlent désormais les deux boutons.
  Le contrôle axe des pages principales avait dépassé 20 s sous charge ; il passe
  avec un seul worker, sans modifier son délai ni ses assertions.
- Après reprise : **252 scénarios distincts validés**, 103 exclusions prévues.
  Le scénario PWA vérifie toujours zéro mutation rejouée et aucune API en cache.
- Reprise du lot 4 enrichi : **12 réussites, 3 exclusions PWA prévues**. Comparaison
  des absences et d’un vrai zéro, axe en thèmes sombre/plein jour, clavier et toucher,
  tableau différé à 2 000 points, galerie avec image chargée puis indisponible,
  précédent/suivant, Échap et retour du focus.
- Dernière reprise comparaison + PWA : **5 réussites, 5 exclusions prévues**.
- `git diff --check` et miroir `CLAUDE.md` / `AGENTS.md` sans écart.

Après la remédiation du 9 septembre 2026 (lot E, `tests/ui/cultures_ui_lot_4.spec.js` porté à
9 scénarios et `tests/ui/cultures_ui_lot_4_journal.spec.js` à 2) :

- **816 tests Python réussis**, 0 échec, 25 s, avec les avertissements de dépréciation existants.
- Les deux specs du lot 4 en une invocation, un worker, par profil :
  `desktop-chromium` 11 réussites / 0 échec / 0 exclusion ; `mobile-chromium` 11 / 0 / 0 ;
  `mobile-etroit` 11 / 0 / 0 ; `mobile-paysage` 11 / 0 / 0 ; `pwa-chromium` 0 / 0 / 11
  exclusions prévues (mutations et interception HTTP hors service worker).
- Garde de cible externe, `PHYTO_UI_BASE_URL` sur un port fermé et `tests/ui/cultures*.spec.js`
  en une seule invocation : **61 exclusions, 0 réussite, 0 échec**, aucune requête sortante.
  Le compte d'exclusions n'est visible qu'en passant par `rtk proxy npx …` ou
  `--reporter=json` : le hook RTK filtre autrement cette ligne.
- Pouvoir discriminant des assertions nouvelles prouvé par trois mutations temporaires de
  `culture_analysis.js`, chacune rattrapée : filtre local sans effet, sélection non repeinte
  après redessin, plafond de quatre relâché d'un cran.
- La fixture navigateur supprime désormais le répertoire temporaire qu'elle a créé : neuf
  scénarios laissent zéro `/tmp/phyto-ui-*` de plus.
- Le serveur unique lancé par le `webServer` de `playwright.config.js` (specs hors carnet :
  `dashboard`, `visual`, `cultures`…) ne fuit plus non plus. `tests/ui_server.py` crée un
  `tempfile.TemporaryDirectory(prefix="phyto-ui-")` que Playwright ne laisse jamais nettoyer :
  il tue le serveur en fin de session, donc ni `atexit` ni le finaliseur ne s'exécutent.
  Le mécanisme est le même que celui de la fixture — imposer un `TMPDIR` qui nous appartient,
  et ne le supprimer qu'**après** la mort du serveur :
  * `tests/ui/global_setup.js` définit le chemin `os.tmpdir()/phyto-ui-webserver-<PID>`, seule
    vérité partagée. Il est **déterministe** et non mémorisé : la config est réévaluée dans
    chaque worker, donc un `mkdtempSync` dans la config créerait un répertoire par worker ;
    seul le processus principal lance le `webServer`, et c'est son PID qui nomme le répertoire ;
  * `playwright.config.js` le passe en `webServer.env.TMPDIR` et confie création **et**
    suppression à la commande elle-même :
    `trap 'rm -rf "$TMPDIR"' EXIT INT TERM HUP; mkdir -p "$TMPDIR" && … tests/ui_server.py`,
    avec `gracefulShutdown: {signal: "SIGTERM", timeout: 5000}`. Le `mkdir -p` est indispensable
    ici et pas dans `globalSetup` : Playwright 1.62.1 démarre le `webServer` **avant** les hooks
    globaux (ordre `clear output` → `plugin setup` → `globalSetup`), et `TemporaryDirectory`
    échoue si `TMPDIR` n'existe pas.

  Le nettoyage n'est **pas** un `globalTeardown`, et c'est délibéré. Dans le même ordre de
  tâches, les teardowns globaux se jouent avant l'arrêt du `webServer` : un teardown effacerait
  le répertoire d'un serveur encore vivant, ce que la fixture du carnet s'interdit
  explicitement, et il ne serait même jamais atteint si le serveur échouait à démarrer (port
  occupé, `PHYTO_TEST_PYTHON` absent), sa tâche n'ayant pas été enregistrée alors que le
  `mkdir -p` a déjà eu lieu. Le `trap` appartient au processus qu'il nettoie : il couvre les
  deux cas. Deux détails vérifiés sur un projet Playwright jetable, et sans lesquels il ne
  nettoie rien : sans `gracefulShutdown`, Playwright arrête le serveur par un `SIGKILL` au
  groupe de processus, qu'aucun `trap` ne voit ; et `/bin/sh` (dash) ne joue pas le `trap EXIT`
  quand il meurt d'un signal non capté, d'où les quatre signaux. Parce que le shell capte
  `TERM`, POSIX lui impose de différer le trap jusqu'à la fin de la commande au premier plan :
  la suppression suit la mort du serveur, jamais l'inverse — vérifié sur `tests/ui_server.py`,
  qui s'éteint bien sur `SIGTERM` (aiohttp) avant que le répertoire ne disparaisse. Un serveur
  qui ne sortirait pas dans les 5 s retombe sur le `SIGKILL` d'avant.

  Avec `PHYTO_UI_BASE_URL`, aucun serveur n'est lancé : `webServerScratchDir()` rend `null`,
  `globalSetup` ne fait rien, rien n'est créé ni supprimé. `--list` n'exécute aucun hook et ne
  crée donc rien. Vérification :

  ```bash
  ls -d /tmp/phyto-ui-* 2>/dev/null | wc -l
  PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/visual.spec.js \
    --workers=1 --project=desktop-chromium
  ls -d /tmp/phyto-ui-* 2>/dev/null | wc -l   # même compte qu'avant
  ```

Les scénarios d’interception HTTP du lot 4 s’exécutent sur bureau, mobile, 320 px
et paysage, hors service worker ; le comportement PWA est exercé par les scénarios
spécifiques existants. Toutes les écritures navigateur restent dans les bases
temporaires isolées de la fixture, jamais sur une cible externe.

```bash
.venv/bin/python -m pytest -q
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --workers=2
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures_ui_lot_4.spec.js --workers=2
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures.spec.js tests/ui/dashboard.spec.js --project=pwa-chromium --workers=1 --grep 'cycles : PWA datée|les pages principales'
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures.spec.js tests/ui/cultures_ui_lot_4.spec.js --workers=1 --grep 'cycles : PWA datée|comparaison alignée'
```

## Captures de validation

- [Comparaison sur bureau](../images/cultures-ui-lot-4/comparaison-bureau.png).
- [Comparaison sur mobile en plein jour](../images/cultures-ui-lot-4/comparaison-mobile-plein-jour.png).
- [Courbe et tableau sur mobile](../images/cultures-ui-lot-4/courbes-mobile.png).

Les données sont fictives. Les captures pleine page montrent la barre mobile fixe
à la position du viewport initial ; ce n’est pas une seconde barre dans la page.
