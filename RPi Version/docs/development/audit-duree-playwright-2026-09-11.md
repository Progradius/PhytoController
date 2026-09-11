# Durée de la suite Playwright — état des lieux et recommandations (11 septembre 2026)

## Résumé

La suite navigateur est longue pour trois raisons, dans cet ordre :

1. **Elle démarre 522 processus Python par exécution complète**, dont **190 pour des tests qui
   sont ensuite ignorés** : le `test.skip(testInfo.project.name …)` est écrit dans le corps du test,
   donc **après** la fixture du carnet, qui a déjà lancé et attendu son serveur.
2. **Chaque démarrage coûte 3 à 8 s** parce que l'interpréteur importe tout le serveur depuis
   `/mnt/c` (venv compris) : c'est 10 fois plus lent que sur le système de fichiers ext4 de WSL.
3. **Le parallélisme est bridé** : ports figés (38123, 39123 + rang du worker) qui interdisent
   deux exécutions simultanées, ordonnancement par fichier (`fullyParallel` absent), budgets de
   20 s qui cèdent sous charge, et un serveur partagé qui porte un limiteur de prévisualisation
   commun à tous les workers. D'où la pratique actuelle — un profil à la fois, `--workers=1`,
   verrou `flock` — qui transforme chaque coût unitaire en temps mural.

Le multiplicateur de fond est la matrice : **150 scénarios deviennent 551 exécutions** (89 d'entre
eux tournent sur 5 ou 6 profils) ; le profil `mobile-zoom`, ajouté ce matin (`6f39986`), en a apporté
93 à lui seul.

Mesuré sur le profil bureau à 8 workers : 361 s aujourd'hui, 224 s avec l'arbre et le venv sur
ext4, 135 s en ajoutant `fullyParallel` — lequel exige d'abord de supprimer le serveur partagé.

Les corrections P0 et P1 ci-dessous ne retirent **aucune couverture**. Seule la P2 (matrice)
en retire, et c'est une décision à prendre.

## Conditions de mesure

- WSL2, 16 cœurs, 47 Go ; Playwright 1.62.1 ; Chromium headless ; Python 3.11.
- Dépôt et `.venv` sur `/mnt/c` (drvfs/9p), comme au quotidien.
- Les expériences ont été jouées sur une **copie** de l'arbre de travail (ports décalés
  48123/49123/51123/52123, rien de modifié dans le dépôt), pour ne pas percuter les exécutions
  d'une autre session qui tournaient au même moment.
- La machine est partagée (plusieurs sessions Claude, Codex, une JVM) : les temps muraux
  multi-workers sont bruités. Les mesures unitaires (import, fork, arrêt) sont répétées et stables.

## État des lieux

### Volume

| | Nombre |
| --- | ---: |
| Tests déclarés | 162 |
| Profils (`projects`) | 6 |
| Couples test × profil | 972 |
| Exécutions réelles | **551** |
| Entrées ignorées à l'exécution (`test.skip` dans le corps) | 421 (43 %) |
| Scénarios distincts exécutés | 150 |
| … sur 1 profil / 2 / 5 / 6 | 51 / 10 / 54 / 35 |
| Serveurs Python dédiés démarrés (fixture carnet ou serveur dédié) | **522** |
| … dont pour un test ignoré | **190 (36 %)** |

Exécutions par profil (entre parenthèses : avec serveur dédié) : bureau 124 (74), mobile 105 (68),
étroit 91 (58), paysage 88 (57), zoom 93 (57), PWA 50 (18).

Méthode : liste réelle de Playwright (`--list`), puis évaluation des conditions de `skip` de chaque
test pour chaque profil. Recoupé sur une exécution réelle (`cultures_ui_lot_2.spec.js` sur
`pwa-chromium` : 2 exécutés, 19 ignorés, **21 serveurs lancés**, compteur posé dans la fixture).

### Coût d'un serveur dédié

