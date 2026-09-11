# Variables d'environnement

Variables lues par le contrôleur (`main.py` et les modules qu'il charge) :

| Variable | Défaut | Usage | Production observée |
|---|---|---|---|
| `PHYTO_DATA_DIR` | absent → `param/` du dépôt | Répertoire unique des données écrites à l'exécution : `param.json` et `.bak`, `runtime_state.json`, `sensor_stats.json`, `equipment_metadata.json`, `.csrf_token`, `operator_history.sqlite3`, `cultures.sqlite3` et `culture_media/`. Rendu absolu et mémorisé au premier accès. Si elle est posée mais que le répertoire ne peut être créé ou n'est pas écrivable, `main.py` **s'arrête** avant le verrou d'instance et avant toute broche ; il n'existe volontairement **aucun** repli silencieux vers `param/`, qui ramènerait les écritures dans le répertoire de travail Git | `/home/progradius/phyto-data`, posé par `deploy/phyto.service` |
| `PHYTO_RUN_MODE` | chaîne vide | Marque le lancement service ; conservée pour compatibilité | `service` |
| `PHYTO_HW_WATCHDOG` | `1` | `0` désactive l'ouverture directe de `/dev/watchdog` | `0`, voie systemd utilisée |
| `PHYTO_LOG_LEVEL` | absent | Priorité sur `Log_Settings.level` | Non fixé dans l'unité observée |
| `PHYTO_ALLOWED_HOSTS` | absent | Noms d'hôte HTTP supplémentaires acceptés, séparés par des virgules | Non fixé ; inutile tant que l'accès se fait par IP privée, `localhost` ou `<nom>.local` |
| `PHYTO_HTTPS_PORT` | `0` | Active le second point d'écoute HTTPS ; `0` le désactive | `443`, posé par le drop-in `deploy/phyto.service.d/pwa-tls.conf` |
| `PHYTO_TLS_CERT_FILE` | absent | Certificat serveur PEM, requis avec un port HTTPS non nul | `/etc/phyto/tls/server.crt`, même drop-in |
| `PHYTO_TLS_KEY_FILE` | absent | Clé privée PEM lisible par l'utilisateur du service, requise avec le certificat | `/etc/phyto/tls/server.key`, même drop-in |
| `PHYTO_VERSION` | absent | Commit annoncé par `/health/live` et `/api/v1/state` quand le processus tourne hors d'un checkout Git (image sans métadonnées) ; prioritaire sur la lecture de `.git` | Non fixé : le commit est lu dans le checkout |
| `PYTHONUNBUFFERED` | Python par défaut | Logs immédiats | `1` |
| `NOTIFY_SOCKET` | fourni par systemd | Active `sd_notify` | Fourni avec `Type=notify` |
| `WATCHDOG_USEC` | fourni par systemd | Timeout watchdog applicatif | 600 s observés |
| `WATCHDOG_PID` | fourni éventuellement par systemd | Vérifie le destinataire | Géré par systemd |
| `PHYTO_FAKE_TIME_UNSYNCED` | absent | Injection de vérification : `1` force l'état temporel `unknown` | **Jamais en production nominale** |
| `PHYTO_FAKE_CONTROL_UNHEALTHY` | absent | Injection de vérification : `1` force `control_healthy()` à faux | **Jamais en production nominale** |

`PHYTO_DATA_DIR` appartient à l'**unité systemd**, pas à la session de l'exploitant : un shell ne la
voit pas. Les commandes d'exploitation la relisent avec `systemctl show`, comme `scripts/deploy.sh`,
et ne l'écrivent jamais sous la forme `${PHYTO_DATA_DIR:-param}` — voir
[Répertoire des données vivantes](../operations/backup-and-restore.md#répertoire-des-données-vivantes)
et la [migration](../operations/migration-donnees-vivantes.md).

Variables des scripts d'exploitation :

| Variable | Script | Usage |
|---|---|---|
| `PHYTO_HOST` | `scripts/phyto-ssh.sh`, `scripts/Invoke-PhytoSsh.ps1` | Cible du pont SSH, défaut `phyto` |
| `PHYTO_APP_DIR` | `scripts/deploy.sh` | Chemin interne transmis lors de la ré-exécution du déploiement |
| `PHYTO_DEPLOY_REEXEC` | `scripts/deploy.sh` | Garde interne : `1` dans la copie ré-exécutée depuis `/tmp` |
| `PHYTO_DEPLOY_HEALTH_VALIDATOR` | `scripts/deploy.sh` | Chemin interne de la copie sous `/tmp` de `utils/deployment_health.py`, qualifiant la santé après redémarrage ; posé par le script lui-même, jamais à la main |
| `PHYTO_UI_BASE_URL` | `scripts/benchmark-web-pages.py` | Origine visée par défaut (même validation que l'option en ligne de commande) |
| `PHYTO_OBSERVATION_SERVICE`, `PHYTO_OBSERVATION_API_BASE`, `PHYTO_OBSERVATION_SECONDS`, `PHYTO_OBSERVATION_INTERVAL_SECONDS`, `PHYTO_OBSERVATION_DIR` | `scripts/observe-jalon2-operator-quality.sh` | Service, API, durée (172 800 s), période (60 s) et répertoire de preuve (`~/phyto-observations`) de l'observateur de 48 h des jalons clos (l'observateur du jalon 1, qui lisait les mêmes variables, a été supprimé le 11/09/2026) |
| `PHYTO_OBSERVATION_DATA_DIR` | `scripts/observe-jalon2-operator-quality.sh` | Variable interne : le script se la passe à lui-même pour sa sonde Influx, jamais à la main. Elle vaut le `PHYTO_DATA_DIR` **lu dans l'unité systemd** (`systemctl show -p Environment`, comme `scripts/deploy.sh`), à défaut `<checkout>/param` ; la valeur retenue est consignée dans `metadata.txt` (`donnees=`). Un `PHYTO_DATA_DIR` de l'environnement de l'observateur est ignoré |
| `PHYTO_OBSERVATION_PROBE_INTERVAL_SECONDS`, `PHYTO_OBSERVATION_EXPECTED_COMMIT` | `scripts/observe-jalon2-operator-quality.sh` | Période des sondes lentes (600 s) et commit attendu (défaut : `HEAD`) |

Les procédures qui utilisent ces observateurs sont archivées :
[Procédures d'observation des jalons 1 et 2](../archive/operations/procedures-observation-jalons-1-2.md).

Variables des tests navigateur (`npm run test:ui`, `npm run measure:ui`), sans effet sur le
contrôleur :

| Variable | Usage |
|---|---|
| `PHYTO_UI_BASE_URL` | Cible externe au lieu du serveur de test local ; les tests mutateurs sont alors ignorés, et la mesure reste strictement en lecture. Une origine HTTP(S) nue, sans identifiant ni chemin |
| `PHYTO_TEST_PYTHON` | Interpréteur qui lance `tests/ui_server.py` — le zygote de chaque worker Playwright et la mesure (défaut `python3`), par exemple `~/.venvs/phyto/bin/python` ; un chemin avec espace est accepté |
| `PHYTO_UI_TEST_PORT` | Port du serveur de test `tests/ui_server.py` lancé à la main (défaut `38123`) ; `0` laisse le noyau choisir un port libre, que le serveur annonce par la ligne `PHYTO_UI_READY <port>`. La suite Playwright n'en utilise aucun : ses serveurs, dupliqués par le zygote, prennent tous un port libre |
| `PHYTO_UI_RUN_ID` | Posée par `playwright.config.js` (PID du processus principal) et héritée par les workers : nomme le dossier de résultats de l'exécution, `/tmp/phyto-playwright-results-<id>`. Ne pas la poser à la main |
| `PHYTO_UI_MEASURE_SCENARIO` | `critical` fait publier une alarme critique factice par `tests/ui_server.py` ; posé par les fixtures et la mesure |
| `PHYTO_UI_MEASURE_PORT` | Port du serveur lancé par `tests/ui/measure_pages.js` (défaut `40123`) |
| `PHYTO_MEASURE_WIDTHS` | Largeurs mesurées, séparées par des virgules (défaut `320,390,1440`) |
| `PHYTO_MEASURE_DIR` | Répertoire des résultats de mesure (défaut `test-results/measure-ui`) |
| `PHYTO_MEASURE_SCREENSHOTS` | `1` enregistre les captures pendant la mesure |
| `PHYTO_MEASURE_HEIGHT` | Hauteur de fenêtre imposée à toutes les largeurs (défaut : fenêtres de l'audit, 844 px à 320 et 390, 900 px à 1440) |
| `PHYTO_MEASURE_PERIMETRE` | `audit` ne joue que les 36 visites de l'audit sur un carnet vide (rejeu d'une révision ancienne) ; défaut `complet` |
| `PHYTO_MEASURE_ROOT` | Arbre servi par `tests/ui_server.py` pendant la mesure (défaut : répertoire courant) ; sert au rejeu d'une extraction, sans rien y recopier |
| `PHYTO_CAPTURE` | Active la capture de preuve de `tests/ui/history.spec.js`, ignorée sinon |
| `PHYTO_CAPTURE_DIR` | Répertoire où cette capture est écrite (défaut : dossier de résultats Playwright, jamais `docs/`) ; `npm run measure:capture-gris` le pose pour régénérer volontairement la capture publiée |

Ne pas placer de secret directement dans une commande shell enregistrée. La future séparation des secrets devra utiliser un `EnvironmentFile` protégé, sans exposer les valeurs dans la documentation ni dans `systemctl status`.

Les trois variables TLS sont une configuration d'exploitation et ne vont pas dans `param.json`. Une
configuration absente laisse HTTP seul ; une configuration partielle ou illisible journalise l'échec
HTTPS mais ne coupe ni HTTP `:8123`, ni la régulation. Voir [PWA et TLS local](../operations/pwa-local-tls.md).
