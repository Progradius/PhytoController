# Interface HTTP

**Implémentation** : serveur `aiohttp` (`network/web/server.py`), écoute HTTP `0.0.0.0:8123` et,
si les trois variables TLS sont valides, HTTPS `0.0.0.0:443` dans le même processus.
**Contrainte** : LAN de confiance uniquement, aucune authentification.
**Statut** : implémenté, **déployé et vérifié sur le Pi** le 25 août 2026 (commit `ad39de2`) —
relevé dans [Baseline web du 25 août 2026](../operations/web-baseline-2026-08-25.md).

## Routes

| Méthode | Route | Effet | Réponse principale |
|---|---|---|---|
| GET | `/`, `/index.html` | Tableau de bord, rafraîchi toutes les 5 s par `/api/v1/state` | HTML 200 |
| GET | `/history` | Historique détaillé sur 24, 48 ou 72 h, alimenté par `/api/v1/history` | HTML 200 |
| GET | `/conf` | Formulaire de configuration, une section dépliable par domaine | HTML 200 |
| POST | `/conf/{section}` | Valide et enregistre **une seule** section | 303 vers `/conf?flash=…` ; 422 si refus |
| GET | `/console` | Console de journalisation | HTML 200 |
| GET | `/console/stream` | Historique puis logs live (SSE, keep-alive 15 s) | Flux 200 |
| GET | `/api/v1/state` | État complet versionné | JSON 200 |
| GET | `/api/v1/alarms` | Occurrences filtrées, actives ou résolues | JSON 200 |
| GET | `/api/v1/alarms/active` | Snapshot léger des occurrences actives en mémoire, sans SQLite ni lecture matérielle | JSON 200 |
| GET | `/api/v1/history?hours=24\|48\|72` | Tendances locales agrégées | JSON 200 ou 503 |
| POST | `/api/v1/config/preview` | Projette une saisie sur un candidat complet **sans rien écrire** | JSON 200 ; 400, 403 ou 429 |
| GET | `/status` | Ancien format d'état, conservé pour les scripts existants | JSON 200 |
| GET | `/health/live` | Le processus HTTP répond et annonce le commit chargé | JSON 200, `live=true`, `version` |
| GET | `/health/ready` | Superviseur sain | JSON 200 ou **503** |
| POST | `/actions/stats/reset` | Efface un min/max (`key=`) | JSON si demandé, sinon 303 vers la carte du capteur |
| POST | `/actions/overrides/create`, `/actions/overrides/cancel` | Pose ou lève une coupure opérateur temporaire | JSON si demandé, sinon 303 vers l'actionneur ou la maintenance |
| POST | `/actions/system/reboot` | `sudo reboot` | 202 |
| POST | `/actions/system/poweroff` | `/sbin/shutdown -h now` | 202 |
| GET | `/monitor` | **Redirection** vers `/#surveillance` | 303 |
| POST | `/monitor` | Compatibilité : `reset_sensor`, `reboot=1`, `poweroff=1` | Comme les routes dédiées |
| GET | `/favicon.ico`, `/favicon.svg` | Icône | 302 puis fichier |
| GET | `/app.webmanifest`, `/service-worker.js`, `/offline` | Manifeste, worker racine et repli PWA | Manifeste/JS/HTML 200 |
| GET | `/static/css/style.css`, `/static/js/*.js`, `/static/fonts/visitor1.ttf` | Assets locaux | Fichier |
| GET | `/static/icons/pwa-*.png` | Icônes PWA normale et maskable | PNG |

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

Ce qui **reste ouvert** : aucune authentification. HTTPS authentifie le contrôleur pour les terminaux
qui ont installé l'autorité locale, mais n'authentifie pas l'opérateur. Ne jamais exposer `8123` ou
`443` sur Internet ni sur un réseau partagé avec des clients non maîtrisés.

## Cache PWA et fraîcheur

Le service worker n'est enregistré que depuis une origine sécurisée. Il précache les assets hachés,
garde la dernière réponse HTML 200 de `/`, `/history` et `/alarms`, et fournit `/offline` aux autres navigations
injoignables. Ses règles sont volontairement asymétriques :

- `/api/v1/**`, `/health/**`, `/status` et le SSE restent **réseau uniquement** ;
- toute méthode mutante reste réseau uniquement, sans Background Sync ni rejeu ;
- `/conf` et `/console` ne sont jamais conservés comme vues hors ligne ;
- les derniers snapshots d'état, d'alarmes et de chaque période d'historique sont conservés séparément dans IndexedDB,
  puis lus uniquement après l'échec d'une requête réseau ;
