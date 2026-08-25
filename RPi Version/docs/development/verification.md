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
- cinq températures invalides puis `REPLI_CAPTEUR` : chauffage OFF, moteur à `sensor_fallback_speed`, alarme persistante ;
- retour du capteur après un repli : sortie du repli et reprise normale ;
- durée maximale de chauffe et cooldown ;
- **jamais** chauffage ON et ventilation ON simultanément, sur toute la bande de consigne, y compris avec une configuration sans zone morte déclarée ;
- seuil de ventilation effectif = `max(maximum, minimum + hystérésis + zone morte)`, relevé signalé et publié ;
- chauffage désactivé : le seuil **n'est pas** relevé et aucun avertissement n'est émis — il n'y a pas deux organes à séparer ;
- température oscillant d'un dixième autour d'un palier : aucun battement de relais (seuil de relâchement et `min_dwell_seconds`) ;
- épisode froid et humide : budgets de renouvellement et de déshumidification consommés séparément, aucun des deux ne court-circuite l'autre, et rien ne ventile sous `absolute_floor_temp` ;
- budgets et phase séquentielle rechargés après redémarrage depuis `param/runtime_state.json` ;
- `runtime_state.json` absent ou corrompu : régulation qui démarre quand même, budgets réarmés ;
- écriture GPIO qui ne suit pas la consigne : alarme CRITICAL ;
- SIGTERM puis niveaux terminaux ;
- watchdog sain, puis arrêt des caresses sur état malsain ;
- POST sans jeton CSRF, avec jeton mais `Origin` tiers, ou avec un `Host` étranger : tous refusés ;
- `POST /conf/{section}` invalide : 422, `param.json` et configuration vivante inchangés ;
- `POST /conf/{section}` valide : fichier réécrit, configuration vivante à jour, travaux concernés relancés ;
- secret laissé vide dans `/conf` : valeur enregistrée conservée, et aucun secret présent dans le HTML servi ;
- `/api/v1/state` et `/status` cohérents avec le superviseur ; `/health/ready` en 503 quand un travail est en défaut.

La politique thermique est une **fonction pure** (`components/climate_policy.decide()`) : ses scénarios se rejouent sans matériel, sans horloge et sans disque. C'est le seul endroit du dépôt où une régulation peut être vérifiée de façon déterministe — 35 scénarios y ont été rejoués lors de la phase 2. Toute évolution de la politique doit être accompagnée des siens.

Une passe de fumigation HTTP couvrant ces points existe sous forme de harnais jetable (aiohttp `TestClient`, stubs `RPi.GPIO`/`smbus2`, sauvegarde/restauration de `param.json`). Elle est à transformer en vérification reproductible : c'est le premier candidat d'une suite de tests, puisqu'elle protège des invariants durables.

## Traçabilité

Consigner commit, environnement, configuration non sensible, scénario, attendu, obtenu, preuve et limite. Les harnais jetables doivent être transformés en vérification reproductible lorsqu'ils protègent un invariant durable.
