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
- [ ] `scripts/deploy.sh` : passer la sonde de `/status` à `/health/ready`
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

**État : code implémenté et vérifié statiquement, non déployé et non qualifié sur Chrome Android.**

Procédure de référence : [`docs/operations/pwa-local-tls.md`](../docs/operations/pwa-local-tls.md).
HTTP `:8123` doit rester la voie de compatibilité et de récupération pendant toute la qualification.
Une panne TLS ou PWA ne doit jamais dégrader la régulation, `control_healthy()` ou le watchdog.

## 1. Préparer et activer TLS

- [ ] Créer l'autorité privée sur le poste d'administration, dans un emplacement protégé situé hors
      du dépôt ; conserver et sauvegarder `phyto-root-ca.key` hors du Raspberry Pi et d'Android
- [ ] Générer le certificat serveur avec `deploy/pwa-tls-server.ext`, puis vérifier sa chaîne, son
      échéance, l'usage `TLS Web Server Authentication` et les SAN `phytocontroller.local`,
      `phytocontroller` et `10.42.0.1`
- [ ] Comparer et consigner l'empreinte SHA-256 de `phyto-root-ca.crt` avant toute distribution
- [ ] Installer sur le Pi uniquement `server.crt`, `server.key` et le certificat public de la racine,
      avec les propriétaires et modes documentés ; confirmer que la clé privée est lisible par
      `progradius` mais pas par les autres utilisateurs
- [ ] Installer le drop-in `deploy/phyto.service.d/pwa-tls.conf`, exécuter `daemon-reload`, puis
      planifier le redémarrage comme une opération de production avec vérification des états GPIO sûrs
- [ ] Vérifier que `:8123` et `:443` écoutent simultanément, que `/health/ready` répond sur HTTP et que
      `/health/live` répond en HTTPS avec validation complète de la chaîne et du nom d'hôte
- [ ] Vérifier dans `/api/v1/state` que `web.https.configured=true`, `ready=true` et `port=443`, sans
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
