# Modèle de sûreté

**Public** : toute personne modifiant ou exploitant les GPIO, relais, timers, moteur, chauffage, arrêt ou watchdog.
**Référence** : commit `61ad3df`.
**Dernière vérification du code** : 25 août 2026.
**Dernière preuve matérielle citée** : arrêt contrôlé vérifié le 25 août 2026, détaillé dans `tasks/audit_phase0_todo.md`.

## Principe

La sûreté repose sur un état électrique explicite, appliqué le plus tôt possible au démarrage, avant chaque relance d'une tâche de contrôle et à chaque arrêt contrôlé. Cet état doit rester piloté jusqu'à la coupure d'alimentation.

Deux polarités opposées coexistent. Les confondre peut fermer un relais au lieu de l'ouvrir.

## Polarités

### Sorties `Component` : actives-BAS

Les éclairages, sorties cycliques et le chauffage utilisent `model.Component` :

| État logique | Niveau GPIO | Relais |
|---|---|---|
| `set_state(1)` | LOW | ON |
| `set_state(0)` | HIGH | OFF |

L'état sûr est HIGH.

### Moteur : actif-HAUT

Les quatre relais de vitesse utilisent `model.Motor` :

| Vitesse | Pin 1 | Pin 2 | Pin 3 | Pin 4 |
|---:|---|---|---|---|
| 0 | LOW | LOW | LOW | LOW |
| 1 | HIGH | LOW | LOW | LOW |
| 2 | LOW | HIGH | LOW | LOW |
| 3 | LOW | LOW | HIGH | LOW |
| 4 | LOW | LOW | LOW | HIGH |

L'état sûr est LOW sur les quatre broches. Plusieurs broches HIGH simultanément constituent un état dangereux.

## Séquence de sûreté logicielle

### Au démarrage du processus

1. Le verrou d'instance est acquis avant tout accès GPIO.
2. La configuration est chargée.
3. Les quatre broches moteur sont forcées LOW.
4. Les sorties génériques sont initialisées HIGH.
5. Les objets métier sont construits.
6. Les tâches supervisées sont démarrées.
7. systemd n'est notifié `READY=1` qu'après le lancement du superviseur.

Limite : aucun code Python ne s'exécute entre la mise sous tension du Pi et ce démarrage. Les niveaux dépendent alors du firmware, des pulls internes et de l'électronique externe.

### Pendant le fonctionnement

- une tâche de contrôle publie des heartbeats ;
- si elle lève une exception, le superviseur applique son état sûr puis la relance avec back-off ;
- si elle reste silencieuse trop longtemps, le veilleur l'annule, applique l'état sûr et la relance ;
- si une sauvegarde de configuration demande un rechargement volontaire (`request_reload()`), la tâche est annulée et relancée **sans** repositionnement de l'état sûr : elle était saine, et couper la charge à chaque enregistrement ferait clignoter le relais. Ce qui doit être relâché l'est déjà par les `finally` de la tâche — le contexte `energized()` coupe sa sortie à l'annulation ;
- si le superviseur devient malsain, le watchdog n'est plus caressé ;
- si l'event loop entier est bloqué, ni le veilleur ni la caresse ne progressent, ce qui laisse systemd déclencher le redémarrage.

### Lors d'un arrêt contrôlé

Les handlers de signal, `atexit` et le `finally` principal convergent vers une fonction idempotente :

- sorties génériques vers HIGH ;
- moteur vers LOW ;
- fermeture magique du watchdog matériel si cette voie est utilisée ;
- conservation des broches en sorties pilotées.

`GPIO.cleanup()` est interdit : il remettrait les broches en entrée et rendrait l'état dépendant des pulls par défaut et du bruit électrique.

## Séquences ON / attente / OFF

Une sortie active-BAS qui reste ON après une annulation peut provoquer une chauffe, un éclairage prolongé ou une inondation. Toute séquence de ce type doit utiliser :

```python
with component.energized():
    await supervised_sleep(duration)
```

