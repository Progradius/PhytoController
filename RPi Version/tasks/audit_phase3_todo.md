# Phase 3 — Chantier « configuration »

Référence : `AUDIT-2026-08-25.md` § 8, Phase 3. Findings visés : **C5, C7, E7, M4-références, F3**.
Le second point de la phase (**sortie des secrets**, finding E14) est **explicitement reporté** à la
demande de l'utilisateur — voir « Reste à faire » en fin de document.

## Constat avant travaux

`AppConfig` est un modèle Pydantic sans propriétaire. Chacun se débrouille :

* `timer_cyclic`, `climate_control`, `DailyTimer.refresh_from_config()` et
  `CyclicTimer.refresh_from_config()` appellent `AppConfig.load()` **à chaque tick** : lecture disque,
  parse JSON et validation intégrale dans le chemin de contrôle, 4 fois par minute. Chaque appelant a
  dû se recoder son propre filet (`last_cfg`, `try/except`, `getattr`) — trois variantes différentes du
  même repli. *(C7, E7)*
* `refresh_from_config()` **remplace** `self._config` par un objet neuf : le minuteur cesse alors de
  partager l'instance que `main.py` a distribuée à `MotorHandler`, `SensorController`, `SystemStatus` et
  au serveur. Deux configurations vivantes coexistent. *(M4-références)*
* `AppConfig.save()` fait du modèle un **second écrivain** de `param.json`, à côté de `/conf`. Il écrit
  ce qu'on lui donne sans revalider l'objet complet. `validate_assignment=True` rejoue bien les
  validateurs *de bloc* à chaque affectation (vérifié) — la brèche n'est donc pas là, mais dans les
  chemins qui contournent l'affectation : une candidate construite depuis un dictionnaire brut, un
  `replace_from`, une régression qui écrirait dans `__dict__`. La barrière manquante est un
  `model_validate` du modèle entier juste avant l'écriture, quel que soit le chemin. *(C5)*
* Aucune copie de secours : un `param.json` corrompu par une coupure secteur est un boot mort définitif.

`F3` (`get_cyclic_period()` lisant `period_minutes`) est déjà corrigé dans l'arbre courant — vérifié,
`controllers/SystemStatus.py` lit bien `period_days`. Rien à faire.

## Travaux

- [x] **3.A `param/config_store.py` — `ConfigStore`** *(C7, E7, M4)*
      Source unique en mémoire. **Une seule instance d'`AppConfig` pour tout le processus**, mutée en
      place (`replace_from`) : les références distribuées au boot restent valides pour toujours.
      * `refresh()` — surveillance `(mtime_ns, taille)`. Fichier inchangé → renvoie l'instance courante
        sans **aucune** I/O de lecture ni parse. Changé → relecture, validation intégrale, mutation en
        place. Échec → on garde la configuration courante et **on retient quand même l'empreinte**, pour
        ne pas reparser un fichier cassé à chaque tick. Ne lève **jamais**.
      * `save(candidate)` — revalidation intégrale (`model_validate`) de la candidate, copie de l'ancien
        contenu vers `param.json.bak`, écriture atomique, puis mutation en place.
      * `commit()` — même chose pour une mutation faite directement sur l'instance partagée ; en cas de
        refus, l'instance est **restaurée depuis le disque** avant de propager l'erreur.
      * `shared_config()` — singleton de processus, sur le patron déjà éprouvé de `utils.state_store`.
- [x] **3.B Repli `.bak`** *(C5)*
      `param.json` illisible au boot → bascule automatique sur `param.json.bak`, qui est **restauré** sur
      `param.json` pour que le boot suivant reparte propre. Le `.bak` est rafraîchi à chaque écriture
      réussie. Il n'y a pas de « défaut sûr » synthétisable au-delà : sans le bloc `GPIO_Settings`, aucune
      broche n'est connue et aucune sortie ne peut être mise dans un état sûr — un refus de démarrer est
      alors la seule réponse honnête.
