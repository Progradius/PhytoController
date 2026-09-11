# Roadmap consolidée

**Public** : pilotage et développement.
**Référence initiale** : commit `61ad3df`, audit et plans au 25 août 2026.
**Dernière mise à jour** : 11 septembre 2026, archivage des plans livrés, incident du 8 septembre et
remédiation web/mobile/PWA.
**Suivi** : cette roadmap et le [registre des risques](risk-register.md) sont les **seuls** suivis
d'avancement tenus à jour ; `tasks/todo.md` porte le détail des cases encore ouvertes. Le § 8 de
l'[audit du 25 août 2026](archive/AUDIT-2026-08-25.md), archivé le 11 septembre 2026, n'est plus mis
à jour.

La roadmap privilégie la réduction du risque physique, puis la reproductibilité et enfin la modernisation. Chaque chantier doit rester livrable, réversible et vérifiable indépendamment.

## Validation automatisée minimale

**État : implémentée hors matériel.**

- [x] Tests paramétrés de `climate_policy.decide()` et de ses invariants thermiques
- [x] Plancher absolu, quotas hiver, repli capteur, durée maximale et cooldown
- [x] Transitions jour/nuit, plages semi-ouvertes et passage à minuit
- [x] `ConfigStore` : sauvegarde, corruption, `.bak`, rollback de commit et erreur d'écriture
- [x] Faux GPIO enregistrant les polarités et le break-before-make moteur
- [x] Superviseur : crash, retour anormal, stall, back-off, reload et état sûr
- [x] HTTP : formulaires, CSRF, Origin, Host, corps borné et actions POST-only
- [x] Protocole matériel séparé, jamais lancé par la suite par défaut
- [ ] Exécuter la suite automatiquement dans une CI au niveau racine du dépôt

## Définitions de sortie

Un chantier n'est terminé que si :

- le code ou le matériel est réalisé ;
- la configuration et la documentation sont mises à jour ;
- le changement est déployé si son périmètre inclut la production ;
- les critères de preuve sont exécutés ;
- les risques associés sont requalifiés ;
- le rollback ou l'état sûr en cas d'échec est connu.

## Lot 1 — Socle documentaire et sécurité

**État : versionné (`b19de46`) ; reste la relecture par l'exploitant.**

- [x] README et avertissement de sécurité
- [x] index et sources de vérité
- [x] vue d'ensemble de l'architecture
- [x] modèle de sûreté
- [x] matrice GPIO et collisions
- [x] runbook d'incident initial
- [x] registre vivant des risques
- [x] roadmap consolidée
- [ ] Relecture par l'exploitant
- [ ] Vérification des commandes du runbook sur le Pi
- [ ] Décider le propriétaire et la fréquence de revue de chaque document

## Lot 2 — Exploitation reproductible

**Objectif : reconstruire et exploiter un Pi sans connaissance implicite.**

- [x] Capturer en lecture seule l'OS, Python, groupes, interfaces et services réels
- [x] Versionner l'unité `phyto.service` et le drop-in watchdog tels qu'observés
- [ ] Revoir et réduire les capacités ambiantes avant de qualifier ces artefacts
- [x] Documenter l'installation Raspberry Pi depuis une image vierge, à exercer
- [x] Documenter I²C, 1-Wire, NetworkManager, NTP et watchdog
- [x] Documenter le déploiement, les préconditions sudo et le rollback
- [x] Écrire la procédure initiale de sauvegarde et de restauration
- [x] Définir les contrôles quotidiens, hebdomadaires et mensuels
- [x] Fixer et vérifier la rétention journald — `SystemMaxUse=200M` appliqué et constaté actif sur le Pi
      ([relevé](archive/operations/production-baseline-2026-08-25.md)) ; la source du bruit est tarie côté logiciel
      (`ds18b20_state=disabled`, voir lot 5)
