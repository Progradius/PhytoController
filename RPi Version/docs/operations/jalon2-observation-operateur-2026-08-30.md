# Observation du lot opérateur, PWA et qualité capteurs — clôture du 30 août 2026

**Objet** : qualifier en continu le lot alarmes/historique, PWA et qualité capteurs déployé en mode
`Sensor_Quality.mode = observe`. **Commit observé** : `b26d2b1`. **Watchdog systemd** : armé à 600 s,
par la même dérogation opérateur que le jalon 1. **Méthode** : lecture seule par
`scripts/observe-jalon2-operator-quality.sh`, une sonde par minute pendant 48 h, plus une sonde
auxiliaire toutes les 10 minutes (historique, manifeste PWA, service worker, page hors ligne,
measurement InfluxDB `sensor_quality`).

## Résultat formel

Le `summary.json` produit sur le Raspberry Pi porte `status=accepted_with_warnings` :

| Preuve | Résultat |
|---|---:|
| Début UTC | 28 août 2026, 18:59:28 |
| Fin UTC | 30 août 2026, 18:59:28 |
| Durée demandée / réelle | 172 800 s / 172 800 s |
| Échantillons | 2 864 |
| Échantillons en échec | **0** |
| Écart maximal entre deux sondes | 63 s |
| Sondes auxiliaires | 287 historique, 287 InfluxDB |
| Échantillons avec avertissement | **835** (29,2 %) |

Une fenêtre antérieure, lancée le 28 août à 18:07:22 UTC sur `5520850`, a été interrompue
volontairement pour laisser passer le redéploiement TLS et applicatif. Elle porte
`status=interrupted`, 22 échecs attendus de types `main_pid_modifie` et
`commit_processus_inattendu`, et a été archivée sous `phyto-observations/invalidated/` sans être
détruite.

## Ce que la fenêtre prouve

`failure_types` est **vide**. Le script échoue un échantillon sur tout changement de PID, de
`boot_id`, du compteur systemd `NRestarts`, de la configuration du watchdog ou du commit du
processus : zéro échec sur 2 864 sondes signifie donc qu'aucun de ces évènements ne s'est produit.
Sur la fenêtre complète, le service est resté `active/running` sans un seul redémarrage, toutes les
tâches supervisées sont restées vivantes et saines, `/health/ready` a répondu 200, `healthy=true` et
`control_healthy=true` en permanence.

