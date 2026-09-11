> Les sections entièrement closes (rattrapage du carnet et lots UI 1 et 2, refonte de la
> journalisation, remédiation du lot UI 4, données vivantes hors du répertoire Git) ont été
> déplacées le 11/09/2026 dans
> [`tasks/archive/todo-sections-closes-2026-09-11.md`](archive/todo-sections-closes-2026-09-11.md).
> Ce fichier ne garde que les sections portant encore une case ouverte.

# TODO — Déploiement et armement de la qualité des capteurs

**État au 1er septembre 2026 à 19:44 UTC** : correctif de figement **déployé au commit
`985e42d`** le 30 août 2026 à 19:07 UTC puis qualifié par une observation continue de 172 800 s :
2 864 échantillons, zéro échec, zéro avertissement et les trois mesures BME280 `normal` pendant
toute la fenêtre. Voir le
[relevé de clôture](../docs/archive/operations/jalon2-correctif-figement-observation-2026-09-01.md).
Lot non qualifié électriquement et mode `Sensor_Quality.mode = observe` à conserver jusqu'à
validation complète.

La fenêtre précédente, close le 30 août à 18:59:28 UTC en `accepted_with_warnings` — 172 800 s,
2 864 échantillons, 0 échec, 835 avertissements de cause unique — a établi la continuité du contrôle
et révélé le défaut de la politique de figement corrigé par `837f778`. Voir le
[relevé de clôture](../docs/archive/operations/jalon2-observation-operateur-2026-08-30.md).

