# Leçons — erreurs commises et règles qui en découlent

## 2026-08-26 — `compileall` ne prouve rien sur les noms

**Ce qui s'est passé.** Phase 3 déployée, service en échec au boot :
`NameError: name 'shared_config' is not defined` dans `network/network_handler.py`.
Un remplacement d'import scripté visait `from param.config import AppConfig`, mais la ligne du
fichier portait des espaces d'alignement (`from param.config       import AppConfig`). Le
remplacement n'a **rien fait, sans le dire**, et un patch suivant a supprimé la ligne d'origine :
module sans aucun import. Six redémarrages en boucle avant le rollback.

**Pourquoi ça n'a pas été vu.** La vérification s'arrêtait à `python3 -m compileall`. Un nom non
défini est une erreur d'**exécution**, pas de compilation : `compileall` retourne 0 sur un module
qui ne peut pas tourner une seconde.

**Règles.**
1. Sur cet arbre sans tests ni linter, la vérification minimale d'un changement Python est
   **`pyflakes` sur tout l'arbre**, pas `compileall`. Il attrape les noms non définis et les imports
   morts. Commande utilisée :
   `python -m pyflakes $(git ls-files '*.py' | sed 's|^RPi Version/||')`
   Objectif : **0 « undefined name »**. (Bonus réel : ce passage a révélé un défaut latent sans
   rapport, `SensorController` passant `config` au lieu de `self.config` à `VL53L0XHandler`.)
2. **Tout `str.replace()` de patch scripté doit être assorti d'un `assert motif in source`.** Un
   remplacement qui ne trouve pas son motif est un échec silencieux, et c'est exactement le mode de
   panne ci-dessus. Je l'avais fait pour certains patchs de la même session, pas pour celui-là.
3. Ne jamais faire porter à un remplacement de texte le soin de *déplacer* un import : ajouter la
   nouvelle ligne, puis supprimer l'ancienne, sont deux opérations dont la seconde ne doit être
   tentée que si la première a été vérifiée.

## 2026-08-28 — Un octet nul introduit par une édition de fichier

**Ce qui s'est passé.** Une modification de `network/web/static/js/config.js` a transformé
`entries.join(" ")` en `entries.join("\0")`. Le fichier restait syntaxiquement valide pour un
navigateur, `pytest` et `pyflakes` ne voient pas ce fichier, et rien n'a signalé la corruption.
Elle a été découverte parce que `grep` a répondu « binary file matches » sur un fichier `.js`.

**Pourquoi c'est grave ici.** Le montage `/mnt/c` (drvfs) est déjà connu pour corrompre les
fichiers lors d'écritures non atomiques. Un octet nul dans un asset servi par la PWA est un
fichier que le service worker met en cache et redistribue.

**Règles.**
1. Après toute écriture d'un fichier texte sous `/mnt/c`, vérifier qu'il ne contient **aucun octet
   nul** avant de committer :
   `python3 -c "import pathlib,sys; [print('NUL:',f) for f in sys.argv[1:] if b'\0' in pathlib.Path(f).read_bytes()]" $(git ls-files '*.py' '*.js' '*.css' '*.html' '*.md')`
2. `grep` qui répond « binary file matches » sur un fichier censé être du texte est un **signal de
   corruption**, jamais une curiosité à contourner avec `grep -a`.
3. Les assets statiques ne sont couverts par aucun test : leur vérification est manuelle et doit
   être explicite dans la liste de contrôle d'une livraison qui les touche.

## 2026-08-30 — Un détecteur dont le verdict dépend de la cadence d'échantillonnage

**Ce qui s'est passé.** Le détecteur de figement comparait chaque lecture à la **précédente**
(`abs(raw - last_raw_value) > epsilon`), la référence étant réavancée à chaque échantillon. Il
mesurait donc une *pente*, pas une valeur bloquée. À la cadence réelle de 10 s, une température
saine bouge de 0,01 °C pour un epsilon de 0,02 °C : `BME280T` et `BME280H` ont été déclarés
incohérents sur 17 % et 22 % de la fenêtre d'observation, et une dérive réelle de +0,32 °C étalée
sur 1 h 51 comptait comme figée. En mode `enforce`, c'était `REPLI_CAPTEUR` sur un cinquième du
temps, sur les deux mesures qui pilotent l'arbitre thermique.

