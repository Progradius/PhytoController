# Carnet de cultures — lot F et passe « photos », bilan du 9 septembre 2026

> Archivé le 11/09/2026 — bilan clos, conservé comme preuve ; ne plus le mettre à jour.

Suite de la remédiation du lot UI 4 (`docs/archive/development/remediation-ui-cultures-lot-4-2026-09-09.md`,
section « Reliquats »). Point de départ `641a7ef`, arbre propre, 820 tests pytest, suite Playwright
284 réussites / 111 exclusions. Six commits, `9136e40..88a6a05` (le dernier étant ce bilan).

## Méthode

Un agent d'implémentation par lot sur des fichiers disjoints (F1 et F2 en parallèle, F1 seul
autorisé à jouer Playwright), relecture du diff par l'orchestrateur, rejeu de pytest complet, des
specs ciblées (un worker, un profil par invocation, chaque profil rejoué par l'orchestrateur) et
commit par liste explicite de fichiers. Puis revue indépendante en lecture seule du diff commité,
agent de correction (en worktree pour le lot F, dans l'arbre pour le lot photos, aucune suite
navigateur ne tournant alors), rejeu, commit. La conception du lot photos a été challengée par un
agent en lecture seule avant l'implémentation ; c'est ce challenge qui a repéré la CSP sans `blob:`.

Une autre session écrivait en parallèle dans le même arbre (`README.md`, `param/param.example.json`,
audit web mobile PWA du même jour) : ces fichiers ont été tenus hors de tous les commits.

## Lot F

| Exigence | Livraison | Commit |
| --- | --- | --- |
| F1 légende des courbes de solutions par mesure | `chart_sources(points, names, metric=None)` ne filtre que la légende ; variantes calculées sur tous les points, communes aux deux figures ; magasin `{"ph","ec","all"}` ; `all` sert au nommage des lignes sans mesure (renouvellements) du tableau équivalent — écart assumé par rapport à la consigne, qui aurait fait retomber la colonne « Cible ou capteur » sur l'identifiant technique (régression P1.1) | `9136e40` |
| F2 `webServer` de Playwright et `/tmp/phyto-ui-*` | `tests/ui/global_setup.js` nomme `os.tmpdir()/phyto-ui-webserver-<PID>`, imposé par `TMPDIR` ; Playwright 1.62.1 démarre le serveur **avant** `globalSetup`, donc `mkdir -p` en tête de la commande | `ce7022a` |
| Revue indépendante du lot F | 14 constats, 0 bloquant, 2 à corriger : le `globalTeardown` s'exécutait **avant** l'arrêt du serveur et n'était jamais atteint si le serveur mourait au démarrage ; sans `gracefulShutdown`, Playwright tue le groupe par `SIGKILL` et aucun `trap` ne s'exécute. Correctif : `trap 'rm -rf "$TMPDIR"' EXIT INT TERM HUP` dans la commande + `gracefulShutdown: SIGTERM 5 s`, `global_teardown.js` supprimé | `d6c101b` |

Preuves du lot F :

- mutation F1 : filtrage par mesure neutralisé, 4 tests tombent (`test_legende_par_mesure_sans_deplacer_les_reperes`, `test_repli_de_legende_ne_compte_que_les_sources_de_la_mesure`, `test_courbes_portent_leur_synthese_et_leurs_reperes`, `test_courbes_de_solutions_portent_synthese_et_legende`) ; le relecteur en comptait cinq, recompté à quatre par l'agent de correction ;
- spec « légende par source » verte sur `desktop-chromium`, `mobile-chromium`, `mobile-etroit`, `mobile-paysage` ;
- `/tmp/phyto-ui-*` : 196 avant et après `visual.spec.js`, 196 après un démarrage avorté du serveur (`PHYTO_TEST_PYTHON=/nonexistent`, exit 127), 196 avec `PHYTO_UI_BASE_URL` ; un répertoire orphelin vide `phyto-ui-webserver-*` créé par un démarrage avorté **avant** la correction a été observé puis retiré, ce qui confirme le constat C2.

Constat démenti : « le webServer démarre après `globalSetup` » (consigne) — l'ordre réel est
`clear output` → `plugin setup` (webServer) → `globalSetup`.

## Passe « photos »

| Exigence de l'audit du 8 septembre | Livraison | Commit |
| --- | --- | --- |
| Aperçu local avant envoi partout | posé par `register` sur tout champ fichier d'images (`data-culture-photo-preview`), indexé par champ, révoqué au changement, au `reset` et au `pagehide` non persistant ; version locale de la fiche retirée ; `grep -L PhytoCultureForms` ne rend que `culture_analysis.js` | `0e3593e`, `ca91af6` |
| Progression d'envoi réelle | `submitBinary` à signature inchangée, `sendUpload` en `XMLHttpRequest` avec gardes partagées `withGuards`, quatre formes de retour du contrat, `<progress>` indéterminée puis chiffrée dans l'`<output>`, pourcentage visible hors de la région atomique ; aucune reprise, file ni rejeu | idem |
| Reprise d'erreur | pas de `form.reset()` : légende, fichier et clé d'idempotence conservés ; barre retirée dans le `finally` des gardes | idem |
| Défaut trouvé en chemin | l'aperçu du lot UI 2 était **bloqué en production** par `img-src 'self' data:` (`naturalWidth == 0`, `complete == true`) ; `blob:` ajouté aux seules images, test de confinement dans `test_http_server.py` | `0e3593e` |

La page `/cultures/cycles` n'a pas de formulaire photo : les « trois formulaires » sont
l'observation de la fiche, la photo par entrée de la fiche (servie par `culture_cycles.js`) et
l'observation du journal.

Revue indépendante : 13 constats, 0 bloquant, 2 à corriger (région `role="status"` atomique
réannoncée à chaque pour cent ; aperçu indexé par formulaire), corrigés dans `ca91af6` avec, en
plus : exception synchrone de `xhr.open`/`send` convertie en refus réseau, délai partagé
`UPLOAD_TIMEOUT_MS`, refus d'un fichier non image, fermeture sur image non décodée, barre créée
à l'intérieur des gardes (`onStart`), `grid-column` de l'aperçu, paragraphe de `CLAUDE.md` replié.

Preuves : mutation « sans `Content-Type` explicite » → T1 tombe (415) ; mutation « barre créée
avant les gardes » → T7 tombe (2 barres au lieu d'une) ; spec photos 7 / 5 / 5 / 5 sur les quatre
profils Chromium (T3 et T7 bureau seulement) ; spec du lot 2 19 / 19.

Constat démenti : sous `page.route`, Chromium n'émet aucun événement `xhr.upload` — T4 assert
l'état indéterminé (`position === -1`), jamais un pourcentage. Le pourcentage réel et le flux
d'annonces d'un lecteur d'écran restent non observables par le banc (dit dans
`docs/archive/development/cultures-ui-photos.md`, « Limites assumées »).

## Validation de sortie

- pytest complet : 823 réussis (820 au départ, +3 : légende par mesure, légende vide, CSP) ;
- suite Playwright complète, un worker, cinq profils : 306 réussites, 124 exclusions, 0 échec
  (43,8 min ; 284 / 111 au départ, les 22 réussites et 13 exclusions de plus sont la spec photos) ;
- garde externe (`PHYTO_UI_BASE_URL=http://127.0.0.1:9`, toutes les specs cultures en une
  invocation) : 340 exclusions, zéro réussite, zéro échec ;
- `/tmp/phyto-ui-*` : 196 avant la suite complète, 196 après, zéro `phyto-ui-webserver-*` restant.

## Reliquats

- suppression des 196 `/tmp/phyto-ui-*` accumulés avant ces lots (16,5 Mio de bases jetables) :
  décision de l'utilisateur ;
- les pages appellent `status(form, …)` avant `submitBinary` : un second envoi refusé par `busy`
  efface la barre de l'envoi en vol (défaut des trois appelants, pas du socle) ;
- comparaison des cycles par âge du stade : décision produit, hors périmètre ;
- `docs/archive/development/remediation-ui-cultures-lot-4-2026-09-09.md` ligne P1.1 décrit encore
  `chart_sources` sous sa forme plate ; rapport daté, laissé tel quel.