~~**Le correctif est déployé mais pas encore qualifié** : la mémoire qualité repart de zéro, donc
aucune mesure ne peut être déclarée figée avant 1 800 s. La preuve attendue est une nuit calme
complète, période où l'ancien critère se déclenchait systématiquement.~~ Paragraphe périmé :
qualification acquise le 1er septembre 2026 (voir l'état ci-dessus).

Références :

- [`docs/reference/configuration.md`](../docs/reference/configuration.md#calibration-et-qualité-des-capteurs) ;
- [`docs/reference/status-schema.md`](../docs/reference/status-schema.md) ;
- [`docs/development/hardware-validation.md`](../docs/development/hardware-validation.md) ;
- [`docs/operations/deployment-and-rollback.md`](../docs/operations/deployment-and-rollback.md).

## 1. Déployer sans armer

- [x] Commiter puis déployer la version avec `Sensor_Quality.mode = observe` ; ne pas saisir
      `ARMER` pendant ce premier déploiement
- [x] Vérifier après déploiement : `phyto.service` actif, `/health/live` et `/health/ready` à 200,
      `control_healthy=true`, commit attendu, aucun redémarrage ou blocage de tâche et aucune alarme
      critique nouvelle
- [x] Vérifier dans `/api/v1/state` que `schema_version=2`, que chaque capteur actif publie
      `status`, `reason_codes`, `raw_value`, `observed_value`, `value`, `control_usable`, les compteurs
      et les seuils effectifs, sans secret ni valeur inventée
- [ ] Confirmer physiquement que le déploiement en observation n'a modifié aucune sortie et relever
      les GPIO selon la procédure matérielle supervisée

## 2. Observer une période représentative

- [x] Lancer `scripts/observe-jalon2-operator-quality.sh` pendant 48 h au commit `5520850`. Début :
      `2026-08-28T18:07:22Z` ; fin attendue : `2026-08-30T18:07:22Z` ; PID observateur initial :
      `381479` ; PID service de référence : `381022` ; répertoire de preuve :
      `~/phyto-observations/jalon2-operateur-qualite-20260828T180722Z`
- [x] Au prochain redéploiement, arrêter proprement le PID observateur vérifié avec `SIGTERM`, attendre
      son `summary.json` interrompu, redéployer et valider le service, puis nettoyer ou archiver
      uniquement le répertoire invalidé ci-dessus
- [x] Après ces contrôles, relancer une nouvelle observation de 172 800 s : début
      `2026-08-28T18:59:28Z`, fin attendue `2026-08-30T18:59:28Z`, PID observateur initial `388349`,
      PID service de référence `387866`, commit `b26d2b1`, preuves sous
      `~/phyto-observations/jalon2-operateur-qualite-20260828T185928Z`
- [x] À la fin de cette nouvelle fenêtre, ne l'accepter que si `status=accepted`, durée réelle d'au
      moins 172 800 s, zéro échantillon en échec et examen explicite de tout avertissement.
      **Clôturée le 30 août 2026 à 18:59:28 UTC** : `status=accepted_with_warnings`, 172 800 s
      réelles, 2 864 échantillons, **0 échec**, 835 avertissements tous dus au même défaut de la
      politique de figement. Examen et décision dans le
      [relevé de clôture](../docs/archive/operations/jalon2-observation-operateur-2026-08-30.md) : fenêtre
      acceptée comme preuve de continuité du contrôle, refusée comme qualification du figement
- [ ] Laisser fonctionner le système en mode `observe` pendant plusieurs cycles jour/nuit et une
      durée représentative des périodes naturellement stables de la serre
- [ ] Relever pour chaque mesure les statuts, `unchanged_for_s`, échecs consécutifs, incohérences,
      expirations de calibration et raisons de dégradation
- [ ] Vérifier le measurement Influx `sensor_quality` et confirmer qu'une valeur suspecte reste
      analysable dans cette série sans apparaître dans les measurements métier de confiance
- [ ] Vérifier que les alarmes qualité sont idempotentes, se résolvent au rétablissement et ne
      dégradent ni `control_healthy()` ni le watchdog
- [ ] Consigner les faux positifs et faux négatifs constatés, avec date et contexte, sans recopier
      la configuration sensible

## 2 bis. Correctif de la politique de figement (30 août 2026)

Résultat final de l'observation précédente : **0 échantillon en échec**, mais 835 échantillons avec
avertissement sur 2 864, tous de la même cause. L'analyse intermédiaire ayant conduit au correctif
portait encore sur 2 284 échantillons et 546 avertissements. `BME280T` et `BME280H` — les deux
mesures qui pilotent l'arbitre thermique — ont été déclarées `inconsistent` sur 23,8 % et 21,5 % de
la fenêtre complète, `reason=frozen`, alors que les capteurs mesuraient normalement (amplitude réelle
6,45 °C et 14,95 %, aucune erreur d'acquisition).

Cause : `evaluate_sample()` comparait chaque lecture à la **précédente**, donc mesurait une pente et
non une valeur bloquée ; à la cadence réelle de 10 s une température saine bouge de 0,01 °C sous un
epsilon de 0,02 °C. Preuve la plus nette : l'épisode du 30/08 02:40:30Z → 04:31:41Z, 6 671 s
déclarées figées pendant lesquelles la température est passée de 25,92 à 26,24 °C. Le même signal
donnait « figé » à 5 s et 10 s d'intervalle et « sain » à 60 s — un verdict fonction de la cadence.

- [x] Ancrer la comparaison sur la valeur du dernier changement réel (`freeze_anchor_value`) au lieu
      de l'échantillon précédent : le verdict devient invariant par cadence
- [x] Passer `freeze_epsilon` à `0.0` pour `BME280T`, `BME280H` et `BME280P`, aligné sur les DS18B20.
      Base de mesure : sur 38 h la plus longue plage de valeurs strictement identiques est de 361 s
      (T), 181 s (H) et 181 s (P), contre des seuils de 1 800 s et 3 600 s
- [x] Supprimer le double arrondi à 0,01 (`lib/sensors/BME280.py` et `BME280Handler._safe`) : la
      précision complète doit atteindre la politique qualité. Arrondi déplacé à l'affichage (filtre
      Jinja `mesure`, `toFixed` côté JS), `decimals` ajouté à la charge utile des min/max
- [x] Supprimer le cliquet de réarmement : trois variations **réelles** suffisent, un échantillon
      calme intercalé ne remet plus le compteur à zéro
- [x] Documenter la séparation des rôles (figement = vivacité de l'acquisition ; redondance =
      justesse) dans `docs/reference/configuration.md`, `safety-model.md`, `verification.md` et
      `CLAUDE.md`/`AGENTS.md`
- [x] Ajouter les tests de non-régression, dont le **test de propriété d'invariance par cadence**
      (5 s / 10 s / 60 s) qui interdit la classe de bug — suite complète : 150 tests verts
- [x] Déployer après la clôture de la fenêtre en cours, puis relancer une observation de 172 800 s
      au commit corrigé. **Fait le 30 août 2026** : déploiement de `985e42d` à 19:07:27 UTC
      (`NRestarts=0`, `boot_id` inchangé), puis nouvelle fenêtre lancée à 19:09:11 UTC — fin attendue
      le **1er septembre à 19:09:11 UTC**, observateur `722191`, service `721771`, preuves sous
      `~/phyto-observations/jalon2-operateur-qualite-20260830T190911Z`
- [x] Contrôler après déploiement : `healthy`/`control_healthy` à `true`, dix tâches saines sans
      restart ni stall, sept domaines sains, **zéro alarme active** (les deux alarmes
      `sensor_quality` latchées ont disparu), trois capteurs en `normal` sans `reason_codes`,
      compteurs d'incohérences remis à zéro, HTTP et HTTPS à 200, aucune entrée de journal en
      WARNING ou plus depuis le démarrage, six actionneurs en `tracking=ok`
- [x] Confirmer les seuils effectifs dans le code déployé : `freeze_epsilon = 0.0` pour les trois
      BME280, `freeze_after_seconds` à 1 800/1 800/3 600, `freeze_min_samples = 30`, mode `observe`,
      aucun profil surchargé ; `runtime_state.json` porte bien `freeze_anchor_value`. Suppression du
      double arrondi visible : `raw_value = 28.523013138119133` au lieu de deux décimales
- [x] Vérifier sur la nouvelle fenêtre que `BME280T`/`BME280H` ne produisent plus d'avertissement de
      figement et que le statut reste `normal` sur les périodes calmes de nuit. **Clôturée le
      1er septembre 2026 à 19:09:11 UTC** : `status=accepted`, 172 800 s réelles, 2 864 échantillons,
      zéro échec, zéro avertissement et 2 864/2 864 statuts `normal` pour chacune des trois mesures
      BME280. Les deux tranches nocturnes du relevé intermédiaire étaient déjà exemptes de faux
      figement.
- [x] Combler le manque côté API : `/api/v1/state` publie désormais `freeze_epsilon`,
      `freeze_after_seconds` et `freeze_min_samples` avec les autres seuils effectifs ; contrat
      documenté, testé et exigé par l'observateur. **Déployé après clôture de la fenêtre le
      1er septembre 2026 au commit `2ecefb1`** : mode `observe` conservé, seuils effectifs conformes
      pour les trois BME280, dix tâches saines et zéro alarme.

**Points laissés ouverts, à mesurer avant activation** (ne pas régler à l'aveugle) :

- `MLX-AMB` et `MLX-OBJ` conservent `freeze_epsilon = 0.05`. La sémantique est désormais saine (bande
  morte ancrée), mais la valeur n'est appuyée sur aucune mesure de bruit — à qualifier si ces
  capteurs sont activés.
- `DS18Handler` arrondit encore à 0,1 °C, une grille bien plus grossière que la résolution réelle des
  sondes. Avec `freeze_epsilon = 0.0`, un plateau prolongé dans un bac d'eau stable pourrait produire
  un faux positif. Sondes désactivées aujourd'hui ; à traiter avant de les activer.

## 3. Calibrer les profils

- [ ] Comparer chaque capteur actif avec un instrument de référence adapté et consigner la méthode,
      la date, les conditions et l'incertitude de la comparaison
- [ ] Renseigner l'offset et la date de calibration, puis vérifier que les diagnostics, compteurs et
      min/max concernés sont réinitialisés comme prévu
- [ ] Ajuster, mesure par mesure, la fraîcheur, la plage plausible, l'epsilon, la durée et le nombre
      minimal d'échantillons de figement à partir des observations réelles
- [ ] Confirmer après chaque modification que les seuils effectifs publiés par l'API correspondent à
      la configuration et qu'aucun ancien diagnostic calculé avec les seuils précédents ne subsiste
- [ ] Laisser à nouveau fonctionner au moins une période représentative après le dernier ajustement

## 4. Stabiliser les identités DS18B20

- [ ] Si les DS18B20 restent désactivés, consigner que cette étape est non applicable ; sinon relever
      physiquement l'identifiant `28-xxxxxxxxxxxx` de chaque sonde
- [ ] Lier chaque `DS18B#1`, `DS18B#2` et `DS18B#3` actif à son identifiant 1-Wire stable depuis
      `/conf`, sans utiliser l'ordre de découverte sysfs
- [ ] Redémarrer le service et vérifier que chaque nom métier conserve la même sonde, la même
      calibration et la même zone malgré un ordre de découverte éventuellement différent
- [ ] Débrancher puis rebrancher une sonde pendant une procédure contrôlée et confirmer qu'elle est
      déclarée absente puis rétablie sans emprunter l'identité d'une autre sonde

## 5. Qualifier la redondance

- [ ] Ne créer un groupe que pour des sondes de même unité, physiquement comparables et exposées au
      même phénomène ; documenter leur emplacement et la tolérance retenue
- [ ] Vérifier avec deux sondes en désaccord qu'aucune n'est choisie arbitrairement
- [ ] Pour tout groupe de trois sondes ou plus, vérifier qu'une valeur divergente est isolée par un
      quorum cohérent
- [ ] Vérifier qu'un quorum indisponible produit un état dégradé ou incohérent explicite et non une
      fausse mesure de confiance
- [ ] Vérifier qu'après un désaccord, trois comparaisons cohérentes sont nécessaires au réarmement
- [ ] Refaire une période d'observation après toute modification d'un groupe ou de sa tolérance

## 6. Qualifier matériellement le repli

- [ ] Planifier une intervention supervisée, charges haute tension consignées au premier passage,
      conformément à `docs/development/hardware-validation.md`
- [ ] Vérifier d'abord le repli historique sur cinq lectures de température manquées : chauffage
      réellement OFF, moteur à `sensor_fallback_speed`, alarme persistante et GPIO cohérents
- [ ] Simuler de façon bornée un figement plausible de `BME280T` en restant en mode `observe` et
      confirmer que le diagnostic apparaît sans changement de sortie
- [ ] Vérifier la récupération du figement sur trois variations plausibles réelles
- [ ] Préparer le scénario armé avec chauffage et moteur sous surveillance, une méthode de retour
      immédiat vers `observe` et une protection thermique indépendante fonctionnelle

## 7. Armer progressivement

- [ ] Avant armement, confirmer : période d'observation terminée, zéro faux positif non expliqué,
      profils stabilisés, identités DS18B20 fixées, redondance qualifiée, matériel validé et moyen de
      retour disponible
- [ ] Relever le commit, l'heure, l'opérateur, les statuts qualité, l'état climatique, les GPIO,
      `control_healthy()`, le watchdog et les alarmes actives
- [ ] Dans `/conf`, passer de `observe` à `enforce` en saisissant explicitement `ARMER`
- [ ] Vérifier immédiatement qu'une incohérence déjà confirmée déclenche `REPLI_CAPTEUR` sans attendre
      une nouvelle lecture : chauffage OFF et moteur à `sensor_fallback_speed`
- [ ] Vérifier qu'en l'absence d'incohérence confirmée l'armement ne provoque ni clignotement de relais,
      ni transition moteur, ni redémarrage anormal d'une tâche
- [ ] Surveiller étroitement un premier cycle complet, puis une période représentative, avec contrôle
      conjoint de l'API, des alarmes, d'InfluxDB, des GPIO et de l'état physique de la serre

## 8. Rollback et critères de clôture

- [ ] Tester le retour `enforce` → `observe` et confirmer qu'une décision qualité déjà en cache perd
      immédiatement son autorité de blocage sans nécessiter de nouvelle lecture matérielle
- [ ] Exercer si nécessaire le rollback applicatif selon la procédure documentée, sans modifier les
      identités ni effacer les preuves de calibration
- [ ] Confirmer après retour ou rollback : service prêt, contrôle sain, watchdog caressé, sorties
      cohérentes, données de confiance non contaminées et alarmes expliquées
- [ ] Mettre à jour le changelog, la roadmap, le registre des risques et un relevé d'exploitation avec
      les dates, seuils retenus, résultats et limites résiduelles
- [ ] Ne déclarer la qualité capteurs « déployée et armée » qu'après clôture de toutes les cases
      applicables et preuve qu'aucune étape n'a dégradé la régulation ou la sûreté électrique

**Limites à conserver dans la clôture** : la détection logicielle ne couvre pas un défaut commun à
plusieurs sondes, un figement plus court que le seuil, un relais mécaniquement collé, la fenêtre de
boot ou une défaillance du Pi. Le thermostat ou fusible thermique indépendant reste obligatoire.

---

# TODO — Sortir la vitesse moteur 4 de GPIO 1 (`ID_SC`)

**Contexte** : diagnostic du 25/08/2026. `motor_pin4` est câblé sur **BCM 1 = `ID_SC`**, broche
réservée à l'EEPROM d'identification des HAT et sondée par le firmware en ALT0 au démarrage.
Le canal fonctionne aujourd'hui (relais qui colle, moteur qui tourne), mais ce n'est pas une
broche GPIO générale : à déplacer par précaution, indépendamment de la panne des vitesses 1 et 3
(qui, elle, est côté puissance et ne se corrige pas en changeant de broche).

**Broche cible proposée : BCM 16** — libre sur ce Pi, aucune fonction alternative gênante, et
déjà en `ip pd | lo` au boot (pull-down par défaut), donc relais moteur actif-HAUT au repos tant
que le service n'a pas démarré. Autres candidates libres : 12, 13, 19, 20, 24 (éviter **6**, qui
est en `ip pu | hi` au boot).

- [ ] Couper le secteur, déplacer le fil de la sortie moteur 4 de la broche physique 28 (BCM 1)
      vers la broche physique 36 (BCM 16)
- [ ] `param/param.json` : `GPIO_Settings.motor_pin4` : `1` → `16` (dépôt local **et** copie du Pi
      `/home/progradius/PhytoController/RPi Version/param/param.json`)
- [ ] Redémarrer `phyto.service` et vérifier au log `MotorHandler (active-HIGH) initialisé sur
      pins [25, 8, 7, 16]`
- [ ] Vérifier au `pinctrl` que BCM 1 est bien relâchée et que BCM 16 pilote le relais 4
      (`pinctrl set 16 op pn dh` → `hi` + claquement + moteur qui tourne)
- [ ] Contrôler qu'aucune autre entrée de `GPIO_Settings` n'utilise 16

**Aucune modification de code nécessaire** : les broches moteur viennent toutes de la config
(`MotorHandler.__init__`, `motor_all_pin_down_at_boot`), et les broches moteur sont déjà exclues
de `GENERIC_SAFE_PINS` dans `main.py`.

---

# TODO — Refonte de l'interface web et de l'acquisition capteurs

**État : implémenté dans l'arbre de travail, vérifié hors matériel, non commité, non déployé.**

## Serveur

- [x] Remplacer le serveur `asyncio.start_server` artisanal par `aiohttp` à routes explicites
- [x] Intergiciels : en-têtes de sécurité + `no-store`, validation du `Host`, CSRF + `Origin`
- [x] Limites : corps 64 Kio, ligne/en-têtes 8190 octets, `shutdown_timeout`, `backlog`
- [x] Assets servis par liste blanche exacte de chemins (fin de la traversée `/static/`)
- [x] `/api/v1/state` versionné, `/health/live`, `/health/ready` (503 sur défaut)
- [x] Actions destructrices sur des routes POST dédiées + confirmation navigateur
- [x] `/monitor` réduit à une redirection ; `POST /monitor` conservé pour compatibilité
- [x] Pages d'erreur HTML pour un navigateur, texte brut sinon, redirections préservées

## Configuration

- [x] `POST /conf/{section}` : candidat `AppConfig` complet revalidé avant écriture atomique
- [x] Rejet sans effet sur `param.json` **ni** sur la configuration vivante
- [x] `replace_from()` : publication dans l'instance partagée, sans réinstanciation
- [x] `supervisor.request_reload()` : relance volontaire, état sûr réappliqué, compteur `reloads`
- [x] Bornes et contraintes croisées (horaires, vitesses, températures, port Influx)
- [x] `validate_assignment` sur tous les modèles
- [x] Secrets ni affichés ni journalisés ; champ vide = valeur conservée
- [x] `GPIO_Settings` en lecture seule

## Capteurs

- [x] `controllers/sensor_catalog.py` : table canonique clés / activation / libellés / measurements
- [x] Exécuteur à un fil : plus aucune lecture bloquante dans l'event loop
- [x] Instantané partagé + job supervisé `sensor_snapshot` (10 s) ; HTTP ne lit plus le matériel
- [x] `reconfigure()` en place, `close()` à l'arrêt du superviseur
- [x] Export Influx en aiohttp, alimenté par l'instantané, jamais de valeur périmée poussée

## Nettoyage

- [x] `network/web/api_handler.py` et `templates/monitor.html` supprimés
- [x] `SystemStatus.get_cyclic_period()` : `period_minutes` inexistant → `period_days`
- [x] `requirements.txt` : `requests` retiré, `jinja2` et `aiohttp>=3.12.15,<3.14` ajoutés

## Reste à faire

- [x] Commiter, déployer sur le Pi et relever le comportement réel (`/health/ready`, console SSE,
      sauvegarde d'une section) — commits `7d455e4`/`ad39de2`, déployés le 25 août 2026 ;
      `/health/ready` 200, flux SSE reçu, `POST /conf/logs` et `/conf/heater` enregistrés, rejet 422
      sans écart de `param.json` (relevé `docs/archive/operations/web-baseline-2026-08-25.md`)
- [ ] Relever sur le Pi une bascule capteur réelle (`reconfigure()` avec le matériel) — non exercée
      par le relevé du 25 août ; suivie par M-CONF-03 dans `docs/risk-register.md`
- [x] `scripts/deploy.sh` : qualifier service, liveness, readiness, contrôle, commit, alarmes critiques
      et stabilité continue avant succès ou après rollback
- [x] Transformer le harnais de fumigation HTTP en vérification reproductible — remplacé par
      `tests/test_http_server.py` (`f8a181d`, 26 août 2026), aiohttp `TestClient` sur loopback : Host
      étranger 421, CSRF/Origin 403, rejet sans écriture, secret vide conservé, horaires, erreurs HTML
      ou texte, remise à zéro de statistique
- [ ] Sortir les commandes système (`nmcli`, `ping`, `timedatectl`, reboot) de l'event loop
- [ ] Contraintes GPIO (unicité, broches réservées) — dépend du `PinRegistry` du lot 3

---

## Revue — refonte web

**Vérifications effectuées** (harnais jetable `/tmp/claude-1000/phyto/test_web.py`, aiohttp
`TestClient`, stubs `RPi.GPIO`/`smbus2`, `param.json` et `sensor_stats.json` sauvegardés puis
restaurés) : **55 contrôles, aucun échec**.

1. Rendu 200 de toutes les routes servies, CSP et `no-store` présents, **aucun secret dans le
   HTML** de `/`, `/conf` et `/console`.
2. `/api/v1/state` : `schema_version=1`, sections attendues, seules les mesures activées.
3. Refus : `Host` étranger → 421, POST sans jeton → 403, `Origin` tiers → 403, champ inattendu →
   422, section inconnue → 404, traversée `/static/../` → 404.
4. `POST /conf/temperature` avec min > max → 422, `param.json` **inchangé** ; puis valeur valide
   → 303, fichier réécrit, configuration vivante à jour, `motor_temp_control` et `heat_control`
   relancés.
5. Secrets Influx laissés vides → valeur conservée ; port hors bornes → 422.
6. `POST /conf/sensors` → `reconfigure()` appelé exactement une fois sur l'instance existante.
7. Réinitialisation de statistique : clé valide → 303, clé inconnue → 400.
8. Horaires : `07:30` accepté et appliqué, `25:00` refusé, `07:30:00` accepté (secondes ignorées).
9. Pages d'erreur : 404/403 en HTML pour un navigateur, en texte pour un client JSON ;
   redirections 303 non transformées ; 405 conserve son en-tête `Allow`.

**Corrections apportées pendant la revue** :

- `<input type="time">` renvoyant `HH:MM:SS` provoquait un 422 : les secondes sont désormais
  ignorées.
- `pages.error_page()` et `templates/error.html` étaient du code mort : ils rendent maintenant
  les erreurs ≥ 400 destinées à un navigateur, redirections exclues.

**Points d'attention traités ensuite** (correctifs suivants, mêmes conditions de vérification —
harnais `/tmp/claude-1000/phyto/test_fixes.py`, **21 contrôles, aucun échec**) :

- [x] **Jeton CSRF régénéré à chaque démarrage** → `utils/csrf.py` : jeton persistant dans
      `param/.csrf_token` (0600, ignoré par git). Un `systemctl restart` n'invalide plus les
      pages ouvertes. Fichier absent, tronqué ou corrompu → régénération ; écriture impossible →
      repli sur un jeton en mémoire, journalisé, jamais fatal.
      *Vérifié* : jeton identique après relecture, mode 0600, régénération sur contenu invalide,
      repli sans exception sur chemin non inscriptible.
- [x] **Sauvegarde d'une section coupant brièvement la sortie** → `TaskSupervisor._runner()` ne
      repositionne plus l'état sûr sur un rechargement **volontaire**. Il le fait toujours sur
      panne, blocage et terminaison anormale, et toujours **avant** le back-off.
      *Vérifié* : `request_reload()` relance sans appeler `safe_state`, `reloads=1`,
      `restarts=0` ; une panne simulée appelle bien `safe_state` et incrémente `restarts`.
      *Résidu voulu* : un timer cyclique annulé pendant sa fenêtre ON voit sa sortie coupée par
      le `finally` d'`energized()` — une sortie ne doit pas rester fermée sans boucle pour la
      surveiller.
- [x] **`SensorStats` sans verrou** → `RLock` autour de `update()`, `clear_key()` et `_dump()`,
      et `get_all()`/`stats` renvoient une copie profonde.
      *Vérifié* : 4 fils concurrents (2 écrivains, 2 lecteurs, 800 mises à jour), aucune
      exception, min/max exacts, copie non partagée, fichier relu cohérent.

**Points d'attention restants** :

- Le Pi exécute `aiohttp 3.11.18`, sous le plancher `>=3.12.15` du nouveau `requirements.txt` :
  `scripts/deploy.sh` met le venv à jour automatiquement, une installation manuelle non.

---

# TODO — Qualification opérationnelle de la PWA locale

**État : code et HTTPS `:443` déployés ; transport TLS vérifié le 28 août 2026, qualification complète
sur Chrome Android et essais de dégradation encore ouverts.** Relevé :
[`docs/archive/operations/pwa-tls-activation-2026-08-28.md`](../docs/archive/operations/pwa-tls-activation-2026-08-28.md).

Procédure de référence : [`docs/operations/pwa-local-tls.md`](../docs/operations/pwa-local-tls.md).
HTTP `:8123` doit rester la voie de compatibilité et de récupération pendant toute la qualification.
Une panne TLS ou PWA ne doit jamais dégrader la régulation, `control_healthy()` ou le watchdog.

## 1. Préparer et activer TLS

- [x] Créer l'autorité privée sur le poste d'administration, dans un emplacement protégé situé hors
      du dépôt — faite le 28 août 2026 (répertoire `0700`, clés `0600`, clé racine jamais transférée
      au Pi, au dépôt ni au client ; relevé d'activation TLS, « Autorité et certificat créés hors du Pi »)
- [ ] Sauvegarder `phyto-root-ca.key` hors du Raspberry Pi et d'Android, sur un support chiffré ou
      amovible protégé, et vérifier qu'une restauration est possible — encore ouvert au relevé du 28 août
- [x] Générer le certificat serveur avec `deploy/pwa-tls-server.ext`, puis vérifier sa chaîne, son
      échéance, l'usage `TLS Web Server Authentication` et les SAN `phytocontroller.local`,
      `phytocontroller` et `10.42.0.1`
- [x] Comparer et consigner l'empreinte SHA-256 de `phyto-root-ca.crt` avant toute distribution
- [x] Installer sur le Pi uniquement `server.crt`, `server.key` et le certificat public de la racine,
      avec les propriétaires et modes documentés ; confirmer que la clé privée est lisible par
      `progradius` mais pas par les autres utilisateurs
- [x] Installer le drop-in `deploy/phyto.service.d/pwa-tls.conf`, exécuter `daemon-reload`, puis
      redémarrer le service — fait le 28 août 2026 à 20:36:18 CEST, `NRestarts=0`,
      `CAP_NET_BIND_SERVICE` acquis, `control_healthy=true`, zéro alarme critique (relevé d'activation TLS)
- [ ] Consigner la vérification des états GPIO sûrs autour de ce redémarrage — absente du relevé du
      28 août, qui ne publie que la santé du contrôle et les alarmes
- [x] Vérifier que `:8123` et `:443` écoutent simultanément, que `/health/ready` répond sur HTTP et que
      `/health/live` répond en HTTPS avec validation complète de la chaîne et du nom d'hôte
- [x] Vérifier dans `/api/v1/state` que `web.https.configured=true`, `ready=true` et `port=443`, sans
      exposition des chemins de clé ou de certificat
- [ ] Simuler un échec TLS contrôlé pendant une fenêtre prévue et confirmer que HTTP `:8123`, la
      régulation, `control_healthy()` et le watchdog restent sains, avec `web.https.ready=false`

## 2. Installer et contrôler la PWA sur Chrome Android

- [ ] Transférer uniquement `phyto-root-ca.crt` sur le terminal Android et comparer son empreinte
      SHA-256 avec celle consignée sur le poste d'administration
- [ ] Installer la racine comme autorité pour les applications ; ne jamais transférer
      `phyto-root-ca.key`, `server.key` ni un fichier PKCS#12 sur le terminal
- [ ] Ouvrir `https://phytocontroller.local/` dans Chrome et vérifier l'absence d'interstitiel ou
      d'avertissement TLS
- [ ] Installer la PWA avec le bouton du tableau de bord et confirmer le lancement en fenêtre
      autonome, l'icône normale/maskable et le nom `PhytoController`
- [ ] Vérifier les raccourcis d'écran d'accueil « Tableau de bord » et « Alarmes » et confirmer qu'ils
      ouvrent la bonne vue dans la PWA

## 3. Qualifier la coupure réseau et la fraîcheur dominante

- [ ] En ligne, ouvrir le tableau de bord et les alarmes, attendre au moins un rafraîchissement réussi
      de l'état, des alarmes et de l'historique, puis relever leurs heures de réception
- [ ] Couper réellement le réseau entre Android et le Pi sans arrêter la PWA
- [ ] Vérifier que la bannière rouge `HORS LIGNE` apparaît rapidement et reste visible sur toutes les
      vues avec « données datant au mieux de… · non actualisées · lecture seule »
- [ ] Vérifier que l'âge affiché augmente avec le temps et qu'aucun snapshot IndexedDB ne remet la vue
      en état « à jour »
- [ ] Vérifier que les dernières vues Tableau de bord et Alarmes restent lisibles, que l'historique
      annonce explicitement l'âge de son snapshot et que les alarmes stockées portent « État non
      confirmé » / « Lecture seule hors ligne »
- [ ] Vérifier que tous les formulaires et boutons de mutation sont désactivés hors ligne, notamment
      acquittement, configuration, remise à zéro, reboot et extinction
- [ ] Inspecter Cache Storage et confirmer l'absence de `/api/**`, `/health/**`, `/status`, du SSE et
      de toute requête POST ; confirmer qu'aucune commande n'est mise en attente ou rejouée
- [ ] Tenter d'ouvrir `/conf`, `/console` et une URL inconnue hors ligne : elles doivent afficher le
      repli neutre, jamais une ancienne page de configuration ou de console

## 4. Qualifier la reconnexion

- [ ] Rétablir le réseau et confirmer que la bannière ne disparaît qu'après une réponse HTTP réelle du
      contrôleur, jamais sur le seul événement navigateur `online`
- [ ] Si la PWA a démarré hors ligne, confirmer qu'elle recharge une seule fois la vue après le premier
      contact réussi, sans boucle de rechargement
- [ ] Vérifier que l'état, les alarmes et l'historique redeviennent frais, que les actions sont
      réactivées et qu'aucune mutation ancienne n'est envoyée
- [ ] Répéter au moins deux cycles coupure/reconnexion et confirmer que l'âge, la bannière et les
      snapshots restent cohérents

## 5. Qualifier les notifications locales

- [ ] Depuis la page Alarmes, vérifier que Chrome ne demande aucune permission avant le clic explicite
      sur « Activer les notifications »
- [ ] Activer les notifications et confirmer que les alarmes déjà présentes servent de référence sans
      déclencher une rafale rétrospective
- [ ] Provoquer de façon sûre une **nouvelle** alarme non acquittée affectant le contrôle, puis vérifier
      une notification unique, son libellé minimal et l'ouverture du bon diagnostic au toucher
- [ ] Vérifier qu'une alarme auxiliaire non critique ne notifie pas et qu'une alarme critique notifie
      même si elle est auxiliaire
- [ ] Vérifier qu'un rafraîchissement de la même occurrence UUID ne renotifie pas ; vérifier qu'une
      escalade de gravité peut renotifier une fois
- [ ] Couper le réseau avec un snapshot d'alarme enregistré et confirmer que sa restauration ne
      déclenche aucune notification
- [ ] Désactiver les notifications depuis l'IHM et confirmer qu'aucune nouvelle notification locale
      n'est émise
- [ ] Consigner la limite attendue : aucune garantie lorsque Chrome suspend ou ferme complètement la
      PWA, puisqu'il n'existe ni Web Push ni service externe

## 6. Exercer le rollback contrôlé

- [ ] Avant rollback, relever le commit, l'état de `phyto.service`, `NRestarts`, `/health/ready`, les
      sorties physiques et la disponibilité simultanée de `:8123` et `:443`
- [ ] Effectuer le rollback selon `docs/operations/deployment-and-rollback.md`, sans `git reset --hard`
      improvisé et sans supprimer les certificats sous `/etc/phyto/tls`
- [ ] Confirmer après rollback que la régulation et HTTP `:8123` sont sains, même si `:443` disparaît
      avec une version antérieure à la PWA
- [ ] Confirmer que la PWA déjà installée reste honnêtement hors ligne avec son dernier snapshot et ne
      présente jamais ces données comme actuelles
- [ ] Redéployer la version PWA, vérifier le retour de `:443`, l'actualisation du service worker et le
      rétablissement des données fraîches
- [ ] Si la coque locale reste bloquée sur une ancienne version, exercer puis documenter la procédure
      de désinstallation ou d'effacement des données du site Chrome

## Critères de clôture

- [ ] Toutes les cases précédentes sont accompagnées d'une date, du terminal Android/Chrome utilisé et
      des observations utiles, sans recopier de secret ni de clé
- [ ] Aucun défaut TLS, cache, notification ou navigateur observé pendant la qualification n'a affecté
      les boucles de contrôle, les sorties GPIO, `control_healthy()` ou le watchdog
- [ ] La clé `phyto-root-ca.key` est absente du Pi, d'Android, de Git et des sauvegardes applicatives
- [ ] Les risques `R-WEB-05` et `R-WEB-06` de `docs/risk-register.md` sont réévalués avec les preuves de
      qualification avant de déclarer la PWA déployée et vérifiée

---

# TODO — Jalon 3 « Configuration guidée » (plan `qol_operator_experience_plan.md`)

**Arbitrages opérateur du 28 août 2026**

- Profil thermique du mode Simple : **aligné sur la configuration déployée**, pas sur la proposition
  du plan — hystérésis 2 °C, zone morte 1 °C, palier 1 °C, relâchement 0,5 °C, maintien 120 s,
  plancher 5 °C, repli capteur 0, marge hiver 2 °C, budgets renouvellement 5 min/h et humidité
  15 min/h, vitesse minimale 0, vitesse hiver par défaut 1. Passer en mode Simple ne modifie donc
  aucun réglage fin tant que l'opérateur ne touche pas aux champs exposés.
- Intensité douce / normale / forte : **mapping du plan conservé** (2/2, 3/3, 4/4 pour
  `max_speed` / `winter_refresh_speed`). Rappel consigné : les vitesses moteur 1 et 3 sont hors
  service côté puissance, « normale » commande donc une vitesse morte tant que la panne dure.
- Livraison en **trois commits** déployables et retirables séparément.

## Commit 1 — 3a formulaire sans perte + 3b registre central des champs

- [x] Étendre `SECTION_FIELDS` en registre : chaque entrée porte sa cible de configuration **et**
      son libellé humain ; supprimer les listes de noms dupliquées
- [x] Construire l'index inverse `payload → champ de formulaire` à partir du même registre
      (horaires compris : `*_hour` / `*_minute` → `start_time` / `stop_time`)
- [x] Humaniser les messages Pydantic (table type → phrase française, bornes injectées depuis `ctx`)
- [x] Rattacher les contraintes croisées aux deux champs concernés (min/max jour, min/max nuit,
      vitesse min/max) au lieu d'une erreur globale
- [x] Re-rendre la saisie du POST sur 422 (multidict), secrets jamais réémis, portée par formulaire
      (`sensor-quality` porté par sa clé capteur)
- [x] Afficher l'erreur sous le champ (`aria-describedby`, `aria-invalid`), bandeau global réservé
      aux erreurs non rattachables
- [x] Focus sur le premier champ refusé ; un champ numérique refusé se re-rend en texte pour que la
      valeur rejetée reste visible et corrigeable
- [x] Factoriser les quatre réponses 422/500 de `_configuration_post` en un seul point
- [x] Tests : saisie conservée, secret absent du HTML, contrainte croisée rattachée, message humanisé

## Commit 2 — 3c prévisualisation serveur

- [x] `POST /api/v1/config/preview` : mêmes parseurs, candidat Pydantic complet, aucune écriture
- [x] Garde d'in-flight (un preview à la fois) + intervalle minimum, corps jamais journalisé,
      aucun champ sensible en réponse, jeton en en-tête `X-CSRF-Token`
- [x] Réponse portant le **seuil de ventilation effectif** reconstruit par `settings_from_config`
      (jour et nuit), l'indicateur « seuil relevé » et les écarts détectés
- [x] IHM : encart de prévisualisation par section, aucune formule thermique dupliquée en JavaScript

## Commit 3 — 3d mode Simple, dirty-check et flash

- [x] Sélecteur Simple / Avancé, simple par défaut, choix mémorisé en `localStorage`
- [x] Section Simple : planning jour/nuit, min/max jour et nuit, humidité max, intensité, saison,
      chauffage, plannings ; profil et mapping ci-dessus
- [x] Un `motor_mode` manuel existant exige un choix explicite avant toute écriture
- [x] Le mode Simple ne s'affiche que si la prévisualisation répond
- [x] Dirty-check sur écarts réels, bouton d'annulation, `beforeunload`
- [x] Flash opaque côté serveur après succès : champs modifiés, heure, mode d'application

## Vérification (identique pour les trois commits)

*Preuve rétrospective du 11/09/2026* : les quatre commits `5c4256a`, `ee42a78`, `f9e7273` et
`054e173` extraits par `git archive` (sans checkout) et rejoués un par un.

- [x] `python -m pyflakes` sur tout l'arbre — 0 « undefined name » (leçon du 26 août 2026) — 0 sur
      chacun des quatre commits (hors `lib/`)
- [x] `python3 -m pytest` vert, sortie conservée dans un fichier temporaire — 131, 135, 140 et
      141 réussites, zéro échec
- [x] Aucun secret dans le HTML rendu — `test_pages_dynamiques_et_secrets_absents`,
      `test_saisie_refusee_est_reaffichee_sans_secret` et
      `test_previsualisation_ne_renvoie_jamais_un_secret`, verts sur `054e173`
- [ ] Aucun secret dans les journaux — aucun test ne l'établit ; relève de la vérification sur le Pi
      ci-dessous (refus des sections `wifi` et `influx`)
- [x] `diff -u CLAUDE.md AGENTS.md` vide si l'un des deux change — vide sur chacun des quatre commits

## Revue — Jalon 3 livré le 28 août 2026

Trois commits sur `feature/qol-operator-experience`, déployables et retirables séparément :

| Commit | Contenu |
|---|---|
| `5c4256a` | 3a + 3b — registre de champs, saisie conservée sur 422, messages humanisés |
| `ee42a78` | 3c — `POST /api/v1/config/preview` et seuil de ventilation effectif |
| `f9e7273` | 3d — mode Simple, suivi des écarts, compte rendu opaque |
| `054e173` | correctifs de revue — compte rendu équipements, octet nul dans `config.js` |

**Critère du plan** — « aucune erreur ne force à ressaisir la section entière, aucun secret ne
réapparaît et le mode simple a un effet déterministe prévisualisé (seuil effectif inclus) » :
couvert et testé (`tests/test_http_server.py`, 141 tests verts).

**Écart assumé par rapport au plan.** Le profil du mode Simple reprend les valeurs déployées et non
celles proposées par le plan (hystérésis 2 °C au lieu de 1 °C, budgets hiver 5/15 au lieu de 8/6) —
arbitrage opérateur, pour qu'un passage en mode Simple ne modifie aucune régulation par lui-même.
Le mapping d'intensité du plan est conservé tel quel, malgré les vitesses moteur 1 et 3 hors
service côté puissance.

**Limite connue, à consigner.** La stickiness des sous-fiches « qualité capteur » conserve la
saisie mais laisse le message d'erreur dans le bandeau global : ces formulaires ne passent pas par
`SECTION_FIELDS`, donc aucune erreur n'y est rattachable à un champ. Le reste des sections place
bien le message sous le champ.

**Reste à faire avant de déclarer le jalon vérifié** (hors portée d'une session sans matériel) :

- [x] Déploiement via `scripts/deploy.sh`, puis vérification HTTP et états GPIO — les quatre commits
      sont ancêtres de `985e42d` (déployé le 30 août 2026 à 19:07 UTC : santé complète, HTTP et HTTPS
      à 200, six actionneurs en `tracking=ok`) et de `2ecefb1` (déployé le 1er septembre, niveaux GPIO
      relevés en référence dans `docs/archive/operations/jalon4-deploiement-2026-09-02.md`) ;
      `git merge-base --is-ancestor` vérifié le 11/09/2026
- [ ] Essai navigateur réel du sélecteur Simple / Avancé, du `beforeunload` et de l'annulation
- [ ] Vérifier sur le Pi qu'aucun secret n'apparaît dans `logs/phyto.log` après un refus de la
      section `wifi` et de la section `influx`
- [ ] Critère de rollback écrit à l'avance et rollback exercé

# TODO — Jalon 4 « Overrides force-OFF, console et système » (plan `qol_operator_experience_plan.md`)

## Arbitrages opérateur (28 août 2026)

| Sujet | Décision |
|---|---|
| Force-OFF moteur vs protections thermiques | **Verrouillage absolu** — prime sur `REPLI_CAPTEUR` et `SECURITE_HAUTE` (écart assumé au plan v2) |
| Durée maximale | 4 h chauffage **et moteur** (garde-fou dérivé), 24 h ailleurs ; défaut 60 min |
| Coupure groupée | Oui — « Arrêt général (maintenance) » déplie les six cibles |
| Visibilité | Bannière globale dédiée + événement `override` en historique ; pas d'alarme pour le forçage lui-même |

Garde-fou compensatoire au verrouillage absolu : alarme `critical`
`motor_lockout_overheat` dès que la température dépasse le seuil de ventilation
effectif pendant qu'un forçage empêche de ventiler.

## Commit 1 — Overrides force-OFF

- [x] `utils/overrides.py` : `ForcedOff` (double horloge), `OverrideStore`, plafonds par cible,
      reprise au boot rebornée et « à confirmer » avant heure fiable
- [x] `utils/state_store.py` : `save(..., strict=True)` qui relance l'`OSError`, défaut inchangé
- [x] `climate_policy` : quatre échéances dans `ClimateInputs`, `_forced_off()` pur,
      `STATE_FORCED_OFF`, `ALARM_MOTOR_LOCKOUT`
- [x] Moteur : première branche de `_decide_motor`, avant `manual` et `sensor_lost`, `immediate=True`
- [x] Chauffage : post-filtre dans `decide()` — alarmes, compteur et cooldown préservés,
      `vent_threshold` intouché
- [x] `climate_control` : une lecture du magasin par tick, snapshot et modes publiés
- [x] Minuteries journalière et cyclique : lecture en tête de boucle, tranche ≤ 30 s
- [x] `main.py` : reprise avant l'initialisation des composants
- [x] Routes `POST /actions/overrides/create` et `/cancel`, cible `all`, 500 si non persisté,
      `request_reload` des minuteries seulement
- [x] `/api/v1/state` : clé `overrides` additive, avec plafonds
- [x] IHM : section « Interventions », dialogues, bannière globale (`render_template`), CSS
- [x] `OperatorService` : `record_override_event`, définition `motor_lockout_overheat`
- [x] Tests : `tests/test_overrides.py` (16), matrice pure (13), routes HTTP (10)
- [x] `pyflakes` 0 « undefined name », `pytest` 190 verts, aucun octet nul, `diff CLAUDE.md AGENTS.md` vide

## Commit 2 — Console

- [x] Flux SSE structuré JSON, tampon serveur 2 000 lignes
- [x] Barre d'outils : pause, autoscroll, filtres niveau/composant, recherche, compteurs,
      copie, téléchargement, effacement de la vue
- [x] Tampon client borné à 2 000, `textContent` uniquement
- [x] Paramètres d'URL `level` / `component` / `q`, liens d'alarme enrichis
- [x] Tests : JSON structuré, message multiligne, borne 2 000, absence d'`innerHTML`, liens

## Commit 3 — Reboot / extinction

- [x] Réponse 202 immédiate, commande différée, code retour toujours journalisé
- [x] Page de suivi + `system.js` : indisponibilité puis deux `/health/live`, échec probable à 30 s
- [x] `POST /monitor` legacy sur le même chemin, URL finale inerte
- [x] `_spawn_system_command` isolé : la suite de tests ne démarre jamais un vrai `reboot`
- [x] Tests : 202 avant lancement, argv correct, `/monitor` legacy, garde-fous du script

## Vérification du jalon 4

- [x] `pyflakes` sur tout l'arbre — 0 « undefined name »
- [x] `pytest` — 200 tests verts (`/tmp/pytest-j4j.txt`)
- [x] Aucun octet nul dans les fichiers texte (leçon du 28 août 2026)
- [x] `diff -u CLAUDE.md AGENTS.md` vide
- [x] Déploiement `scripts/deploy.sh` commit par commit, vérification HTTP et états GPIO sur le Pi
      (2 septembre 2026 — voir `docs/archive/operations/jalon4-deploiement-2026-09-02.md`)
- [x] Verrou moteur absolu qualifié sur matériel : mode manuel vitesse 2 → quatre broches LOW,
      puis retour à la vitesse 2 à la levée
- [x] Expiration automatique et reprise après redémarrage qualifiées sur le Pi
- [x] Raison d'un forçage absente de `phyto.log` et de `journalctl`
- [x] Essai réel d'un redémarrage : 202 avant coupure, disparition, `boot_id` changé,
      deux `/health/live` puis retour annoncé, GPIO identiques à la référence
- [x] Coupure en pleine impulsion qualifiée sur la serre : forçage créé pendant une phase ON
      séquentielle de `cyclic_2`, `energized()` coupe le relais à la seconde sur annulation de la
      tâche, et la phase reprend depuis l'état persisté à l'expiration
- [ ] Console : stabilité à 2 000 lignes en observation longue

La **coupure sur faute** est sortie du périmètre du jalon 4 (arbitrage du 2 septembre 2026) : le
jalon ne touche pas au chemin `energized()`, sa moitié logicielle est couverte par la suite de
tests, et sa moitié électrique appartient à `docs/development/hardware-validation.md`, où elle
était déjà inscrite (« Relais actifs-BAS » étapes 4-5, « Supervision et arrêt » étape 1).

## Lot F et lot « photos » du carnet (9 septembre 2026)

Suite des reliquats de la remédiation du lot UI 4. Point de départ `641a7ef`.

- [x] F1 — légende des courbes de solutions calculée par mesure (`chart_sources(..., metric)`,
      `{"ph","ec","all"}`, gabarit, JS, doc, tests purs/HTTP/spec, mutation : 4 tests tombent) — `9136e40`
- [x] F2 — `webServer` de Playwright : `global_setup.js`/`global_teardown.js`, `TMPDIR` déterministe
      par PID, quatre gardes au teardown ; 196 `/tmp/phyto-ui-*` avant et après `visual.spec.js` — `ce7022a`
- [x] Revue indépendante du lot F (2 à corriger, 1 démenti) et corrections (`trap` + `gracefulShutdown`,
      `globalTeardown` supprimé, docstring, libellé de légende vide, `html.unescape`) — `d6c101b`
- [x] Lot photos — aperçu local dans le socle (`register`), progression d'envoi par XHR dans
      `submitBinary` (signature inchangée), CSP `img-src blob:` (aperçu du lot 2 bloqué en production),
      spec `cultures_ui_photos.spec.js` 6/5/5/5 sur quatre profils, docs, rapport — `0e3593e`
- [x] Revue indépendante du lot photos (2 à corriger, 0 bloquant) et corrections (région atomique,
      aperçu par champ, barre dans les gardes, T7 avec mutation prouvée) — `ca91af6`
- [x] Validation de sortie : 823 pytest ; suite Playwright complète 306 / 124 exclusions / 0 échec ;
      garde externe 340 exclusions ; bilan `docs/archive/development/lot-f-photos-cultures-2026-09-09.md` ;
      `tasks/lessons.md`
- [ ] À demander à l'utilisateur : suppression des 196 `/tmp/phyto-ui-*` accumulés (16,5 Mio)

Hors périmètre (décision produit) : comparaison des cycles par âge du stade.

# Suivi — remédiation web, mobile et PWA (plan `docs/development/remediation-web-mobile-pwa-2026-09-09.md`)

Source : audit du 9 septembre 2026 (`docs/development/audit-web-mobile-pwa-2026-09-09.md`, départ `641a7ef`).
Baseline : départ `8023123` (arbre non commité à la reprise du 10/09/2026 16:00 ; pytest 850 réussites / 3 échecs
sur Solutions ; Playwright non rejoué par la première passe). État fiche par fiche établi par cinq relectures
Opus et contre-vérifié : section « État d'avancement — reprise du 10 septembre 2026 » du plan.

Reprise du 10/09/2026 (orchestrateur garant, agents Opus par périmètre de fichiers disjoints) :
- [x] Vague A (10/09, 16 h 40 → 19 h) — Solutions/fiche (A1), Cycles/Journal (A2), Plages/éclairage/équipements (A3),
      Tableau/alarmes/console (A4), PWA/brouillons/socle formulaires (A5)
- [x] Vague B (outillage, Configuration, Historique, docs) — outillage lot 0, Configuration, Historique, finitions lot 5, documentation, tests R4.1
- [x] Rejeu Playwright par profil, trois revues indépendantes (R1/R2/R3), vague de correction, remesure, commits par lot

## Arbitrages à obtenir avant les lots concernés
- [x] Barre mobile Serre · Cultures · Alarmes · Plus (R1.3)
- [x] Vues Saisir/Relevés/Analyser par `?view=` sur la route existante (R1.6)
- [x] Brouillons : texte et sélections seulement, mesures exclues, 24 h (R3.4)
- [x] Mise à jour PWA sans `skipWaiting` automatique (R3.3)
- [x] Nom de la route et de l'entrée « Application sur ce téléphone » (R2.4)

## Lot 0 — outillage
- [x] R0.1 script de mesure versionné `tests/ui/measure_pages.js` (rejoue `measures.json` à ±2 %)
- [x] R0.2 banc `scripts/benchmark-web-pages.py` + carnet 30/90/365 j
- [x] R0.3 macros `templates/macros/ui.html` (8 composants) + doc contributing

## Lot 1 — lecture et urgence
- [x] R1.1 Alarmes : occurrences avant notifications et filtres (UX-01)
- [x] R1.2 Tableau : bande compacte, priorités, lignes d'équipement repliables, défaut jamais caché (UX-02)
- [x] R1.3 Barre mobile avec Cultures, onglet actif du carnet visible (UX-03)
- [x] R1.4 Console : région nommée, `/console` dans le test axe, actions mobiles, repli presse-papiers (UX-04)
- [x] R1.5 Notifications : premier plan et connexion explicités, aide par navigateur (UX-06)
- [x] R1.6 Solutions : vues Saisir/Relevés/Analyser, état vide, relevés compacts (UX-07)
- [x] R1.7 Filtre `nombre` + réplique JS, données brutes inchangées (UX-08)
- [x] R1.8 Fiche : synthèse et actions en tête, retour à la liste positionné (UX-09)
- [x] R1.9 Pages d'erreur : retour contextuel, réessai GET ; résumé de `system_action.html` (vérifié à la reprise : tests pytest des referers et du réessai verts)
- [x] Vérification lot 1 : pytest, Playwright 5 profils un par un, pyflakes, `node --check`, octets nuls, `diff CLAUDE.md AGENTS.md`, mesures après

## Lot 2 — application mobile quotidienne
- [x] R2.1 Configuration : groupes, horaires, tableau modifié → appliqué, barre non masquante, virgule (UX-10)
- [x] R2.2 Historique : indicateurs, un tracé, détail sous le graphique, axes 13 px, `pan-y` (UX-11)
- [x] R2.3 Légendes courtes / complètes des graphiques
- [x] R2.4 Page `/app` : connexion, installation par plateforme, copies, notifications, version (UX-05)
- [x] R2.5 Hors ligne : `data-offline-local`, messages des filtres GET, `/offline` avec carnet (UX-12)
- [x] R2.6 Cycles : rappels du jour, À faire / Comparer, espace Sauvegarde
- [x] R2.7 Plages, éclairage, équipements : sélecteur d'abord, déclaré / appliqué, affectations en tête
- [x] R2.8 Journal : ligne par opération, détails repliés, recherche visible, contexte au retour
- [x] Vérification lot 2 (même liste) + docs `http-interface.md`, `pwa-local-tls.md`, `cultures.md`

## Lot 3 — cycle de vie PWA
- [x] R3.1 `fetchWithBudget` (8 s navigation, 15 s précache), test réseau muet et test 500 (UX-13)
- [x] R3.2 Initialisation sans attendre `serviceWorker.ready`, états worker/stockage en échec (UX-13)
- [x] R3.3 Mise à jour explicite : `updatefound`, bouton, `PhytoForms.isDirty()`, deux fenêtres (UX-14)
- [x] R3.4 Brouillons déclaratifs (après arbitrage) (UX-15)
- [x] Vérification lot 3 + CLAUDE.md/AGENTS.md (service worker, brouillons)

## Lot 4 — qualification
- [x] R4.1 Protocole Q01–Q15 et `qualification.spec.js` livrés (UX-16)
- [ ] R4.1 Grille appareils réels / VoiceOver / TalkBack / zoom / clavier virtuel remplie — **opérateur** (`docs/development/qualification-mobile-pwa.md`, aujourd'hui entièrement « NE »)
- [ ] R4.2 Baseline de performance sur Pi et téléphone, budgets, décision sur `/conf` (UX-17) — **opérateur** : outils prêts (`--base-url`, copie isolée), baseline Pi/téléphone à mener sur place
- [x] R4.3 Protocole de validation produit (dix tâches, objectifs chiffrés) — `docs/development/validation-produit-protocole.md`
- [ ] R4.3 Sessions P01–P10 avec deux opérateurs, résultats consignés, décisions sur les options préparées — **opérateur**

## Écarts résiduels (revérification du 11/09/2026 — détail dans le plan, section « État d'avancement »)
- [ ] E1 R5.1 `.actuator-group-title` à 0,78 rem sous 700 px (`style.css:551`)
- [ ] E2 R1.7 infobulle des points de Solutions non formatée (`culture_solutions.js:350`)
- [ ] E3 R2.5 `data-offline-filter` manquant sur le filtre Portée/Stade (`culture_light.html:81`)
- [ ] E4 R2.4 mention iOS 26 absente de l'aide d'installation
- [ ] E5 R2.8 index des copies repoussant « Opérations du carnet » sous le premier écran
- [ ] E6 R1.8/R2.7 premier écran de la fiche et de Plages avec cible non mesuré
- [ ] E7 R0.1 rejeu ±2 % de la baseline de l'audit non démontré

## Lot 5 — finitions
- [x] R5.1 Visitor réservée à la marque, chiffres tabulaires (UX-18)
- [x] R5.2 Contrastes plein jour, séries distinguables sans la couleur (UX-18)
- [x] R5.3 `.action-link` 44 px, glossaire des libellés (UX-18)
- [x] R5.4 Photo mobile : capture optionnelle, refus explicites, reprise sans doublon (UX-19)

## Revue de la reprise (10/09/2026, soirée)

- pytest : **914 réussites** ; `npm run test:js` : 9 ; pyflakes propre sur les fichiers touchés ; `diff -u CLAUDE.md AGENTS.md` vide ; aucun octet nul.
- Playwright : six profils (`desktop-chromium`, `mobile-chromium`, `mobile-etroit`, `mobile-paysage`, `pwa-chromium`, `mobile-zoom`), un worker, résultats consignés dans le plan (section « État d'avancement ») et le message de bilan.
- Mesures « après » : `docs/images/remediation-web-mobile-pwa-2026-09-09/` (R1.2 2 514 px, R1.6 1 881 px soit −42,3 %, R2.3 1 754 px, R2.8 115 px par entrée — réduction non vérifiable ; 0 violation axe sur 130 relevés, 0 contraste sous seuil ; chiffres finaux de `08a4815`, les valeurs intermédiaires −40,1 % / 1 899 px / −40 % sont périmées).
- Sept défauts de fond trouvés par les revues et corrigés : rechargement réseau à chaque `resize`, `Content-Length` faux sur les copies hors ligne, minuteur effaçant un refus serveur, clé d'idempotence écrasée entre note et photo, page Plages annonçant une plage inatteignable, focus du champ refusé jamais posé sur `/conf`, harnais de test sans états d'actionneurs.
- Reste à l'opérateur : R4.2 (Pi/téléphone), grille appareils réels de R4.1, sessions de R4.3.

# Écarts résiduels, documentation et archivage (11/09/2026)

Suite de la revérification commitée en `e29bf96`. Agents sur fichiers disjoints, orchestrateur garant
(pytest complet et Playwright ciblé à chaque rendu, commit par liste de fichiers, revue indépendante).

- [ ] Lot A — code E1 à E5 (CSS, infobulle Solutions, filtre Éclairage, aide iOS 26, ordre du journal)
- [ ] Lot B — outillage de mesure : E6 (premier écran fiche et Plages avec cible), E7 (rejeu de la
      baseline `8023123` à ±2 %), capture en niveaux de gris hors fichier versionné, remesure finale
- [ ] Lot C — docs d'exploitation et de référence : chemins `PHYTO_DATA_DIR`, routes et schéma d'état
      manquants, 11 jobs, procédures de jalons sorties vers l'archive
- [ ] Lot D — archivage (`docs/archive/`, `tasks/archive/`), suppressions (`notes`, images non
      référencées, plan de journalisation, script jalon 1), roadmap, registre, index, CHANGELOG
- [ ] Revue indépendante du diff complet, correctifs, bilan dans le plan de remédiation