- une réponse IndexedDB ne retire jamais la bannière « HORS LIGNE » et ne déclenche jamais de
  notification ; seule une nouvelle réponse HTTP du contrôleur le peut.

La PWA demande la permission de notification uniquement sur clic. Elle notifie les nouvelles alarmes
affectant le contrôle et toutes les alarmes critiques, avec déduplication par UUID. Il ne s'agit pas de
Web Push : Chrome peut suspendre la page, donc aucune notification n'est garantie PWA fermée.

## Configuration POST

`POST /conf/{section}` suit une séquence stricte :

1. rejet des champs inconnus ou dupliqués (422) ;
2. construction d'un **`AppConfig` candidat complet** à partir de la configuration courante, sur
   lequel la section postée est appliquée ;
3. validation Pydantic intégrale du candidat, contraintes croisées comprises (422 sinon) ;
4. écriture atomique du fichier ; en cas d'échec disque, la configuration active reste
   inchangée (500) ;
5. remplacement de la configuration vivante, puis application à chaud ;
6. `303 See Other` vers `/conf?flash={jeton}#{section}`.

Un rejet à n'importe quelle étape laisse `param.json` **et** la configuration en mémoire
intacts. Les sections connues sont : `simple`, `life`, `daily-timer-1`, `daily-timer-2`,
`day-night`, `cyclic-1`, `cyclic-2`, `temperature`, `heater`, `motor`, `sensors`,
`sensor-quality`, `equipment`, `wifi`, `influx`, `logs`.

Le jeton de redirection est **opaque** : le compte rendu — champs modifiés, heure, mode
d'application — reste côté serveur, à usage unique et périmé au bout de trois minutes, plutôt que
recopié dans une URL rejouable ou partageable. L'ancien `?success={section}` reste accepté.

`GPIO_Settings` n'est **pas** exposé en écriture : la page l'affiche en lecture seule.

### Refus sans perte de saisie

Un 422 re-rend la **saisie postée**, pas la configuration enregistrée : corriger un champ
n'oblige jamais à ressaisir le reste de la section. Le message est placé sous le champ concerné
(`aria-invalid`, `aria-describedby`), traduit depuis les types d'erreur Pydantic avec la borne
refusée, et une contrainte croisée — minimum/maximum de jour, de nuit, vitesse minimale/maximale —
est rattachée à ses **deux** champs plutôt qu'au bandeau global. Un champ numérique refusé se
re-rend en `type="text"` : `type="number"` vide silencieusement une saisie non numérique, et la
valeur rejetée resterait invisible.

Un secret n'est **jamais** réémis, refusé ou non : il repartirait dans le HTML d'une interface
sans authentification. Le champ revient vide, avec la mention « laisser vide pour conserver ».

Le registre `SECTION_FIELDS` de `network/web/server.py` est la source unique des cibles et des
libellés ; l'index inverse « clé JSON → champ de formulaire » en est **dérivé**, ce qui permet de
reposer un refus Pydantic sur le champ réellement saisi, horaires compris.

### Prévisualisation

`POST /api/v1/config/preview` projette une saisie sur un candidat `AppConfig` complet **sans
écrire quoi que ce soit**. Corps JSON `{"section": "...", "fields": {...}}`, jeton en en-tête
`X-CSRF-Token` (le middleware CSRF consomme `request.post()`, qui laisse intact un corps JSON).
La réponse porte les écarts détectés, les refus humanisés et l'arbitrage thermique effectif. Les
**deux** hystérésis du système y sont lisibles, car elles ne se voient pas dans le formulaire :

- celle du **chauffage** — `heater_on_at_or_below`, `heater_off_above`, `heater_hysteresis` :
  la bande morte dans laquelle le chauffage reste dans son état, allumé sous la consigne basse et
  coupé seulement au-dessus de consigne basse + hystérésis ;
- celle des **paliers de ventilation** — `vent_release` et, pour chaque palier, `starts_at` et
  `releases_below` : un palier engagé ne redescend que sous un seuil distinct, et jamais avant
  `min_dwell_seconds`. Sans ce second seuil affiché, une température oscillant d'un dixième autour
  du seuil d'engagement semblerait inoffensive alors qu'elle ferait battre le relais.