- [ ] Exercer le runbook : service mort, config invalide, tâche malsaine, alarme chauffage
- [x] Qualifier le déploiement sur le service actif, `/health/live`, `/health/ready`,
      `control_healthy`, le commit attendu, l'absence d'alarme critique et 15 s de stabilité continue

**Critère de sortie** : un second Pi peut être installé avec les artefacts du dépôt et des secrets fournis séparément ; sa configuration système est comparable à la référence.

## Lot 3 — Sécurité matérielle et brochage

**Objectif : garantir l'état sûr même avant Python et pendant les pannes brutales.**

- [ ] Valider le schéma électrique réel hors tension
- [ ] Installer les pulls externes adaptés aux deux polarités
- [ ] Installer thermostat ou fusible thermique en série
- [ ] Définir et installer l'interlock des vitesses moteur
- [ ] Évaluer un watchdog externe coupant l'alimentation de la carte relais (garde-fou matériel 1.C
      de la phase 1 de l'audit, repris ici à l'archivage de son bilan)
- [ ] Migrer la vitesse 4 hors BCM 1 — procédure détaillée (cible BCM 16) dans `tasks/todo.md`
- [ ] Planifier la migration des vitesses hors BCM 7/8
- [ ] Créer le `PinRegistry` avec propriétaire, direction, polarité et niveau sûr
- [ ] Interdire doublons et GPIO réservés avant tout accès matériel
- [ ] Générer la configuration de boot depuis le registre validé
- [ ] Mesurer les GPIO depuis la mise sous tension jusqu'à READY
- [x] Retirer les lignes dangereuses `gpio=N=op,dh` — fichier `notes` supprimé le 11 septembre 2026,
      contenu encore utile reporté dans l'installation et systemd ; leur **remplacement** correct reste
      la génération ci-dessus

**Critère de sortie** : les relais restent inactifs pendant boot, arrêt, reset et perte du processus selon une procédure mesurée ; plusieurs vitesses ne peuvent pas être alimentées simultanément.

## Lot 4 — Thermique unifié et configuration fiable

**Objectif : une décision cohérente et une source de configuration unique.**

### Arbitre thermique

*(Phase 2, commit `a04abbd` : implémenté, **déployé et vérifié sur le Pi** le 26 août 2026 —
[relevé](archive/operations/climate-baseline-2026-08-26.md). Décision consignée dans
[ADR-0004](decisions/ADR-0004-unified-climate-arbiter.md).)*

- [x] Extraire une fonction pure — `components/climate_policy.decide()`, sans GPIO, disque ni horloge implicite
- [x] Garantir l'exclusion chauffage/extraction — travail unique `climate_control`
- [x] Définir une zone morte valide — garantie **par construction** et non par un validateur bloquant, qui aurait rendu le `param.json` déployé illisible
- [x] Définir la priorité humidité/froid avec un plancher absolu — `absolute_floor_temp`
- [x] Nommer deux budgets distincts — renouvellement et déshumidification, bornés et comptés en temps réellement écoulé
- [x] Ajouter une hystérésis à état — seuil de relâchement distinct et `min_dwell_seconds`
- [x] Persister quota hiver et phase cyclique — `utils/state_store.py`
- [x] Définir le comportement sur capteur absent, hors plage ou figé — qualification complète, déploiement initial en `observe`, puis repli nommé `REPLI_CAPTEUR` après armement explicite
- [x] Vérification en production : huit travaux sains, cohérence décision ↔ `pinctrl`, état persisté,
      rechargement à chaud sans coupure de sortie
- [ ] **TODO à la prochaine activation de la régulation thermique automatique** — essai supervisé
      avec le matériel réel : vérifier au moins un franchissement des seuils de chauffe et de
      ventilation, l'hystérésis, le temps de maintien des paliers, la limite de chauffe continue et
      son repos forcé, les budgets hiver/déshumidification et la concordance décision API ↔ GPIO.
      Décision opérateur du 28 août 2026 : cette qualification est volontairement reportée jusqu'à
      l'activation du chauffage et du mode automatique. L'observation continue alors réalisée en
      chauffage désactivé et moteur manuel valide la stabilité du contrôle, des minuteries, des
      capteurs et du suivi des sorties, mais pas ces règles thermiques dynamiques.