- [x] **3.C Boucles de contrôle sans I/O ni exception** *(C7, E7)*
      `timer_cyclic`, `climate_control`, `DailyTimer.refresh_from_config()` et
      `CyclicTimer.refresh_from_config()` consomment `store.refresh()`. Les trois replis artisanaux
      (`last_cfg`, `try/except` autour de `AppConfig.load()`) disparaissent : le repli est désormais dans
      le magasin, écrit une fois.
- [x] **3.D Écriture unique et revalidée** *(C5)*
      `AppConfig.save()` est remplacé par `AppConfig.to_json()` (sérialisation seule, y compris la
      rétro-compatibilité `"enabled"`/`"disabled"`). Le magasin est le **seul** écrivain de `param.json`.
      `/conf` et les setters des minuteurs passent par lui, et rien n'atteint le disque sans être passé
      par un `model_validate` du modèle complet.
- [x] **3.E Contraintes complétées** *(C5)*
      * `GPIOSettings` : bornes `0 ≤ broche ≤ 27` (BCM). **Pas** d'unicité — 27 et 22 portent deux rôles
        dans la configuration en production ; un validateur d'unicité serait un boot mort. C'est le
        `PinRegistry` de la Phase 1 qui traitera les collisions, avec la migration de broches qui va avec.
      * `NetworkSettings.host_machine_address` : `min_length=1`.
      * Cycle séquentiel de durée nulle (`on + off == 0`) : **pas** de validateur bloquant non plus, mais
        une garde dans `timer_cyclic` — sans elle, deux `sleep(0)` enchaînés font tourner la boucle à
        vide à 100 % de CPU. `Cyclic2_Settings` porte aujourd'hui `0/0` (inoffensif car en mode
        journalier) : un validateur strict aurait refusé la configuration en production.

## Vérification

Pas de suite de tests dans cet arbre (`CLAUDE.md`). Vérifications menées :

- [x] `python3 -m compileall` sur les fichiers touchés.
- [x] Banc à blanc hors matériel : chargement, `refresh()` sans changement (aucune relecture),
      modification externe du fichier (prise en compte), fichier tronqué (configuration courante
      conservée, aucune exception), candidate invalide (refus + instance intacte), `param.json` détruit
      au boot (restauration depuis `.bak`).
- [x] `diff -u CLAUDE.md AGENTS.md` vide.
- [x] `param/param.json.bak` ajouté au `.gitignore` — il porte les mêmes secrets en clair que
      `param.json` (voir E14 ci-dessous), il n'a aucune raison d'entrer dans l'historique à son tour.

## Reste à faire — reporté

- [ ] **E14 — Sortie des secrets** *(reporté à la demande de l'utilisateur, 2026-08-26)*
      Wi-Fi (`wifi_ssid`, `wifi_password`) et InfluxDB (`influx_db_user`, `influx_db_password`) restent
      **en clair dans `param.json`, lui-même suivi par git**. À faire en un seul lot, parce que les trois
      morceaux sont indissociables :
      1. `pydantic-settings` : un bloc `NetworkSecrets` alimenté par l'environnement, `param.json` ne
         portant plus que les champs non sensibles ;
      2. `EnvironmentFile=/etc/phyto/secrets.env` (0600, hors git) dans le drop-in systemd, et le mode
         « lancement manuel » documenté en conséquence ;
      3. `git filter-repo` sur les 11 commits touchant `param.json`, `.gitignore` mis à jour, puis
         **rotation effective** des identifiants Wi-Fi et InfluxDB — l'historique reste public tant que
         la rotation n'est pas faite (point 8 de la Phase 0, lui aussi en attente de ce lot).
      Tant que ce lot n'est pas fait, `SENSITIVE_FIELDS` dans `network/web/server.py` reste la seule
      protection : les valeurs ne sont jamais journalisées ni réaffichées, seulement « modifié ».