S'y ajoutent le **seuil de ventilation reconstruit** avec son indicateur « relevé » et l'écart en
degrés par rapport à la consigne saisie, et l'échelle des paliers avec la vitesse réellement
commandée après `clamp_speed`.

C'est le seul moyen de voir avant enregistrement que `vent_threshold` peut dépasser la consigne
haute saisie de l'hystérésis plus la zone morte — un écart que le formulaire seul tairait. Les
formules ne sont pas rejouées en JavaScript : `components/climate_policy.preview_thresholds()`
réutilise `settings_from_config`, `vent_threshold` et `clamp_speed`, ceux-là mêmes que `decide()`
utilisera.

Garde-fous : une prévisualisation à la fois par processus, intervalle minimum de 0,4 s (429
sinon), corps jamais journalisé, aucun champ sensible dans la réponse, et `sensor-quality` comme
`equipment` refusées (400) car elles ne passent pas par le même parseur.

### Mode Simple

`POST /conf/simple` regroupe la conduite courante en **une seule sauvegarde atomique** : planning
jour/nuit, les deux minuteries d'éclairage, consignes de jour et de nuit, humidité maximale,
intensité de ventilation, saison et chauffage. Il impose en plus un profil de réglages fins
(hystérésis, zone morte, palier, relâchement, maintien, plancher, repli capteur, marges et budgets
hiver, vitesse minimale et vitesse hiver par défaut). Ces valeurs sont **celles de la configuration
déployée**, décision opérateur du 28 août 2026 : passer en mode Simple ne change donc rien tant que
l'opérateur ne touche pas aux champs exposés, et tout écart restant est listé dans le formulaire
comme dans la prévisualisation avant l'enregistrement.

L'intensité écrit `max_speed` et `winter_refresh_speed` — douce 2/2, normale 3/3, forte 4/4.
Rappel matériel : les vitesses moteur 1 et 3 sont hors service côté puissance, « normale » commande
donc une vitesse morte tant que la panne dure ; c'est l'annotation `out_of_service` des métadonnées
d'équipement qui porte cette information.

`intensity` et `season` sont **obligatoires** : leur absence est un refus, pas un « inchangé ».
C'est ce qui force le choix explicite quand le moteur est en pilotage manuel — aucune saison n'est
alors présélectionnée, et le mode Simple refuse par ailleurs de faire *entrer* en manuel.

Côté interface, le sélecteur Simple / Avancé n'apparaît **que si la prévisualisation répond** : le
mode Simple écrit de vrais paramètres thermiques, et il ne se livre pas sans le retour qui les rend
visibles. Le choix est mémorisé en `localStorage`, mais une section refusée impose son propre mode,
sans quoi le champ fautif serait masqué. Chaque formulaire suit ses écarts réels : un bouton
d'annulation restaure la saisie initiale et un garde `beforeunload` retient la page tant qu'une
modification n'est pas enregistrée.

### Application à chaud

| Section | Effet immédiat |
|---|---|
| `logs` | `apply_log_settings()` : niveau et rétention |
| `sensors` | `SensorController.reconfigure()` sur la même instance, puis rechargement Influx |
| `influx` | Rechargement de l'endpoint Influx |
| `daily-timer-*`, `cyclic-*` | `supervisor.request_reload()` du minuteur concerné |
| `temperature`, `heater`, `motor`, `sensors` | `supervisor.request_reload()` de `climate_control` : chauffage et ventilation repartent ensemble sur la nouvelle consigne |
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
  `DS18B#3`) ; toute autre clé renvoie 400. L'amélioration JavaScript demande du JSON et met la
  carte à jour seulement après la réponse ; le formulaire HTML reste le repli complet ;
- `POST /actions/overrides/create` et `/actions/overrides/cancel` utilisent la même amélioration
  progressive. Aucun ordre n'est optimiste, mémorisé hors ligne ou rejoué ;
- `POST /actions/system/reboot` et `/actions/system/poweroff` : jeton CSRF **et** confirmation
  explicite dans une boîte de dialogue du navigateur ; réponse 202, ou 500 si la commande
  échoue ;
- `POST /monitor` reste accepté pour les scripts existants et redirige vers les mêmes
  traitements.

Ne jamais déplacer une de ces actions derrière un GET : une préconnexion de navigateur ou un
`<img src>` sur n'importe quelle page du LAN suffirait à l'exécuter.
