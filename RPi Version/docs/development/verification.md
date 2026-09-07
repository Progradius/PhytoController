# Stratégie de vérification

Une suite `pytest` reproductible couvre les contrats purs, la persistance, les doubles GPIO, le
superviseur et l'interface HTTP. Elle est obligatoire pour tout changement Python, mais ne suffit pas à
qualifier une transition électrique réelle. Il n'existe pas de linter configuré et `compileall` seul ne
constitue jamais une preuve de sûreté.

## Commandes

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

Les tests doivent rester exécutables sans root, réseau externe, bus I²C ou Raspberry Pi. Les tests HTTP
utilisent uniquement un socket loopback éphémère. Ils ne chargent jamais
le `param/param.json` vivant comme fixture : `tests/conftest.py` construit une configuration fictive et
chaque test persistant écrit sous `tmp_path`. Les imports de `RPi.GPIO` ne sont autorisés qu'après
installation explicite du faux de `tests/fakes/rpi_gpio.py`.

## Niveaux

1. **Statique** : lecture des flux, imports, polarités, exceptions et annulations.
2. **Syntaxe** : compilation avec le venv Pi.
3. **Suite automatisée** : `pytest`, faux `RPi.GPIO`, fichiers temporaires et scénarios déterministes.
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
- figement confirmé en observation puis armement : exclusion immédiate sans nouvelle lecture ; trois variations plausibles, pas nécessairement consécutives, pour le réarmement ;
- figement : verdict **invariant par cadence** de lecture, dérive lente sous l'epsilon non figée, valeur strictement identique figée ;
- désaccord redondant à deux sondes sans choix arbitraire, majorité cohérente à trois sondes et récupération temporisée ;
- migration SQLite v1 → v3 avec sauvegarde 0600, agrégation des statuts qualité et sessions de relecture GPIO ;
- transitions d'actionneurs enrichies par la relecture GPIO, durées calculées sur l'horloge monotone, non raccordées entre deux démarrages et nouvelle session après perte d'événement ;
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
- `/api/v1/state` et `/status` cohérents avec le superviseur ; `/health/ready` en 503 quand un travail est en défaut ;
- forçage « arrêt » échu au **premier** des deux horloges, dans les deux sens de saut NTP ; verrouillage moteur primant sur `REPLI_CAPTEUR`, `SECURITE_HAUTE` et le mode manuel ; `heater_forced_off` sans effet sur `vent_threshold` ; alarmes de repli et de durée de chauffe toujours émises sous forçage ; `motor_lockout_overheat` ouverte quand la serre dépasse le seuil malgré le verrou ;
- création de forçage refusée sans heure fiable, hors liste blanche d'équipements, hors plafond (4 h chauffage et moteur), ou si l'écriture de `runtime_state.json` échoue ; annulation appliquée même si sa trace échoue ; reprise au démarrage rebornée et marquée « à confirmer » avant heure fiable ;
- reboot et extinction répondant 202 **avant** de lancer la commande, `POST /monitor` emprunant le même chemin, et aucun sous-processus démarré par la suite de tests.

La politique thermique est une **fonction pure** (`components/climate_policy.decide()`) : ses scénarios se rejouent sans matériel, sans horloge et sans disque. C'est le seul endroit du dépôt où une régulation peut être vérifiée de façon déterministe — 35 scénarios y ont été rejoués lors de la phase 2. Toute évolution de la politique doit être accompagnée des siens.

La fumigation HTTP utilise `aiohttp.TestClient`, un `ConfigStore` temporaire et des doubles sans I/O
matérielle. Les actions reboot/poweroff sont vérifiées comme POST-only et protégées, sans jamais lancer
de sous-processus.

L'invariant climatique « jamais chauffage et ventilation simultanés » concerne la **ventilation
thermique** (`VENTILER`/`SECURITE_HAUTE`). En hiver, les épisodes bornés `RENOUVELER` et
`DESHUMIDIFIER` peuvent volontairement coexister avec la chauffe ; en manuel, la vitesse vient de
l'opérateur. Les tests distinguent ces contrats au lieu d'interdire globalement tout moteur pendant la
chauffe.

La qualification des niveaux électriques suit séparément
[`hardware-validation.md`](hardware-validation.md), charges consignées puis relais seuls.

## Traçabilité

Consigner commit, environnement, configuration non sensible, scénario, attendu, obtenu, preuve et limite. Les harnais jetables doivent être transformés en vérification reproductible lorsqu'ils protègent un invariant durable.