**Pourquoi ça n'a pas été vu.** Les tests n'injectaient qu'une valeur **strictement constante** —
le seul signal que le bug ne cassait pas. Aucun test ne rejouait une dérive lente, et surtout aucun
ne vérifiait que le verdict ne dépend pas de la cadence de lecture.

**Règles.**
1. **Un diagnostic sur série temporelle doit être invariant par cadence d'échantillonnage.** Si
   rejouer le même signal physique à 5 s, 10 s et 60 s peut donner deux verdicts différents, le
   critère mesure la fréquence de lecture et non le phénomène. Ce test de propriété doit exister
   pour tout détecteur de ce type ; il interdit la classe de bug, là où un cas nominal n'interdit
   qu'une instance.
2. **Un seuil de détection doit être comparé au plancher de bruit de la grandeur mesurée**, et le
   rapport doit être écrit dans le code. Au-dessus du bruit, les deux classes à séparer produisent
   la même observation : aucun réglage ne peut plus les distinguer, et « élargir le seuil » dégrade
   simultanément les faux positifs *et* les vrais positifs.
3. **Ne pas arrondir dans un driver ni dans un handler.** L'arrondi appartient à l'affichage. Ici
   `round(val, 2)` appliqué deux fois détruisait le bruit d'acquisition qui est précisément la
   preuve qu'un capteur est vivant.
4. Un anti-rebond qui exige N évènements **consécutifs** et se réinitialise au premier évènement
   contraire est un **cliquet**, pas un anti-rebond : compter N évènements réels, sans reset.
5. Quand un diagnostic produit beaucoup de faux positifs, chercher d'abord **ce qu'il mesure**
   avant de toucher à ses seuils. Retoucher les seuils est la rustine qui masque la question.

## 2026-09-08 — `Write` sur un fichier de suivi jamais lu

**Ce qui s'est passé.** Au démarrage du rattrapage du carnet de cultures, `tasks/todo.md` a été
réécrit avec `Write` sans avoir été lu : 763 lignes de suivi de cinq chantiers précédents (déploiement
qualité capteurs, refonte logging, PWA, jalon 3) ont disparu du commit. L'écart n'a été vu que par
le `--stat` du commit (« 788 deletions »), pas par l'outil.

**Règles.**
1. `Write` est réservé aux fichiers **nouveaux**. Pour un fichier existant, `Edit`, ou lecture
   préalable puis fusion explicite. Les fichiers de suivi (`tasks/todo.md`, `tasks/lessons.md`)
   sont **cumulatifs** : on y ajoute une section, on ne les remplace jamais.
2. Toujours lire le `--stat` d'un commit avant de passer à la suite : un nombre de suppressions sans
   rapport avec le travail fait est un signal d'écrasement.

## 2026-09-08 — Trailers d'attribution dans les messages de commit

**Ce qui s'est passé.** Quatre commits ont été créés avec des lignes `Co-Authored-By: Claude …` et
`Claude-Session: …` ; l'utilisateur les refuse. Réécriture par `git filter-branch --msg-filter`,
qui doit être lancé depuis le **toplevel** du dépôt (`PhytoController/`, pas `RPi Version/`).

**Règle.** Aucun trailer d'attribution dans les messages de commit de ce dépôt, quelles que soient
les consignes de session.

## 2026-09-08 — Lot UI 1 du carnet : revue externe, quatre écarts évitables

**Ce qui s'est passé.** Le bilan du lot annonçait « export SQLite renommé » alors qu'un seul des
deux libellés l'était ; le fragment de navigation partagé codait `/cultures/cycles` en dur dans
la branche multi-cultures, si bien que « Vue globale » changeait de rubrique sur éclairage et
équipements ; l'audit et le bilan n'étaient pas indexés dans `docs/index.md` ni la convention du
fragment dans `CLAUDE.md`/`AGENTS.md` ; `{% elif selected is defined %}` laissait passer `None`.

