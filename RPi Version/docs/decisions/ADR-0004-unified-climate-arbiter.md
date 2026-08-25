# ADR-0004 — Arbitre thermique unifié et politique en fonction pure

**Statut** : accepté. **Date** : 26 août 2026. **Commit** : `e93644a`.
**Déploiement** : non exercé sur le Pi au moment de la rédaction.

## Contexte

Le chauffage et l'extraction régulaient la **même** température dans deux boucles supervisées
indépendantes, sans arbitre. Sur la configuration déployée (minimum 23 °C, maximum 25 °C,
hystérésis 2 °C), toute la bande de consigne était une zone où le chauffage chauffait pendant que
l'extracteur évacuait : deux charges qui se combattent, une facture doublée et une consigne jamais
tenue (audit C9).

Le mode hiver présentait un second défaut : le seuil d'humidité court-circuitait le quota de
renouvellement d'air. Un épisode froid et humide pouvait donc ventiler sans limite alors que le
quota existait précisément pour l'empêcher (audit C8).

Ces deux comportements ne sont pas des réglages malheureux : ils sont structurels dès lors que
deux tâches décident séparément d'un même équilibre.

## Décision

1. **Un seul travail supervisé**, `climate_control`, pilote le chauffage *et* le moteur.
   `heat_control` et `temp_control` disparaissent en tant que tâches. Une consigne contradictoire
   n'est plus représentable : il n'y a plus qu'un décideur.
2. **La décision est une fonction pure**, `components/climate_policy.decide()` : aucun accès GPIO,
   aucune lecture disque, aucune horloge implicite. Le temps entre par `ClimateInputs`, l'état par
   une `ClimateMemory` gelée. La coroutine ne fait qu'appliquer le résultat.
3. **La zone morte est garantie par construction, pas par validation** :
   `seuil_ventilation = max(target_temp_max, target_temp_min + hysteresis_offset + vent_deadband)`.
4. **Deux budgets horaires distincts et bornés** en mode hiver — renouvellement
   (`winter_refresh_minutes_per_hour`) et déshumidification (`winter_humidity_minutes_per_hour`) —
   comptés en minutes réellement écoulées, avec un plancher thermique absolu
   (`absolute_floor_temp`) sous lequel plus rien ne ventile.
5. **Un repli nommé**, `REPLI_CAPTEUR` : température durablement illisible → chauffage coupé, moteur
   à `sensor_fallback_speed` (0 par défaut), alarme persistante.
6. **L'état de régulation survit au redémarrage** via `utils/state_store.py`
   (`param/runtime_state.json`, écriture atomique et throttlée).

## Conséquences

La régulation devient rejouable : 27 scénarios ont pu être rejoués sur `decide()` sans matériel,
ce qui était impossible tant que la décision était mêlée aux écritures GPIO. Toute évolution de la
politique thermique doit désormais passer par cette fonction et être accompagnée de ses scénarios.

Sur la configuration déployée, la ventilation démarre à **26 °C au lieu de 25 °C** : c'est le seuil
relevé par la garantie de zone morte. Le changement est visible — journalisé en WARNING dédupliqué
et publié dans le bloc `climate` de `/api/v1/state` — et non silencieux.

`hysteresis_offset` ne porte plus qu'une seule sémantique, la bande morte du chauffage. Sept
nouveaux champs de configuration apparaissent dans `/conf`.

Le fichier `param/runtime_state.json` est propre à la machine, ignoré par git, et **n'est pas
sauvegardé par `scripts/deploy.sh`** : sa perte réarme les budgets, sans danger.

## Alternatives écartées

**Un validateur de configuration refusant une bande sans zone morte** — c'est ce que demandait
l'audit. Écarté : le `param.json` **déjà déployé** (23/25/2) serait devenu illisible, donc le boot
serait mort au premier redémarrage. Une règle de sûreté qui empêche le contrôleur de démarrer ne
protège rien. La contrainte est donc appliquée au calcul, en signalant l'écart plutôt qu'en
refusant la configuration.

**Garder deux tâches et ajouter un verrou partagé** — écarté : le verrou aurait rendu l'exclusion
mutuelle vraie à un instant donné sans jamais produire une décision cohérente, et deux boucles
auraient continué à osciller autour de la même consigne.

**Compter les budgets en nombre de ticks** — écarté au profit du temps réellement écoulé
(`monotonic`) : un tick manqué, un redémarrage ou une charge CPU auraient faussé le quota.

## Réexamen

Obligatoire si un troisième organe thermique apparaît (déshumidificateur dédié, ouvrant motorisé),
si la serre reçoit plusieurs zones, si un capteur de température indépendant est ajouté, ou si la
protection thermique matérielle de `R-SAFE-03` est installée — cette dernière changerait les
hypothèses de repli.

Cette décision **ne remplace pas** [ADR-0001](ADR-0001-gpio-polarities-and-safe-state.md) : les
polarités et l'état sûr terminal restent la couche en dessous, et `climate_control` conserve un
`safe_state` au superviseur.
