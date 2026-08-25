# TODO — Audit 2026-08-25, Phase 0 (garde-fous immédiats)

Plan source : `AUDIT-2026-08-25.md` § 8.

**Statut : phase 0 terminée, déployée et vérifiée sur le matériel** (commit `649eb20`, Pi sur `master`,
déploiement du 2026-08-25 ~20:54 via `scripts/deploy.sh`). Détail des preuves en fin de fichier.

## Fait

- [x] **0.1 Verrou d'instance** *(C4)* — `utils/single_instance.py`, socket Unix
      abstrait `\0phyto-controller`, pris tout en haut de `main.py` avant tout
      accès GPIO et avant l'enregistrement des handlers de signaux / `atexit`.
      Attente bornée à 15 s (fenêtre stop→start d'un `systemctl restart`), puis
      `sys.exit(1)` — code **non nul** pour que systemd et le contrôle de santé
      de `scripts/deploy.sh` voient une panne, pas un « exited » silencieux.
- [x] **0.2 Écriture atomique** *(C7, M5)* — `utils/atomic_io.write_text_atomic()`
      (tmp dans le même dossier + `fsync` + `os.replace` + `fsync` du répertoire,
      mode du fichier existant reporté), branché dans `AppConfig.save()` et
      `SensorStats._dump()`.
- [x] **0.3 Garde de lecture** *(C6, C7)* — `try/except` + repli sur la dernière
      config valide dans `components/cyclic_timer_handler.py` et
      `components/MotorHandler.py`. Un `param.json` momentanément illisible ne
      tue plus la tâche de contrôle.
- [x] **0.4 Suppression de `GPIO.cleanup()`** *(C3)* — l'état sûr est terminal :
      les broches restent des sorties pilotées. `cleanup_gpio()` rendu idempotent
      (3 chemins d'appel : signal, `atexit`, `finally`).
- [x] **0.5 Repli chauffage** *(C10)* — validation de plage `]-20 ; 60[`,
      5 lectures manquées consécutives → OFF forcé + alarme persistante,
      durée max d'allumage continu 120 min + repos 15 min. Durées sur
      `time.monotonic()` (immunes aux sauts NTP).

- [x] **0.6 `/monitor` : actions en POST** *(C12)* — `GET /monitor` ne fait plus
      que rendre la page (aucun effet de bord) ; reset de stat, reboot et
      extinction passent par `POST /monitor`, avec réponse `303 See Other`
      (Post/Redirect/Get : un F5 ne rejoue pas l'action) et `405 + Allow` sur
      les autres méthodes. Les 3 formulaires de `templates/monitor.html` sont
      basculés en POST. Un POST dont l'en-tête `Origin` diffère de `Host` est
      refusé en `403` : ça ferme le formulaire hébergé sur un site tiers, seul
      vecteur restant une fois le GET neutralisé. Absence d'`Origin` (curl,
      script local) : laissé passer.
      **Décision : pas d'authentification** sur l'IHM, accès LAN uniquement.

## Relogés — améliorations futures

- [ ] **0.6bis Validation de l'en-tête `Host`** *(C12)* — liste blanche des
      hôtes acceptés, contre le DNS rebinding (un domaine tiers qui résout vers
      l'IP du Pi rend l'origine « légitime » et contourne le contrôle
      `Origin`). Reste théorique sur un LAN domestique ; à traiter avec la
      migration aiohttp (Phase 4).
- [ ] **0.7 Confinement de `/static/`** *(C11)* — `Path.resolve()` + vérification
      d'appartenance au dossier `static/`, ou liste blanche. Le serveur peut
      tourner en root : un path traversal lit n'importe quel fichier du Pi.
      Sera couvert d'office par la migration vers aiohttp (Phase 4).
- [ ] **0.8 Rotation des secrets Wi-Fi + InfluxDB** *(E14, C13)* — `param.json`
      est suivi dans git et `/conf` les publie en clair : les considérer comme
      compromis. À faire avec la sortie des secrets vers `pydantic-settings` /
      `EnvironmentFile=` et le `git filter-repo` (Phase 3).

## Points de suivi laissés ouverts par la Phase 0

- Le repli chauffage sur perte de capteur est un **OFF sec**, pas un cycle de
  sécurité borné. C'est le compromis retenu ici (risque incendie > risque de
  gel, et l'alarme est visible) ; le repli borné dans le temps appartient à
  l'arbitre thermique unique de la Phase 2.
- Les seuils du chauffage sont des **constantes de module**, pas des champs de
  `param.json` : un nouveau champ ferait diverger le `param.json` du dépôt de
  celui du Pi, que `deploy.sh` restaure à chaque déploiement. À reprendre avec
  le `ConfigStore` de la Phase 3.
- L'alarme chauffage est exposée par `heater_control.get_heater_alarm()` mais
  n'est **pas encore publiée sur `/status`** — à câbler avec le superviseur de
  tâches de la Phase 1.

## Vérification sur le matériel — 2026-08-25, 20:54 → 21:00

Pi sur `master` à `649eb20`, service `active`, `NRestarts=0`, une seule instance.

| Point | Preuve |
|---|---|
| 0.1 Verrou | `@phyto-controller` présent dans `/proc/net/unix`, détenu par le service ; une 2ᵉ acquisition depuis un autre process renvoie `False` ; le verrou disparaît à l'arrêt et est repris au démarrage suivant |
| 0.2 Écriture atomique | `sensor_stats.json` réécrit toutes les ~15-30 s, **mode 644 préservé**, **0 résidu `.tmp`** sur relevés espacés |
| 0.3 Garde de lecture | les 8 tâches démarrées et actives ; `cyclic_timer_1/2` et `motor_temp_control` tournent |
| 0.4 État sûr terminal | **coupure réelle du service** : les 9 broches restent `op` (sorties), génériques à `hi`, moteur à `lo`. GPIO 5/18/27 étaient `lo` (actifs) et 8 était `hi` (vitesse 2) avant l'arrêt → niveaux **écrits**, pas hérités. Journal : `Broches maintenues à l'état sûr (sorties pilotées)` une seule fois → `cleanup_gpio()` idempotent confirmé |
| 0.5 Chauffage | T = 27,1 °C (dans `]-20 ; 60[`), chauffage `disabled` → OFF forcé, GPIO 23 = `hi`. Aucune alarme |
| 0.6 `/monitor` | `GET /monitor?reboot=1&poweroff=1` → **200, le Pi n'a pas redémarré** (uptime 9292 → 9295 s). `POST` origine tierce → **403** journalisé. `POST` → **303 + `Location`**. `DELETE` → **405 + `Allow`** |

Sans le correctif 0.4, `systemctl stop phyto` laissait le **chauffage 230 V en
état de commande** (GPIO 23 retombant au pull-down) sans régulateur jusqu'au
démarrage suivant. C'est le mode de panne le plus coûteux de la phase 0.

## Suite

Phase 1 (« état sûr » structurel : PinRegistry, superviseur de tâches,
`energized()`, watchdog par heartbeats) — voir `AUDIT-2026-08-25.md` § 8.
**Des travaux de phase 1 sont en cours dans l'arbre de travail** (`utils/supervisor.py`,
`beat()`/`hb_sleep()` dans les handlers, `Component.energized()`) : non commités
au moment de la rédaction de ce bilan, donc non vérifiés ici.