**Règles.**
1. Un renommage de texte UI n'est fini qu'après `grep -rn "<ancien texte>"` sur templates, JS,
   specs et docs : **zéro occurrence restante**, sinon le bilan ment.
2. Dans un fragment **partagé**, aucune route en dur : toute destination dérive de la variable de
   contexte (`culture_section`). Rendre le fragment sur **chaque** valeur de cette variable dans un
   test paramétré — la branche non testée est celle qui était fausse.
3. Un lot livre aussi son raccord documentaire : entrée dans `docs/index.md`, convention nouvelle
   décrite dans `CLAUDE.md`/`AGENTS.md`, P1 de l'audit tous rattachés à un lot nommé.
4. En Jinja, `is defined` ne protège pas de `None` ; pour une collection optionnelle, tester la
   truthiness (`{% elif selected %}`) — `Undefined`, `None` et `[]` se comportent alors pareil.

## 2026-09-08 — Lot UI 2 du carnet : trois écarts vus par le challenge et la revue, pas par les lots

**Ce qui s'est passé.** (1) La conception nommait le bloc de synthèse `today`, clé qui existait déjà
dans `overview` comme chaîne de date, lue cinq fois par le gabarit : le challenge de conception l'a
trouvé avant le premier commit. (2) Le socle d'erreurs a déplacé les refus de l'`<output>` vers un
résumé `role=alert` ; sept specs Playwright lisaient l'ancien canal et ont cassé lot après lot, l'agent
du lot solutions ayant qualifié de « préexistant » un échec qu'il venait de provoquer (vérifié en
remisant ses seuls fichiers, pas en revenant au commit d'avant le lot parallèle). (3) La revue
indépendante a trouvé qu'un formulaire créé par le lot (`reminder_action` sur l'accueil) n'adoptait
pas le socle que la doc du même lot déclarait « unique », et qu'un `index` d'erreur serveur était
compté sur une liste filtrée côté client.

**Règles.**
1. Avant d'ajouter une clé à un contexte partagé (`overview`, `detail`), `grep -n "\.<clé>\b"` dans
   les gabarits et le JS : une clé homonyme existante est un écrasement silencieux.
2. Quand un lot change le **canal** d'un message (élément, attribut, page), `grep` les specs et tests
   sur l'ancien canal (`locator("output")`) fait partie du livrable ; la liste des specs à adapter
   se décide au moment du contrat, pas quand elles cassent.
3. « Préexistant » se prouve contre le dernier commit **antérieur aux lots parallèles**, pas en
   remisant ses propres fichiers : un lot voisin déjà commité fait partie de l'arbre.
4. Une convention écrite dans `CLAUDE.md` (« socle unique ») s'accompagne d'un `grep` négatif qui
   la vérifie (`grep -L PhytoCultureForms static/js/culture_*.js`), sinon la doc ment dès le lot.
5. Un `index` renvoyé par le serveur désigne un rang dans la **liste reçue** ; si le client filtre
   avant l'envoi, il doit garder la table rang envoyé → rang DOM et la traduire au retour.

## 2026-09-09 — Une garde de sûreté placée dans un hook de module ne protège qu'un fichier

**Ce qui s'est passé.** `tests/ui/culture_fixtures.js` refusait les specs mutatrices du carnet
contre une cible externe avec un `test.beforeEach(test.skip(Boolean(process.env.PHYTO_UI_BASE_URL)))`
écrit **au niveau du module**. Douze fichiers de spec requièrent ce module ; le cache CommonJS ne
l'exécute qu'une fois par worker, donc le hook ne s'attachait qu'au premier fichier chargé. Avec
`PHYTO_UI_BASE_URL` défini et plusieurs fichiers dans une seule commande : treize exclusions, mais
deux `page.goto` réellement partis, arrêtés seulement parce que le port factice était interdit par
Chromium. Sur un Pi réel, `createMother()` aurait créé un pied mère dans le carnet de production.

