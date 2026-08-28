# TODO — Déploiement et armement de la qualité des capteurs

**État** : lot redéployé au commit `b26d2b1`, pré-monitoring validé et nouvelle observation 48 h en
cours depuis le 28 août 2026 à 18:59:28 UTC. Première preuve invalidée proprement interrompue et
archivée. Lot non qualifié électriquement et mode `Sensor_Quality.mode = observe` à conserver jusqu'à
validation complète.

Références :

- [`docs/reference/configuration.md`](../docs/reference/configuration.md#calibration-et-qualité-des-capteurs) ;
- [`docs/reference/status-schema.md`](../docs/reference/status-schema.md) ;
- [`docs/development/hardware-validation.md`](../docs/development/hardware-validation.md) ;
- [`docs/operations/deployment-and-rollback.md`](../docs/operations/deployment-and-rollback.md).

## 1. Déployer sans armer

- [x] Commiter puis déployer la version avec `Sensor_Quality.mode = observe` ; ne pas saisir
      `ARMER` pendant ce premier déploiement
- [x] Vérifier après déploiement : `phyto.service` actif, `/health/live` et `/health/ready` à 200,
      `control_healthy=true`, commit attendu, aucun redémarrage ou blocage de tâche et aucune alarme
      critique nouvelle
- [x] Vérifier dans `/api/v1/state` que `schema_version=2`, que chaque capteur actif publie
      `status`, `reason_codes`, `raw_value`, `observed_value`, `value`, `control_usable`, les compteurs
      et les seuils effectifs, sans secret ni valeur inventée
- [ ] Confirmer physiquement que le déploiement en observation n'a modifié aucune sortie et relever
      les GPIO selon la procédure matérielle supervisée

## 2. Observer une période représentative

- [x] Lancer `scripts/observe-jalon2-operator-quality.sh` pendant 48 h au commit `5520850`. Début :
      `2026-08-28T18:07:22Z` ; fin attendue : `2026-08-30T18:07:22Z` ; PID observateur initial :
      `381479` ; PID service de référence : `381022` ; répertoire de preuve :
      `~/phyto-observations/jalon2-operateur-qualite-20260828T180722Z`
- [x] Au prochain redéploiement, arrêter proprement le PID observateur vérifié avec `SIGTERM`, attendre
      son `summary.json` interrompu, redéployer et valider le service, puis nettoyer ou archiver
      uniquement le répertoire invalidé ci-dessus
- [x] Après ces contrôles, relancer une nouvelle observation de 172 800 s : début
      `2026-08-28T18:59:28Z`, fin attendue `2026-08-30T18:59:28Z`, PID observateur initial `388349`,
      PID service de référence `387866`, commit `b26d2b1`, preuves sous
      `~/phyto-observations/jalon2-operateur-qualite-20260828T185928Z`
- [ ] À la fin de cette nouvelle fenêtre, ne l'accepter que si `status=accepted`, durée réelle d'au
      moins 172 800 s, zéro échantillon en échec et examen explicite de tout avertissement
- [ ] Laisser fonctionner le système en mode `observe` pendant plusieurs cycles jour/nuit et une
      durée représentative des périodes naturellement stables de la serre
- [ ] Relever pour chaque mesure les statuts, `unchanged_for_s`, échecs consécutifs, incohérences,
      expirations de calibration et raisons de dégradation
- [ ] Vérifier le measurement Influx `sensor_quality` et confirmer qu'une valeur suspecte reste
      analysable dans cette série sans apparaître dans les measurements métier de confiance
- [ ] Vérifier que les alarmes qualité sont idempotentes, se résolvent au rétablissement et ne
      dégradent ni `control_healthy()` ni le watchdog
- [ ] Consigner les faux positifs et faux négatifs constatés, avec date et contexte, sans recopier
      la configuration sensible

## 3. Calibrer les profils

- [ ] Comparer chaque capteur actif avec un instrument de référence adapté et consigner la méthode,
      la date, les conditions et l'incertitude de la comparaison
- [ ] Renseigner l'offset et la date de calibration, puis vérifier que les diagnostics, compteurs et
      min/max concernés sont réinitialisés comme prévu
- [ ] Ajuster, mesure par mesure, la fraîcheur, la plage plausible, l'epsilon, la durée et le nombre
      minimal d'échantillons de figement à partir des observations réelles
- [ ] Confirmer après chaque modification que les seuils effectifs publiés par l'API correspondent à
      la configuration et qu'aucun ancien diagnostic calculé avec les seuils précédents ne subsiste
- [ ] Laisser à nouveau fonctionner au moins une période représentative après le dernier ajustement

## 4. Stabiliser les identités DS18B20

- [ ] Si les DS18B20 restent désactivés, consigner que cette étape est non applicable ; sinon relever
      physiquement l'identifiant `28-xxxxxxxxxxxx` de chaque sonde
- [ ] Lier chaque `DS18B#1`, `DS18B#2` et `DS18B#3` actif à son identifiant 1-Wire stable depuis
      `/conf`, sans utiliser l'ordre de découverte sysfs
- [ ] Redémarrer le service et vérifier que chaque nom métier conserve la même sonde, la même
      calibration et la même zone malgré un ordre de découverte éventuellement différent
- [ ] Débrancher puis rebrancher une sonde pendant une procédure contrôlée et confirmer qu'elle est
      déclarée absente puis rétablie sans emprunter l'identité d'une autre sonde

## 5. Qualifier la redondance

- [ ] Ne créer un groupe que pour des sondes de même unité, physiquement comparables et exposées au
      même phénomène ; documenter leur emplacement et la tolérance retenue
- [ ] Vérifier avec deux sondes en désaccord qu'aucune n'est choisie arbitrairement
- [ ] Pour tout groupe de trois sondes ou plus, vérifier qu'une valeur divergente est isolée par un
      quorum cohérent
- [ ] Vérifier qu'un quorum indisponible produit un état dégradé ou incohérent explicite et non une
      fausse mesure de confiance
- [ ] Vérifier qu'après un désaccord, trois comparaisons cohérentes sont nécessaires au réarmement
- [ ] Refaire une période d'observation après toute modification d'un groupe ou de sa tolérance

## 6. Qualifier matériellement le repli

- [ ] Planifier une intervention supervisée, charges haute tension consignées au premier passage,
      conformément à `docs/development/hardware-validation.md`
- [ ] Vérifier d'abord le repli historique sur cinq lectures de température manquées : chauffage
      réellement OFF, moteur à `sensor_fallback_speed`, alarme persistante et GPIO cohérents
- [ ] Simuler de façon bornée un figement plausible de `BME280T` en restant en mode `observe` et
      confirmer que le diagnostic apparaît sans changement de sortie
- [ ] Vérifier la récupération du figement sur trois variations plausibles réelles
- [ ] Préparer le scénario armé avec chauffage et moteur sous surveillance, une méthode de retour
      immédiat vers `observe` et une protection thermique indépendante fonctionnelle

## 7. Armer progressivement

- [ ] Avant armement, confirmer : période d'observation terminée, zéro faux positif non expliqué,
      profils stabilisés, identités DS18B20 fixées, redondance qualifiée, matériel validé et moyen de
      retour disponible
- [ ] Relever le commit, l'heure, l'opérateur, les statuts qualité, l'état climatique, les GPIO,
      `control_healthy()`, le watchdog et les alarmes actives
- [ ] Dans `/conf`, passer de `observe` à `enforce` en saisissant explicitement `ARMER`
- [ ] Vérifier immédiatement qu'une incohérence déjà confirmée déclenche `REPLI_CAPTEUR` sans attendre
      une nouvelle lecture : chauffage OFF et moteur à `sensor_fallback_speed`
- [ ] Vérifier qu'en l'absence d'incohérence confirmée l'armement ne provoque ni clignotement de relais,
      ni transition moteur, ni redémarrage anormal d'une tâche
- [ ] Surveiller étroitement un premier cycle complet, puis une période représentative, avec contrôle
      conjoint de l'API, des alarmes, d'InfluxDB, des GPIO et de l'état physique de la serre

## 8. Rollback et critères de clôture

- [ ] Tester le retour `enforce` → `observe` et confirmer qu'une décision qualité déjà en cache perd
      immédiatement son autorité de blocage sans nécessiter de nouvelle lecture matérielle
- [ ] Exercer si nécessaire le rollback applicatif selon la procédure documentée, sans modifier les
      identités ni effacer les preuves de calibration
- [ ] Confirmer après retour ou rollback : service prêt, contrôle sain, watchdog caressé, sorties
      cohérentes, données de confiance non contaminées et alarmes expliquées
- [ ] Mettre à jour le changelog, la roadmap, le registre des risques et un relevé d'exploitation avec
      les dates, seuils retenus, résultats et limites résiduelles
- [ ] Ne déclarer la qualité capteurs « déployée et armée » qu'après clôture de toutes les cases
      applicables et preuve qu'aucune étape n'a dégradé la régulation ou la sûreté électrique

**Limites à conserver dans la clôture** : la détection logicielle ne couvre pas un défaut commun à
plusieurs sondes, un figement plus court que le seuil, un relais mécaniquement collé, la fenêtre de
boot ou une défaillance du Pi. Le thermostat ou fusible thermique indépendant reste obligatoire.

---

# TODO — Refonte de la journalisation (plan `tasks/logging_refonte_plan.md`)

## P3 — Sécurité
- [x] 3.1 Credentials Influx hors de l'URL (`requests.post(params=…)`), messages d'erreur limités à
      `host:port/db` + classe d'exception
- [x] 3.2 `utils/log_dedup.py` (`StateLogger`) appliqué à Influx, capteurs, `config.load()`, `SensorStats`
- [ ] 3.3 *(hors code : à faire sur le Pi — `journalctl --vacuum-size=200M`, `journald.conf`,
      changement du mot de passe InfluxDB)*

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

# TODO — Sortir la vitesse moteur 4 de GPIO 1 (`ID_SC`)

**Contexte** : diagnostic du 25/08/2026. `motor_pin4` est câblé sur **BCM 1 = `ID_SC`**, broche
réservée à l'EEPROM d'identification des HAT et sondée par le firmware en ALT0 au démarrage.
Le canal fonctionne aujourd'hui (relais qui colle, moteur qui tourne), mais ce n'est pas une
broche GPIO générale : à déplacer par précaution, indépendamment de la panne des vitesses 1 et 3
(qui, elle, est côté puissance et ne se corrige pas en changeant de broche).

**Broche cible proposée : BCM 16** — libre sur ce Pi, aucune fonction alternative gênante, et
déjà en `ip pd | lo` au boot (pull-down par défaut), donc relais moteur actif-HAUT au repos tant
que le service n'a pas démarré. Autres candidates libres : 12, 13, 19, 20, 24 (éviter **6**, qui
est en `ip pu | hi` au boot).