Temps d'import de `tests/ui_server.py` (`build_app()` ajoute ~60 ms) :

| Emplacement | Seul | 8 démarrages simultanés |
| --- | ---: | ---: |
| Arbre et venv sur `/mnt/c` (situation actuelle) | 3,3 s | 7,2 – 8,3 s |
| Arbre sur `/mnt/c`, venv sur ext4 | 1,6 – 2,0 s | ~1,7 s |
| Arbre et venv sur ext4 | 0,33 s | ~1,0 s |
| Processus pré-importé puis `fork()` + `build_app()` | **0,02 s** | — |

S'y ajoutent :

- **La détection de disponibilité est quantifiée à la seconde.** La fixture sonde `/health/ready`
  par `expect.poll`, dont les paliers sont 100, 250, 500 puis 1000 ms : les temps observés tombent
  sur 0,36 / 0,87 s (ext4) ou 2,87 / 3,87 s (`/mnt/c`). En moyenne ~0,5 s perdue par démarrage.
- **`tests/ui_server.py` importe `tests.test_http_server`, donc `pytest`** (0,68 s des 3,3 s) pour
  réutiliser quatre faux objets.
- L'arrêt (SIGTERM → sortie) coûte ~0,3 s : acceptable.

Effet sur une spec réelle (`cultures_ui_lot_2.spec.js`, 1 worker) :

| Cas | ext4 | venv `/mnt/c` |
| --- | ---: | ---: |
| Profil PWA (19 tests ignorés sur 21) | 22,5 s | 78 s |
| Profil bureau (20 tests exécutés) | 113 s | 182 s |

### Ordonnancement et parallélisme

- **Ports figés.** `webServer` sur 38123, carnet sur 39123 + rang du worker, serveurs dédiés sur
  41123/42123 + rang. Deux exécutions simultanées sur la même machine se percutent — constaté deux
  fois pendant cet audit (`http://localhost:38123 is already used`). `pwa_connexion.spec.js:111` code
  en outre `http://127.0.0.1:38123` en dur. C'est ce qui a imposé le `flock` et `--workers=1` entre
  sessions (voir `tasks/lessons.md`, leçon 4 de la reprise web/mobile/PWA).
- **Pas de `fullyParallel`.** Les tests d'un même fichier restent en série dans un worker ; le
  fichier le plus long borne le temps mural. `pwa_connexion.spec.js` cumule 71 s de
  `waitForTimeout` volontaires (scénarios temporels réels) et ~165 s au total sur le bureau ;
  `cultures_ui_lot_2.spec.js` pèse 85 à 150 s selon la charge.
- Le **serveur partagé n'est modifié par aucune spec** (les mutations passent toutes par un serveur
  dédié ; `config.spec.js` l'écrit en tête), **mais il n'est pas sans état** :
  `POST /api/v1/config/preview` est limité à l'échelle du processus (une prévisualisation à la fois,
  puis `PREVIEW_MIN_INTERVAL_SECONDS = 0.4`, sinon 429 — `network/web/server.py:1041`). Or `/conf`
  n'affiche le sélecteur Simple/Avancé que si cette prévisualisation répond
  (`static/js/config.js:522`). Tous les workers partagent donc ce limiteur : deux pages `/conf`
  ouvertes au même instant, sur n'importe quel profil, peuvent se refuser mutuellement la
  prévisualisation. Sous `fullyParallel`, `config.spec.js:170` échoue ainsi 2 fois sur 2 ; sans lui,
  le couplage est latent (les 6 profils de `config.spec.js`, `dashboard.spec.js` et
  `qualification.spec.js` visitent `/conf` en parallèle).

### Stabilité sous charge

À 8 workers, deux tests échouent de façon reproductible par dépassement de budget, sans
chevauchement avec une autre exécution Playwright :