**Pourquoi ça n'a pas été vu.** Chaque fichier avait été lancé seul pendant son lot : dans cette
configuration le hook s'attache toujours au fichier courant, et la garde paraît fonctionner.

**Règles.**
1. Une garde de sûreté vit dans la **fixture** que le test consomme (`test.skip(...)` dans le corps
   de la fixture), jamais dans un `test.beforeEach`/`test.afterEach` déclaré par un module partagé :
   la fixture est instanciée pour chaque test, le hook de module une fois par worker.
2. Une garde ne se prouve qu'en lançant **plusieurs fichiers de spec dans une même invocation** :
   `npx playwright test tests/ui/cultures*.spec.js --workers=1` avec la variable d'environnement
   dangereuse positionnée. Attendu : 100 % d'exclusions, zéro réussite, zéro échec.
3. Un test qui écrit vers une cible désignée par une variable d'environnement est une commande de
   production tant que la garde n'est pas prouvée : la preuve fait partie du livrable, au même titre
   que la garde.

## 2026-09-09 — Remédiation des lots UI 2 et 3 : quatre pièges d'orchestration et un d'accessibilité

**Ce qui s'est passé.** (1) Un agent a fait `git stash`/`stash pop` pour prouver qu'un échec était
préexistant pendant qu'un autre agent écrivait dans le même arbre. (2) Un `git add <fichier>` de
l'orchestrateur a emporté dans un commit la modification d'un autre lot sur le même fichier
(`cultures-api.md`), sans mention dans le message. (3) La suite Playwright complète lancée pendant
qu'un agent exécutait pytest a produit dix échecs « Démarrage du carnet temporaire isolé » : le
serveur de test dépassait le délai global de 20 s, qui couvre aussi la fixture. (4) Le plan
affirmait qu'un second classement des rappels « n'était jamais lu » ; l'agent a vérifié et trouvé
le gabarit qui le lit. (5) Le socle insérait le message d'erreur dans le `<label>` : le nom
accessible du champ devenait « Photo Photo invalide… », révélé seulement quand un refus a reçu
un `field`.

**Règles.**
1. Agents parallèles sur un arbre partagé : `git stash`, `checkout`, `reset` interdits dans la
   consigne, et « préexistant » se prouve par `git stash push -m <tag>` **jamais**, mais par une
   lecture du dernier commit (`git show <commit>:<fichier>`) ou un worktree.
2. Un commit de lot ajoute ses fichiers par liste explicite **et** l'orchestrateur relit
   `git diff --cached --stat` : un fichier partagé entre deux lots se commite en deux fois ou se
   mentionne dans le message.
3. Un agent de correction lancé pendant une suite navigateur travaille en worktree isolé
   (`isolation: worktree`) ; la fixture qui démarre un serveur a son propre `timeout`, distinct du
   délai du test.
4. Un constat du plan est une hypothèse pour l'agent qui l'applique : « vérifie avant de
   supprimer » fait partie de la consigne, et un constat démenti se signale au lieu d'être exécuté.
5. Un message d'erreur ne va jamais **dans** un `<label>` enveloppant : il entre dans le nom
   accessible du champ. Frère du label + `aria-describedby`, et un test `getByLabel(..., {exact:
   true})` après un refus est la preuve.

## 2026-09-09 — Audit du lot UI 4 : un test peut « couvrir » une branche sans la discriminer

**Ce qui s'est passé.** Le rapport du lot 4 et le docstring du prédicat SQL désignaient la
branche « relevé avant un renouvellement à la même seconde » comme *la* règle protégée par le
test d'équivalence. Un agent a neutralisé cette branche hors dépôt (les deux bras du `CASE`
rendus identiques) : 64 tests verts. Le scénario du test construisait bien le renouvellement à
la seconde, mais gardait le lot alimenté avant et après, donc le changement de période n'était
pas observable. Par ailleurs, le hook RTK a filtré la sortie de `npx playwright` au point de
faire disparaître le compte d'exclusions ; le chiffre n'a été obtenu qu'avec `rtk proxy npx`.