- [ ] Couper le secteur, déplacer le fil de la sortie moteur 4 de la broche physique 28 (BCM 1)
      vers la broche physique 36 (BCM 16)
- [ ] `param/param.json` : `GPIO_Settings.motor_pin4` : `1` → `16` (dépôt local **et** copie du Pi
      `/home/progradius/PhytoController/RPi Version/param/param.json`)
- [ ] Redémarrer `phyto.service` et vérifier au log `MotorHandler (active-HIGH) initialisé sur
      pins [25, 8, 7, 16]`
- [ ] Vérifier au `pinctrl` que BCM 1 est bien relâchée et que BCM 16 pilote le relais 4
      (`pinctrl set 16 op pn dh` → `hi` + claquement + moteur qui tourne)
- [ ] Contrôler qu'aucune autre entrée de `GPIO_Settings` n'utilise 16

**Aucune modification de code nécessaire** : les broches moteur viennent toutes de la config
(`MotorHandler.__init__`, `motor_all_pin_down_at_boot`), et les broches moteur sont déjà exclues
de `GENERIC_SAFE_PINS` dans `main.py`.

---

# TODO — Refonte de l'interface web et de l'acquisition capteurs

**État : implémenté dans l'arbre de travail, vérifié hors matériel, non commité, non déployé.**

