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
| GET | `/alarms` | Alarmes actives et occurrences résolues, alimentées par `/api/v1/alarms` | HTML 200 |
| GET | `/app` | Page de **cet appareil** : type de connexion, installation, inventaire des copies hors ligne, notifications locales, version active du service worker. Page de lecture, sans CSRF ni secret, mise en cache comme les autres pages de lecture | HTML 200 |
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
| POST | `/actions/history/notes` | Ajoute une annotation opérateur sans effet sur la régulation | JSON 201 si demandé, sinon 303 vers `/history#operator-notes` |
| POST | `/actions/system/reboot` | `sudo reboot` | 202 |
| POST | `/actions/system/poweroff` | `/sbin/shutdown -h now` | 202 |
| GET | `/monitor` | **Redirection** vers `/#surveillance` | 303 |
| POST | `/monitor` | Compatibilité : `reset_sensor`, `reboot=1`, `poweroff=1` | Comme les routes dédiées |
| GET | `/favicon.ico`, `/favicon.svg` | Icône | 302 puis fichier |
| GET | `/app.webmanifest`, `/service-worker.js`, `/offline` | Manifeste, worker racine et repli PWA | Manifeste/JS/HTML 200 |
| GET | `/cultures…`, `/api/v1/cultures/…` | Carnet de cultures — contrat détaillé dans [API du carnet](cultures-api.md) | HTML / JSON |
| GET | `/static/css/style.css`, `/static/js/*.js`, `/static/fonts/visitor1.ttf` | Assets locaux | Fichier |
| GET | `/static/icons/pwa-*.png` | Icônes PWA normale et maskable | PNG |

Toute autre route renvoie 404. Il n'existe **pas** de service de répertoire : les chemins servis sont
exactement ceux de la liste ci-dessus et ceux du carnet, ce qui remplace l'ancien `/static/` non confiné.

### Paramètres de lecture

Ces paramètres ne changent **que** ce qui est affiché : aucune écriture, aucune persistance, aucune
route nouvelle. Une valeur inconnue retombe sur le défaut, elle n'est jamais un refus.