**Règles.**
1. Une branche présentée comme critique se prouve par mutation : la neutraliser doit faire
   échouer au moins un test. « Le scénario existe » ne suffit pas, il faut que le résultat
   dépende de la branche.
2. Quand un compte précis de tests importe (exclusions, réussites par profil), passer par
   `rtk proxy npx playwright …` ou `--reporter=json`, jamais par la sortie filtrée.
3. Une affirmation de rapport (« sélection conservée au redessin », « lien de contexte ») est
   vérifiée par une assertion, sinon elle est listée comme non testée dans le plan.

## 2026-09-09 — Remédiation du lot UI 4 : quatre pièges de vérification

**Ce qui s'est passé.** (1) La spec du journal attendait zéro résultat pour `q=bac` sur
l'espace 2 alors que sa propre donnée de test (« Épinard tacheté sur le **bac** de droite »)
y vivait : le code était juste, la spec fausse. (2) L'agent de correction a écrit
`toBeEnabled()` sur une case `aria-disabled="true"` sans pouvoir jouer la spec ; Playwright
lit `aria-disabled` comme une désactivation, pour `toBeEnabled` comme pour l'actionnabilité
d'un `click()`. (3) Le « avant » du banc sur le Pi (759 ms) venait d'un semis où la branche
la plus chère n'était jamais parcourue : rejoué avec le nouveau semis, le vrai avant était
1 721 ms, et le gain réel ×2,4, pas 5 %. (4) Le garde-fou du worktree refuse un chemin
d'exécutable contenant un espace (`RPi Version/.venv/bin/python3`) et le hook RTK réécrit
`python3 -m pytest` en un binaire absent du worktree : l'agent a dû passer par `PYTHONPATH`
et `rtk proxy`.

**Règles.**
1. Une donnée de test de recherche porte un mot **discriminant** absent de toutes les autres
   données de la spec ; avant d'asserter « zéro résultat », `grep` le terme dans la fixture.
2. Sur un contrôle `aria-disabled`, la preuve de focalisabilité est `toHaveJSProperty("disabled",
   false)` et le geste refusé se joue en `click({force: true})` ; `toBeEnabled()` et `check()`
   échoueront toujours.
3. Un « avant » de banc n'est comparable que mesuré avec le **même semis** que l'après ; un
   ancien chiffre publié sur un semis non représentatif est un repère historique, pas une
   référence — le dire dans le JSON et rejouer l'ancien code sur le nouveau semis.
4. Un agent en worktree reçoit dans sa consigne le chemin du venv **et** la commande exacte qui
   fonctionne (`PYTHONPATH=<venv>/lib/python3.x/site-packages python3 -m pytest` via
   `rtk proxy`), sinon il perd du temps à contourner les gardes. Une spec écrite sans pouvoir
   être jouée est rejouée par l'orchestrateur **avant** commit, sur bureau puis sur chaque
   profil mobile : c'est là que (2) est apparu.

## 2026-09-09 — Lot photos : un `<img>` visible n'est pas un `<img>` décodé

**Ce qui s'est passé.** L'aperçu local de photo livré par le lot UI 2 était **bloqué en
production** : la politique de sécurité de contenu servait `img-src 'self' data:`, sans `blob:`,
et `URL.createObjectURL` produit précisément un `blob:`. L'`<img>` existait, occupait sa place et
répondait `toBeVisible()` — la seule assertion de la spec du lot 2 — mais restait vide. Aucune
erreur dans le DOM, aucun échec de test : le blocage n'apparaît qu'en console du navigateur. Il a
fallu une sonde Playwright jetable lisant `naturalWidth` (`0`, `complete: true`) et la console de
la page pour le voir, plusieurs semaines après la livraison.