## Serveur

- [x] Remplacer le serveur `asyncio.start_server` artisanal par `aiohttp` à routes explicites
- [x] Intergiciels : en-têtes de sécurité + `no-store`, validation du `Host`, CSRF + `Origin`
- [x] Limites : corps 64 Kio, ligne/en-têtes 8190 octets, `shutdown_timeout`, `backlog`
- [x] Assets servis par liste blanche exacte de chemins (fin de la traversée `/static/`)
- [x] `/api/v1/state` versionné, `/health/live`, `/health/ready` (503 sur défaut)
- [x] Actions destructrices sur des routes POST dédiées + confirmation navigateur
- [x] `/monitor` réduit à une redirection ; `POST /monitor` conservé pour compatibilité
- [x] Pages d'erreur HTML pour un navigateur, texte brut sinon, redirections préservées

## Configuration

- [x] `POST /conf/{section}` : candidat `AppConfig` complet revalidé avant écriture atomique
- [x] Rejet sans effet sur `param.json` **ni** sur la configuration vivante
- [x] `replace_from()` : publication dans l'instance partagée, sans réinstanciation
- [x] `supervisor.request_reload()` : relance volontaire, état sûr réappliqué, compteur `reloads`
- [x] Bornes et contraintes croisées (horaires, vitesses, températures, port Influx)
- [x] `validate_assignment` sur tous les modèles
- [x] Secrets ni affichés ni journalisés ; champ vide = valeur conservée
- [x] `GPIO_Settings` en lecture seule

