# Sections closes de `tasks/todo.md` (archivées le 11/09/2026)

> Archivé le 11/09/2026 — sections entièrement closes, déplacées telles quelles depuis
> [`tasks/todo.md`](../todo.md) et conservées comme preuve ; ne plus les mettre à jour. Seuls les
> chemins devenus faux ont été corrigés, et la case 3.3 de la journalisation est annotée (transfert).

Sections reprises, dans leur ordre d'origine : rattrapage du carnet de cultures et lots UI 1 et 2 ;
refonte de la journalisation ; remédiation du lot UI 4 du carnet ; données vivantes hors du
répertoire de travail Git.

---

# Suivi — rattrapage du carnet de cultures (plan `gestion_cultures_rattrapage_plan.md`)

Orchestration : agents Opus 5 par lot, vérification et commits par l'orchestrateur.
Baseline (8 septembre 2026, `58e97e6`) : 273 pytest, 92 Playwright, `git diff --check` propre.

## Phase 0 — préparation
- [x] Fixture Playwright partagée `tests/ui/culture_fixtures.js` (un spec par lot, sans conflit)
- [x] Commit du plan de rattrapage et de la préparation
- [x] Conception du schéma 4 (migrations lots D à H) avant toute évolution de schéma

## Phase 1 — lots sans évolution de schéma (parallèle)
- [x] Lot A — correction de relevés liés à une intervention ancienne (`2284074`)
- [x] Lot B — cycles longs, agrégation bornée en magasin, PWA bornée (`1cdf87d`)
- [x] Lot C — étapes rétrospectives d'un parcours repris (`e749c80`)
- [x] Vérification phase 1 : 281 pytest, 107 Playwright sur 5 profils, pyflakes, octets nuls

## Phase 2 — schéma 4 puis lots D à H
- [x] Migration schéma 4 (une seule, sauvegarde `.before-v4.sqlite3`) — `ca865d0`, 287 pytest
- [x] Pré-câblage partagé (scripts vides servis, motif service worker, liens de navigation)
- [x] Lot D — vérifications déclaratives corrigibles (`f4a00cc`)
- [x] Lot E — plages cibles pH/EC facultatives et historisées (`f51e619`)
- [x] Lot G — affectations d'équipements datées (`d40a243`)
- [x] Lot F — repères d'éclairage et état opérationnel (`8d7c9b5`)
- [x] Lot H — journal transversal et observations d'espace (`a7d2eab`)
- [x] Vérification phase 2 : 346 pytest, 135 Playwright sur 5 profils (fixture isolée par test, `d568ae2`)

## Phase 3 — clôture (lot I)
- [x] Suite pytest complète (357), Playwright complète 5 profils (135 réussis, 70 exclusions), pyflakes, octets nuls
- [x] Migration 1/2/3 → 4, interruption, refus d'écriture, schéma futur, corruption (`tests/test_culture_schema_v4.py`, `tests/test_culture_cloture.py`)
- [x] Sauvegarde/restauration ZIP sur copie isolée avec données anciennes et nouvelles
- [x] Documentation (guide, contrat API, sauvegarde, roadmap, plan de référence), CLAUDE.md = AGENTS.md
- [x] Tableau de traçabilité du plan (commit, tests, limites) par lot

## Lot UI 1 (audit UI/UX) — corrections après revue externe du 8 septembre 2026
- [x] A — « Vue globale » multi-cultures reste dans la rubrique courante ; libellé « Contexte de retour » sur
      éclairage/équipements ; test paramétré sur `cycles`/`light`/`equipment`
- [x] B — « Base SQLite seule (sans photos) » aussi sur l'accueil du carnet (`cultures.html`)
- [x] C — audit et bilan indexés dans `docs/index.md` ; convention `culture_navigation.html` + `culture_section`
      dans `CLAUDE.md`/`AGENTS.md` (diff vide)
- [x] D — fragment tolérant à `selected=None` / `culture_subjects=None`, testé
- [x] P1 « erreurs associées aux champs » rattaché au lot 2 dans le tableau des lots de l'audit
- [x] pytest complet : 363 verts ; revue indépendante Opus des corrections
- [x] Playwright carnet (lots B, C, D, F, H) relancé après corrections : 31 réussis, 24 exclusions de profil

