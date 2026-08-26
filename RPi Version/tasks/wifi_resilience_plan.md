# Plan de résilience Wi-Fi avec accès de secours sans Ethernet — v2

> **Révision du 2026-08-26** après challenge adversarial (4 agents : 1 vérification d'ancrage code,
> 3 réfutateurs — mécanique NetworkManager vérifiée en direct sur le Pi, machine à états, périmètre).
> La v1 (daemon D-Bus dédié + PolicyKit + socket Unix + transactions checkpoint) est **abandonnée
> comme architecture de premier lot** : 5 bloquants confirmés sur la cible, ~2 800 LOC et ~12 nouveaux
> modes de panne système pour un besoin qui en compte 3. Les réfutations sont tracées en annexe pour
> que le travail ne soit pas perdu si le lot D est un jour lancé.

## Verdict

- **GO** pour les lots A, B et C ci-dessous, dans cet ordre. Chacun est livrable et vérifiable seul.
- **NO-GO** sur le daemon D-Bus custom tel que spécifié en v1. Il est reporté en lot D, conditionnel :
  il ne se justifie que si 3 à 6 mois d'exploitation du lot C prouvent que le chemin manuel
  (AP de secours + SSH + `nmcli`) est insuffisant. S'il est lancé un jour, les corrections
  obligatoires de l'annexe s'appliquent intégralement.

## Objectifs (inchangés)

1. **(a)** Reconnexion Wi-Fi robuste : une perte de box ne doit plus être définitive jusqu'au reboot.
2. **(b)** Accès de secours : après une longue indisponibilité, le Pi expose un point d'accès WPA2
   `PhytoController-Rescue-<id>` sur `10.42.0.1`, joignable sans mDNS.
3. **(c)** Changement de SSID sans se scier la branche.
4. La régulation (timers, moteur, chauffage, GPIO) survit intégralement à toute panne réseau ; rien
   dans le sous-système réseau ne touche aux GPIO, ne redémarre le contrôleur, NetworkManager ou le Pi.

## Lot A — Application, zéro mutation réseau (~50 LOC, déployable immédiatement)

Aucun risque d'accès : rien ne touche à NetworkManager ni aux profils.

1. **`gates_watchdog` / `control_healthy` dans le superviseur.** Ajouter à
   `TaskSupervisor.register()` (`utils/supervisor.py:169-176`) un attribut `gates_watchdog`
   (`True` pour timers, `climate_control`, capteurs ; `False` pour `influx_push` et `http_server`).
   `is_healthy()` reste inchangé pour compatibilité (`supervisor.py:210-211`) ; ajouter
   `control_healthy()` / `control_unhealthy_names()` et brancher le watchdog dessus
   (`controllers/PuppetMaster.py:231-237`). Préserver `WatchdogSec` (600 s) >
   `MAX_SILENCE_SECONDS` (300 s) et le raisonnement de `MAX_PET_PERIOD_SECONDS`.
2. **Rendre `http_server` réellement observable.** Aujourd'hui il est enregistré avec
   `max_silence=None` (`PuppetMaster.py:218`) et `is_alive()` teste le runner, jamais terminé : il
   est structurellement incapable d'être malsain. Ajouter une coroutine de battement (`beat()`
   toutes les 10 s après démarrage du site) et `max_silence=120`. Un serveur pendu ou en crash-loop
   devient détectable et redémarrable par le superviseur — c'est l'IHM, futur unique accès en secours.
3. **Retirer de `main.py` l'appel à `do_connect()` et le ping de l'hôte** (`main.py:194-199`,
   `main.py:209-210`, `network/network_handler.py`). Deux `subprocess.run` sans `timeout=` au boot ;
   sous systemd (`User=progradius`), `do_connect()` est déjà un no-op (`network_handler.py:63`).
   `network_handler.py` n'a aucun autre consommateur : suppression pure. `set_ntp_time()`
   (`main.py:203`) suit la même règle : non bloquant, le boot continue immédiatement en mode local.
4. **État réseau en lecture seule dans `/status`**, de manière additive : `control_healthy`,
   `network_degraded`, et un bloc `network` minimal (interface, SSID actif, IPv4, passerelle,
   `offline_for_s`) alimenté par une lecture périodique non bloquante (nmcli asynchrone ou D-Bus
   propriétés, toutes les 10 s) enregistrée au superviseur avec `gates_watchdog=False`, une fabrique
   (`lambda:`), `supervisor.sleep()` et `beat()`. Une coupure Wi-Fi est un **état métier dégradé**,
   pas une exception de tâche ; log des seules transitions via `StateLogger`, en français.
