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
- [ ] **OUVERT — à vérifier le 26/08/2026 (après minuit) : la rotation quotidienne en conditions
      réelles.** Seul maillon non testé en production (validé en local uniquement, en forçant
      `doRollover()`). Attendu : `logs/phyto.log.2026-08-26.gz` de quelques Ko, un `phyto.log`
      neuf qui repart à la ligne 1, et aucune erreur de rotation dans le fichier ni dans
      `journalctl -u phyto`. Commande de contrôle depuis WSL :
      `./scripts/phyto-ssh.sh 'ls -la ~/PhytoController/"RPi Version"/logs/'`
      Si l'archive manque : vérifier que le processus n'a pas redémarré pile à minuit (le
      handler ne rattrape pas une rotation manquée au démarrage) et que `logs/` est accessible
      en écriture à `progradius`.

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