### Configuration

*(Phase 3, commit `f840a91` : implémenté, vérifié hors matériel et **déployé** — il est ancêtre de
`e91b021`, déployé le 26 août 2026 et observé 48 h, puis de tous les commits déployés depuis
(`985e42d`, `2ecefb1`, `47784dc`) ; vérifié par `git merge-base --is-ancestor`. Bilan archivé :
[`tasks/archive/audit_phase3_todo.md`](../tasks/archive/audit_phase3_todo.md).)*

- [x] Créer un `ConfigStore` unique — `param/config_store.py`, **seul propriétaire et seul écrivain** de
      `param.json` ; une unique instance d'`AppConfig` par processus, mutée en place (`replace_from`), donc
      les références distribuées au boot restent valides sans abonnement
- [x] Charger une copie candidate et la revalider intégralement
- [x] Activer `validate_assignment` sur tous les modèles
- [x] Ajouter les contraintes de bornes et les contraintes croisées température/vitesses
- [ ] Ajouter les contraintes GPIO (unicité, broches réservées) — **bornes BCM 0–27 faites ; l'unicité est
      délibérément absente** : 27 et 22 portent chacun deux rôles dans la configuration en production, un
      validateur d'unicité serait un boot mort. Bloqué par le `PinRegistry` et la migration de broches du
      lot 3, qui doivent arriver ensemble
- [x] Définir migrations et sauvegarde `.bak` — `param.json.bak` rafraîchi à chaque écriture réussie,
      repli et **restauration** automatiques au boot si `param.json` est illisible. Pas de « défaut sûr »
      synthétisable au-delà : sans `GPIO_Settings` aucune broche n'est connue, donc aucune sortie ne peut
      être mise en état sûr — refuser de démarrer est la seule réponse honnête
- [x] Retirer les lectures disque des chemins de contrôle — `refresh()` compare `(mtime_ns, taille)` et ne
      fait **aucune** I/O tant que le fichier est inchangé ; il ne lève jamais, et un échec retient quand
      même l'empreinte pour ne pas reparser un fichier cassé à chaque tick. Les trois replis artisanaux
      autour de `AppConfig.load()` ont disparu
- [x] Distinguer champs à chaud et champs nécessitant redémarrage
- [x] Créer un `SensorController.reconfigure()` unique avec sérialisation et fermeture
- [ ] Sortir les secrets vers un environnement protégé — **reporté à la demande de l'exploitant**
      (26 août 2026)
- [x] Masquer les secrets dans `/conf`
- [ ] Faire tourner les identifiants et décider du nettoyage de l'historique Git — indissociable du point
      précédent : `pydantic-settings` + `EnvironmentFile=` + `git filter-repo` **puis** rotation effective,
      en un seul lot ; l'historique reste exposé tant que la rotation n'est pas faite

**Critère de sortie** : aucune configuration invalide n'atteint le disque ou les boucles, toutes les préoccupations observent la même version, et chauffage/ventilation proviennent d'une décision unique testable.

## Lot 5 — Frontière I/O, maintenance et gouvernance

**Objectif : réduire les blocages, l'exposition LAN et la dérive future.**

### I/O et HTTP

*(Refonte web et capteurs, commits `7d455e4`/`ad39de2` : **déployée et vérifiée** sur le Pi le 25 août 2026
— [relevé](archive/operations/web-baseline-2026-08-25.md). Contrôle d'origine affiné ensuite par `4eca26d`/`7919419` :
`Referrer-Policy: same-origin` au lieu de `no-referrer`, faute de quoi Firefox n'envoyait ni `Origin` ni
`Referer` sur un POST de formulaire et se prenait un `403`.)*