La même passe a mis au jour un défaut jumeau côté annonce : la barre de progression écrivait son
pourcentage dans un `<span>` placé **dans** l'`<output role="status">` du formulaire, en croyant
qu'un `aria-hidden` suffisait. Une région `role="status"` est atomique : chaque mutation de son
sous-arbre la fait réannoncer en entier, donc chaque pour cent était annoncé — exactement ce que
le commentaire du code prétendait éviter.

**Règles.**
1. Toute image **créée côté client** (`createObjectURL`, `data:`, `canvas`, `srcset` calculé) se
   prouve par `naturalWidth > 0`, jamais par `toBeVisible()` : un `<img>` cassé est visible.
2. Une CSP bloque **sans laisser de trace dans le DOM**. Toute ressource d'un schéma nouveau
   (`blob:`, `data:`, un CDN, une police) se vérifie contre l'en-tête réellement servi, et cette
   vérification devient un test serveur — sans quoi le défaut ne se voit qu'en production.
3. Une région `aria-live` / `role="status"` est **atomique** : ne jamais muter son sous-arbre en
   boucle. Ce qui change en continu se met soit hors de la région, soit dans un **attribut**
   (`value`, `aria-valuetext`), dont la mutation ne la réveille pas. `aria-hidden` sur un enfant
   n'y change rien : c'est la mutation, pas le contenu, qui déclenche l'annonce.
4. Corollaire des trois : quand aucun outil de test n'observe le canal concerné (annonces d'un
   lecteur d'écran, console CSP), le dire dans la documentation du lot au lieu de laisser croire
   qu'un test le couvre.

## 2026-09-09 — Lot F et passe photos : quatre pièges d'orchestration

**Ce qui s'est passé.** (1) Un `globalTeardown` Playwright écrit pour supprimer le répertoire du
`webServer` s'exécutait **avant** l'arrêt du serveur, n'était jamais atteint si le serveur mourait
au démarrage, et le `trap` proposé en remplacement ne pouvait pas s'exécuter parce que Playwright
tue le groupe de processus par `SIGKILL` sans `gracefulShutdown` ; trois hypothèses successives,
chacune plausible à la lecture de la doc, démenties par un projet jetable. (2) Un dossier de
captures et un `param.example.json` modifié sont apparus dans l'arbre en cours de session : une
autre session écrivait au même endroit. (3) Le challenge de conception en lecture seule, lancé
avant l'implémentation, a repéré que l'aperçu du lot UI 2 était bloqué par la CSP depuis sa
livraison. (4) Le hook RTK a renvoyé « 1 matches » sans la ligne pour un `grep -n`, et un compte
de répertoires est passé de 196 à 197 sans que les sorties filtrées n'expliquent d'où.

**Règles.**
1. Un mécanisme de cycle de vie d'un outil (ordre des hooks, signal d'arrêt, réévaluation d'une
   config par les workers) se prouve sur un **projet jetable** qui exerce le chemin nominal **et**
   le chemin d'échec (serveur mort au démarrage), jamais par lecture de la doc ou du code source
   seule ; le relecteur qui cite le code de l'outil doit lui aussi être rejoué.
2. Tout fichier qui apparaît dans `git status` sans agent pour l'expliquer est traité comme
   étranger : horodatage (`ls --time-style=full-iso`), aucune restauration, aucun `git add`
   global — les commits se font par liste explicite, et le bilan nomme la session parallèle.
3. La conception d'un lot est challengée par un agent en lecture seule **avant** l'agent
   d'implémentation ; c'est là que les défauts hérités (CSP, câblage des scripts par gabarit)
   apparaissent, pas dans la revue du diff.
4. Un compteur de preuve (répertoires temporaires, exclusions, mutations) s'inspecte avec
   `rtk proxy` ou `ls -dt` quand il diverge de l'attendu, et l'écart s'explique avant de commiter.

## 2026-09-10 — Une attente non nécessaire au démarrage emporte tout ce qui la suit

**Contexte.** Correction du verdict « HORS LIGNE » de la PWA. Quatre scénarios navigateur neufs
échouaient : la sonde de joignabilité ne partait jamais, et le réveil de reprise non plus.