## Lot UI 2 (audit UI/UX) — parcours quotidiens (plan `~/.claude/plans/lucky-seeking-thacker.md`)
Conception Opus challengée (10 objections) avant exécution ; agents Opus 5 par lot sur fichiers disjoints,
orchestrateur garant (contrats, pytest, Playwright, diffs, revue indépendante, commits). Référence : 363 pytest.
- [x] W1 backend — `CultureError(field, index)`, `error_response`, `allowed_actions`/`stage_options`/
      `first_stage`/`creation_stages`/`fiche_actions` purs (équivalence avec le gabarit sur 126 états),
      `reminder_buckets(rows, today, zone)`, `agenda` dans `_overview`, `reminders`/`media`/`actions` dans
      `_detail`, `event_id` dans `mutate`, prévalidation `_create` (`62e29e7`, 589 pytest)
- [x] W2 socle — `static/js/culture_forms.js` (register/submitJson/submitBinary/showError/clearErrors/status),
      4 points d'enregistrement, adoption minimale dans targets/light/equipment/journal (`6e73b67`)
- [x] W3 accueil « Aujourd'hui » (rappels actionnables), fiche (en-tête, triade, ancres, photos, bilan),
      observation + photo en un parcours, échec partiel (595 pytest ; specs cultures/C/D vertes)
- [x] W4 intentions visibles sur solutions, `?kind=…#saisie`, relevé depuis la fiche sans ressaisir la cible
      (`9365ee6`) — specs A/E/G et « panne réseau » lisent `.culture-form-errors` (correction orchestrateur)
- [x] Orchestrateur : `detail.stage_options` et contexte `creation` (premier stade, stades acceptés) exposés
      depuis le modèle pur, écart signalé par W3
- [x] W5 création « Je démarre » / « déjà en cours », frise, fixture Playwright mise à jour (`b2eca0f`,
      597 pytest) — `stage_options_full` exposé et spec du lot C ajustée par l'orchestrateur
- [x] W6a contrat API, guide « journée type », index, CLAUDE.md = AGENTS.md (`4030858`)
- [x] W6b spec Playwright `tests/ui/cultures_ui_lot_2.spec.js` (10 scénarios, 5 profils) ; bilan
      `docs/archive/development/cultures-ui-lot-2-2026-09-08.md`
