# Interface HTTP

**Implémentation** : serveur `aiohttp` (`network/web/server.py`), écoute `0.0.0.0:8123`.
**Contrainte** : LAN de confiance uniquement, aucune authentification.
**Statut** : implémenté, **déployé et vérifié sur le Pi** le 25 août 2026 (commit `ad39de2`) —
relevé dans [Baseline web du 25 août 2026](../operations/web-baseline-2026-08-25.md).

## Routes

| Méthode | Route | Effet | Réponse principale |
|---|---|---|---|
| GET | `/`, `/index.html` | Tableau de bord, rafraîchi toutes les 5 s par `/api/v1/state` | HTML 200 |
| GET | `/conf` | Formulaire de configuration, une section dépliable par domaine | HTML 200 |
| POST | `/conf/{section}` | Valide et enregistre **une seule** section | 303 vers `/conf?success=…` ; 422 si refus |
| GET | `/console` | Console de journalisation | HTML 200 |
| GET | `/console/stream` | Historique puis logs live (SSE, keep-alive 15 s) | Flux 200 |
| GET | `/api/v1/state` | État complet versionné | JSON 200 |
| GET | `/status` | Ancien format d'état, conservé pour les scripts existants | JSON 200 |
| GET | `/health/live` | Le processus HTTP répond | JSON 200 |
| GET | `/health/ready` | Superviseur sain | JSON 200 ou **503** |
| POST | `/actions/stats/reset` | Efface un min/max (`key=`) | 303 vers `/#statistiques` |
| POST | `/actions/system/reboot` | `sudo reboot` | 202 |
| POST | `/actions/system/poweroff` | `/sbin/shutdown -h now` | 202 |
| GET | `/monitor` | **Redirection** vers `/#surveillance` | 303 |
| POST | `/monitor` | Compatibilité : `reset_sensor`, `reboot=1`, `poweroff=1` | Comme les routes dédiées |
| GET | `/favicon.ico`, `/favicon.svg` | Icône | 302 puis fichier |
| GET | `/static/css/style.css`, `/static/js/*.js`, `/static/fonts/visitor1.ttf` | Assets locaux | Fichier |

Toute autre route renvoie 404. Il n'existe **pas** de service de répertoire : la liste ci-dessus
est la liste exhaustive des chemins servis, ce qui remplace l'ancien `/static/` non confiné.

## Règles de sécurité appliquées

- Aucun effet persistant ou destructeur derrière un GET.
- **CSRF** : jeton comparé en temps constant sur `POST`, `PUT`, `PATCH`, `DELETE`, présent dans
  chaque formulaire et dans `<meta name="csrf-token">`. Il est **persistant** : conservé dans
  `param/.csrf_token` (mode 0600, hors git), il survit à un redémarrage du service, de sorte
  qu'une page laissée ouverte pendant un `systemctl restart` reste valide. Un fichier absent,
  illisible ou corrompu entraîne la génération d'un nouveau jeton ; si l'écriture échoue, le
  serveur retombe sur un jeton en mémoire et le journalise.
- **Origin** : un `Origin` présent et différent du `Host` est refusé (403). Une requête sans
  `Origin`, telle que `curl`, reste acceptée : le jeton CSRF est alors la seule barrière.
- **Host** : seuls `localhost`, le nom de la machine, `<nom>.local`, les adresses privées, de
  bouclage ou de lien local sont acceptés ; sinon **421**. Cela ferme le DNS rebinding.
  `PHYTO_ALLOWED_HOSTS` (liste séparée par des virgules) ajoute des noms.
- **Corps** : 64 Kio maximum, lignes et en-têtes plafonnés à 8190 octets.
- **En-têtes** : `Content-Security-Policy` sans `unsafe-inline` (aucun script ni style en ligne
  dans les pages), `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, et
  `Cache-Control: no-store` sur tout le contenu dynamique.
- **Erreurs** : un navigateur reçoit une page HTML, un client non-HTML le texte brut. Les
  redirections ne sont jamais transformées en page d'erreur.
- **Secrets** : `/conf` n'affiche plus aucun mot de passe. Les champs sensibles sont vides et
  indiquent seulement si une valeur est enregistrée ; les laisser vides conserve l'existant.

Ce qui **reste ouvert** : aucune authentification, port en clair. Ne pas exposer 8123 sur
Internet ni sur un réseau partagé avec des clients non maîtrisés.

## Configuration POST

`POST /conf/{section}` suit une séquence stricte :

1. rejet des champs inconnus ou dupliqués (422) ;
2. construction d'un **`AppConfig` candidat complet** à partir de la configuration courante, sur
   lequel la section postée est appliquée ;
3. validation Pydantic intégrale du candidat, contraintes croisées comprises (422 sinon) ;
4. écriture atomique du fichier ; en cas d'échec disque, la configuration active reste
   inchangée (500) ;
5. remplacement de la configuration vivante, puis application à chaud ;
6. `303 See Other` vers `/conf?success={section}#{section}`.

Un rejet à n'importe quelle étape laisse `param.json` **et** la configuration en mémoire
intacts. Les sections connues sont : `life`, `daily-timer-1`, `daily-timer-2`, `cyclic-1`,
`cyclic-2`, `temperature`, `heater`, `motor`, `sensors`, `wifi`, `influx`, `logs`.

`GPIO_Settings` n'est **pas** exposé en écriture : la page l'affiche en lecture seule.

### Application à chaud

| Section | Effet immédiat |
|---|---|
| `logs` | `apply_log_settings()` : niveau et rétention |
| `sensors` | `SensorController.reconfigure()` sur la même instance, puis rechargement Influx |
| `influx` | Rechargement de l'endpoint Influx |
| `daily-timer-*`, `cyclic-*`, `temperature`, `heater`, `motor` | `supervisor.request_reload()` du ou des travaux concernés |
| `wifi` | Aucun : redémarrage requis, la page l'indique |

`request_reload()` annule puis relance le travail **sans repositionner son état sûr** : la
tâche était saine, et couper la charge à chaque enregistrement ferait clignoter le relais. Une
sortie garde donc son état pendant que la boucle repart et le réévalue immédiatement.

Une exception subsiste, et elle est voulue : un timer cyclique annulé **pendant sa fenêtre ON**
voit le `finally` de `Component.energized()` couper sa sortie. Une sortie ne doit jamais rester
fermée alors que la boucle qui la surveille a disparu ; la fenêtre suivante reprend
normalement.

## Actions système

- `POST /actions/stats/reset` avec `key=` parmi les clés suivies (`BME280T`, `BME280H`,
  `DS18B#3`) ; toute autre clé renvoie 400 ;
- `POST /actions/system/reboot` et `/actions/system/poweroff` : jeton CSRF **et** confirmation
  explicite dans une boîte de dialogue du navigateur ; réponse 202, ou 500 si la commande
  échoue ;
- `POST /monitor` reste accepté pour les scripts existants et redirige vers les mêmes
  traitements.

Ne jamais déplacer une de ces actions derrière un GET : une préconnexion de navigateur ou un
`<img src>` sur n'importe quelle page du LAN suffirait à l'exécuter.
