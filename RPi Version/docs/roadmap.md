# Roadmap consolidée

**Public** : pilotage et développement.
**Référence initiale** : commit `61ad3df`, audit et plans au 25 août 2026.
**Dernière mise à jour** : 26 août 2026, après le magasin de configuration unique (`f840a91`).
**Suivi de l'audit** : le tableau d'avancement par phase et le séquencement révisé vivent dans
[`AUDIT-2026-08-25.md` § 8](../AUDIT-2026-08-25.md). Cette roadmap en est la vue par lot livrable ; les
deux doivent rester cohérentes.

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
      ([relevé](operations/production-baseline-2026-08-25.md)) ; la source du bruit est tarie côté logiciel
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
- [ ] Migrer la vitesse 4 hors BCM 1
- [ ] Planifier la migration des vitesses hors BCM 7/8
- [ ] Créer le `PinRegistry` avec propriétaire, direction, polarité et niveau sûr
- [ ] Interdire doublons et GPIO réservés avant tout accès matériel
- [ ] Générer la configuration de boot depuis le registre validé
- [ ] Mesurer les GPIO depuis la mise sous tension jusqu'à READY
- [ ] Corriger ou remplacer les lignes dangereuses dans `notes`

**Critère de sortie** : les relais restent inactifs pendant boot, arrêt, reset et perte du processus selon une procédure mesurée ; plusieurs vitesses ne peuvent pas être alimentées simultanément.

## Lot 4 — Thermique unifié et configuration fiable

**Objectif : une décision cohérente et une source de configuration unique.**

### Arbitre thermique

*(Phase 2, commit `a04abbd` : implémenté, **déployé et vérifié sur le Pi** le 26 août 2026 —
[relevé](operations/climate-baseline-2026-08-26.md). Décision consignée dans
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
- [ ] Essai sur plages limites avec le matériel réel : la serre est en chauffage désactivé et moteur
      manuel, donc ni les seuils de chauffe, ni les paliers de ventilation, ni les budgets hiver
      n'ont encore été exercés en conditions réelles

### Configuration

*(Phase 3, commit `f840a91` : implémenté et vérifié hors matériel, **non encore déployé**. Bilan :
[`tasks/audit_phase3_todo.md`](../tasks/audit_phase3_todo.md).)*

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
— [relevé](operations/web-baseline-2026-08-25.md). Contrôle d'origine affiné ensuite par `4eca26d`/`7919419` :
`Referrer-Policy: same-origin` au lieu de `no-referrer`, faute de quoi Firefox n'envoyait ni `Origin` ni
`Referer` sur un POST de formulaire et se prenait un `403`.)*

- [x] Migrer vers aiohttp
- [x] Ajouter timeouts, limites de body et en-têtes de sécurité
- [x] Confiner les fichiers statiques — liste blanche exacte de chemins
- [x] Valider `Host` et documenter le filtrage réseau
- [x] Séparer `/health/live` et `/health/ready`
- [x] Déplacer l'export Influx et les lectures capteurs hors event loop
- [x] Implémenter la PWA locale : HTTPS natif optionnel, manifeste, coque hors ligne à fraîcheur
      dominante et notifications locales actives — **code non déployé**, autorité Android et scénarios
      coupure/reconnexion encore à qualifier
- [ ] Sortir les commandes système (`nmcli`, `ping`, `timedatectl`, reboot) de l'event loop — **reboot et
      poweroff faits** (`asyncio.create_subprocess_exec`) ; `nmcli`/`ping`/`timedatectl` restent des
      `subprocess.run` bloquants **sans `timeout=`**. Ils ne s'exécutent qu'au boot, donc ils ne bloquent
      pas la boucle aujourd'hui — mais la reconnexion Wi-Fi supervisée ne peut pas exister avant qu'ils en
      sortent
- [ ] Ajouter disjoncteur et métrique d'ancienneté InfluxDB — timeout borné (`ClientTimeout(total=4)`) et
      déduplication des erreurs (`StateLogger`) faits ; rien ne suspend encore les envois après N échecs,
      et l'ancienneté du dernier point poussé n'est pas publiée
- [ ] Ajouter reconnexion Wi-Fi supervisée — une perte Wi-Fi en marche reste définitive jusqu'au reboot.
      **Invariant à préserver** : la régulation locale survit intégralement à une panne réseau
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
- [x] Définir le processus de release et de retour arrière
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
- [ ] Archiver les TODO remplacés après transfert de leurs informations

**Critère de sortie** : une panne I/O ne bloque pas la régulation, l'interface résiste aux requêtes hostiles du LAN, les releases sont reproductibles et les décisions structurelles sont traçables.

## Ordre et dépendances

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

*(Révisées le 26 août 2026. Les lots 4 « thermique » et 4 « configuration » sont clos côté code ; l'ordre
ci-dessous suit le risque physique résiduel, cohérent avec le séquencement du § 8 de l'audit.)*

1. **Déployer et vérifier le magasin de configuration** (`f840a91`) sur le Pi — c'est le seul chantier
   terminé qui ne soit pas encore en production.
2. **Ouvrir le lot 3** : schéma électrique relu hors tension, puis `PinRegistry`, migration des broches
   moteur et génération de la configuration de boot. Seul chantier restant qui touche la sûreté
   électrique, et il débloque la contrainte d'unicité GPIO laissée désactivée au lot 4.
3. **Traiter le temps et le réseau** (RTC / `time_synced`, reconnexion Wi-Fi supervisée) — première classe
   de panne non électrique : commutation 230 V à contretemps après une coupure secteur hors réseau.
4. **Exercer le runbook** sur les quatre scénarios prévus. Le contrôle de déploiement qualifie désormais
   `/health/live`, `/health/ready`, la santé du contrôle, le commit et les alarmes sur une fenêtre stable.
5. **Hygiène de build** : épinglage des dépendances, décision Docker, validations automatisées minimales.
6. **Essai thermique sur plages limites** — dépend de la saison et de la remise en service du chauffage,
   se planifie indépendamment.
7. **Secrets (rotation et historique Git)** — reporté par décision de l'exploitant, à reprendre en un lot
   indivisible.

## Relation avec les anciens plans

- `AUDIT-2026-08-25.md` reste la preuve historique détaillée ; son § 8 est le seul suivi d'avancement tenu
  à jour, cette roadmap en étant la vue par lot livrable.
- `tasks/audit_phase0_todo.md` à `tasks/audit_phase3_todo.md` restent les bilans des phases réalisées et
  reportées, avec leurs preuves de vérification.
- `tasks/logging_refonte_plan.md` conserve le plan initial de logging.
- `tasks/todo.md` conserve des actions ponctuelles historiques.

Quand tous leurs éléments utiles auront été transférés et reliés à une preuve, ces fichiers pourront être marqués « remplacés par la roadmap et le registre des risques », sans supprimer l'historique.