- [x] Revue indépendante Opus du diff `2597e8f..HEAD` : 0 bloquant de sécurité, 8 importants (B1–B8) et
      2 écarts de la spec (rappel hors écran à 393 px, 409 dans l'output) — tous corrigés par un agent dédié,
      doc réalignée
- [x] Vérification de sortie : 601 pytest ; Playwright carnet un worker par profil : bureau 36, mobile 31,
      étroit 26, paysage 24, PWA 10, 0 échec ; 42 captures (7 états × 3 largeurs × 2 thèmes) dans le
      scratchpad de session ; `git diff --check`, CLAUDE.md = AGENTS.md, schéma 4 et `param/` intacts,
      aucun inline, aucun SQLite hors magasin, pyflakes propre
- Hors lot, à consigner : `.gitattributes`/`.gitignore` à la racine étaient déjà modifiés avant le lot et
  ne sont pas commités ici. Leçons : `tasks/lessons.md` (section du 8 septembre 2026, lot UI 2).

## Revue
- Organisation : un agent Opus par lot, sur des fichiers disjoints, avec un brief commun ; l'orchestrateur a
  vérifié chaque rendu (suite complète, diffs des fichiers partagés, invariants) avant de committer.
- Trois interventions de l'orchestrateur hors délégation : raccord des durées dans la comparaison des cycles,
  remplacement de deux BOM littéraux par <code>"&#92;ufeff"</code>, et isolation du carnet Playwright **par test** (deux specs
  d'un même worker se disputaient l'espace 2, exclusif).
- Erreurs corrigées en cours de route et consignées dans `tasks/lessons.md` : écrasement de ce fichier par `Write`,
  trailers d'attribution refusés dans les messages de commit.
- Limites résiduelles ouvertes (voir `docs/risk-register.md` R-CULT-01 à 03 et « Limites connues » du contrat
  API) : table `requests` jamais purgée ; plafonds ZIP/médias ; `_solution_data` et `measures` non bornés ;
  aucune capture d'écran des quatre nouvelles pages ; aucune qualification sur le Pi.

---

# TODO — Refonte de la journalisation (plan `tasks/logging_refonte_plan.md`)

*Note d'archivage* : le plan `tasks/logging_refonte_plan.md`, livré en `fb26cd2` et doublon de cette
section, a été supprimé le 11/09/2026 ; il reste récupérable par
`git show fb26cd2:"RPi Version/tasks/logging_refonte_plan.md"`. Les restes en prose de la revue
ci-dessous sont soldés ainsi : journald plafonné et constaté (case 3.3), anciens `phyto.log.N` sortis
de Git (P6, `git ls-files logs` vide au 11/09/2026), mot de passe InfluxDB transféré (case 3.3) ;
`~/app.log` n'a pas été relevé.

## P3 — Sécurité
- [x] 3.1 Credentials Influx hors de l'URL (`requests.post(params=…)`), messages d'erreur limités à
      `host:port/db` + classe d'exception
- [x] 3.2 `utils/log_dedup.py` (`StateLogger`) appliqué à Influx, capteurs, `config.load()`, `SensorStats`
- [x] 3.3 *(hors code : à faire sur le Pi — `journalctl --vacuum-size=200M`, `journald.conf`,
      changement du mot de passe InfluxDB)* — **journald fait** : `SystemMaxUse=200M` actif et journald
      à 141,3 Mio, sous le plafond (relevé `docs/archive/operations/production-baseline-2026-08-25.md`).
      **Mot de passe InfluxDB non changé : transféré** à la roadmap (lot 4, « Faire tourner les
      identifiants ») et au risque R-CONF-02, où la rotation est suivie avec la sortie des secrets

## P1 — Cœur de logging
- [x] 1.1 `utils/logger.py` supprimé + `CLAUDE.md` mis à jour (nouvelle section « Logging »)
- [x] 1.2 `debug()`/`critical()`/`exception()`, remap des niveaux (`action`/`clock` → DEBUG),
      filtre unique console+fichier, section `Log_Settings` (Pydantic + `param.json`),
      priorité `PHYTO_LOG_LEVEL` > `param.json` > INFO, application au boot et sur POST `/conf`
- [x] 1.3 Format `%(asctime)s [%(levelname)s] [%(name)s] %(message)s`, paramètre `name=`,
      `box()`/`title()` sur une seule ligne côté fichier et soumis au filtre, horodatage console en
      mode rich, plus d'émojis dans le fichier, messages uniformisés en français

## P2 — Transitions plutôt qu'états
- [x] 2.1 `Component.set_state()` et `Motor._set_pin()` ne journalisent qu'un changement réel
- [x] 2.2 Boucles périodiques : ticks en DEBUG, évènements en INFO (cyclic/daily/heater/motor/influx/http)
- [x] 2.3 Capteurs : état actif/inactif journalisé une fois à l'init, lectures en DEBUG,
      échecs dédupliqués

## P4 — Couverture
- [x] 4.1 PuppetMaster : traceback complète, tâches nommées + références conservées,
      `add_done_callback` qui signale toute terminaison
- [x] 4.2 `main.py` : plus aucun `print()`, `traceback.print_exc()` → `exception()`
- [x] 4.3 `except: pass` supprimés (dailytimer → ERROR, stats → WARNING dédupliqué, VL53 → DEBUG)
- [x] 4.4 `config.load()/save()`, `SensorStats._dump()`, GPIO `(RuntimeError, ValueError, OSError)`,
      I2C `PermissionError/OSError`, HTTP (headers, `IncompleteReadError`, 404, `int()/float()`),
      code retour de `reboot`/`shutdown`, `reload_sensor_handler()` protégé à l'import

## P5 — `/console` sans PTY
- [x] `utils/log_stream.py` : handler mémoire (deque 1000) + queues SSE du processus courant
- [x] PTY / second `main.py` supprimés, `wait_closed()`, désabonnement idempotent, découpage SSE
- [x] xterm.js vendoré dans `network/web/static/{js,css}`

## P6 — Rétention
- [x] `TimedRotatingFileHandler` (minuit) + archives gzip + `retention_days`
- [x] Anciens `phyto.log.N` sortis de git, supprimés du Pi, `logs/` ajouté au `.gitignore`
- [x] **Rotation quotidienne vérifiée en conditions réelles le 26/08/2026 à 00:18.**
      `logs/phyto.log.2026-08-25.gz` (4,6 Kio) contient l'intégralité de la journée,
      `logs/phyto.log` repart à la ligne 1, aucune erreur de rotation dans le fichier ni dans
      `journalctl -u phyto`.
      **Enseignement** : à 00:17, aucune archive n'existait encore. `TimedRotatingFileHandler`
      ne bascule pas sur une minuterie mais sur la **première écriture après minuit** ; les
      boucles journalisant leurs ticks en DEBUG, un contrôleur calme n'écrit rien pendant des
      dizaines de minutes. La bascule s'est produite immédiatement à l'émission d'une ligne
      provoquée. Ne pas diagnostiquer une panne de rotation sur la seule absence d'archive.

---

## Revue

**Vérifications effectuées** (pas de suite de tests dans ce dépôt — scripts jetables sous
`/tmp/claude-1000/phyto/`, venv avec pydantic/jinja2 + stubs `RPi.GPIO`/`smbus2`) :

1. Façade de log : DEBUG filtré en niveau INFO (console **et** fichier), `box()` écrit
   `ligne1 | ligne2` sur une seule ligne, `StateLogger` produit exactement 2 lignes pour 5 échecs
   suivis d'un rétablissement, `apply_log_settings()` ajuste niveau et `backupCount` à chaud,
   `PHYTO_LOG_LEVEL` reste prioritaire sur `param.json`.
2. Rotation : `doRollover()` produit bien `phyto.log.<date>.gz` relisible.
3. `param.json` : round-trip `load()`/`save()` conserve les booléens `"enabled"/"disabled"` et la
   section `Log_Settings` ; section absente → défauts INFO/14 ; JSON corrompu → 1 seule ERREUR.
4. GPIO (stubs) : `Component` actif-LOW inchangé (`set_state(1)` → LOW), 3 appels dont un no-op →
   2 lignes ; `Motor` actif-HIGH avec exactement une pin HIGH pour la vitesse 2, tout LOW en 0.
5. `temp_control` en mode hiver : 1 ligne INFO à la transition, silence sur les ticks suivants,
   1 ligne à la bascule « sécurité haute T ».
6. PuppetMaster : une tâche qui `return` → ERREUR « terminée alors qu'elle ne devrait jamais
   s'arrêter », une tâche qui lève → ERREUR + traceback complète.
7. Flux SSE : message émis dans le processus courant reçu par la queue et présent dans l'historique.

**Reste à faire sur le Pi** (P3.3 / P6, hors dépôt) : vacuum de journald, `SystemMaxUse=200M`,
changement du mot de passe InfluxDB (à reporter dans `param.json` local), suppression des vieux
`phyto.log.N` et de `~/app.log`.

**Corrections issues de l'observation en production (25/08/2026, Pi)** :
- La console web affichait `\r\n` en clair (double échappement dans le template) et débordait sur
  mobile (grille 80 colonnes de xterm.js) : remplacée par un afficheur natif HTML/CSS, coloré par
  niveau, sans dépendance JS (xterm.js vendoré supprimé).
- Un POST `/conf` instanciait **deux** `SensorController` (donc deux `/dev/i2c-1` jamais refermés),
  et un troisième était créé à l'import d'`influx_handler` : `reload_sensor_handler()` accepte
  désormais un handler existant, l'init à l'import est supprimée et PuppetMaster partage l'instance
  unique. Un boot = une ouverture du bus.
- Le formulaire postant tous les champs, « Configuration sauvegardée » listait 7 modifications pour
  un seul changement réel : seuls les écarts sont désormais journalisés.

**Point d'attention** : `logs/phyto.log.1` … `.5` sont **suivis par git** (héritage de l'ancienne
rotation). Ils ne contiennent pas de credentials (vérifié), mais mériteraient un
`git rm --cached logs/phyto.log*` + une entrée `.gitignore` — non fait, hors périmètre du plan.

