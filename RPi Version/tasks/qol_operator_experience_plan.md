# Plan — Expérience opérateur « maintenant, pourquoi, ensuite » (v2, après revue contradictoire)

## Objectif et livraison

Transformer l'interface locale en poste de conduite explicable : état réel et demandé des équipements,
cause, durée, prochaine transition, alarmes actionnables, tendances locales, configuration guidée et
interventions temporaires sûres.

La réalisation se fait sur `feature/qol-operator-experience`, en quatre jalons déployables :

1. état explicable, heure fiable et équipements nommés ;
2. centre d'alarmes et historique local ;
3. configuration guidée et formulaires sans perte ;
4. overrides force-OFF, console bornée et retour reboot/extinction.

Invariants : aucune commande GPIO depuis HTTP, `Component` actif-BAS, moteur actif-HAUT, jamais de
`GPIO.cleanup()`, activation protégée par `energized()`, politique thermique pure, watchdog gouverné
par la santé du contrôle seulement, `ConfigStore` seul écrivain de `param.json`, aucun secret dans
HTML/logs/historique, interface LAN sans authentification, CSP stricte et assets locaux.

**Règle de déploiement** : une livraison ne modifie jamais à la fois une condition de commutation et le
watchdog qui la surveille. Le rebranchement du watchdog (jalon 1, étape santé) se déploie d'abord avec
`PHYTO_HW_WATCHDOG=0` pendant 48 h, `snapshot()` comparé avant/après, puis réarmement.

## Décisions d'arbitrage (opérateur, 2026-08-26)

- **Boot sans NTP** : suspension **bornée** (pas d'OFF illimité) — voir « Heure fiable ».
- **Périmètre** : plan complet conservé (Canvas, mode Simple, 10 alarmes, 72 h), corrigé des bloquants.
- **InfluxDB** : opérationnel et consulté ; l'historique local est un complément autonome, pas un
  remplacement.
- **Overrides** : **force OFF uniquement**. Aucun force ON, sur aucune sortie — la matrice de priorité
  à 5 niveaux et la reprise d'un ON au reboot disparaissent du périmètre.

## Corrections structurantes issues de la revue

1. La prémisse « NTP bloquant au boot » était fausse : `set_ntp_time()` (`function.py:62`) journalise le
   résultat et continue. Le moniteur asynchrone est un **ajout**, pas un remplacement ; son seul vrai
   correctif boot est un `timeout=` sur le subprocess.
2. « Aucun rattrapage » ne s'applique **pas** aux timers journaliers : le daily est un asservissement de
   niveau (l'état voulu est une fonction de l'heure), il reprend immédiatement en pleine plage. Le seul
   rattrapage indésirable réel est celui des **impulsions** du cyclique en mode journalier
   (`cyclic_timer_handler.py:140-146`).
3. `Equipment_Metadata` sort de `param.json` : fichier séparé `param/equipment_metadata.json`.
4. La persistance des overrides est spécifiée (`state_store`, `force=True` + mode strict) et l'expiration
   utilise **deux horloges** (epoch + monotonic, échue au premier des deux).
5. **Fuite de secret à corriger avant toute console téléchargeable** : `network/network_handler.py:80-81`
   logge le mot de passe Wi-Fi via `CalledProcessError.__str__` (argv complet de `nmcli`). Ne logger que
   `returncode` + classe. Correctif préalable, hors jalon, à livrer en premier.

## Interfaces et stockage

### Configuration (`param.json`, via `ConfigStore` uniquement)

- Ajouter `Day_Night_Settings` (`start_hour`, `start_minute`, `stop_hour`, `stop_minute`, **`source`** :
  `"dailytimer1"` | `"custom"`), référence globale du climat et des cycles séquentiels. La plage est
  `[début, fin)`. Le champ `source` rend l'héritage **explicite et persistant** : avec
  `source="dailytimer1"`, les horaires suivent DailyTimer 1 en continu (pas de copie gelée) — c'est la
  parade au piège `to_json()` qui matérialiserait un défaut et le gèlerait à la première sauvegarde
  d'une autre section. L'IHM affiche l'écart quand jour/nuit ≠ horaires d'éclairage.
- La règle `[début, fin)` est aujourd'hui **dupliquée trois fois** (`model/DailyTimer.py:141`,
  `cyclic_timer_handler.py:228`, `climate_control.py:109`) : extraire un helper unique **avant** de
  changer la borne, sinon « le jour » diverge entre lumière, cyclique et climat. Sémantique
  `start == stop` : plage vide (jamais actif), documentée dans l'IHM.