- [x] Migrer vers aiohttp
- [x] Ajouter timeouts, limites de body et en-têtes de sécurité
- [x] Confiner les fichiers statiques — liste blanche exacte de chemins
- [x] Valider `Host` et documenter le filtrage réseau
- [x] Séparer `/health/live` et `/health/ready`
- [x] Déplacer l'export Influx et les lectures capteurs hors event loop
- [x] Implémenter la PWA locale : HTTPS natif optionnel, manifeste, coque hors ligne à fraîcheur
      dominante et notifications locales actives — **HTTPS `:443` déployé et vérifié le 28 août 2026**
      ([relevé](archive/operations/pwa-tls-activation-2026-08-28.md)) ; autorité sur Android, scénarios
      coupure/reconnexion et notifications encore à qualifier (`tasks/todo.md`, section PWA)
- [ ] Sortir les commandes système (`nmcli`, `ping`, `timedatectl`, reboot) de l'event loop — **reboot et
      poweroff faits** (`asyncio.create_subprocess_exec`) ; `nmcli`/`ping`/`timedatectl` restent des
      `subprocess.run` bloquants **sans `timeout=`**. Ils ne s'exécutent qu'au boot, donc ils ne bloquent
      pas la boucle aujourd'hui — mais la reconnexion Wi-Fi supervisée ne peut pas exister avant qu'ils en
      sortent
- [ ] Ajouter disjoncteur et métrique d'ancienneté InfluxDB — timeout borné (`ClientTimeout(total=4)`) et
      déduplication des erreurs (`StateLogger`) faits ; rien ne suspend encore les envois après N échecs,
      et l'ancienneté du dernier point poussé n'est pas publiée
- [ ] Ajouter reconnexion Wi-Fi supervisée — une perte Wi-Fi en marche reste définitive jusqu'au reboot.
      **Invariant à préserver** : la régulation locale survit intégralement à une panne réseau. Seul
      plan vivant de R-NET-01 : [`tasks/wifi_resilience_plan.md`](../tasks/wifi_resilience_plan.md)
      (v2 du 26 août 2026, non implémentée)
- [ ] Ajouter RTC et politique `time_synced` — `set_ntp_time()` n'attend ni ne vérifie
      `NTPSynchronized=yes`, aucun drapeau n'oppose une heure douteuse aux minuteurs journaliers, et le Pi
      n'a pas de RTC. Après coupure secteur hors réseau, les DailyTimers commutent du 230 V à des heures
      arbitraires

### Projet et gouvernance