Les actionneurs ont tous conservé `tracking=ok` sans péremption : consigne demandée et état GPIO réel
concordants du début à la fin. L'heure est restée fiable, l'historique SQLite disponible (720
intervalles de 120 s, 3 séries, 21 évènements, aucune lacune au-delà d'un intervalle), et HTTPS `:443`
`configured=true / ready=true` sans jamais dégrader HTTP `:8123` ni le contrôle.

La continuité du contrôle, l'acquisition, la couche opérateur, la PWA et le transport TLS sont donc
qualifiés par cette fenêtre.

## Ce que la fenêtre invalide

Les 835 avertissements ont **une cause unique** :

| Type d'avertissement | Occurrences |
|---|---:|
| `capteur:BME280T:inconsistent` | 682 |
| `capteur:BME280H:inconsistent` | 617 |
| `capteur_bloquerait_controle:BME280T` | 682 |
| `capteur_bloquerait_controle:BME280H` | 617 |
| `alarme_controle_active` | 834 |

| Mesure | `normal` | `inconsistent` |
|---|---:|---:|
| BME280T | 2 182 | **682** (23,8 %) |
| BME280H | 2 247 | **617** (21,5 %) |
| BME280P | 2 864 | 0 |

Tous portent `reason=frozen`, sur les deux mesures qui pilotent l'arbitre thermique, alors que les
capteurs mesuraient normalement : 6,45 °C et 14,95 % d'amplitude réelle sur la fenêtre, aucune erreur
d'acquisition, aucune valeur hors plage.

L'analyse a établi que le défaut est dans la politique, pas dans le matériel. `evaluate_sample()`
comparait chaque lecture à la **précédente** en réavançant sa référence à chaque échantillon : elle
mesurait une pente, pas une valeur bloquée. À la cadence réelle de 10 s, une température saine bouge
de 0,01 °C pour un `freeze_epsilon` de 0,02 °C, donc aucune lecture ne comptait comme un changement.

Preuves relevées sur la production :

- épisode du 30 août, 02:40:30Z → 04:31:41Z : **6 671 s déclarées figées** pendant que la température
  passait de 25,92 °C à 26,24 °C, soit seize fois l'epsilon ;
- à 10 s d'intervalle, **0 / 45** couples dépassent l'epsilon sur BME280T et BME280H, contre 3 / 45
  sur BME280P — c'est le seul motif pour lequel la pression n'a jamais été déclarée figée ;
- rejoué à 60 s, le même signal donne le verdict **inverse** (14,6 % des couples au-dessus de
  l'epsilon pour T) : le verdict dépendait de la fréquence de lecture, pas du phénomène ;
- le réarmement exigeait trois dépassements **consécutifs**, jamais observés en 7,5 min de relevé sur
  aucune des trois mesures : une fois posé, le verrou ne tombait plus.

La fenêtre ne qualifie donc **pas** la politique de figement, et l'armement `enforce` aurait exclu du
contrôle les deux mesures thermiques sur près d'un quart du temps.

## Décision

La fenêtre est **acceptée comme preuve de continuité du contrôle** et refusée comme qualification du
diagnostic de figement. Les avertissements sont examinés, expliqués et attribués à un unique défaut
logiciel, corrigé par le commit `837f778` : comparaison ancrée sur la valeur du dernier changement
réel, `freeze_epsilon` ramené à 0,0 pour les BME280, suppression du double arrondi à 0,01 dans le
driver et le handler, réarmement sur trois variations réelles et non consécutives, et test de
propriété d'invariance par cadence.

Conditions de reprise, dans cet ordre :

1. déployer le commit corrigé selon [Déploiement et rollback](deployment-and-rollback.md) — aucun
   observateur ne tourne, la fenêtre s'est close d'elle-même, il n'y a donc pas de `SIGTERM` à
   envoyer ;
2. vérifier après redémarrage que les deux alarmes `sensor_quality` latchées ont disparu : le
   changement de `freeze_epsilon` modifie la signature de profil, ce qui réinitialise la mémoire
   qualité et purge les diagnostics calculés avec les anciens seuils ;
3. relancer une fenêtre complète de 172 800 s au commit corrigé ;
4. n'envisager l'armement `enforce` qu'après cette fenêtre, et après les étapes de calibration,
   d'identités DS18B20, de redondance et de qualification matérielle listées dans
   [`tasks/todo.md`](../../tasks/todo.md).

## Suite donnée le 30 août 2026

Le correctif a été déployé le soir même. Service redémarré à 19:07:27 UTC, `MainPID=721771`,
`NRestarts=0`, `boot_id` inchangé — seul le service a redémarré, pas la machine.

Contrôles après déploiement, tous conformes :

| Contrôle | Résultat |
|---|---|
| Commit déployé | `985e42d`, `phyto.deployRef=feature/qol-operator-experience` |
| Service | `active/running`, `NRestarts=0`, watchdog armé à 600 s |
| Santé | `healthy=true`, `control_healthy=true`, `/health/live` et `/health/ready` à 200 |
| Tâches supervisées | 10 vivantes et saines, 0 restart, 0 stall, aucune erreur ; 7 domaines sains |
| Journal depuis le démarrage | aucune entrée de niveau WARNING ou supérieur |
| **Alarmes actives** | **0** — les deux alarmes `sensor_quality` latchées ont disparu |
| Capteurs | `BME280T`, `BME280H`, `BME280P` en `normal`, sans `reason_codes`, `control_disposition=trusted` |
| Compteurs qualité | `incoherences_since_calibration` remis à 0, `unchanged_for_s` reparti de 0 |
| Actionneurs | six sorties en `tracking=ok`, aucune périmée, états restaurés après le redémarrage |
| Transports | HTTP `:8123` et HTTPS `:443` à 200, `web.https.ready=true` |

La réinitialisation de la mémoire qualité est bien venue du changement de signature de profil, et non
d'un effacement manuel : `param/runtime_state.json` porte désormais le champ `freeze_anchor_value` et
une signature contenant `freeze_epsilon: 0.0`.

Seuils effectifs relus dans le code déployé, via `effective_quality_profile()` :

| Mesure | `freeze_epsilon` | `freeze_after_seconds` | `freeze_min_samples` | fraîcheur |
|---|---:|---:|---:|---:|
| BME280T | 0.0 | 1 800 | 30 | 20 s |
| BME280H | 0.0 | 1 800 | 30 | 20 s |
| BME280P | 0.0 | 3 600 | 30 | 30 s |

`Sensor_Quality.mode = observe`, aucun profil surchargé. La suppression du double arrondi est
également visible : `raw_value` vaut désormais `28.523013138119133` là où il était limité à deux
décimales.

**Réserve de méthode** : une absence d'alarme juste après le déploiement ne prouve rien par
elle-même. La mémoire qualité repart de zéro, donc aucune mesure ne *peut* être déclarée figée avant
1 800 s. La preuve du correctif est la nuit qui suit, période calme où l'ancien critère se
déclenchait systématiquement.

### Nouvelle fenêtre d'observation

| Référence | Valeur |
|---|---|
| Début | 30 août 2026 à 19:09:11 UTC |
| Fin attendue | **1er septembre 2026 à 19:09:11 UTC** |
| Durée demandée | 172 800 s |
| Commit observé | `985e42d` |
| PID observateur | `722191` |
| PID service de référence | `721771` |
| Preuves | `~/phyto-observations/jalon2-operateur-qualite-20260830T190911Z` |

Les trois premiers échantillons sont `OK`, sans échec ni avertissement, les trois mesures en
`normal`. La fenêtre ne sera qualifiée qu'après sa durée complète et la lecture de son `summary.json`.

## Qualifications manuelles encore dues

Le résumé les rappelle explicitement : PWA Chrome Android avec coupure, reconnexion et notifications ;
calibration par instrument de référence ; armement `Sensor_Quality enforce` ; repli matériel et
régulation thermique automatique. Le chauffage est resté désactivé et le moteur en mode manuel à la
vitesse 2 pendant toute la fenêtre : les règles thermiques dynamiques ne sont pas davantage
qualifiées qu'au jalon 1.