- `cultures.spec.js:36` — parcours long (deux mères, un lot, une note, une correction, axe) **sans**
  `test.setTimeout`, donc soumis aux 20 s globaux ;
- `cultures_lot_g.spec.js:129` — prédicat « Ouverture de la saisie enregistrée » à 20 s.

Ce ne sont pas des défauts applicatifs : ce sont des budgets calibrés pour une machine au repos.
Ils cèdent précisément quand les démarrages de serveurs saturent les entrées-sorties.

### Banc profil bureau (124 exécutions, 8 workers)

Exécutions sérialisées par le verrou `flock` de l'autre session (aucun chevauchement Playwright),
charge ambiante non nulle :

| Cas | Temps mural | Somme des durées | Échecs |
| --- | ---: | ---: | --- |
| A — venv `/mnt/c`, ordonnancement par fichier (situation actuelle) | 361 s | 947 s | 2 : budgets de 20 s (`cultures.spec.js:36`, `cultures_lot_g.spec.js:129`) |
| B — venv et arbre sur ext4, par fichier | 224 s | 855 s | 0 |
| C — ext4 + `fullyParallel` | 135 s | 791 s | 2 : limiteur de prévisualisation (`config.spec.js:170`), budget (`cultures_lot_g.spec.js:129`) |

Une première passe, polluée par une exécution concurrente, donnait le même ordre (256 / 262 /
154 s) et les mêmes échecs. Lecture : ext4 seul retire ~40 % du temps mural et fait disparaître les
échecs de budget ; `fullyParallel` retire encore ~40 %, mais révèle le couplage du limiteur. Le
profil bureau ne représente que 124 des 551 exécutions.

### Ce qui n'est pas un problème

- Les traces (`trace: "retain-on-failure"`) : 113 s avec, 111 s sans. À conserver.
- L'arrêt des serveurs (~0,3 s).
- Le volume de code des specs : les tests eux-mêmes durent 1 à 17 s, raisonnable pour des parcours
  complets.

## Recommandations

Classement : P0 = gain fort, sans perte de couverture, faible risque ; P1 = gain fort, conception à
soigner ; P2 = décision de couverture ; P3 = confort.

### P0-1 — Décider du profil **avant** la fixture : étiquettes et `grep` par projet

Remplacer les ~113 `test.skip(testInfo.project.name …)` par une étiquette déclarative sur le test
(`test("…", {tag: "@bureau-mobile"}, …)`) et un `grep` / `grepInvert` sur chaque projet de
`playwright.config.js`. Un test exclu n'est alors **ni planifié, ni instancié** : aucune fixture,
aucun serveur, aucun navigateur.

- Gain : −190 démarrages (−36 %) et −421 entrées ignorées dans les rapports.
- La matrice devient lisible en un seul endroit, au lieu d'être dispersée dans 22 fichiers.
- À préserver : la garde « cible externe » (`PHYTO_UI_BASE_URL`) **reste dans la fixture** — elle
  protège d'une écriture sur un Pi réel et ne dépend pas du profil (`docs/development/verification.md`).
- Les skips qui dépendent d'une donnée d'exécution (`page.viewportSize()`, `PHYTO_CAPTURE`)
  restent tels quels : ils ne concernent aucun test à serveur dédié.

### P0-2 — Ports éphémères et signal de disponibilité

`tests/ui_server.py` se lie au port `0`, puis écrit une ligne `PHYTO_UI_READY <port>` sur sa sortie
une fois l'écoute ouverte (`web.AppRunner` + `web.TCPSite` au lieu de `web.run_app`). La fixture
attend cette ligne au lieu de sonder `/health/ready`.

- Supprime la quantification à la seconde (~0,5 s × 332 démarrages utiles).
- Supprime **toute collision de ports** : deux sessions, deux agents ou un humain et un agent
  peuvent jouer Playwright en même temps. Le `flock` et `--workers=1` deviennent inutiles.
