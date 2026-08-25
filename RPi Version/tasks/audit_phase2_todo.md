# Audit — Phase 2 : chantier « thermique unifié »

Branche : `audit-phase2-thermique` · Base : `ad39de2` · Référence : `AUDIT-2026-08-25.md` §8 Phase 2.

**Findings couverts** : C8, C9, C10, E8, E9, E10, M11, M13, M14 (+ E6 pour la persistance de la
phase séquentielle).

## 1. Problème à supprimer

Deux boucles indépendantes (`temp_control` moteur, `heat_control` chauffage) lisent la **même**
température, sans se connaître, et prennent des décisions contradictoires :

- sur toute la bande de consigne (23-25 °C sur la config déployée), le chauffage chauffe pendant que
  l'extracteur évacue (C9) ;
- en mode hiver, l'humidité court-circuite le quota de renouvellement et `winter_default_speed=1`
  interdit l'arrêt : ventilation permanente par grand froid (C8) ;
- le cache `current_state` du chauffage n'est jamais reconfronté au GPIO (E8) ;
- pas d'hystérésis à état côté moteur → battement de relais au seuil (E9) ;
- quota hiver non persisté, fenêtre sur `datetime.now()`, comptage en minutes *nominales* (E10, M14) ;
- `hysteresis_offset` porte trois sémantiques incompatibles (M11) ;
- `clamp_speed` transforme un ordre d'arrêt en marche quand `min_speed ≥ 1` (M13).

## 2. Cible

Un **arbitre thermique unique** : une seule coroutine supervisée lit T/RH une fois, appelle une
fonction **pure** de décision, puis applique le résultat au chauffage *et* au moteur.

```
decide(settings, inputs, memory) -> (ClimateDecision, ClimateMemory)
```

- `ClimateSettings` (gelée) : les consignes de la phase jour ou nuit en cours, projetées depuis
  `AppConfig` par `settings_from_config()` — seul point du module qui connaisse la configuration
- `ClimateInputs` : `now_mono`, `now_epoch`, `temperature`, `humidity`, `is_day`
- `ClimateMemory` (gelée, sérialisable) : état chauffage + `heater_on_since`,
  `heater_cooldown_until`, `sensor_failures`, vitesse moteur + `motor_speed_since`, fenêtre de
  budgets (`quota_window_start`, `renew_minutes_used`, `humidity_minutes_used`, `credit_kind`)
- `ClimateDecision` : `heater_on`, `motor_speed`, `state` ∈
  {`DESACTIVE`, `CHAUFFER`, `NEUTRE`, `VENTILER`, `RENOUVELER`, `DESHUMIDIFIER`, `SECURITE_HAUTE`,
  `PLANCHER_THERMIQUE`, `REPLI_CAPTEUR`, `MANUEL`}, `reason`, `alarm`, seuils effectifs et budgets

Aucun import GPIO, aucun I/O, aucune horloge implicite dans le module de politique : il est testable
à la main et rejouable.

### Zone morte garantie **par construction**

`seuil_ventilation = max(target_temp_max, target_temp_min + heater_hysteresis + vent_deadband)`.

L'audit demandait un *validateur* qui refuse une config sans zone morte ; un validateur bloquant
rendrait le `param.json` déployé (min 23 / max 25 / hyst 2) illisible → boot mort. On garantit donc
la zone morte par le calcul, et on journalise (WARNING dédupliqué) quand le seuil effectif a dû être
relevé. Le seuil effectif est publié dans `/api/v1/state`, donc visible, jamais silencieux.

### Hystérésis à état + temps de maintien (E9)