---

## Remédiation du lot UI 4 du carnet (9 septembre 2026)

Plan : `docs/archive/development/remediation-ui-cultures-lot-4-2026-09-09.md` (état des lieux, R1.1 à
R4.4, lots A à E). Aucun P0. Déroulé le 9 septembre 2026, commits `591520f..fc2a222`.

- [x] Lot A — explorateur, galerie, CSS (R1.1, R1.3, R1.4, R1.6, R2.4, R3.2, R3.6) — `2ff0180`
- [x] Lot B — magasin cycles/solutions, pagination, banc, mutation « avant » (R1.2, R2.1–R2.3, R3.7, R4.1) — `1dc848d`
- [x] Lot C — légende, synthèse, lien de contexte, archives (R1.5, R3.1, R3.3, R3.5) — `932b2fc`
- [x] Lot D — recherche et filtres rapides du journal (R3.4) — `c7ddf8c`
- [x] Lot E — spec du lot 4, fixture `/tmp`, documentation (R4.2–R4.4) — `d78f805`
- [x] Banc rejoué sur le Pi, rapport du lot 4 mis à jour — `017605b` (1 721 ms → 721 ms à 4 cultures, même semis)
- [x] Revue indépendante du diff (3 P1, 9 P2) et corrections en worktree — `fc2a222`
- [x] Validation de sortie : 820 pytest ; suite Playwright complète 284 / 111 exclusions / 0 échec ;
      specs du lot 4 11/11 sur quatre profils après fusion ; garde externe 61 exclusions