## Capteurs

- [x] `controllers/sensor_catalog.py` : table canonique clés / activation / libellés / measurements
- [x] Exécuteur à un fil : plus aucune lecture bloquante dans l'event loop
- [x] Instantané partagé + job supervisé `sensor_snapshot` (10 s) ; HTTP ne lit plus le matériel
- [x] `reconfigure()` en place, `close()` à l'arrêt du superviseur
- [x] Export Influx en aiohttp, alimenté par l'instantané, jamais de valeur périmée poussée

## Nettoyage

- [x] `network/web/api_handler.py` et `templates/monitor.html` supprimés
- [x] `SystemStatus.get_cyclic_period()` : `period_minutes` inexistant → `period_days`
- [x] `requirements.txt` : `requests` retiré, `jinja2` et `aiohttp>=3.12.15,<3.14` ajoutés

## Reste à faire

- [ ] Commiter, déployer sur le Pi et relever le comportement réel (`/health/ready`, console SSE,
      sauvegarde d'une section, bascule capteur)
- [x] `scripts/deploy.sh` : qualifier service, liveness, readiness, contrôle, commit, alarmes critiques
      et stabilité continue avant succès ou après rollback
- [ ] Transformer le harnais de fumigation HTTP en vérification reproductible
- [ ] Sortir les commandes système (`nmcli`, `ping`, `timedatectl`, reboot) de l'event loop
- [ ] Contraintes GPIO (unicité, broches réservées) — dépend du `PinRegistry` du lot 3

---

## Revue — refonte web

**Vérifications effectuées** (harnais jetable `/tmp/claude-1000/phyto/test_web.py`, aiohttp
`TestClient`, stubs `RPi.GPIO`/`smbus2`, `param.json` et `sensor_stats.json` sauvegardés puis
restaurés) : **55 contrôles, aucun échec**.

1. Rendu 200 de toutes les routes servies, CSP et `no-store` présents, **aucun secret dans le
   HTML** de `/`, `/conf` et `/console`.
2. `/api/v1/state` : `schema_version=1`, sections attendues, seules les mesures activées.
3. Refus : `Host` étranger → 421, POST sans jeton → 403, `Origin` tiers → 403, champ inattendu →
   422, section inconnue → 404, traversée `/static/../` → 404.
4. `POST /conf/temperature` avec min > max → 422, `param.json` **inchangé** ; puis valeur valide
   → 303, fichier réécrit, configuration vivante à jour, `motor_temp_control` et `heat_control`
   relancés.
5. Secrets Influx laissés vides → valeur conservée ; port hors bornes → 422.
6. `POST /conf/sensors` → `reconfigure()` appelé exactement une fois sur l'instance existante.
7. Réinitialisation de statistique : clé valide → 303, clé inconnue → 400.
8. Horaires : `07:30` accepté et appliqué, `25:00` refusé, `07:30:00` accepté (secondes ignorées).
9. Pages d'erreur : 404/403 en HTML pour un navigateur, en texte pour un client JSON ;
   redirections 303 non transformées ; 405 conserve son en-tête `Allow`.

**Corrections apportées pendant la revue** :

- `<input type="time">` renvoyant `HH:MM:SS` provoquait un 422 : les secondes sont désormais
  ignorées.
- `pages.error_page()` et `templates/error.html` étaient du code mort : ils rendent maintenant
  les erreurs ≥ 400 destinées à un navigateur, redirections exclues.

**Points d'attention traités ensuite** (correctifs suivants, mêmes conditions de vérification —
harnais `/tmp/claude-1000/phyto/test_fixes.py`, **21 contrôles, aucun échec**) :