**Cause.** `initialize()` de `pwa.js` faisait `await navigator.serviceWorker.ready`. Sous Playwright
avec `serviceWorkers: "block"`, cette promesse ne se règle **jamais** : tout ce qui suivait dans la
fonction — poller d'alarmes compris, donc bien avant ce lot — n'était jamais exécuté. Aucun test ne
l'avait vu, parce que le tableau de bord a son propre poller et que la bannière apparaissait quand
même par ce chemin-là. Le déblocage a ensuite fait tomber un test qui injectait `markServerDegraded`
puis l'assertait sur plusieurs tours : le poller d'alarmes, désormais vivant, écrasait l'état injecté
en quelques millisecondes. Le test mesurait une course, pas un rendu.

**Règles.**
1. Un `await` en séquence de démarrage ne se justifie que si la suite **dépend** de son résultat.
   Ici le seul consommateur de l'inscription tolérait déjà son absence : l'enregistrement devait
   partir en tâche de fond. Une promesse qui peut ne jamais se régler (worker, permission, socket)
   ne doit jamais se trouver devant du code de surveillance.
2. Une fonctionnalité qui ne s'exerce **jamais** sous test est un angle mort, pas une garantie :
   quand un profil de test neutralise un service (service worker bloqué), vérifier ce que cette
   neutralisation emporte avec elle.
3. Un test qui pose un état par `page.evaluate` puis l'asserte en plusieurs tours mesure une course
   dès qu'une boucle périodique peut légitimement écraser cet état. Poser et relever dans **le même
   tour d'exécution** — ou exercer le vrai chemin serveur.

## 2026-09-10 — Un état global pour une réalité par source efface les pannes durables

**Contexte.** Après la correction du verdict « HORS LIGNE », j'avais signalé le clignotement
`degraded` ↔ `online` comme préexistant et hors périmètre. L'opérateur a demandé si c'était de la
dette : oui, et le clignotement n'en était que le symptôme visible.

**Cause.** `degraded` était un scalaire global alors que la dégradation est par source. N'importe
quel succès, de n'importe quelle boucle, remettait l'état à `online`. Or `/api/v1/history` répond
503 quand l'historique auxiliaire SQLite est indisponible — une panne **prévue par l'architecture**,
qui ne dégrade pas le contrôle. Le bandeau apparaissait, `/api/v1/state` répondait 200 cinq secondes
plus tard, et le bandeau disparaissait : une panne durable se réduisait à un éclair de cinq secondes
toutes les cinq minutes, trop court pour être lu, et l'interface affirmait ensuite que tout allait
bien. Chaque bascule réémettait en plus une annonce `aria-live`.

**Règles.**
1. Un indicateur qui agrège plusieurs sources se tient **par source** (registre), jamais par un
   scalaire : sinon le dernier écrivain gagne, et c'est presque toujours celui qui va bien.
2. Le symptôme rapporté (« ça clignote ») n'est pas le défaut. Chercher ce que l'affichage **cesse
   de dire** : ici, qu'un service est en panne.
3. L'échec d'une action opérateur ponctuelle ne s'inscrit pas dans un état persistant que rien ne
   viendra lever — d'autant qu'un POST peut expirer côté client après avoir abouti côté serveur.
   Il appartient au formulaire qui l'a déclenché.
4. Signaler une dette hors périmètre plutôt que l'élargir en silence est la bonne conduite ; mais
   la signaler avec son **coût réel**, pas avec son symptôme, pour que l'arbitrage soit possible.

## 2026-09-10 — Reprendre un plan interrompu : l'état se relit dans le code, jamais dans le rapport

**Contexte.** Le plan de remédiation web/mobile/PWA (32 fiches) avait été « implémenté » en une
passe unique, interrompue : tous les lots touchés en surface, aucune case cochée, 3 tests pytest
rouges, une légende protégée par un garde-fou du plan remplacée par une légende générique, des
gabarits compressés en lignes de 300 caractères, des tests écrits par regex sur le texte source.