`Component.energized()` coupe la sortie dans un `finally`, vérifie le retour à OFF, effectue une seconde tentative et produit une alarme CRITICAL si l'état reste actif ou devient invérifiable.

Une séquence manuelle `set_state(1)`, attente, `set_state(0)` est interdite.

## Garde-fous chauffage

Les protections implémentées sont :

- plage valide strictement comprise entre -20 °C et 60 °C ;
- cinq lectures manquées ou invalides consécutives avant arrêt forcé ;
- alarme persistante accessible dans `/status` ;
- maximum de 120 minutes d'allumage continu ;
- repos forcé de 15 minutes après dépassement ;
- calcul des durées par horloge monotone.

Ces protections ne couvrent pas :

- un capteur figé sur une valeur basse mais plausible ;
- un relais mécaniquement collé ;
- un processus tué sans handler ;
- une défaillance du Pi, de l'alimentation ou de la carte SD ;
- une sortie activée pendant la fenêtre de boot.

Un thermostat ou fusible thermique indépendant et câblé en série reste requis pour une protection physique crédible.

## Matrice des pannes

| Événement | Réponse logicielle attendue | État attendu | Limite / protection externe |
|---|---|---|---|
| Exception d'un timer | État sûr puis relance | Sortie HIGH/OFF | Relais collé non détecté physiquement |
| Annulation pendant un cycle | `energized()` exécute son `finally` | Sortie HIGH/OFF | Dépend de la réussite GPIO |
| Tâche silencieuse > 300 s | Annulation et relance | État sûr de la tâche | Event loop fonctionnel requis |
| Event loop bloqué | Plus de caresse watchdog | Redémarrage après timeout | Niveaux au reset à garantir matériellement |
| Cinq mesures T invalides | Chauffage forcé OFF, alarme | Chauffage HIGH/OFF | Thermostat indépendant requis |
| Chauffe > 120 min | OFF pendant 15 min | Chauffage HIGH/OFF | Relais collé non couvert |
| SIGTERM/SIGINT/SIGHUP | Fermeture watchdog et état sûr | Génériques HIGH, moteur LOW | Vérifié sur Pi le 25/08/2026 |
| SIGKILL/OOM | Aucun handler Python | Latches potentiellement conservés | Watchdog, pulls et protections matérielles |
| Mise sous tension | Aucun code avant Python | Non garanti actuellement | Pulls externes et boot config correcte |
| Plusieurs relais moteur HIGH | Erreur journalisée, lecture renvoyée comme vitesse 0 | État physique dangereux persistant | Interlock et coupure immédiate à implémenter |

## Invariants de développement

1. Chaque broche possède un propriétaire unique, une polarité et un état sûr.
2. Les listes de broches génériques et moteur ne se recouvrent jamais.
3. Une sortie moteur ne doit pas utiliser un GPIO réservé ou tiré HIGH au boot.
4. Une erreur d'écriture GPIO ne doit pas être convertie en faux succès.
5. Un cache logiciel ne prouve pas l'état électrique réel.
6. Les temps de sécurité utilisent `time.monotonic()`.
7. Toute valeur de capteur `None`, hors plage ou non finie est invalide.
8. Toute tâche longue qui pilote une sortie est supervisée avec un état sûr.
9. La fabrique d'une tâche supervisée retourne une nouvelle coroutine à chaque relance.
10. Une modification de sûreté décrit les transitions attendues au boot, en fonctionnement, sur exception, sur annulation et à l'arrêt.

## Protections matérielles recommandées

À réaliser hors code après validation du schéma électrique :

- pull-down externe de 4,7 kΩ sur chaque entrée moteur active-HAUT ;
- pull-up externe adapté sur chaque entrée active-BAS ;
- thermostat ou fusible thermique en série avec le chauffage ;
- interlock électromécanique empêchant plusieurs vitesses moteur simultanées ;
- watchdog externe capable de couper l'alimentation de la carte relais ;
- configuration de boot générée depuis une source de brochage validée.

Ces protections doivent être consignées dans un schéma électrique versionné et vérifiées hors tension avant mise en service.