Échelle de ventilation : palier `k` (1..4) engagé à `seuil + (k-1)·vent_step`, relâché seulement
sous `seuil + (k-1)·vent_step − vent_release`, et **aucun** changement de palier avant
`min_dwell_seconds` (sauf montée d'urgence en sécurité haute).

### Budgets bornés (C8, M14)

L'humidité ne court-circuite plus rien : `winter_refresh_minutes_per_hour` gouverne le
renouvellement d'air et `winter_humidity_minutes_per_hour` la déshumidification — deux ressources
**distinctes et bornées**. Comptage en minutes **réellement écoulées** (`monotonic`), fenêtre
glissante d'une heure ancrée sur l'epoch (persistée, réarmée sur saut d'horloge arrière), plancher
absolu `absolute_floor_temp` sous lequel plus rien ne ventile. Budgets épuisés →
`winter_default_speed`, ou 0 s'il fait franchement froid ; le clamp ne remonte plus un ordre d'arrêt
(M13).

### Politique de repli nommée (C10)

`REPLI_CAPTEUR` : après `MAX_CONSECUTIVE_SENSOR_FAILURES` lectures invalides (hors `]-20 ; 60[`
incluses), chauffage OFF + alarme persistante, moteur à `sensor_fallback_speed` (défaut 0). Les
garde-fous Phase 0 (durée max d'allumage continu, repos forcé) sont conservés, déplacés dans la
fonction pure.

### Écriture idempotente (E8)

La mémoire est recalée sur l'**état GPIO réel** (`get_state()`, `get_motor_speed()`) à chaque tick,
avant la décision. L'écriture du chauffage est **vérifiée** après coup : une sortie qui ne suit pas
lève une alarme CRITICAL au lieu d'être avalée. Une consigne d'arrêt du moteur passe par `all_off()`,
qui réécrit les quatre broches sans consulter le cache.

## 3. Persistance (E10, E6)

`utils/state_store.py` — petit magasin JSON atomique (modèle `SensorStats`), sections nommées,
écriture throttlée. Deux usages :

1. `climate` : fenêtre de quota hiver + minutes consommées → un reboot ne réaccorde plus 5 min de
   vitesse 4 ;
2. `cyclic_1` / `cyclic_2` : phase séquentielle des minuteurs cycliques (phase courante + échéance)
   → un redémarrage ne relance plus une phase ON complète. Un enregistrement échu est ignoré : la
   reprise ne peut que raccourcir un cycle, jamais en inventer un.

## 4. Tâches

- [x] `components/climate_policy.py` : dataclasses + `decide()` pure
- [x] `utils/state_store.py` : persistance JSON atomique throttlée
- [x] `components/climate_control.py` : coroutine unique (lecture capteurs, application, persistance)
- [x] `param/config.py` : `TemperatureSettings` (`vent_deadband`, `vent_step`, `vent_release`,
      `absolute_floor_temp`, `min_dwell_seconds`), `MotorSettings` (`sensor_fallback_speed`,
      `winter_humidity_minutes_per_hour`)
- [x] Suppression de `heat_control` et de `temp_control` (le hardware `MotorHandler` reste)
- [x] `controllers/PuppetMaster.py` : un seul travail `climate_control`, état sûr = chauffage OFF +
      moteur OFF
- [x] `network/web/server.py` : `RELOAD_JOBS`, alarme, bloc `climate` dans `/api/v1/state`
- [x] `components/cyclic_timer_handler.py` : reprise de la phase séquentielle persistée
- [x] Documentation : `CLAUDE.md`/`AGENTS.md`, `docs/architecture/*`, `docs/reference/*`,
      `docs/operations/incident-runbook.md`, `CHANGELOG.md`
- [x] Vérification : rejeu de scénarios sur `decide()` (banc hors dépôt), relecture des chemins GPIO

## 5. Revue

### Ce qui a été fait

| Fichier | Nature |
|---|---|
| `components/climate_policy.py` | **nouveau** — décision pure : dataclasses gelées, `decide()`, seuils dérivés, budgets |
| `components/climate_control.py` | **nouveau** — coroutine unique : lecture, resynchronisation matérielle, application vérifiée, persistance |
| `utils/state_store.py` | **nouveau** — `param/runtime_state.json`, atomique, throttlé, sections nommées |
| `components/heater_control.py` | **supprimé** — remplacé par l'arbitre |
| `components/MotorHandler.py` | `temp_control` supprimé ; ne reste que le pilotage bas niveau |
| `components/cyclic_timer_handler.py` | reprise de la phase séquentielle persistée |
| `param/config.py` | 7 nouveaux champs (5 température, 2 moteur), `hysteresis_offset` recentré sur le chauffage |
| `param/param.json` | valeurs par défaut explicitées |
| `controllers/PuppetMaster.py` | un travail `climate_control` au lieu de deux ; état sûr chauffage **puis** moteur |
| `network/web/server.py` | `RELOAD_JOBS`, alarme renommée, bloc `climate` dans `/api/v1/state` |
| `network/web/templates/*.html`, `static/js/dashboard.js` | 7 champs de configuration, carte « Régulation thermique » |
| `CLAUDE.md`, `AGENTS.md`, `docs/**`, `CHANGELOG.md` | documentation alignée (mirrors vérifiés par `diff -u`) |

### Décisions de conception à ne pas défaire

1. **Zone morte par construction, pas par validateur.** L'audit demandait un validateur de
   configuration ; il aurait rendu le `param.json` déployé (23/25/2) illisible, donc le boot mort.
   Le seuil effectif est calculé, journalisé et publié. *(arbitrage validé avec l'exploitant)*
2. **Deux budgets hiver, pas un seul.** Le renouvellement d'air et la déshumidification sont deux
   besoins distincts ; les fusionner aurait soit supprimé la déshumidification, soit rouvert C8.
   Chacun est borné, donc aucun ne peut ventiler en continu par grand froid.
3. **Le renouvellement d'hiver peut tourner pendant que le chauffage chauffe.** C'est voulu et
   **borné** — à ne pas confondre avec le conflit C9, qui portait sur la ventilation *thermique*, et
   que la zone morte rend impossible.
4. **`decide()` ne doit jamais faire d'I/O.** Toute règle ajoutée dans `climate_control` plutôt que
   dans `climate_policy` sortirait du périmètre rejouable.
5. **`min_dwell_seconds` ne s'applique pas à la première décision** d'une tâche qui redémarre : une
   relance du superviseur ne doit pas suspendre la ventilation deux minutes.

### Vérification

Aucun test n'est ajouté au dépôt (le projet n'en a pas et l'interdit). Les vérifications ont été
menées hors dépôt, dans le scratchpad de session :

- **27 scénarios rejoués** sur `decide()` : zone morte (5 assertions, dont « jamais chauffage +
  ventilation » sur toute la plage), hystérésis et temps de maintien (4), budgets hiver et plancher
  (7), repli capteur (5), durée max d'allumage et repos forcé (3), clamp d'arrêt (2), comptage en
  temps réel (1), saut NTP arrière (1). **Tous passants.**
- **Fumigation de la boucle** avec GPIO/capteurs stubés : 22 °C → chauffage ON (GPIO LOW) et moteur
  0 ; 27,5 °C → chauffage OFF (GPIO HIGH) et vitesse 2 au seuil effectif de 26 °C ; capteur mort →
  `REPLI_CAPTEUR`, chauffage coupé, alarme levée ; retour du capteur → alarme levée, régulation
  reprise ; état persisté relu correctement.
- **Configuration** : `AppConfig.load()` sur le `param.json` réel, aller-retour `save()`/`load()`,
  rendu de `/conf` (7 nouveaux champs présents) et du tableau de bord (carte arbitre).
- **Imports** de `PuppetMaster`, `server` et `cyclic_timer_handler` avec un stub GPIO.

### Reste ouvert (hors périmètre Phase 2)

- Essai sur matériel réel : la ventilation démarre désormais à 26 °C au lieu de 25 sur la
  configuration déployée — à confirmer en conditions réelles avant déploiement.
- E7 (relecture de configuration par cycle métier) et l'ordonnanceur cyclique à échéances absolues
  (E6 complet) relèvent du chantier « configuration » (Phase 3).
- R-SAFE-06 : le verrouillage dégradé sur état multi-relais reste à faire ; seule une consigne
  d'arrêt rattrape désormais l'état via `all_off()`.