| Route | Paramètre | Effet |
|---|---|---|
| `GET /cultures/solutions` | `view=saisir\|releves\|analyser` | Choisit la vue servie. Les trois panneaux sont rendus ; ceux qui ne sont pas la vue courante portent `hidden`. Sans `view`, le défaut se déduit de la demande : `kind=` ouvre la saisie, `entry=` montre les relevés, une cible encore sans relevé ouvre la saisie, sinon les relevés |
| `GET /cultures/cycles` | `view=faire\|comparer` | Idem, défaut `faire` — tout ce qui vit dans « Comparer » (comparaison, synthèse climatique, détail horaire, vérifications) n'est dans la page qu'avec `view=comparer` |
| `GET /cultures/{id}` | `retour=<chemin>` | Adresse de retour contextualisée, émise par les liens du journal (vue courante, filtres normalisés et pagination). Acceptée **seulement** si elle commence par `/cultures` et ne contient ni `//` initial ni `\` ; sinon simplement ignorée, le retour restant non contextualisé |
| `GET /cultures/targets` | `at=<AAAA-MM-JJ>` | Date à laquelle la plage applicable est résolue (défaut : aujourd'hui). Une date impossible est refusée (400), avec ou sans cible |

Les « onglets » de vue sont des **liens** qui rechargent la page : l'état actif se lit sur
`aria-current="page"`, jamais sur un `role="tab"`/`aria-selected`, qui promettraient un panneau
échangé sur place. La navigation du carnet conserve la vue de « Solutions et relevés » d'une
rubrique à l'autre.

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
  redirections ne sont jamais transformées en page d'erreur. La page porte au plus trois liens,
  tous décidés par le serveur (`_error_response`) :
  - **« Revenir à la page précédente »** — seulement si l'en-tête `Referer` désigne la **même
    origine** que la requête (même schéma, même hôte, hôte lui-même dans la liste autorisée,
    sans identifiants dans l'URL). Il est réémis en **chemin seul** — chemin, requête, ancre —,
    jamais en URL absolue, et un résultat commençant par `//` est écarté : une page d'erreur ne
    doit pas pouvoir offrir un lien sortant choisi par l'appelant ;
  - **« Réessayer »** — seulement pour une requête **GET** dont le statut est 500, 502, 503 ou
    504. Jamais après un POST (rejouer une mutation n'est pas une réparation), jamais sur un 4xx,
    qu'un simple renvoi ne corrigerait pas ;
  - **« Retour au tableau de bord »** — toujours.
- **Secrets** : `/conf` n'affiche plus aucun mot de passe. Les champs sensibles sont vides et
  indiquent seulement si une valeur est enregistrée ; les laisser vides conserve l'existant.

Ce qui **reste ouvert** : aucune authentification. HTTPS authentifie le contrôleur pour les terminaux
qui ont installé l'autorité locale, mais n'authentifie pas l'opérateur. Ne jamais exposer `8123` ou
`443` sur Internet ni sur un réseau partagé avec des clients non maîtrisés.

## Cache PWA et fraîcheur

Le service worker n'est enregistré que depuis une origine sécurisée. Il précache les assets hachés,
garde la dernière réponse HTML 200 de `/`, `/history`, `/alarms` et `/app`, et fournit `/offline` aux autres
navigations injoignables.

Le service worker applique un budget d'attente explicite : 8 s pour une navigation de page
(`/`, `/history`, `/alarms`, `/app`, pages du carnet et photos), 15 s pour le préchargement des
ressources hachées et le préchauffage des pages de lecture. `/api/`, `/actions/`, `/health/`,
`/status` et `/console/stream` restent **réseau uniquement** : jamais mis en cache, et sans aucun
budget du worker — c'est la requête de la page qui décide de son propre délai. Seule l'adresse
**sans paramètres** de `/`, `/history`, `/alarms` et `/app` est conservée comme page ; une adresse
filtrée n'est pas une vue hors ligne. Le repli sur une copie datée n'a lieu que sur un **échec de transport** (erreur réseau
ou expiration du budget) : une réponse HTTP du contrôleur est toujours servie telle quelle, et une
réponse **5xx n'est jamais remplacée par une copie ni mise en cache** — c'est la page d'erreur du
serveur qui s'affiche. Le worker n'active jamais une nouvelle version de lui-même : une version
installée attend le message `{type:"activer"}` envoyé par le bouton « Mettre à jour ».

Ce bouton est unique dans la page : il vit dans la bannière de mise à jour de `base.html`, et `/app`
n'en porte pas de second. Après activation, la page ne se recharge que si aucune saisie n'est en
cours (`window.PhytoForms.isDirty()` faux) ; sinon la mise à jour est annoncée comme effective à la
prochaine ouverture. Les caches d'une version précédente ne sont supprimés qu'à l'activation, après
`clients.claim()` : une page déjà ouverte, hors ligne comprise, continue de lire les copies de sa
propre version tant que l'opérateur n'a pas activé la suivante.

L'inventaire des copies conservées est rendu par un fragment partagé (`templates/offline_index.html`,
section `#copies`) inclus par `/app`, `/offline`, `/cultures/cycles` et `/cultures/journal` : date de
la dernière copie, liste des pages du carnet conservées, et le rappel que les filtres qui nécessitent
le serveur restent indisponibles hors ligne.

Ses règles sont volontairement asymétriques :

- `/api/v1/**`, `/health/**`, `/status` et le SSE restent **réseau uniquement** ;
- toute méthode mutante reste réseau uniquement, sans Background Sync ni rejeu ;
- `/conf` et `/console` ne sont jamais conservés comme vues hors ligne ;
- les derniers snapshots d'état, d'alarmes et de chaque période d'historique sont conservés séparément dans IndexedDB,
  puis lus uniquement après l'échec d'une requête réseau ;