- [x] **Jeton CSRF régénéré à chaque démarrage** → `utils/csrf.py` : jeton persistant dans
      `param/.csrf_token` (0600, ignoré par git). Un `systemctl restart` n'invalide plus les
      pages ouvertes. Fichier absent, tronqué ou corrompu → régénération ; écriture impossible →
      repli sur un jeton en mémoire, journalisé, jamais fatal.
      *Vérifié* : jeton identique après relecture, mode 0600, régénération sur contenu invalide,
      repli sans exception sur chemin non inscriptible.
- [x] **Sauvegarde d'une section coupant brièvement la sortie** → `TaskSupervisor._runner()` ne
      repositionne plus l'état sûr sur un rechargement **volontaire**. Il le fait toujours sur
      panne, blocage et terminaison anormale, et toujours **avant** le back-off.
      *Vérifié* : `request_reload()` relance sans appeler `safe_state`, `reloads=1`,
      `restarts=0` ; une panne simulée appelle bien `safe_state` et incrémente `restarts`.
      *Résidu voulu* : un timer cyclique annulé pendant sa fenêtre ON voit sa sortie coupée par
      le `finally` d'`energized()` — une sortie ne doit pas rester fermée sans boucle pour la
      surveiller.
- [x] **`SensorStats` sans verrou** → `RLock` autour de `update()`, `clear_key()` et `_dump()`,
      et `get_all()`/`stats` renvoient une copie profonde.
      *Vérifié* : 4 fils concurrents (2 écrivains, 2 lecteurs, 800 mises à jour), aucune
      exception, min/max exacts, copie non partagée, fichier relu cohérent.

**Points d'attention restants** :

- Le Pi exécute `aiohttp 3.11.18`, sous le plancher `>=3.12.15` du nouveau `requirements.txt` :
  `scripts/deploy.sh` met le venv à jour automatiquement, une installation manuelle non.

---

# TODO — Qualification opérationnelle de la PWA locale

**État : code et HTTPS `:443` déployés ; transport TLS vérifié le 28 août 2026, qualification complète
sur Chrome Android et essais de dégradation encore ouverts.** Relevé :
[`docs/operations/pwa-tls-activation-2026-08-28.md`](../docs/operations/pwa-tls-activation-2026-08-28.md).

Procédure de référence : [`docs/operations/pwa-local-tls.md`](../docs/operations/pwa-local-tls.md).
HTTP `:8123` doit rester la voie de compatibilité et de récupération pendant toute la qualification.
Une panne TLS ou PWA ne doit jamais dégrader la régulation, `control_healthy()` ou le watchdog.

## 1. Préparer et activer TLS

