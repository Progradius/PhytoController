# Plan d'implémentation — Refonte de la journalisation (RPi Version)

> Validé le 2026-08-25. Contexte : logs à ~5 Mo/jour (53 lignes/min), historique perdu en ~29 h,
> journal systemd à 2,7 Go, secrets InfluxDB en clair dans les logs, trous de couverture critiques.
> Analyse complète : voir la conversation du 2026-08-25 (état des lieux code + mesures sur le Pi).
>
> Déploiement cible : le Pi est sur `winter_mode` (mergé dans `master`) ; après implémentation,
> push de `master` puis bascule du Pi dessus.

---

## Phase P3 — Sécurité (URGENT, à faire en premier)

### 3.1 Purger les secrets des logs InfluxDB
- [ ] `network/web/influx_handler.py` : ne plus construire l'URL avec `u=...&p=...` dans la query
      string (`_query_base`, l.25-30). Passer les credentials via `requests.post(..., params=...)`
      ou `auth=`, hors de l'URL loggable.
- [ ] Les messages d'erreur du POST (l.56) ne doivent jamais inclure l'URL complète : logger
      `host:port/db` + classe d'exception + message court, jamais `repr(exception)` de requests.
- [ ] Vérifier qu'aucun autre module ne logge d'URL avec credentials (`grep -rn "u=" network/`).