Revue : bilan et reliquats dans la section finale du plan. Reliquats hors lot à arbitrer :
aperçu photo avant envoi, progression d'envoi, comparaison par âge du stade, légende des
solutions calculée sur tous les points d'une figure, `webServer` de Playwright encore
producteur de `/tmp/phyto-ui-*`.

---

# Données vivantes hors du répertoire de travail Git (incident du 08/09/2026)

Cause établie : un `git checkout master` lancé à la main sur le Pi a matérialisé le `param.json`
du commit `e93644a` par-dessus la configuration vivante — la branche déployée ne suivait pas le
fichier, la révision visée le suivait encore. 26 h 21 sans Éclairage 2 ni cycle 2, 6 h
d'Éclairage 1 perdues, chauffage réactivé à tort 22 min.

- [x] `utils/runtime_paths.py` : `data_dir()` / `data_file()` purs et mémoïsés, `ensure_data_dir()`
      qui échoue bruyamment, défaut inchangé sur `param/`
- [x] `tests/test_runtime_paths.py` : défaut, surcharge, variable vide, chemin relatif, mémoïsation,
      absence de création, mode 0700, échec sans repli
- [x] Huit ancrages reroutés : `param/config.py`, `param/equipment_metadata.py`,
      `model/SensorStats.py`, `utils/csrf.py`, `utils/state_store.py`, `utils/operator_history.py`,
      `utils/culture_store.py`, `utils/pretty_console.py`
- [x] `main.py` : `ensure_data_dir()` avant le verrou d'instance et tout accès fichier
- [x] `scripts/deploy.sh` : répertoire lu dans l'unité systemd (`systemctl show`), gardes et
      validation Pydantic sur le chemin résolu
- [x] `deploy/phyto.service` : `Environment=PHYTO_DATA_DIR=/home/progradius/phyto-data`
- [x] `tests/test_deploy_safety.py` : sonde en interpréteur neuf, aucun des 8 chemins dans le dépôt
- [x] Documentation : `docs/operations/migration-donnees-vivantes.md`, `README.md`,
      `docs/operations/install-raspberry-pi.md`, miroirs `CLAUDE.md` / `AGENTS.md`
- [x] Migration sur le Pi le 10/09/2026 (fenêtre d'arrêt de ~2 min, sauvegarde
      `~/phyto-backups/20260910-075633-avant-migration`)
- [x] Preuve de non-régression : checkout vers `e93644a` dans un clone jetable — le commit
      matérialise bien `param.json` (3106 o, la taille exacte du fichier écrasé le 08/09) dans
      l'arbre de travail, et l'empreinte SHA-256 de la configuration vivante est inchangée

## Revue

`python3 -m pytest` : 835 passed. `diff -u CLAUDE.md AGENTS.md` vide.
Le défaut `param/` est inchangé, donc développement, tests et Docker ne bougent pas ; seul le Pi,
dont l'unité pose `PHYTO_DATA_DIR`, sort du répertoire de travail Git.
Point à ne jamais relâcher : aucun repli silencieux vers `param/` dans `ensure_data_dir()`, sans
quoi le processus se remettrait à écrire dans le dépôt sans que personne ne le voie.

### Sortie de migration (10/09/2026)

`~/phyto-data` porte les 8 entrées vivantes ; `param/` ne contient plus que du versionné et
`git status` du dépôt est vide. Les descripteurs ouverts du processus pointent bien vers
`~/phyto-data` (les deux SQLite), `runtime_state.json` et `sensor_stats.json` y sont réécrits,
et `.csrf_token` a gardé son horodatage du 25/08 — il a été relu, pas régénéré, donc aucune page
ouverte n'a été invalidée.

Configuration : aucun écart avec la référence du 03/09. GPIO inchangés, chauffage désactivé,
`max_speed` à 2. Intégrité SQLite `ok` sur les deux bases (21 et 5 tables). `/health/ready`
`{"ready": true}`, et `/`, `/history`, `/alarms`, `/cultures`, `/conf`, `/health/live` en 200.