- [ ] Créer l'autorité privée sur le poste d'administration, dans un emplacement protégé situé hors
      du dépôt ; conserver et sauvegarder `phyto-root-ca.key` hors du Raspberry Pi et d'Android
- [x] Générer le certificat serveur avec `deploy/pwa-tls-server.ext`, puis vérifier sa chaîne, son
      échéance, l'usage `TLS Web Server Authentication` et les SAN `phytocontroller.local`,
      `phytocontroller` et `10.42.0.1`
- [x] Comparer et consigner l'empreinte SHA-256 de `phyto-root-ca.crt` avant toute distribution
- [x] Installer sur le Pi uniquement `server.crt`, `server.key` et le certificat public de la racine,
      avec les propriétaires et modes documentés ; confirmer que la clé privée est lisible par
      `progradius` mais pas par les autres utilisateurs
- [ ] Installer le drop-in `deploy/phyto.service.d/pwa-tls.conf`, exécuter `daemon-reload`, puis
      planifier le redémarrage comme une opération de production avec vérification des états GPIO sûrs
- [x] Vérifier que `:8123` et `:443` écoutent simultanément, que `/health/ready` répond sur HTTP et que
      `/health/live` répond en HTTPS avec validation complète de la chaîne et du nom d'hôte
- [x] Vérifier dans `/api/v1/state` que `web.https.configured=true`, `ready=true` et `port=443`, sans
      exposition des chemins de clé ou de certificat
- [ ] Simuler un échec TLS contrôlé pendant une fenêtre prévue et confirmer que HTTP `:8123`, la
      régulation, `control_healthy()` et le watchdog restent sains, avec `web.https.ready=false`

## 2. Installer et contrôler la PWA sur Chrome Android

- [ ] Transférer uniquement `phyto-root-ca.crt` sur le terminal Android et comparer son empreinte
      SHA-256 avec celle consignée sur le poste d'administration
- [ ] Installer la racine comme autorité pour les applications ; ne jamais transférer
      `phyto-root-ca.key`, `server.key` ni un fichier PKCS#12 sur le terminal
- [ ] Ouvrir `https://phytocontroller.local/` dans Chrome et vérifier l'absence d'interstitiel ou
      d'avertissement TLS
- [ ] Installer la PWA avec le bouton du tableau de bord et confirmer le lancement en fenêtre
      autonome, l'icône normale/maskable et le nom `PhytoController`
- [ ] Vérifier les raccourcis d'écran d'accueil « Tableau de bord » et « Alarmes » et confirmer qu'ils
      ouvrent la bonne vue dans la PWA

## 3. Qualifier la coupure réseau et la fraîcheur dominante

- [ ] En ligne, ouvrir le tableau de bord et les alarmes, attendre au moins un rafraîchissement réussi
      de l'état, des alarmes et de l'historique, puis relever leurs heures de réception
- [ ] Couper réellement le réseau entre Android et le Pi sans arrêter la PWA
- [ ] Vérifier que la bannière rouge `HORS LIGNE` apparaît rapidement et reste visible sur toutes les
      vues avec « données datant au mieux de… · non actualisées · lecture seule »
- [ ] Vérifier que l'âge affiché augmente avec le temps et qu'aucun snapshot IndexedDB ne remet la vue
      en état « à jour »
- [ ] Vérifier que les dernières vues Tableau de bord et Alarmes restent lisibles, que l'historique
      annonce explicitement l'âge de son snapshot et que les alarmes stockées portent « État non
      confirmé » / « Lecture seule hors ligne »
- [ ] Vérifier que tous les formulaires et boutons de mutation sont désactivés hors ligne, notamment
      acquittement, configuration, remise à zéro, reboot et extinction
- [ ] Inspecter Cache Storage et confirmer l'absence de `/api/**`, `/health/**`, `/status`, du SSE et
      de toute requête POST ; confirmer qu'aucune commande n'est mise en attente ou rejouée