5. **Corrections d'ancrage** (la v1 prescrivait du travail déjà livré) :
   - `requests.post()` → aiohttp : **déjà fait** (`influx_handler.py:7,108-109`). Reste seulement à
     ajouter `sock_connect=2`/`sock_read=2` au `ClientTimeout`.
   - `influx_push` toujours enregistré : **déjà le cas** (`PuppetMaster.py:196-200`) ; le gating
     `host_machine_state` est dans la boucle, pas à l'enregistrement.
6. `time.monotonic()` pour tous les délais applicatifs (déjà la convention du dépôt).

## Lot B — Hygiène des secrets, indépendante (~30 min)

La v1 couplait ce correctif de 10 minutes à un chantier d'un mois, en en perdant l'essentiel :
retirer `wifi_ssid`/`wifi_password` du fichier vivant ne retire rien de l'**historique git**, où les
valeurs sont déjà en clair, et `influx_db_password` y reste aussi.

1. Rotation du mot de passe Wi-Fi de la box (action exploitant, à faire de toute façon).
2. `git rm --cached param/param.json` + entrée `.gitignore` + `param/param.json.example` sans secret.
3. Documenter dans le README/runbook que `param.json` est local à chaque Pi.

## Lot C — Résilience Wi-Fi par mécanismes NetworkManager standard (~1 journée)

Principe directeur : **le chemin de secours ne doit pas dépendre d'un composant qui peut échouer.**
Pas de daemon, pas de PolicyKit, pas de socket : un profil NM, un timer systemd et ~100 lignes de
shell lisibles avec `nmcli con show` et `journalctl`, réparables par l'exploitant dans 3 ans.

### C.1 — Profil station : reconnexion illimitée

- **Toujours via `nmcli con mod`, jamais via D-Bus `Update()`** : `GetSettings()` D-Bus ne retourne
  pas les secrets et `Update()` remplace le profil intégralement — un patch naïf efface le PSK de la
  box et coûte l'accès au Pi (bloquant C vérifié : `psk-flags=0`, secret dans le keyfile root).
  `nmcli con mod` refusionne les secrets correctement.
- Sur le profil actif `preconfigured` (conservé, jamais renommé/désactivé/réactivé) :
  `connection.autoconnect yes`, `connection.autoconnect-retries 0` (illimité, vérifié en 1.42),
  `connection.autoconnect-priority 100`, `802-11-wireless.powersave 2` (désactivé — effet **à la
  prochaine association seulement**, pas à chaud : l'assumer). Ne **pas** poser
  `connection.interface-name` : aucune valeur ajoutée, et une erreur ne se verrait qu'au prochain boot.
- Conserver `connection.auth-retries` par défaut. Conserver intégralement SSID, PSK, adressage
  statique, DNS, routes et IPv6 existants.
- **Reboot complet vérifié** avant de considérer la migration acquise et avant toute étape suivante.

### C.2 — Profil de secours `phyto-rescue`

Créé par un provisioner root explicite, **jamais** lancé par `scripts/deploy.sh` :

- `802-11-wireless.mode ap`, bande 2,4 GHz, WPA2-PSK, `ipv4.method shared` avec `10.42.0.1/24`
  (supporté et vérifié : `dnsmasq-base 2.90` installé, pas de `dnsmasq.service` concurrent,
  `AP: yes` au chipset), IPv6 désactivé, `connection.autoconnect no` (la bascule est pilotée par le
  timer, pas par les priorités NM), pas de route par défaut (neutralise le piège `FORWARD DROP` de
  Docker).
- Clé WPA2 demandée deux fois sans écho au provisioning (12–63 caractères) ; jamais dans les
  arguments de processus, l'environnement, les logs ou `param.json` ; stockée uniquement dans le
  keyfile NM (0600 root).
- SSID `PhytoController-Rescue-<4 derniers du numéro de série>` **dérivé une seule fois au
  provisioning et écrit dans le profil** ; jamais recalculé à l'exécution (une carte SD déplacée sur
  un autre Pi divergerait silencieusement). Toute lecture ultérieure du SSID se fait dans le profil.
