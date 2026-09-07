# Variables d'environnement

| Variable | Défaut | Usage | Production observée |
|---|---|---|---|
| `PHYTO_RUN_MODE` | chaîne vide | Marque le lancement service ; conservée pour compatibilité | `service` |
| `PHYTO_HW_WATCHDOG` | `1` | `0` désactive l'ouverture directe de `/dev/watchdog` | `0`, voie systemd utilisée |
| `PHYTO_LOG_LEVEL` | absent | Priorité sur `Log_Settings.level` | Non fixé dans l'unité observée |
| `PHYTO_ALLOWED_HOSTS` | absent | Noms d'hôte HTTP supplémentaires acceptés, séparés par des virgules | Non fixé ; inutile tant que l'accès se fait par IP privée, `localhost` ou `<nom>.local` |
| `PHYTO_HTTPS_PORT` | `0` | Active le second point d'écoute HTTPS ; `0` le désactive | `443` prévu pour la PWA locale |
| `PHYTO_TLS_CERT_FILE` | absent | Certificat serveur PEM, requis avec un port HTTPS non nul | `/etc/phyto/tls/server.crt` prévu |
| `PHYTO_TLS_KEY_FILE` | absent | Clé privée PEM lisible par l'utilisateur du service, requise avec le certificat | `/etc/phyto/tls/server.key` prévu |
| `PYTHONUNBUFFERED` | Python par défaut | Logs immédiats | `1` |
| `NOTIFY_SOCKET` | fourni par systemd | Active `sd_notify` | Fourni avec `Type=notify` |
| `WATCHDOG_USEC` | fourni par systemd | Timeout watchdog applicatif | 600 s observés |
| `WATCHDOG_PID` | fourni éventuellement par systemd | Vérifie le destinataire | Géré par systemd |
| `PHYTO_FAKE_TIME_UNSYNCED` | absent | Injection de vérification : force l'état temporel `unknown` | **Jamais en production nominale** |
| `PHYTO_FAKE_CONTROL_UNHEALTHY` | absent | Injection de vérification : force `control_healthy()` à faux | **Jamais en production nominale** |

Variables des scripts locaux :

| Variable | Usage |
|---|---|
| `PHYTO_HOST` | Cible du pont SSH, défaut `phyto` |
| `PHYTO_APP_DIR` | Chemin interne transmis lors de la ré-exécution du déploiement |
| `PHYTO_DEPLOY_REEXEC` | Garde interne du script de déploiement |

Ne pas placer de secret directement dans une commande shell enregistrée. La future séparation des secrets devra utiliser un `EnvironmentFile` protégé, sans exposer les valeurs dans la documentation ni dans `systemctl status`.

Les trois variables TLS sont une configuration d'exploitation et ne vont pas dans `param.json`. Une
configuration absente laisse HTTP seul ; une configuration partielle ou illisible journalise l'échec
HTTPS mais ne coupe ni HTTP `:8123`, ni la régulation. Voir [PWA et TLS local](../operations/pwa-local-tls.md).