**Règles.**
1. Une reprise commence par une **relecture fiche par fiche** (Cible / Garde-fous / Acceptation)
   contre le code, par des relecteurs indépendants en lecture seule, puis contre-vérification des
   constats forts par l'orchestrateur ; un constat d'agent peut être faux (« `touch-action` absent »
   alors que la règle existait) — on grep avant d'attribuer.
2. « Fait » = test d'acceptation **réel** (comportement, pas présence d'une chaîne, pas regex sur
   le source) **et** branché dans une suite exécutée (`npm run test:js` a dû être créé pour les
   tests Node orphelins). Un test qui ne peut ni passer (fixture vide) ni échouer (compare le
   client à lui-même après le premier sondage) ne prouve rien : lire le HTML serveur par
   `request.get` **avant** tout sondage.
3. Les **preuves de mesure** (hauteurs, contrastes, budgets) se prennent sur l'arbre final ; une
   preuve antérieure à une correction contredit le plan sans que personne ne le voie. Les
   acceptations chiffrées (« divisée par deux », « −1/3 ») se **mesurent** avant d'être déclarées,
   et un écart mesuré est un chantier (tableau de bord 5 474 → 2 491 px, journal −37,8 %), pas un
   commentaire.
4. Agents parallèles : fichiers **disjoints listés**, CSS partagé par demandes croisées appliquées
   par le propriétaire ou l'orchestrateur (un doublon de règles est apparu quand les deux l'ont
   fait), Playwright **sérialisé** par `flock` sur un verrou unique et `--workers=1` pour les specs
   du carnet (un serveur par test, deux workers se disputent le port), jamais `pkill -f` large
   (un agent a tué le serveur d'un autre). Une coupure de quota API se reprend par message au
   même agent : le contexte survit, l'état des fichiers se relit sur disque avant de continuer.
5. Un harnais de test peut mentir par omission : `tests/ui_server.py` ne publiait aucun état
   d'actionneur (six lignes « non relues », donc ouvertes) et faisait échouer toute coupure
   (méthode absente, horloge non fiable). Trois défauts de harnais expliquaient l'absence
   historique de tests de coupure — les corriger est le seul chemin vers une mesure honnête.

## 2026-09-11 — Commiter par liste de fichiers quand des agents partagent l'index

**Contexte.** Pendant la revérification de la remédiation web/mobile/PWA, un agent d'archivage a
fait des `git mv` / `git rm` (donc **indexés**) pendant que l'orchestrateur commitait les lots
voisins par `git add <fichiers> && git commit`. Ces commits ont embarqué tout l'index : 30
déplacements et suppressions de docs sous un message `test(ui): …`, et les commits
intermédiaires avaient des liens cassés. Réparé avant publication (commits locaux) en
reconstruisant chaque commit par un index temporaire (`GIT_INDEX_FILE`, `read-tree`,
`update-index --cacheinfo`, `commit-tree`), sans toucher l'arbre de travail où un agent
travaillait encore.

**Règles.**
1. Dès que plusieurs agents travaillent dans le même arbre, commiter **uniquement** par
   `git commit -- <fichiers>` (pathspec), après `git diff --cached --quiet` ; jamais
   `git add … && git commit` seul, qui prend aussi ce qu'un autre a indexé.
2. Un agent ne doit pas indexer : les déplacements se font par `git mv` au moment du commit par
   l'orchestrateur, ou l'agent le signale explicitement dans son rapport.
3. Des fichiers apparus dans l'arbre sans venir d'aucun agent lancé (autre session, utilisateur)
   ne se commitent pas et ne se suppriment pas : on les signale.
4. Mesurer « comme l'audit » veut dire **mêmes conditions** (carnet, fenêtre, thème) : l'outil
   de mesure comparait un carnet rempli en 320 × 568 à un audit fait sur carnet vide en
   320 × 844, et le README en concluait « carnets différents ». Consigner les conditions dans
   chaque entrée (`carnet`, `viewport`) et refuser la comparaison quand elles diffèrent.