- Avahi : `allow-interfaces=wlan0` dans `avahi-daemon.conf` (règle l'annonce parasite de
  `docker0`/`172.17.0.1` ; pas d'Ethernet sur ce Pi donc pas d'effet de bord). Le secours reste
  toujours joignable en direct sur `http://10.42.0.1:8123`, sans dépendre de mDNS. Qualifier le nom
  réel : `_build_allowed_names()` (`server.py:185-193`) n'autorise `phytocontroller.local` que si
  `socket.gethostname()` vaut `phytocontroller` — vérifier le hostname du Pi, l'ajuster si besoin.
- Le provisioner sauvegarde avant mutation (métadonnées non secrètes du profil actif, copie protégée
  de `param.json`) et fournit un **`--undo`** documenté qui restaure ces sauvegardes — un provisioner
  sans chemin de retour n'est pas idempotent, il est optimiste.

### C.3 — Bascule : timer systemd + script, indépendants de tout processus applicatif

`phyto-rescue.timer` (toutes les 60 s) exécutant `phyto-rescue-check.sh` (~100 lignes) :

- **Critère de validité : jamais « une IPv4 est présente ».** L'adressage est statique
  (`method=manual`) : NM pose l'adresse dès l'association L2, box remplacée comprise — le critère v1
  ne serait jamais entré en secours sur cette machine précisément dans le scénario « changement de
  box » (bloquant B). Utiliser l'état de connectivité NM (`nmcli networking connectivity check` /
  propriété `Connectivity`, le Pi rapporte `full` aujourd'hui) ou la joignabilité de la passerelle.
- **Horodatage persistant `last-online`** (fichier sous `/var/lib/phyto-rescue/`, écrit atomiquement)
  mis à jour uniquement après **120 s de connectivité continue** — un Wi-Fi qui bat de l'aile
  (accroche 40 s toutes les 3 min) ne réarme pas le compteur et finit en secours au lieu d'une perte
  d'accès permanente (réfutation C). Le seuil traverse les redémarrages du script, du service et du Pi.