- Corriger au passage `pwa_connexion.spec.js:111` (URL en dur) et citer `PHYTO_TEST_PYTHON` dans
  `webServer.command` (un chemin avec espace casse la commande aujourd'hui).
- Le `webServer` partagé garde provisoirement un port fixe, rendu surchargeable (`PHYTO_UI_PORT`) ;
  il disparaît avec P1-1.

### P0-3 — Alléger l'import du serveur de test

Déplacer `CSRF_TOKEN`, `FakeEquipmentStore`, `FakeSensors`, `FakeStatus`, `FakeSupervisor` de
`tests/test_http_server.py` vers un module sans dépendance à `pytest` (par exemple
`tests/fakes/http_server.py`), importé par les deux. Gain ~20 % de chaque import.

### P0-4 — Environnement : venv hors de `/mnt/c`

Créer le venv de test sur ext4 (`python3 -m venv ~/.venvs/phyto`, `pip install -r
requirements-dev.txt`) et le désigner par `PHYTO_TEST_PYTHON`. Import divisé par ~2. Cloner le
dépôt lui-même sous `~/` le divise par 10, si l'outillage Windows le permet. Aucun changement de code.

### P1-1 — Un processus « zygote » par worker, un `fork()` par test

Garder l'invariant actuel — **un processus neuf par test**, donc aucun état partagé (espace 2
exclusif, overrides, registre d'état, `ConfigStore`) — mais ne plus payer l'import à chaque fois :

1. une fixture de **portée worker** lance `tests/ui_server.py --zygote`, qui importe tout, vérifie
   `threading.active_count() == 1` (condition d'un `fork()` sûr, vérifiée aujourd'hui : un seul
   thread après import) et attend des ordres ;
2. la fixture de **portée test** demande un enfant (`TMPDIR`, variables de scénario comme
   `PHYTO_UI_MEASURE_SCENARIO`) ; l'enfant applique son environnement, remet `tempfile.tempdir`
   à `None`, appelle `build_app()`, se lie au port `0` et renvoie son port ;
3. l'arrêt reste un SIGTERM à l'enfant, puis la suppression du répertoire, comme aujourd'hui.

Mesuré : 20 ms par serveur au lieu de 1 à 8 s. Rejeté : réutiliser un serveur par worker en
« réinitialisant » le carnet — les singletons de module fuiraient d'un test à l'autre, et
l'isolation deviendrait une promesse au lieu d'une construction.

À 20 ms, un serveur par test ne coûte plus rien : **tous** les tests peuvent avoir le leur, y
compris les lectures. Le `webServer` partagé disparaît, et avec lui le limiteur de prévisualisation
partagé, le dernier port figé et le `trap` de nettoyage de `playwright.config.js`. Une seule
mécanique remplace les trois actuelles (`webServer`, fixture du carnet, `serveurDedie`).

### P1-2 — `fullyParallel: true`, puis budgets revus

**Pas avant P1-1** : tant que le serveur partagé existe, `fullyParallel` fait échouer
`config.spec.js:170` (limiteur commun, voir plus haut). Contourner ce limiteur dans le harnais serait
tester autre chose que la production. Ensuite, activer `fullyParallel` pour que les fichiers longs
se répartissent entre workers (−40 % mesuré sur le bureau), après deux passes complètes à 8 workers
sans échec. Donner aux parcours longs un budget explicite (`test.slow()` ou `test.setTimeout`)
plutôt que de compter sur les 20 s globaux — `cultures.spec.js:36` en premier ;
`cultures_lot_g.spec.js:129` a cédé même sur ext4 sous `fullyParallel`.

### P2 — Matrice de profils (décision de couverture)

Aujourd'hui, un scénario **fonctionnel** du carnet (conflit 409, idempotence, refus de date,
correction) tourne sur bureau, mobile, étroit, paysage et zoom. Les trois derniers profils ne
changent que la géométrie ; ils ont été créés pour la mise en page et le reflow (fiche R4.1).
Proposition :