- [ ] Tenter d'ouvrir `/conf`, `/console` et une URL inconnue hors ligne : elles doivent afficher le
      repli neutre, jamais une ancienne page de configuration ou de console

## 4. Qualifier la reconnexion

- [ ] Rétablir le réseau et confirmer que la bannière ne disparaît qu'après une réponse HTTP réelle du
      contrôleur, jamais sur le seul événement navigateur `online`
- [ ] Si la PWA a démarré hors ligne, confirmer qu'elle recharge une seule fois la vue après le premier
      contact réussi, sans boucle de rechargement
- [ ] Vérifier que l'état, les alarmes et l'historique redeviennent frais, que les actions sont
      réactivées et qu'aucune mutation ancienne n'est envoyée
- [ ] Répéter au moins deux cycles coupure/reconnexion et confirmer que l'âge, la bannière et les
      snapshots restent cohérents

## 5. Qualifier les notifications locales

- [ ] Depuis la page Alarmes, vérifier que Chrome ne demande aucune permission avant le clic explicite
      sur « Activer les notifications »
- [ ] Activer les notifications et confirmer que les alarmes déjà présentes servent de référence sans
      déclencher une rafale rétrospective
- [ ] Provoquer de façon sûre une **nouvelle** alarme non acquittée affectant le contrôle, puis vérifier
      une notification unique, son libellé minimal et l'ouverture du bon diagnostic au toucher
- [ ] Vérifier qu'une alarme auxiliaire non critique ne notifie pas et qu'une alarme critique notifie
      même si elle est auxiliaire
- [ ] Vérifier qu'un rafraîchissement de la même occurrence UUID ne renotifie pas ; vérifier qu'une
      escalade de gravité peut renotifier une fois
- [ ] Couper le réseau avec un snapshot d'alarme enregistré et confirmer que sa restauration ne
      déclenche aucune notification
- [ ] Désactiver les notifications depuis l'IHM et confirmer qu'aucune nouvelle notification locale
      n'est émise
- [ ] Consigner la limite attendue : aucune garantie lorsque Chrome suspend ou ferme complètement la
      PWA, puisqu'il n'existe ni Web Push ni service externe

## 6. Exercer le rollback contrôlé

- [ ] Avant rollback, relever le commit, l'état de `phyto.service`, `NRestarts`, `/health/ready`, les
      sorties physiques et la disponibilité simultanée de `:8123` et `:443`
- [ ] Effectuer le rollback selon `docs/operations/deployment-and-rollback.md`, sans `git reset --hard`
      improvisé et sans supprimer les certificats sous `/etc/phyto/tls`
- [ ] Confirmer après rollback que la régulation et HTTP `:8123` sont sains, même si `:443` disparaît
      avec une version antérieure à la PWA
- [ ] Confirmer que la PWA déjà installée reste honnêtement hors ligne avec son dernier snapshot et ne
      présente jamais ces données comme actuelles
- [ ] Redéployer la version PWA, vérifier le retour de `:443`, l'actualisation du service worker et le
      rétablissement des données fraîches
- [ ] Si la coque locale reste bloquée sur une ancienne version, exercer puis documenter la procédure
      de désinstallation ou d'effacement des données du site Chrome

## Critères de clôture

- [ ] Toutes les cases précédentes sont accompagnées d'une date, du terminal Android/Chrome utilisé et
      des observations utiles, sans recopier de secret ni de clé
- [ ] Aucun défaut TLS, cache, notification ou navigateur observé pendant la qualification n'a affecté
      les boucles de contrôle, les sorties GPIO, `control_healthy()` ou le watchdog
- [ ] La clé `phyto-root-ca.key` est absente du Pi, d'Android, de Git et des sauvegardes applicatives
- [ ] Les risques `R-WEB-05` et `R-WEB-06` de `docs/risk-register.md` sont réévalués avec les preuves de
      qualification avant de déclarer la PWA déployée et vérifiée

---

# TODO — Jalon 3 « Configuration guidée » (plan `qol_operator_experience_plan.md`)

**Arbitrages opérateur du 28 août 2026**