- [ ] Ajouter `LICENSE` AGPL-3.0
- [x] Ajouter `SECURITY.md` sans exposer de secret ni de topologie sensible
- [x] Ajouter `CHANGELOG.md`
- [x] Écrire les ADR initiaux
- [x] Écrire la checklist de changement sûr
- [x] Définir le processus de release et de retour arrière — depuis le 11 septembre 2026 dans
      [Déploiement et rollback](operations/deployment-and-rollback.md#processus-de-release)
- [ ] Verrouiller les dépendances compatibles Raspberry Pi — toujours en `>=`, sans `pip-compile` ni
      contrôle de vulnérabilités
- [ ] Décider si Docker est supporté, expérimental ou retiré — **l'image ne démarre pas** :
      `python:3.9.22-slim-bullseye` alors que `function.py` et `components/dailytimer_handler.py` écrivent
      `X | None` sans `from __future__ import annotations` (le Pi tourne en 3.11, ce qui masque le défaut).
      S'y ajoutent `sudo` en PID 1, `NOPASSWD:ALL` et `COPY . .` avant `requirements.txt`. Trancher avant
      d'investir : réparer ou retirer
- [x] Supprimer le code mort de la couche web (`api_handler.py`, `monitor.html`, `get_cyclic_period()` cassé)
- [ ] Supprimer le reste du code mort après vérification des usages — `initial_setup_tool.py` reste relatif
      au répertoire courant (crée un `param.json` fantôme depuis la racine) et écrit encore
      `period_minutes`, clé que le modèle ne connaît plus ; `param.json.bak-gpio17` traîne dans le dépôt
- [ ] Mettre en place des validations automatisées minimales et reproductibles
- [x] Archiver les TODO remplacés après transfert de leurs informations — fait le 11 septembre 2026
      (`docs/archive/`, `tasks/archive/`) ; restes ouverts reportés ici et dans `tasks/todo.md`

**Critère de sortie** : une panne I/O ne bloque pas la régulation, l'interface résiste aux requêtes hostiles du LAN, les releases sont reproductibles et les décisions structurelles sont traçables.

## Ordre et dépendances

### Gestion des cultures — chantier complémentaire, 7 septembre 2026

*(Mise à jour du 11 septembre 2026 : plans livrés et archivés. Le carnet tourne sur le Pi depuis au
plus tard le 10 septembre 2026 — la sortie de migration des données vivantes y constate
`/cultures` en 200 et `cultures.sqlite3` intègre sous `~/phyto-data` ; le commit exact déployé reste
à relever sur le Pi. Aucune qualification fonctionnelle du carnet sur le Pi n'est consignée, hors
banc de performance du lot UI 4 rejoué sur le Pi, `017605b`.)*

La première livraison (`3ac74e5`, 7 septembre) : mères individuelles, lots multi-origines,
effectifs, stades et occupation datés, récolte/séchage,
journal corrigible et durable, archives, export et sauvegarde/restauration sur copie.
Les stades sont déclaratifs ; aucune commande matérielle ni dépendance du contrôle envers SQLite.
Voir le [plan détaillé archivé](../tasks/archive/gestion_cultures_plan.md), le
[guide](operations/cultures.md) et le [contrat API](reference/cultures-api.md). Le jalon 2 est implémenté sur la même branche : solutions et préparations datées, pH/EC,
arrosages partagés, recettes versionnées, corrections, courbes et export CSV filtré ;
le jalon 3 ajoute photos bornées, rappels, vérifications déclaratives, synthèses climatiques
durables, bilan enrichi, comparaison, consultation PWA et sauvegarde ZIP restaurable sur copie.
Les trois jalons sont implémentés et vérifiés hors matériel, sans déploiement Pi. Ce chantier ne clôt aucun risque matériel ci-dessus.

**Rattrapage après audit — écarts A à H livrés le 8 septembre 2026**, sur la même branche et
toujours sans déploiement Pi à cette date. Le [plan de rattrapage archivé](../tasks/archive/gestion_cultures_rattrapage_plan.md)
en donne le détail lot par lot ; commits `2284074`, `e749c80`, `1cdf87d`, `ca865d0`, `40a07db`,
`f4a00cc`, `f51e619`, `8d7c9b5`, `d40a243`, `a7d2eab`, `d568ae2`. Contenu : correction d'un relevé
lié à une intervention ancienne (A), consultation intégrale des cycles longs avec détail horaire
paginé et pages PWA bornées (B), complément rétrospectif d'un parcours repris (C), puis le
**schéma 4** et les vérifications corrigibles (D), les plages cibles pH/EC historisées (E), les
repères d'éclairage rapprochés des horaires configurés (F), les affectations d'équipements datées
(G) et le journal transversal avec observations d'espace (H). Volumétrie relevée hors matériel avec
12 000 agrégats horaires : page des cycles 258 217 octets, JSON 178 966 octets — mesures de
validation, sans qualification des performances sur le Pi. Les limites résiduelles connues sont
listées dans le [contrat API](reference/cultures-api.md#limites-connues). Ce rattrapage
n'autorise aucun déploiement et ne clôt aucun risque matériel.

**Lots UI du carnet, 8 et 9 septembre 2026** — audit UI/UX (`bcb0a48`), lot UI 1 (`cc59e48`,
`2597e8f`), lot UI 2 (`62e29e7`..`c879d51`), lot UI 3 (`d9d3dfd`..`0665d80`), remédiation des lots 2
et 3 (`719ebd8`..`78f568b`), lot UI 4 (`183189b`), remédiation du lot 4 (`591520f`..`641a7ef`), lot F
et passe « photos » (`9136e40`..`1b31d82`). Bilans archivés sous
[`archive/development/`](archive/development/). Limites résiduelles : R-CULT-01 à 03.

### Incident du 8 septembre 2026 et données vivantes hors du dépôt

*(Livré et déployé.)* Un `git checkout master` manuel sur le Pi a matérialisé l'ancien `param.json`
du commit `e93644a` par-dessus la configuration vivante : 26 h 21 sans Éclairage 2 ni cycle 2.
Réponse structurelle : `utils/runtime_paths.py` et `PHYTO_DATA_DIR` (`fd632bf`, 10 septembre),
unité `deploy/phyto.service` porteuse du chemin, `scripts/deploy.sh` lisant ce chemin dans l'unité.
Migration exécutée sur le Pi le 10 septembre 2026 (`eefa74c`) ; procédure et preuve de
non-régression : [migration des données vivantes](operations/migration-donnees-vivantes.md). Risque
associé : R-OPS-04 du registre.

- [x] Données écrites à l'exécution sorties du répertoire de travail Git
- [x] Migration du Pi et preuve : checkout vers `e93644a` sans effet sur la configuration vivante
- [ ] Commit exact servi par le Pi après la migration : à relever sur le Pi et à consigner

### Remédiation web, mobile et PWA — 10 et 11 septembre 2026

Audit du 9 septembre (`ada577f`) et plan de remédiation :
[audit](development/audit-web-mobile-pwa-2026-09-09.md) et
[plan](development/remediation-web-mobile-pwa-2026-09-09.md). Livré dans le dépôt par `6f39986`
(outillage de mesure, banc, macros), `f93e8cb` (lecture et urgence), `d89c060` (configuration et
historique), `6562a2f` (carnet sur mobile), `b801a8b` (page `/app`, hors ligne, mise à jour
explicite, brouillons), `366e1a5` et `08a4815` (documentation et preuves de mesure), état revérifié
en `e29bf96`. **Déploiement sur le Pi : à relever sur le Pi**, aucun relevé n'est consigné.

- [x] Lots 0, 1, 2, 3 et 5 du plan, vérifiés hors matériel (pytest, Playwright par profil, mesures)
- [x] Écarts résiduels E1 à E11 de la revérification du 11 septembre, corrigés le même jour avec la
      revue indépendante qui a suivi (bilan : plan de remédiation, section « État d'avancement »)
- [ ] Filtre `mesure` du tableau de bord et durées « 1.5 h » au point décimal : décision à prendre
- [ ] R4.1 — grille appareils réels, VoiceOver, TalkBack, zoom et clavier virtuel : **opérateur**
      ([`qualification-mobile-pwa.md`](development/qualification-mobile-pwa.md))
- [ ] R4.2 — baseline de performance sur le Pi et sur téléphone, décision sur `/conf` : **opérateur**
      ([`web-perf-baseline-2026-09-10.md`](development/web-perf-baseline-2026-09-10.md))
- [ ] R4.3 — sessions P01 à P10 avec deux opérateurs : **opérateur**
      ([`validation-produit-protocole.md`](development/validation-produit-protocole.md))


```text
Lot 1 Documentation
  └─ Lot 2 Exploitation reproductible
       ├─ Lot 3 Matériel et GPIO
       └─ Lot 4 Thermique et configuration
            └─ Lot 5 I/O et gouvernance finale
```

Le travail documentaire du lot 5 peut commencer plus tôt, mais les références exhaustives de configuration et d'HTTP ne doivent être déclarées stables qu'après les refontes correspondantes.

**Écart assumé au 26 août 2026** : le volet « I/O et HTTP » du lot 5 a été livré **avant** le lot 4, la
refonte web ayant été menée hors séquence. Cela n'a pas créé de dette — la frontière I/O ne dépendait
d'aucun des deux autres chantiers — mais le graphe ci-dessus ne décrit plus l'ordre réel. Le seul
prérequis encore vivant est **lot 3 → contraintes GPIO du lot 4**.

## Prochaines actions immédiates

*(Révisées le 1er septembre 2026 après acceptation de la fenêtre corrective ; l'ordre reprend ensuite
le risque physique résiduel.)*

1. [x] **Clôturer la fenêtre qualité** : `summary.json` accepté, 172 800 s, 2 864 échantillons, zéro
   échec et zéro avertissement ; correctif de figement qualifié en mode `observe`.
2. [x] **Déployer séparément l'observabilité des seuils effectifs** : commit `2ecefb1` chargé le
   1er septembre à 19:47 UTC ; `freeze_epsilon`, `freeze_after_seconds` et `freeze_min_samples`
   vérifiés dans `/api/v1/state`, mode `observe` conservé, santé complète et zéro alarme.
3. **Ouvrir le lot 3** : schéma électrique relu hors tension, puis `PinRegistry`, migration des broches
   moteur et génération de la configuration de boot. Seul chantier restant qui touche la sûreté
   électrique, et il débloque la contrainte d'unicité GPIO laissée désactivée au lot 4.
4. **Traiter le temps et le réseau** (RTC / `time_synced`, reconnexion Wi-Fi supervisée) — première classe
   de panne non électrique : commutation 230 V à contretemps après une coupure secteur hors réseau.
5. **Exercer le runbook** sur les quatre scénarios prévus. Le contrôle de déploiement qualifie désormais
   `/health/live`, `/health/ready`, la santé du contrôle, le commit et les alarmes sur une fenêtre stable.
6. **Hygiène de build** : épinglage des dépendances, décision Docker, validations automatisées minimales.
7. **Essai thermique sur plages limites** — dépend de la saison et de la remise en service du chauffage,
   se planifie indépendamment.
8. **Secrets (rotation et historique Git)** — reporté par décision de l'exploitant, à reprendre en un lot
   indivisible.
9. **Qualifications opérateur de la remédiation web/mobile/PWA** (R4.1 à R4.3) et relevé du commit
   servi par le Pi *(ajout du 11 septembre 2026)*.

## Relation avec les anciens plans

*(Appliqué le 11 septembre 2026.)* Les plans et bilans livrés sont **remplacés par la roadmap et le
registre des risques** et archivés sans perte d'historique :

- `docs/archive/AUDIT-2026-08-25.md` reste la preuve historique détaillée ; son § 8 n'est plus tenu
  à jour ;
- `tasks/archive/` : bilans des phases 0 à 3 de l'audit, plan d'expérience opérateur, plans du carnet
  de cultures et [sections closes de `tasks/todo.md`](../tasks/archive/todo-sections-closes-2026-09-11.md) ;
- `docs/archive/operations/` et `docs/archive/development/` : relevés de production datés et bilans
  des lots UI du carnet ;
- `tasks/logging_refonte_plan.md`, doublon de `tasks/todo.md` livré en `fb26cd2`, a été supprimé ;
  récupérable par `git show fb26cd2:"RPi Version/tasks/logging_refonte_plan.md"`.

Restent vivants : `tasks/todo.md` (cases encore ouvertes), `tasks/wifi_resilience_plan.md` (R-NET-01),
`tasks/plan_dette_technique.md` et `tasks/lessons.md`. Les restes ouverts des plans archivés
(secrets, `PinRegistry`, broches moteur dont la vitesse 4, garde-fous matériels) figurent aux lots 3
et 4 ci-dessus.