### Métadonnées équipements (`param/equipment_metadata.json`, fichier séparé)

Indexé par identifiant technique stable (liste blanche : `daily_1`, `daily_2`, `cyclic_1`, `cyclic_2`,
`motor`, `heater`). Une entrée porte `display_name`, `usage_type`, `zone`, `icon`, `wiring_note`,
`dashboard_visible`, `out_of_service` (annotation d'un défaut matériel connu — ex. vitesses moteur
1 et 3 HS côté puissance : le registre n'alarme pas un écart demandé/relu documenté ici).

- Fichier **séparé de `param.json`** : renommer une lampe ne doit ni réécrire le fichier de contrôle
  critique (secrets inclus), ni consommer `param.json.bak`, ni invalider le cache `(mtime_ns, size)` de
  toutes les boucles, ni disparaître au premier passage d'`initial_setup_tool.py`.
- Booléens JSON **natifs** (aucun alias legacy `enabled`/`disabled` : ni l'ESP32 ni l'outil de setup ne
  lisent ce fichier, la contrainte n'existe pas). Écriture via `write_text_atomic()`, magasin ~60 lignes
  calqué sur `utils/state_store.py`. Absence → catalogue actuel par défaut. La visibilité n'a aucun
  effet sur le contrôle. Catalogue d'icônes local uniquement ; aucun upload ou asset externe.

### État opérationnel

Créer un registre en mémoire alimenté par les boucles métier et consommé par HTTP, généralisant le
patron existant `_snapshot`/`get_climate_snapshot()` (`climate_control.py:53-82`). Chaque actionneur
publie identifiant, métadonnées, état/vitesse **demandé**, mode, motif, durée monotone et prochaines
transitions typées (`clock`, `condition`, `safety_deadline`, `none`).

Garde-fous non négociables :

- Le registre ne stocke **jamais** l'état « réel » : `Component.get_state()`/`get_motor_speed()` lisent
  la broche à la demande côté lecteur HTTP (accès `/dev/gpiomem`, sub-µs). Un réel figé est un mensonge.
- Les callbacks `safe_state` du superviseur publient eux-mêmes (une relance repositionne l'état sans
  passer par la boucle) ; chaque entrée est datée en `monotonic` et périmée côté lecteur
  (> 2 × période → « inconnu »).
- Durées en `time.monotonic()` exclusivement. Écriture depuis l'event loop, par remplacement de dict.
- **Interdit à la régulation de lire le registre pour décider** (commentaire dans le module) : c'est de
  l'observabilité, pas une seconde vérité.

Contenus : timers (phase, suspension, motif, fin de phase, prochain déclenchement), moteur (mode,
vitesse avant dwell, vitesse effective relue, dwell restant, budgets hiver, repli capteur), chauffage
(motif, seuil d'arrêt, durée ON, limite continue, cooldown).

### Heure fiable

Ajouter un moniteur asynchrone de synchronisation, à trois états :

- `synchronized` : `NTPSynchronized=yes` observé (vérification par `stat` de
  `/run/systemd/timesync/synchronized` ou `asyncio.create_subprocess_exec` avec timeout — **jamais**
  `subprocess.run` dans une coroutine : le loop bloqué cesse de caresser le watchdog) ;
- `plausible` : horloge ≥ dernier horodatage connu (timesyncd restaure `/var/lib/systemd/timesync/clock`
  au boot : l'heure est ancienne, pas absurde) ;
- `unknown` : rien de tout ça.

Comportement : suspension des minuteries journalières **uniquement en `unknown`, et bornée à
15 minutes** (constante dédiée) ; au-delà, reprise en `plausible` avec **alarme persistante « heure non
fiable »** non masquable par acquittement. Les cycles séquentiels ne dépendent de l'horloge murale que
pour le choix jour/nuit : ils tournent en **paramètres nuit** dès le boot, jamais OFF. Le climat utilise
les consignes de nuit tant que non `synchronized`. Après une première validation, une perte NTP
temporaire est signalée sans suspension. Un reboot remet la confiance à zéro (mais la suspension reste
bornée). À la synchronisation, ignorer les **impulsions** journalières déjà passées (voir jalon 1).

### Santé, alarmes et historique

- Ajouter domaine et `gates_watchdog` aux tâches. Timers, climat et acquisition capteur gouvernent le
  watchdog ; HTTP, Influx, historique, réseau, temps et disque sont auxiliaires/maintenance. Ce split
  corrige un enchaînement réel : un Influx en crash-loop atteint le back-off max 300 s =
  `MAX_SILENCE_SECONDS` → `is_healthy()` faux → plus de caresse → reboot machine pour une panne de base
  de données.
  * Vérifier au démarrage que l'ensemble `gates_watchdog` est **non vide** et journaliser sa composition
    (`all([])` vaut True — exactement la caresse aveugle que `watchdog.py` interdit).
  * Donner aux auxiliaires un `max_silence` large ou `None`, sinon ils s'affichent « malsains » en
    permanence pour rien.
- Conserver `is_healthy()` pour `/status`, `/api/v1/state` **et `/health/ready`** (le health-check de
  `deploy.sh` doit continuer de voir un HTTP mort) ; ajouter `control_healthy()` et brancher le watchdog
  dessus.
- Créer des alarmes idempotentes avec gravité, catégorie, début, durée, résolution, conséquence,
  conseil, lien interne et acquittement séparé. L'acquittement marque « vue » sans masquer la condition.
  L'alias opérateur est facultatif, mémorisé par navigateur, non authentifié, **borné à 32 caractères
  charset `[A-Za-z0-9 ._-]`, jamais interpolé dans un log** (il partirait dans le SSE et le
  téléchargement console), requêtes SQLite paramétrées uniquement.
- Persister dans `param/operator_history.sqlite3` (SQLite stdlib, WAL, `user_version`) : échantillons
  d'une minute sur 72 h, événements de sorties/config/alarme/override/action système, alarmes résolues
  sur 30 jours avec plafond de 2 000 occurrences. Conditions d'entrée non négociables :
  * **un seul thread propriétaire** de la connexion, tous les accès (lecture *et* écriture) via
    `run_in_executor` — patron identique à `SensorController` (`ThreadPoolExecutor(max_workers=1)`).
    Le serveur HTTP et la régulation partagent le même event loop : un commit ou un `SELECT` à froid
    depuis le loop bloque les caresses watchdog. « La régulation ne lit jamais SQLite » ne suffit pas —
    c'est le thread qui compte ;
  * `PRAGMA synchronous=NORMAL`, `journal_mode=WAL` posé à la création, `auto_vacuum=NONE` décidé à la
    création (fichier plafonné à son high-water mark, quelques Mo — accepté), **un commit par
    échantillon**, jamais par mesure. Perte des derniers commits sur coupure secteur : **acceptée**
    (c'est de l'historique) ;
  * au boot, `PRAGMA quick_check` (hors event loop, `main.py` est séquentiel) ; échec → renommage en
    `.corrupt`, recréation vide, alarme auxiliaire. **Jamais d'échec de boot pour de l'historique** ;
  * `.gitignore` : la base **et** ses annexes `-wal`/`-shm` (et corriger au passage
    `param/sensor_stats.json`, tracké par erreur alors qu'écrit à l'exécution — `deploy.sh` fait
    `git stash` + pull).
- Échantillonnage depuis le snapshot capteurs existant (rafraîchi toutes les 10 s) et les relectures
  GPIO — aucune lecture matérielle supplémentaire. Deux règles d'honnêteté :
  * n'écrire une valeur capteur que si `status == "ok"`, sinon `NULL` (`last_good_value` peut avoir
    30 min : l'historiser fabrique une ligne plate mensongère) ;
  * le moteur porte un champ d'état `ok`/`unreadable`/`conflict` — `get_motor_speed()` renvoie 0 pour
    l'arrêt, l'erreur GPIO **et** l'anomalie multi-relais, trois choses différentes.
  Un échantillon 1/min est un point instantané, pas une moyenne — ne pas le présenter autrement.
- Une panne de l'historique déclenche une alarme auxiliaire sans affecter le contrôle.

### API

Faire évoluer `/api/v1/state` de façon additive en conservant les champs existants et en ajoutant
`equipment`, `actuators`, `time`, les domaines de santé, le résumé des alarmes, les overrides et la
disponibilité de l'historique. Ajouter `control_healthy` et l'état temporel à `/status`.

Nouvelles routes :

- `GET /alarms`, `GET /api/v1/alarms`, `POST /actions/alarms/ack` ;
- `GET /api/v1/history?hours=24|48|72`, 720 **buckets** maximum. Downsampling **en SQL**
  (`GROUP BY ts/bucket`, une passe en C — jamais en Python sur le loop) ; chaque bucket porte
  `bucket_start_ts` explicite (sinon un trou est indiscernable d'un décalage) et `min/avg/max` (une
  moyenne seule écrase les pointes que `min_at`/`max_at` promettent) ; actionneurs : **taux de marche**
  (fraction ON du bucket) ;
- `POST /api/v1/config/preview`, sans écriture — garde d'in-flight (un preview à la fois par processus)
  + intervalle minimum (validation Pydantic complète sur un Pi, rate illimité sinon), réutilisation de
  `_validate_form_shape`, aucun champ sensible en réponse, aucun log du corps, jeton CSRF en en-tête
  `X-CSRF-Token` pour un corps JSON (le middleware consomme `request.post()`) ;
- `POST /actions/overrides/create` et `/actions/overrides/cancel` — cibles restreintes à la liste
  blanche d'identifiants, jamais un numéro de broche ni un nom libre.

Toute mutation reste POST + CSRF/Origin ; aucun effet persistant derrière GET. Lucidité sur le modèle de
menace : le jeton CSRF est servi à tout client du LAN et l'`Origin` n'est vérifié que s'il est présent —
c'est le niveau déjà accepté pour reboot/poweroff, ne pas le décrire comme davantage.

## Jalon 1 — Maintenant, pourquoi, ensuite

1. Introduire heure fiable (trois états, suspension bornée), planning jour/nuit (`source` explicite),
   registre opérationnel et santé par domaine (watchdog réarmé après la fenêtre d'observation 48 h).
2. Rendre les ordonnanceurs explicites, en distinguant **deux familles** :
   * **asservissements de niveau** (daily 1 & 2, jour/nuit) : l'état voulu est une fonction de l'heure —
     reprise **immédiate** en pleine plage après reboot ou relance de tâche. Seul changement : borne
     `[début, fin)` via le helper unique ;
   * **ordonnanceurs d'impulsions** (cyclique en mode journalier) : prochain déclenchement strictement
     futur, **aucun rattrapage des impulsions passées** (c'est le bug réel actuel : démarrage à 20 h avec
     `first_trigger_hour=8` → toutes les impulsions manquées tirées bout à bout).
   Séquentiels en paramètres nuit (jamais OFF) avant heure fiable ; attentes interruptibles avec
   heartbeat (`request_reload` garde son saut délibéré de l'état sûr — verrouillé par `CLAUDE.md`).
3. Publier les détails climatiques (vitesse voulue/effective, dwell, budgets, durée chauffage).
4. Ajouter les métadonnées (fichier séparé) et leur configuration.
5. Refaire les cartes : nom, état, cause, depuis, ensuite ; moteur et chauffage détaillés. Un écart
   demandé/relu couvert par `out_of_service` s'affiche comme défaut matériel connu, pas comme anomalie.
6. Corriger le rafraîchissement de `state.timers` dans `dashboard.js`.
7. Afficher les dates `min_at` et `max_at`.

Critère : chaque état réel est explicable depuis le tableau de bord ; aucune minuterie journalière ne
commute en état `unknown` avant l'échéance de suspension ; une lampe en pleine plage se rallume
immédiatement après reboot.

## Jalon 2 — Alarmes et tendances

0. **Préalable livré séparément** : correctif de la fuite du mot de passe Wi-Fi dans
   `network_handler.py` (returncode + classe seulement).
1. Introduire SQLite (conditions ci-dessus), gestionnaire d'alarmes et enregistreur auxiliaire (dans le
   thread SQLite dédié).
2. Couvrir repli capteur, GPIO non suivi, contrôle malsain, deux relances/10 min, Influx, NTP/heure non
   fiable, réseau, disque sous 10 % (critique 5 %, résolution 12/7 %), restauration `.bak` et historique
   indisponible.
3. Ajouter bannière globale, résumé dashboard et page `/alarms` avec filtres et acquittement.
4. Échantillonner toutes les mesures actives sans lecture matérielle supplémentaire (règles
   `status=="ok"` et état moteur ci-dessus).
5. Afficher 24 h par défaut, choix 24/48/72 h, trous réels non interpolés, bandes min/avg/max, bandes de
   consigne/actionneurs (taux de marche) et marqueurs d'alarme/configuration, avec Canvas natif.

Critère : une panne de contrôle est distincte d'une dégradation auxiliaire et les 72 dernières heures
restent explicables sans InfluxDB (qui reste la référence analytique — l'historique local est un
complément autonome).

## Jalon 3 — Configuration guidée

Ordre interne imposé : **3a d'abord** (la douleur réelle), puis preview, puis mode Simple (qui dépend
de la preview).

- **3a. Formulaire sans perte** : sur 422, re-rendre la **saisie** (multidict du POST) et non la config
  enregistrée (défaut actuel de `_configuration_post` : toute la section est perdue), secrets vidés,
  erreurs sous les champs (`aria-describedby`, focus sur la première), messages Pydantic humanisés
  (dictionnaire ~15 entrées type → phrase française), contraintes croisées reliées.
- **3b. Registre central des champs** : **étendre `SECTION_FIELDS` existant** (déjà l'inverse exact du
  registre visé, déjà utilisé pour parsing et allow-list) — pas de composant autonome redondant.
- **3c. Prévisualisation serveur** utilisant les mêmes parseurs, le candidat Pydantic complet et les
  formules de politique ; aucune formule thermique dupliquée en JavaScript. La preview doit rendre
  visible le seuil de ventilation **effectif** (`vent_threshold` reconstruit peut dépasser le max
  affiché de hystérésis + zone morte : sans preview, le mode Simple ment de ~2 °C en silence).
- **3d. Mode Simple** : sélecteur Simple/Avancé, simple par défaut, choix mémorisé en `localStorage`.
  Le mode simple expose planning jour/nuit, min/max jour/nuit, humidité max, intensité
  douce/normale/forte, été/hiver, chauffage et plannings. Profil proposé : hystérésis 1 °C, zone morte
  1 °C, palier 1 °C, relâchement 0,5 °C, dwell 120 s, plancher 5 °C, repli 0, marge hiver 2 °C, budgets
  8/6 min/h, vitesse minimale 0, vitesse hiver 1 ; douce mappe max/renouvellement à 2/2, normale 3/3,
  forte 4/4 ; été mappe `auto`, hiver `winter`. **Ces valeurs sont une proposition : validation
  explicite par l'opérateur avant implémentation** (elles écrivent de vrais paramètres thermiques). Un
  mode manuel existant exige un choix explicite. Le mode Simple ne se livre qu'avec la preview active.
- Détecter uniquement les différences réelles, proposer annulation et `beforeunload`.
- Après succès, afficher champs modifiés, heure et mode d'application via flash opaque côté serveur.

Critère : aucune erreur ne force à ressaisir la section entière, aucun secret ne réapparaît et le mode
simple a un effet déterministe prévisualisé (seuil effectif inclus).

## Jalon 4 — Overrides force-OFF, console et système

### Overrides (force OFF uniquement)

Entrée de politique persistée, jamais accès GPIO. Un override ne peut que **couper** : chauffage,
moteur, sorties génériques. Aucun force ON, sur aucune cible.

- Insertion dans la politique : champ(s) ajoutés à **`ClimateInputs`** (dataclass gelée — pas à
  `ClimateSettings`, un override n'est pas de la configuration), expiration évaluée **dans** `decide()`
  à partir de `inputs.now_mono`/`now_epoch` — aucun `monotonic()` ajouté dans `climate_policy`, la
  pureté et le rejeu sont préservés.
- Chauffage : champ **distinct `heater_forced_off`** — ne pas détourner `heater_enabled`, dont dépend
  `vent_threshold` (le détourner décalerait silencieusement le seuil de ventilation pendant 24 h).
- Priorité conservée : protections thermiques et repli capteur priment. `sensor_fallback_speed` ou
  `STATE_OVERHEAT` peuvent écraser un force OFF moteur ; l'IHM affiche alors « override **suspendu** par
  REPLI_CAPTEUR / sécurité haute », jamais « actif ».
- Timers : à chaque create/cancel visant `daily_x`/`cyclic_x`, `supervisor.request_reload(job)` (sinon
  latence jusqu'à 10 jours) ; l'override est lu en tête de boucle ; `energized()` garantit la coupe à
  l'annulation.
- Durées : force OFF 24 h max, expiration **obligatoire**, raison facultative ≤ 200 caractères (jamais
  interpolée dans un log). Double horloge : `expires_at_epoch` persisté (seul survivant d'un reboot,
  seule échéance affichable) **et** `deadline_mono` calculée à la création — échu au **premier** des
  deux (un saut NTP avant coupe plus tôt, un saut arrière ne prolonge rien).
- Persistance : section `overrides` de `utils/state_store.py`, avec `save(force=True, strict=True)` —
  le throttle 60 s et l'`OSError` avalée actuels rendraient « création refusée sans persistance »
  intenable ; le POST répond 500 si l'écriture échoue. Le défaut avalant reste inchangé pour les budgets
  hiver. Pas de SQLite dans ce chemin (le jalon 4 ne dépend pas du jalon 2).
- Heure fiable (`synchronized` ou `plausible`) obligatoire à la création. Bannière globale et annulation
  immédiate (appliquée même si sa trace doit être retentée). Au reboot : un force OFF non expiré est
  repris ; repris **avant** heure fiable, son échéance est rebornée sur monotonic à 24 h et marquée
  « à confirmer » (un force OFF chauffage repris indéfiniment = serre non chauffée).

### Console

Flux SSE structuré (timestamp, niveau, composant, message — sérialisé `json.dumps`, découpage
multi-lignes conservé), buffers serveur et navigateur bornés à 2 000 lignes, pause/reprise, autoscroll,
filtres, recherche, compteurs, copie, téléchargement, effacement visuel et paramètres URL pour les liens
d'alarme. Filtres/recherche/surlignage : **`textContent` uniquement, jamais `innerHTML`** (le piège XSS
classique de ce genre d'écran — l'existant est propre, ne pas régresser).

### Reboot/extinction

Conserver POST, CSRF et confirmation. Retourner une page 202 avant de lancer la commande avec court
délai (corrige l'`await process.wait()` actuel qui ne revient jamais sur un vrai reboot), puis remplacer
l'URL par un GET inerte **en dur** (`/`), jamais une URL portant un paramètre d'action. Le legacy
`POST /monitor` emprunte le **même** chemin. Reboot : observer d'abord l'indisponibilité, exiger deux
réponses `/health/live`, annoncer le retour et rediriger après cinq secondes. Extinction : expliquer
l'attente de la LED et l'arrêt de la régulation jusqu'à remise sous tension. Sans disparition sous
30 secondes, signaler un échec probable et proposer alarmes/console — cette détection est
**obligatoire** : le passage au 202 supprime la seule détection d'échec existante (le code retour).

## Vérification

Ne pas inventer de suite de tests ou linter. Utiliser relecture statique, `compileall`, harnais jetables
sous `/tmp`, intégration sans charge, puis essais matériels surveillés.

**Points d'injection de faute** (indispensables, sinon les garde-fous critiques restent invérifiables) :
`PHYTO_FAKE_TIME_UNSYNCED=1` (force l'état `unknown`) et un moyen de forcer `control_healthy()` à faux —
variables d'environnement, inertes en production nominale.

**Critère de rollback par livraison, écrit à l'avance** : le signal qui déclenche (ex. écart de
régulation, alarme, absence de caresse), le délai d'observation, et l'opérateur tranche.

- Ancien `param.json` : comportement inchangé et round-trip legacy complet ; `equipment_metadata.json`
  absent → catalogue par défaut ; passage d'`initial_setup_tool.py` → métadonnées intactes.
- Boot en `unknown` : timers journaliers suspendus puis reprise bornée à 15 min avec alarme ;
  séquentiels en paramètres nuit ; synchronisation tardive sans rattrapage d'impulsions ; **reboot en
  pleine plage d'éclairage → lampe ON immédiatement**.
- Fin daily exacte (`[début, fin)` via le helper unique, les trois sites alignés), reprise séquentielle
  bornée, changement pendant longue attente réactif.
- API legacy présente ; demandé/réel/motif/durée/ensuite cohérents ; entrée périmée → « inconnu ».
- Panne Influx/historique : watchdog caresse ; panne contrôle : plus de caresse et état sûr (vérifié via
  le point d'injection, pas en laissant rebooter la serre).
- Acquittement non masquant, réoccurrence distincte, seuils disque sans battement.
- 72 h conservées, purge, 720 buckets avec `bucket_start_ts`, trous non interpolés, valeurs non-`ok` en
  `NULL`, aucune lecture capteur due à HTTP, `quick_check` et recréation sur base corrompue.
- Erreurs config sans mutation, saisie conservée sur 422, secrets absents du HTML/log/SQLite (mot de
  passe Wi-Fi inclus — vérifier le correctif `network_handler`), dirty-check réel, preview affichant le
  seuil de ventilation effectif.
- Matrice override **pure d'abord** (harnais sur `decide()` : expiration double horloge, suspension par
  repli/sécurité, `heater_forced_off` sans effet sur `vent_threshold`) puis GPIO sur banc hors serre :
  génériques OFF=HIGH, moteur OFF=tout LOW, `energized()` coupe sur expiration/annulation/faute, jamais
  chauffage et ventilation simultanés. Rappel matériel : vitesses moteur 1 et 3 HS et GPIO 17 HS —
  tout contrôle « relu == demandé » doit passer par `out_of_service` sous peine de faux négatifs
  permanents.
- Console stable à 2 000 lignes (observation longue, pas une vérification) ; GET d'action sans effet ;
  pages reboot/extinction conformes, y compris `POST /monitor`.
- Si `CLAUDE.md` ou `AGENTS.md` change, les modifier identiquement et exiger un diff vide.

Après chaque jalon : compilation avant arrêt, déploiement via `scripts/deploy.sh`, vérification HTTP et
GPIO, preuve consignée et rollback exercé.

## Hors périmètre

Pas d'authentification, de multi-zone, d'upload d'icône, de lien Grafana, de changement GPIO/câblage,
de RTC matériel, de portage ESP32, de résilience Wi-Fi active/AP de secours, ni de migration/rotation
des secrets. **Pas de force ON** (décision opérateur — réévaluable plus tard comme extension, avec sa
propre revue de sûreté). Le réseau ajouté ici reste strictement observable en lecture seule.
