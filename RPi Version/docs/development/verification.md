# Stratégie de vérification

Il n'existe pas encore de suite de tests ou linter configurés. Ne pas déclarer un changement sûr sur la seule base de `compileall`.

## Niveaux

1. **Statique** : lecture des flux, imports, polarités, exceptions et annulations.
2. **Syntaxe** : compilation avec le venv Pi.
3. **Harnais ciblé** : stubs RPi.GPIO/smbus2 et scénarios déterministes.
4. **Intégration sans charge** : processus, HTTP, configuration, supervision.
5. **Matériel sous surveillance** : GPIO, relais puis équipement.
6. **Production** : déploiement, statut, logs, métriques et rollback.

## Scénarios minimaux de sûreté

- seconde instance refusée sans écriture GPIO ;
- erreur de config sans fichier tronqué ;
- exception d'une tâche puis état sûr et relance ;
- tâche silencieuse puis stall et relance ;
- annulation dans `energized()` puis OFF ;
- cinq températures invalides puis chauffage OFF et alarme ;
- durée maximale de chauffe et cooldown ;
- SIGTERM puis niveaux terminaux ;
- watchdog sain, puis arrêt des caresses sur état malsain ;
- POST sans jeton CSRF, avec jeton mais `Origin` tiers, ou avec un `Host` étranger : tous refusés ;
- `POST /conf/{section}` invalide : 422, `param.json` et configuration vivante inchangés ;
- `POST /conf/{section}` valide : fichier réécrit, configuration vivante à jour, travaux concernés relancés ;
- secret laissé vide dans `/conf` : valeur enregistrée conservée, et aucun secret présent dans le HTML servi ;
- `/api/v1/state` et `/status` cohérents avec le superviseur ; `/health/ready` en 503 quand un travail est en défaut.

Une passe de fumigation HTTP couvrant ces points existe sous forme de harnais jetable (aiohttp `TestClient`, stubs `RPi.GPIO`/`smbus2`, sauvegarde/restauration de `param.json`). Elle est à transformer en vérification reproductible : c'est le premier candidat d'une suite de tests, puisqu'elle protège des invariants durables.

## Traçabilité

Consigner commit, environnement, configuration non sensible, scénario, attendu, obtenu, preuve et limite. Les harnais jetables doivent être transformés en vérification reproductible lorsqu'ils protègent un invariant durable.