### 3.2 Dédupliquer les erreurs répétées (anti-flood)
- [ ] Créer un petit utilitaire `utils/log_dedup.py` (ou intégré à `pretty_console`) : classe
      `StateLogger` — logge **1 fois à l'entrée en panne** (ERROR), un compteur silencieux pendant,
      **1 fois au rétablissement** (INFO avec durée + nombre d'échecs).
- [ ] L'appliquer au push InfluxDB (`influx_handler.py`) : panne réseau de 3 h = 2 lignes, pas 180.
- [ ] L'appliquer aux lectures capteur en échec récurrent (`sensor_handlers/*`).

### 3.3 Assainir le Pi et les credentials
- [ ] Sur le Pi : `sudo journalctl --vacuum-size=200M` puis `/etc/systemd/journald.conf` →
      `SystemMaxUse=200M`, `systemctl restart systemd-journald`.
- [ ] Changer le mot de passe InfluxDB (exposé dans les logs, le journal ET `param/param.json`
      tracké en git). Mettre à jour `param.json` sur le Pi. Ne jamais écrire la valeur dans un
      commit/log/issue.
- [ ] Optionnel (durable) : sortir les credentials de `param.json` versionné (fichier local non
      tracké ou variables d'env) — à discuter, impacte `param/config.py`.

---

## Phase P1 — Refonte du cœur de logging (`utils/pretty_console.py` façade unique)

### 1.1 Supprimer le code mort et unifier
- [ ] Supprimer `utils/logger.py` (importé nulle part ; risque de double handler/rotation corrompue).
- [ ] Mettre à jour `CLAUDE.md` (section Style) qui le référence encore.

### 1.2 Niveaux réels et configurables
- [ ] Exposer `debug()` dans `pretty_console` (mappé `logging.DEBUG`).
- [ ] Re-mapper : `info` → INFO, `success` → INFO, `action`/`clock` → **DEBUG** (bruit de
      fonctionnement), `warning` → WARNING, `error` → ERROR. Gérer CRITICAL dans `_log_to_file`
      (actuellement perdu en silence, l.107-115).
- [ ] Le niveau filtre **console ET fichier** (aujourd'hui `_log_to_file` est inconditionnel,
      l.124 ; le handler fichier n'a aucun `setLevel`, l.48).
- [ ] Source du niveau, par priorité : env `PHYTO_LOG_LEVEL` > `param.json` > défaut `INFO`.
      Ajouter une section `Log_Settings` dans `param/param.json` + modèle Pydantic dans
      `param/config.py` (alias PascalCase, ne pas oublier le round-trip dans `save()`).
      Champs : `level` (DEBUG/INFO/WARNING/ERROR), `retention_days` (défaut 14).
- [ ] Appliquer le niveau au boot (`main.py`) et lors d'un POST `/conf`
      (`server.py::_apply_conf_changes`) pour un changement à chaud sans restart.

### 1.3 Format cohérent
- [ ] Format fichier : `%(asctime)s [%(levelname)s] [%(name)s] %(message)s` — loggers par module
      (`logging.getLogger("phyto.motor")`, `"phyto.timer"`, `"phyto.influx"`, `"phyto.http"`,
      `"phyto.gpio"`, `"phyto.main"`, ...). `pretty_console` accepte un paramètre `name=` optionnel
      (défaut `phyto`) plutôt que des préfixes manuels `[MOTOR][MANUAL]` etc.
- [ ] `box()` et `title()` : affichage console inchangé, mais côté fichier **une seule ligne**
      résumée (jamais de multi-ligne — casse le parsing ; 4 100 `[BOX]` mesurés par fichier).
      Les soumettre au filtre de niveau (aujourd'hui ils échappent à `_should_display`).
- [ ] Timestamp console y compris en mode rich (branche l.121 : ajouter `_stamp()`).
- [ ] Plus d'émojis/icônes dans le **fichier** (`❌`/`✅`/`🎯`/`▶️`/`✔` en dur dans
      `BME280Handler.py:45,50`, `DS18Handler.py:25`, `network_handler.py:43,66`,
      `influx_handler.py:59`, `VEML6075Handler.py:44`) — les icônes restent l'affaire de la console.
- [ ] Uniformiser en français : `VEML6075Handler.py:44` (« ready »), `VL53L0XHandler.py:38,64`,
      `dailytimer_handler.py:40` (« switched ON »).

---

## Phase P2 — Logger les transitions, pas les états

### 2.1 Modèles GPIO : log uniquement sur changement réel
- [ ] `model/Component.py:42` — `set_state()` compare à l'état courant ; no-op → aucun log
      (ou DEBUG). C'est l'amplificateur n°1 (4 438 lignes/fichier).
- [ ] `model/Motor.py` — idem sur la vitesse.

### 2.2 Boucles périodiques : tick = DEBUG, événement = INFO
- [ ] `components/cyclic_timer_handler.py:41` — timer désactivé : **un seul log à la transition**
      enabled→disabled, puis silence (47 % du volume actuel : 3 lignes/5 s/timer).
- [ ] `components/MotorHandler.py:143` — logger la vitesse **après** le test de changement,
      seulement si elle change. Les logs des branches `auto` (l.159-171) et `winter` (l.205-237)
      passent en DEBUG sauf changement de consigne.
- [ ] `components/heater_control.py:49,62` — « État conservé » → DEBUG ; INFO uniquement sur
      allumage/extinction.
- [ ] `components/dailytimer_handler.py:17,28,42,45` + `model/DailyTimer.py:79` — « check @ »,
      « rafraîchi », « aucun changement », « prochaine vérif » → DEBUG ; INFO seulement sur ON/OFF.
- [ ] `network/web/influx_handler.py:49` — valeurs par measurement → DEBUG (elles sont déjà dans
      Influx) ; garder en INFO un résumé périodique éventuel (ex. 1 ligne/heure) ou rien.
- [ ] `network/web/server.py:171` — ne plus logger les assets statiques (`/static/...`) ; les
      autres requêtes → DEBUG ; les POST de conf → INFO (c'est un événement).

### 2.3 Capteurs absents/désactivés : un log à l'init, pas en boucle
- [ ] `controllers/SensorController.py:158` — un capteur **désactivé dans `Sensor_State`** n'est
      pas une anomalie : retour `None` sans warning en boucle. Logger la liste des capteurs
      actifs/inactifs **une fois à l'init**.
- [ ] `sensor_handlers/DS18Handler.py` — « Capteur DS18B20 #N inexistant » : 1 warning à l'init
      si activé mais introuvable, puis passage silencieux (ou StateLogger de P3.2).
- [ ] Harmoniser les logs de lecture : `HCSR04Handler.py:49`, `MLX90614Handler.py:52,66` loggent
      chaque valeur lue (les autres capteurs non) → DEBUG partout.

> Objectif mesurable : < 100 lignes/jour en régime stable (vs ~76 000 aujourd'hui).

---

## Phase P4 — Combler les trous de couverture

### 4.1 PuppetMaster : diagnostic des tâches
- [ ] `controllers/PuppetMaster.py:59-65` — exception handler : logger la **traceback complète**
      (`exc_info` / `traceback.format_exception`) + le **nom de la tâche** (`context.get("task")`).
- [ ] Nommer chaque tâche (`loop.create_task(coro, name="daily_timer_1")`, l.75-132), **conserver
      les références**, et attacher un `add_done_callback` qui logge en ERROR toute tâche qui se
      termine (fin = anormal pour ces boucles infinies — aujourd'hui une coroutine qui `return`
      meurt en silence, ex. `cyclic_timer_handler.py:129` mode inconnu).

### 4.2 `main.py` : le shutdown doit être dans le fichier
- [ ] Remplacer les 11 `print()` (l.57-249) par le logger (`phyto.main`) : cleanup GPIO, signaux
      SIGINT/SIGTERM/SIGHUP, watchdog, erreurs de boot. `traceback.print_exc()` (l.185, 261) →
      `logger.exception(...)` équivalent.
- [ ] Préserver la garantie GPIO safe-state existante (ne toucher qu'au logging, pas à la logique).

### 4.3 Supprimer les `except: pass`
- [ ] `components/dailytimer_handler.py:31-32` — échec d'extinction GPIO → **ERROR** (relais
      potentiellement resté fermé : c'est le pire événement silencieux du système).
- [ ] `controllers/SensorController.py:165-166` (stats) → WARNING dédupliqué.
- [ ] `sensor_handlers/VL53L0XHandler.py:73-74` (close bus) → DEBUG.

### 4.4 Config et I/O
- [ ] `param/config.py` — `load()` (l.162-164) : try/except avec log ERROR explicite (fichier
      corrompu, validation Pydantic) ; appelée en boucle toutes les 5-60 s, l'erreur doit être
      dédupliquée (StateLogger). `save()` (l.166-199) : try + log succès (DEBUG) / échec (ERROR).
- [ ] `model/SensorStats.py:46-47` — `_dump()` sous try, échec → WARNING dédupliqué (disque plein).
- [ ] `model/Component.py:43`, `model/Motor.py:41,64` — élargir `RuntimeError` à
      `(RuntimeError, ValueError, OSError)` avec log ERROR.
- [ ] `controllers/SensorController.py:45` — attraper aussi `PermissionError`/`OSError` sur
      l'ouverture I2C ; logger la dégradation quand les handlers sont instanciés avec `i2c=None`.
- [ ] `network/web/server.py` — headers malformés (l.168), `IncompleteReadError` (l.177),
      404 (l.210-212, 311-312), `int()/float()` sur POST utilisateur (l.353-361, 387-395) :
      attraper et logger en WARNING/DEBUG, ne jamais tuer la connexion en silence.
- [ ] `network/web/server.py:237,240` — `os.system("sudo reboot"/"shutdown")` : vérifier le code
      retour et logger l'échec.
- [ ] `network/web/influx_handler.py:33` — `reload_sensor_handler()` à l'import, hors try : le
      déplacer/protéger pour qu'un échec de config ne fasse pas planter l'import de PuppetMaster.

---

## Phase P5 — `/console` refondu (suppression du PTY + second main.py)

Problème actuel : `server.py:100-147` lance un **second `main.py` complet** dans un PTY (deux
processus pilotent les mêmes GPIO, double rotation corrompue du même fichier de log, cascade
récursive hors mode service, PTY permanent même sans client).

- [ ] Créer un `logging.Handler` en mémoire (deque `maxlen=1000`) branché sur le logger `phyto`
      du **processus courant**, avec un hook de diffusion vers les queues SSE.
- [ ] `server.py` : la route `/console/stream` rejoue la deque puis streame ce handler.
      Supprimer `_spawn_pty_and_broadcast()` et toute la mécanique PTY/subprocess, y compris la
      distinction `PHYTO_RUN_MODE` qui n'existait que pour ça (garder la variable pour le reste).
- [ ] Corriger au passage : `await writer.wait_closed()` après `close()` (l.288), retrait de queue
      idempotent (l.287), découpage de l'historique rejoué, filtrage des séquences ANSI côté
      serveur (le fichier n'en contient plus après P1.3).
- [ ] `templates/console.html` : vendorer xterm.js en local (`/static/`) au lieu du CDN unpkg.com
      (le Pi doit fonctionner sans Internet).

---

## Phase P6 — Rétention et destinations

- [ ] Remplacer `RotatingFileHandler(1 Mo × 5)` par `TimedRotatingFileHandler(when="midnight",
      backupCount=Log_Settings.retention_days)` + compression des archives (namer/rotator gzip).
      Avec la verbosité de P2, un fichier/jour restera minuscule.
- [ ] Mode service : conserver stdout (journald) **et** fichier est acceptable une fois le volume
      divisé par ~500, journald étant plafonné à 200M (P3.3). Ne pas dupliquer davantage.
- [ ] Nettoyer sur le Pi les anciens `phyto.log.N` et le `~/app.log` orphelin (racine home) ;
      `start.sh`/`startup.sh` à la racine home sont obsolètes (le service systemd fait foi) — à
      confirmer avant suppression.

---

## Vérification (pas de test suite dans ce repo — vérification par lecture + observation)

1. Relecture croisée : chaque `set_state`/boucle modifiée → décrire les transitions GPIO attendues
   (convention : `Component` actif-LOW, `Motor` actif-HIGH — ne rien inverser).
2. Lancement local possible en mode dégradé ? Non (GPIO/I2C) → vérification sur le Pi :
   déployer sur une branche, `journalctl -u phyto -f` + `tail -f logs/phyto.log` pendant 15 min :
   - régime stable = quasi-silence (quelques DEBUG si niveau DEBUG, rien en INFO) ;
   - forcer un événement (toggle DailyTimer via `/conf`) = lignes INFO propres ;
   - couper Influx = 1 ERROR à la panne, 1 INFO au rétablissement ;
   - `grep -c "p=" logs/phyto.log` = 0 (aucun credential).
3. Vérifier `/console` : flux live du processus courant, un seul `python3 main.py` dans `ps aux`.
4. `param.json` round-trip : POST `/conf` → `save()` → relire → booléens `"enabled"/"disabled"`
   préservés, section `Log_Settings` incluse.

## Déploiement

1. Implémenter sur une branche locale, merger dans `master`, push.
2. Sur le Pi : `git fetch && git checkout master && git pull`, ajuster `param.json` local
   (nouvelle section `Log_Settings`, nouveau mot de passe Influx), `sudo systemctl restart phyto`.
3. Appliquer P3.3 (vacuum + journald.conf) — one-shot, indépendant du code.
4. Observer 24 h, puis supprimer les vieux logs.