- Profil thermique du mode Simple : **aligné sur la configuration déployée**, pas sur la proposition
  du plan — hystérésis 2 °C, zone morte 1 °C, palier 1 °C, relâchement 0,5 °C, maintien 120 s,
  plancher 5 °C, repli capteur 0, marge hiver 2 °C, budgets renouvellement 5 min/h et humidité
  15 min/h, vitesse minimale 0, vitesse hiver par défaut 1. Passer en mode Simple ne modifie donc
  aucun réglage fin tant que l'opérateur ne touche pas aux champs exposés.
- Intensité douce / normale / forte : **mapping du plan conservé** (2/2, 3/3, 4/4 pour
  `max_speed` / `winter_refresh_speed`). Rappel consigné : les vitesses moteur 1 et 3 sont hors
  service côté puissance, « normale » commande donc une vitesse morte tant que la panne dure.
- Livraison en **trois commits** déployables et retirables séparément.

## Commit 1 — 3a formulaire sans perte + 3b registre central des champs

- [x] Étendre `SECTION_FIELDS` en registre : chaque entrée porte sa cible de configuration **et**
      son libellé humain ; supprimer les listes de noms dupliquées
- [x] Construire l'index inverse `payload → champ de formulaire` à partir du même registre
      (horaires compris : `*_hour` / `*_minute` → `start_time` / `stop_time`)
- [x] Humaniser les messages Pydantic (table type → phrase française, bornes injectées depuis `ctx`)
- [x] Rattacher les contraintes croisées aux deux champs concernés (min/max jour, min/max nuit,
      vitesse min/max) au lieu d'une erreur globale
- [x] Re-rendre la saisie du POST sur 422 (multidict), secrets jamais réémis, portée par formulaire
      (`sensor-quality` porté par sa clé capteur)
- [x] Afficher l'erreur sous le champ (`aria-describedby`, `aria-invalid`), bandeau global réservé
      aux erreurs non rattachables
- [x] Focus sur le premier champ refusé ; un champ numérique refusé se re-rend en texte pour que la
      valeur rejetée reste visible et corrigeable
- [x] Factoriser les quatre réponses 422/500 de `_configuration_post` en un seul point
- [x] Tests : saisie conservée, secret absent du HTML, contrainte croisée rattachée, message humanisé

## Commit 2 — 3c prévisualisation serveur

- [ ] `POST /api/v1/config/preview` : mêmes parseurs, candidat Pydantic complet, aucune écriture
- [ ] Garde d'in-flight (un preview à la fois) + intervalle minimum, corps jamais journalisé,
      aucun champ sensible en réponse, jeton en en-tête `X-CSRF-Token`
- [ ] Réponse portant le **seuil de ventilation effectif** reconstruit par `settings_from_config`
      (jour et nuit), l'indicateur « seuil relevé » et les écarts détectés
- [ ] IHM : encart de prévisualisation par section, aucune formule thermique dupliquée en JavaScript

## Commit 3 — 3d mode Simple, dirty-check et flash

- [ ] Sélecteur Simple / Avancé, simple par défaut, choix mémorisé en `localStorage`
- [ ] Section Simple : planning jour/nuit, min/max jour et nuit, humidité max, intensité, saison,
      chauffage, plannings ; profil et mapping ci-dessus
- [ ] Un `motor_mode` manuel existant exige un choix explicite avant toute écriture
- [ ] Le mode Simple ne s'affiche que si la prévisualisation répond
- [ ] Dirty-check sur écarts réels, bouton d'annulation, `beforeunload`
- [ ] Flash opaque côté serveur après succès : champs modifiés, heure, mode d'application

## Vérification (identique pour les trois commits)

- [ ] `python -m pyflakes` sur tout l'arbre — 0 « undefined name » (leçon du 26 août 2026)
- [ ] `python3 -m pytest` vert, sortie conservée dans un fichier temporaire
- [ ] Aucun secret dans le HTML rendu ni dans les journaux
- [ ] `diff -u CLAUDE.md AGENTS.md` vide si l'un des deux change