- une réponse IndexedDB ne retire jamais la bannière « HORS LIGNE » et ne déclenche jamais de
  notification ; seule une nouvelle réponse HTTP du contrôleur le peut.

Le verdict de connexion a **un seul propriétaire**, dans `static/js/pwa.js`. Les boucles métier ne
déclarent plus de panne : elles signalent un échec de transport, et la décision se prend sur une
seule grandeur, le **temps de silence** — aucune réponse du contrôleur, quelle qu'elle soit, 5xx
compris — avec un seuil de 20 s. Un échec isolé ne bascule donc plus l'interface en lecture seule.
L'entrée est immédiate dans un seul cas, et il repose sur une preuve : une page servie par le cache
du service worker (marquée `phyto-offline-shell`, ou `phyto-offline-snapshot` pour le carnet), dont
la navigation a donc réellement échoué. Deux horloges cohabitent sans se recouvrir : l'âge affiché
vient de la dernière réponse **métier** exploitable, le verdict de joignabilité de la dernière
réponse HTTP quelconque.

« SERVICE DÉGRADÉ » suit la même discipline, **par source**. Une réponse HTTP non-OK est une preuve
et s'affiche donc sans délai, mais elle est inscrite au nom de la boucle qui l'a reçue — `state`,
`alarms` ou `history` — et n'est levée que lorsque **cette** boucle répond correctement : le succès
d'une autre source ne prouve rien sur elle. C'est ce qui rend une panne durable observable ; un état
global unique la faisait disparaître au premier succès venu, réduisant une indisponibilité de
l'historique auxiliaire à un éclair de cinq secondes toutes les cinq minutes. L'échec d'une **action
opérateur** ponctuelle n'entre jamais dans ce bandeau : il est rapporté à son formulaire, parce que
rien ne viendrait le lever et qu'un POST peut expirer côté client après avoir abouti côté serveur.
Une entrée en « HORS LIGNE » efface les dégradations : plus rien ne répond, donc plus rien n'est su.

Tant que l'interface est hors ligne, le navigateur sonde `/health/live` toutes les 2 s (puis 15 s
après trois minutes), page visible uniquement, et n'en lit **que le statut HTTP** : le contrat de
liveness est préservé. Cette sonde ne retire jamais la bannière — elle réveille les boucles métier
en annulant leur temporisation, et c'est leur réponse fraîche qui la retire. Une reprise de
l'application (`pageshow`, retour de visibilité, `online`) provoque le même réveil et remet le
compteur de silence à zéro : une application rouverte après une longue absence ne s'affiche jamais
en rouge du seul fait de cette absence.

La PWA demande la permission de notification uniquement sur clic. Elle notifie les nouvelles alarmes
affectant le contrôle et toutes les alarmes critiques, avec déduplication par UUID. Les notifications
sont actives lorsque l’application est ouverte au premier plan et connectée au contrôleur. Le système
peut les suspendre en arrière-plan ; ce n’est pas une alerte à distance. Il ne s’agit pas de Web Push
et aucune notification n’est garantie une fois la PWA fermée.

## Lecture et annotation de l'historique

La page `/history` calcule dans le navigateur un bilan de la période affichée : part des intervalles
dont la température moyenne est dans la cible, temps observé sous et au-dessus des consignes, plus
longue excursion, écart maximal, activité des actionneurs et nombre d'événements. Ces indicateurs
restent des lectures de l'agrégat retourné par `/api/v1/history` ; ils n'inventent ni n'interpolent les
lacunes.

`POST /actions/history/notes` accepte `category` (`observation`, `intervention`, `culture` ou
`maintenance`), `note` (1 à 240 caractères) et un `alias` facultatif (32 caractères maximum). La note
est enregistrée comme événement `operator_note` dans l'historique auxiliaire SQLite et apparaît sur
les courbes ainsi que dans leur exploration clavier. Elle ne modifie ni la configuration, ni un GPIO,
ni la santé du contrôle. Comme toute mutation, la route exige le jeton CSRF et une origine valide ;
aucune écriture ni commande n'est mise en attente hors ligne.

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