- `last-online` plus vieux que **10 min** et `phyto-rescue` inactif → `nmcli con up phyto-rescue`.
- **AP collant tant qu'un client est associé** : pas de sonde station si `iw dev wlan0 station dump`
  montre au moins un pair. Le signal de retenue est l'**association**, pas une requête HTTP — la
  retenue v1 (armée par l'IHM) était circulaire : elle supposait un AP déjà présent (réfutation G).
- Sans client associé après **10 min** d'AP : `nmcli con down phyto-rescue` ; l'autoconnect NM
  (illimité, C.1) tente la station seul. Si `last-online` n'est pas rafraîchi dans les 2 min, le
  timer remonte l'AP au tick suivant. Fenêtre AP-absent bornée et sans machine à états.
- Unité : `Wants=NetworkManager.service` + `After=` (**jamais `Requires=`** : un NM en `failed`
  désactiverait le filet définitivement), `StartLimitIntervalSec=0`. Le script est une séquence
  fixe : pas d'état en RAM, chaque tick repart de l'observation réelle (`nmcli`), donc pas de
  divergence état-fictif/état-réel possible.
- Logs : transitions uniquement, en français, dans journald via `systemd-cat -t phyto-rescue`.

### C.4 — Changement de SSID : runbook, pas transaction

Fréquence réelle ≈ 1 fois / 2 ans ; le chemin existe déjà et coûte 0 ligne :

1. Attendre le secours (≤ ~12 min après la perte) ou le provoquer (`sudo nmcli con up phyto-rescue`).
2. Se connecter à `PhytoController-Rescue-XXXX`, SSH sur `10.42.0.1`.
3. `sudo nmcli device wifi connect "<SSID>" password "<clé>"` — NM crée le profil, l'ancien
   `preconfigured` reste en place comme repli.
4. Vérifier, puis aligner priorités/retries comme en C.1 sur le nouveau profil.

À documenter dans le runbook d'incident. La page `/network` transactionnelle est reportée au lot D.

### C.5 — Nettoyage applicatif (après C.3 qualifié seulement)

- Retirer `wifi_ssid`, `wifi_password` de `Network_Settings` (`param/config.py:105-112`).
  **Conserver `host_machine_state`** : ce n'est pas un vestige, c'est l'interrupteur d'export Influx
  (`influx_handler.py:114`) — le supprimer casserait le toggle de `/conf`.
- Traiter les quatre consommateurs que la v1 oubliait, sous peine de `KeyError` au rendu de `/conf` :
  `SECTION_FIELDS["wifi"]` (`server.py:99-102`), `SENSITIVE_FIELDS` (`server.py:44-48`),
  `pages.py:77` (`wifi_password_set=`), `templates/conf.html:159-160`.
- Les anciennes clés JSON sont déjà ignorées à la lecture (Pydantic v2, `extra` non contraint) ;
  la réécriture du fichier vivant passe par `ConfigStore.save()/commit()`, jamais en direct.
- `initial_setup_tool.py:413-424` : ne plus demander d'identifiants Wi-Fi.

### C.6 — Filet hors bande optionnel, coût quasi nul

`dtoverlay=dwc2` + gadget `g_ether` dans `/boot/firmware/config.txt` : Ethernet-sur-USB via le port
USB-C du Pi 4, indépendant de tout le sous-système Wi-Fi et de tout logiciel PhytoController.
3 lignes ; ne remplace pas l'AP (accès physique rare) mais c'est le filet ultime.

## Qualification (discipline v1 conservée intégralement)

- Pas de suite de tests dans le dépôt : vérification par lecture ciblée, `compileall`, `bash -n` sur
  le script, et essais d'intégration sur le Pi.
- Déploiement en deux phases : (1) lot A applicatif, réseau intact ; (2) provisioner explicite (C.1
  puis reboot vérifié, puis C.2/C.3).
- Pendant l'installation : jamais `connection down`, `device disconnect` ni
  `systemctl restart NetworkManager` ; vérifier profil de secours et `/status` avant tout essai
  disruptif ; vérifier depuis Windows que `phytocontroller.local` atteint l'adresse courante.
- **Essai contrôlé du secours, utilisateur présent** : checkpoint 300 s sur `wlan0`
  (`nmcli con checkpoint` étant absent en 1.42, via `busctl call ... CheckpointCreate` root, prouvé
  d'abord par un Create/Destroy à vide) → `nmcli con up phyto-rescue` → connecter Windows à l'AP →
  vérifier `http://10.42.0.1:8123/status` **et le DHCP obtenu** → retour station → si une étape
  échoue ou si SSH disparaît, ne rien forcer, attendre le rollback automatique.
- Scénarios d'acceptation matériels (repris de v1, adaptés) : box absente au boot puis revenue ;
  coupure < 10 min sans apparition durable du secours ; coupure > 10 min avec IHM joignable sur
  `10.42.0.1` ; box revenue pendant le secours sans client associé → retour station ≤ ~12 min ;
  client associé → AP maintenu ; **Wi-Fi instable (flapping) → secours atteint quand même** ;
  timer/script tué → relance systemd ; aucune saturation de logs ; aucun secret dans processus,
  journaux, HTML, `/status` ou `param.json`.
- Pendant chaque scénario : `phyto.service` et son PID ne redémarrent pas ; le watchdog ne dépend
  que de `control_healthy` ; timers/moteur/chauffage poursuivent ; aucune transition GPIO
  supplémentaire ; polarités inchangées.
- Ne retirer les clés Wi-Fi de la configuration vivante (C.5) qu'après réussite de l'essai contrôlé.
- Mettre à jour la documentation + les invariants réseau dans `AGENTS.md` et `CLAUDE.md` de façon
  strictement identique (`diff -u CLAUDE.md AGENTS.md` sans sortie).
- `scripts/deploy.sh` peut signaler un provisioning absent/obsolète mais n'installe, ne modifie ni
  ne teste jamais un profil Wi-Fi.

## Lot D — Différé, conditionnel (réévaluer après 3–6 mois de lot C en production)

1. **Disjoncteur Influx** (~80 LOC, indépendant de tout ceci, livrable quand on veut) : ouverture
   après 3 cycles en échec, essais semi-ouverts 5/10/20/30 min, fermeture sur cycle réussi, état
   exposé dans `/status`, aucun identifiant dans les erreurs.
2. **Page `/network` transactionnelle et/ou daemon réseau.** Uniquement si l'exploitation prouve que
   le runbook C.4 est insuffisant — et alors **pas** sous la forme v1 (daemon + user dédié + polkit +
   socket + protocole JSON) : `CheckpointCreate` appelé directement par le serveur aiohttp existant
   via une action polkit unique. Les corrections de l'annexe sont alors **obligatoires**.

## Hypothèses et limites

- Cible qualifiée en direct : Raspberry Pi 4, Bookworm, NetworkManager 1.42.4, `wlan0`, `AP: yes`,
  `dnsmasq-base 2.90` présent, polkit 122, Avahi présent, profil actif `preconfigured` en
  `ipv4.method=manual` (`192.168.1.15/24`), série `…9ce4`.
- `wpa_supplicant` est le backend normal de NM, pas un gestionnaire concurrent.
- Réseaux WPA2/WPA3 Personal uniquement ; Enterprise, WEP et ouverts hors périmètre.
- Pas d'authentification applicative supplémentaire (LAN de confiance) ; l'AP de secours est
  obligatoirement protégé par la clé WPA2 du provisioning. `10.42.0.1` est déjà accepté par la
  validation `Host` existante (`is_private`, `server.py:285-287`) — aucune modification requise.
- Les identifiants Influx restent dans le mécanisme actuel ; seule l'hygiène du lot B est incluse.
- La garantie « récupérable en Wi-Fi » couvre : erreurs de profil, changement de box, longues
  indisponibilités, Wi-Fi instable, crash applicatif, crash du script (séquence fixe relancée par
  systemd). Elle ne couvre pas : panne physique du chipset, coupure d'alimentation, brouillage
  permanent, perte de la clé WPA2 de secours.

## Annexe — réfutations retenues contre la v1 (traçabilité)

Vérifiées sur le Pi ou dans le code ; obligatoires si le lot D ressuscite un jour la mécanique v1.

| # | Bloquant v1 | Constat |
|---|---|---|
| 1 | Liste PolicyKit | `checkpoint-rollback` = `auth_admin_keep`, `wifi.share.protected` = `no` hors session : le daemon v1 ne pouvait ni créer un checkpoint ni allumer l'AP. Actions à ajouter si lot D. |
| 2 | « IPv4 attribuée = valide » | Faux avec `ipv4.method=manual` : adresse posée dès l'association L2. Utiliser la connectivité NM ou la passerelle. |
| 3 | D-Bus `Update()` « en place » | Efface le PSK (les secrets ne sont pas retournés par `GetSettings`) : perte d'accès provoquée par le plan lui-même. `nmcli con mod` ou `GetSecrets`+fusion obligatoires. |
| 4 | Ordre candidat→checkpoint | `DELETE_NEW_CONNECTIONS` ne supprime que les connexions créées **après** le checkpoint : candidats orphelins garantis. Checkpoint d'abord. Et promouvoir le candidat **avant** `CheckpointDestroy`. |
| 5 | « Si le daemon meurt, NM restaure l'AP » | Faux hors fenêtre de checkpoint ; les checkpoints ne survivent pas à un restart de NM. La garantie doit être portée par un mécanisme indépendant du daemon (d'où le timer du lot C). |
| 6 | Compteurs volatils + `Requires=` + `StartLimitBurst` | Crash-loop = seuil 600 s jamais atteint ; NM en `failed` = daemon arrêté définitivement. `Wants=`, `StartLimitIntervalSec=0`, horodatage persistant. |
| 7 | Flapping | Une IPv4 fugace remettait le compteur à zéro : le mode de défaillance le plus probable devenait une perte d'accès permanente. Stabilité 120 s requise. |
| 8 | IHM de secours inobservable | `http_server` avec `max_silence=None` ne peut jamais être malsain : AP joignable, IHM morte, aucun moyen d'entrer. Corrigé au lot A ; si lot D, `/status` de secours servi par le daemon lui-même. |
| 9 | Transaction depuis l'AP | Boucle non convergente (confirmation exigée depuis une liaison que l'utilisateur ne retrouve pas ; « depuis la nouvelle liaison » de toute façon invérifiable et tautologique). Si lot D : confirmation **inversée**, depuis l'AP. |
| 10 | `settings.modify.system` | Donne de fait `GetSecrets` sur tous les PSK système : « clé root-only » trompeur dans le modèle de menace. |
| 11 | Ancrage code | `requests`→aiohttp déjà fait ; `influx_push` déjà inconditionnel ; section `/conf` « wifi » et double rôle de `host_machine_state` non traités ; `10.42.0.1` déjà autorisé par la validation `Host`. |
| 12 | SSID recalculé à l'exécution | Divergence silencieuse si la carte SD change de Pi : dériver une fois au provisioning, lire ensuite dans le profil. |
| 13 | Sonde vs autoconnect | Dès que l'AP tombe pour sonder, l'autoconnect NM court après le daemon et peut activer un autre profil : vérifier l'UUID de l'`ActiveConnection`, pas la seule IPv4. `psk-flags=0` requis sur tout profil créé par programme. |
| 14 | `/var/lib` du daemon | Ni `StateDirectory=` ni propriétaire spécifiés : EROFS sous `ProtectSystem=strict`. |