- scénarios fonctionnels du carnet : **bureau + mobile** ;
- étroit, paysage, zoom : specs de mise en page (`qualification`, `dashboard`, `config`,
  premiers écrans, absence de défilement horizontal) ;
- PWA : inchangé ;
- une variable `PHYTO_UI_MATRICE=complete` rejoue la matrice entière avant fusion.

Effet : jusqu'à −172 exécutions à serveur dédié sur les 332. À trancher test par test : un
scénario fonctionnel qui vérifie aussi « rien ne déborde à 320 px » garde ses profils étroits.

### P3 — Commandes par niveau

- `npm run test:ui:rapide` : bureau + mobile, pour la boucle de développement ;
- `npm run test:ui` : matrice P2 ;
- `npx playwright test --last-failed` pour rejouer les seuls échecs ;
- `--only-changed` n'aide qu'à moitié ici : il suit les imports JavaScript, pas les gabarits Jinja,
  le CSS ni le Python — une modification de gabarit ne sélectionnerait aucune spec.

## Ordre proposé et critère de réussite

1. P0-4 (environnement, immédiat), P0-3, P0-1, P0-2 — chacune se vérifie seule.
2. P1-1, puis P1-2.
3. P2 après accord, test par test.

Mesure de référence et de réussite : la suite complète, 8 workers, sur une machine au repos, avec
son temps mural, le nombre de serveurs démarrés et zéro échec sur deux passes consécutives. Le
compteur de démarrages se pose dans la fixture le temps de la mesure.

## Bilan de mise en œuvre (11 septembre 2026)

P0 et P1 livrés sur la branche `perf/playwright-duree` (commits `295259d` à `cc0d293`, puis
`a16c325` pour les corrections de la revue indépendante). P2 et P3 n'ont pas été engagés : P2 est une décision de
couverture.

### Résultat mesuré, suite complète

La suite comptait alors 176 tests, soit 1 056 couples test × profil sur `master`.

| | `master` (référence) | Branche, arbre et `.venv` sur `/mnt/c` | Branche, arbre et venv sur ext4 |
| --- | ---: | ---: | ---: |
| Couples planifiés | 1 056 | 580 | 580 |
| Exécutions réelles | 577 | 577 | 577 |
| Interpréteurs Python démarrés | 522 + 1 `webServer` | 1 zygote par worker | 1 zygote par worker |
| Workers | 8 (défaut) | 6 (défaut `40%`) | 6 |
| Temps mural | **997 s** | **602 s** | 388 à 572 s selon la charge ambiante |
| CPU moyen | 45 % (attente disque) | 51 % | 64 % |
| Échecs | 9 | 3 | 0 à 3 |

L'ensemble exécuté est **identique** avant et après (577 couples, vérifié couple par couple,
puis recoupé par la revue indépendante).

### Défauts de fond révélés et corrigés

- **Collision de ports** : `EADDRINUSE` sur un port fixe situé dans la plage éphémère de Linux,
  sans aucun serveur à l'écoute. Observé dans la référence (`cultures_lot_f.spec.js:21`). Supprimé :
  tous les serveurs se lient au port 0.
- **Limiteur de prévisualisation partagé** : dans la référence, `qualification.spec.js:156` échoue
  sur deux profils avec `POST /api/v1/config/preview` → **429** (trace). `/conf` reste alors en mode
  avancé et la mise en page change. Supprimé : chaque test a son serveur.
- **Course de navigation** (`cultures_lot_g.spec.js:129`) : un `goto` lancé pendant la navigation
  que la page déclenche elle-même après un enregistrement restait suspendu sans erreur. 25 échecs
  sur 40 répétitions avant la correction, 0 sur 40 après.
- **Budget sous-dimensionné** (`cultures.spec.js:37`) : 14 à 17 s au repos pour 20 s de budget.
  Il échoue sur trois profils dans la référence ; 25 sur 25 après la correction.
- **Dossier de résultats partagé** : une exécution vidait les traces d'une exécution simultanée.
  Corrigé par un dossier par exécution et un fichier `--last-failed` stable par checkout.

### Écarts avec les recommandations

- P0-2 : la variable `PHYTO_UI_PORT` n'a pas été créée. Le `webServer` a disparu avec P1-1.
- P1-2 : `fullyParallel` rapporte peu sur la suite complète (412 s → 388 à 415 s à 8 workers),
  déjà bien répartie par fichier. Il rapporte beaucoup sur une exécution ciblée d'un fichier long.
- La suite s'est révélée **limitée par le CPU** : 6 workers → 572 s, CPU 64 %, 0 échec ; 8 → 512 s,
  82 %, 2 échecs ; 12 → 470 s, 89 %, 9 échecs. Le défaut est donc `workers: "40%"`.

### Ce qui reste — préexistant, à décider

1. **Plantage de `chrome-headless-shell`** (SIGSEGV, adresse `0x1b0`, même site dans le binaire à
   chaque fois), sur le seul profil PWA. Sur 260 exécutions PWA : 2 plantages sur `master`, 5 sur la
   branche, **0 avec le Chromium complet** (`channel: "chromium"`, nouveau mode headless, +18 % de
   temps). Le Chromium complet a toutefois produit un échec de focus (`config.spec.js:78`) jamais vu
   avec `headless-shell`. Il faut le qualifier avant de basculer ce profil.
2. **Garde de performance** `cultures_ui_lot_4.spec.js:74` : moins de 10 s pour atteindre le dernier
   point, contre 1,0 s au repos. Elle cède sous charge des deux côtés : 10,05 s sur `master`, 10,6 à
   11,1 s sur la branche. Une garde de coût quadratique mesurée en temps réel dans une suite
   parallèle dépend de la machine.
3. **Charge extérieure à la suite** : ce poste fait tourner plusieurs sessions en même temps. Des
   budgets de 20 s cèdent encore quand la machine sature (`qualification.spec.js:249` : la page
   `/cultures` y a mis 4 s à charger au lieu de 80 ms).
4. **Clics pendant un défilement animé**, surtout sur `mobile-paysage` (320 px de haut, presque
   tout hors écran). Le journal d'action du clic « Créer un lot » (`cultures.spec.js:37`, passe de
   contrôle) montre « element is not stable » cinq fois, puis « done scrolling » suivi de
   « element is outside of the viewport ». Playwright a rendu la main alors que le défilement
   animé (`style.css:36`, `scroll-behavior: smooth`) se poursuivait. Le clic est parti, mais aucune
   requête n'a été envoyée. Sur ce profil, chaque clic y coûte 1 à 1,6 s. Piste : jouer la suite
   en `reducedMotion: "reduce"`, que `style.css` honore déjà (`scroll-behavior: auto !important`).
   Elle n'est **pas** adoptée : une répétition ciblée (30 exécutions sur `mobile-paysage`) passe à
   l'identique dans les deux configurations, et la course n'apparaît que sous la charge de la
   suite complète. À qualifier par plusieurs passes complètes avant d'en décider.
5. **WSL et `/mnt/c`** : l'écart restant entre `/mnt/c` (602 s) et ext4 (388 à 572 s) tient à drvfs.
   Deux voies : un clone sous `~/`, sans aucune modification de code ; ou un runner Windows sur le
   modèle de `deci`. Pour ce dépôt, cette seconde voie rencontre des obstacles : le zygote repose sur
   `fork()`, absent de Windows ; `requirements.txt` exige `RPi.GPIO` ; l'arrêt passe par les signaux
   POSIX. Il faudrait un montage hybride, Playwright sous Windows et zygote sous WSL, à prototyper et
   à mesurer avant toute décision.
