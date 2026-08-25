# Changelog

Ce changelog commence avec la consolidation documentaire du 25 août 2026. L'historique antérieur reste disponible dans Git et dans `AUDIT-2026-08-25.md`.

Les mentions **code**, **déployé** et **vérifié matériellement** sont distinctes.

## Non publié

### Arbitre thermique unifié (audit — phase 2)

**Code, branche `audit-phase2-thermique` ; non déployé.** Vérifié par rejeu de 27 scénarios sur la
fonction de décision pure (banc hors dépôt), rendu des pages et aller-retour `save()`/`load()` de la
configuration.

- `climate_control` remplace `motor_temp_control` et `heat_control` : un **seul** travail supervisé
  lit la température une fois et pilote chauffage **et** ventilation de façon cohérente. *(C9)*
- Décision extraite en fonction **pure** `climate_policy.decide()` — sans GPIO, sans disque, sans
  horloge implicite, donc rejouable et auditable.
- **Zone morte garantie par construction** : le seuil de ventilation ne descend jamais sous
  `minimum + hystérésis + zone morte`. Sur la configuration déployée (23/25/2), la ventilation
  démarre désormais à 26 °C au lieu de 25 — un WARNING le signale et `/api/v1/state` publie le seuil
  effectif. Aucune configuration existante n'est refusée. *(C9)*
- Mode hiver : deux budgets horaires **bornés et distincts** (renouvellement, déshumidification)
  comptés en minutes réellement écoulées, plus un **plancher thermique absolu**. L'humidité ne
  court-circuite plus le quota. *(C8, M14)*
- Hystérésis à état avec seuil de relâchement distinct et temps de maintien minimal
  (`min_dwell_seconds`) : fin du battement de relais au seuil. *(E9)*
- Chauffage et moteur resynchronisés sur leur **état GPIO réel** à chaque tick, écriture vérifiée et
  alarme CRITICAL si la sortie ne suit pas. *(E8)*
- `clamp_speed` ne remonte plus un ordre d'arrêt vers `min_speed`. *(M13)*
- Repli capteur nommé `REPLI_CAPTEUR` : chauffage coupé, moteur à `sensor_fallback_speed`, alarme
  persistante ; garde-fous de durée maximale d'allumage conservés. *(C10)*
- `utils/state_store.py` (`param/runtime_state.json`, atomique et throttlé) : budgets hiver et phase
  séquentielle des minuteurs cycliques survivent à un redémarrage. *(E10, E6)*
- Nouveaux champs de configuration : `vent_deadband`, `vent_step`, `vent_release`,
  `absolute_floor_temp`, `min_dwell_seconds`, `sensor_fallback_speed`,
  `winter_humidity_minutes_per_hour` — tous exposés dans `/conf`. `hysteresis_offset` ne porte plus
  qu'une seule sémantique, la bande morte du chauffage. *(M11)*
- Tableau de bord : carte « Régulation thermique » (état, motif, seuils effectifs, budgets).

### Interface web et acquisition capteurs

**Code `7d455e4` et `ad39de2` ; déployé et vérifié matériellement le 25 août 2026.** Vérifié en
local par fumigation HTTP (aiohttp `TestClient`, stubs GPIO/I²C) puis sur le Pi — relevé dans
`docs/operations/web-baseline-2026-08-25.md`.

- Serveur `aiohttp` à routes explicites en remplacement du serveur artisanal : jeton CSRF,
  contrôle d'`Origin`, validation du `Host` (DNS rebinding fermé), corps limité à 64 Kio,
  en-têtes de sécurité, `no-store` sur le dynamique, assets servis par liste blanche exacte.
- Tableau de bord rafraîchi par `/api/v1/state` (schéma versionné), `/health/live` et
  `/health/ready` (503 sur défaut), `/status` conservé, `/monitor` réduit à une redirection.
- `/conf` découpé par section : candidat `AppConfig` complet revalidé avant écriture atomique,
  rejet sans effet sur le disque ni sur la configuration vivante, application à chaud par
  `supervisor.request_reload()`, GPIO en lecture seule, secrets ni affichés ni journalisés.
- Contraintes de configuration ajoutées : bornes horaires, vitesses, températures, port Influx,
  `validate_assignment` sur tous les modèles, min ≤ max jour et nuit.
- `controllers/sensor_catalog.py` : table canonique des mesures pour l'IHM, l'export et
  l'activation matérielle.
- `SensorController` unique : exécuteur à un fil, instantané partagé rafraîchi toutes les 10 s
  par le job supervisé `sensor_snapshot`, `reconfigure()` en place, `close()` à l'arrêt. Aucune
  requête HTTP ne déclenche plus de lecture matérielle.
- Export InfluxDB en aiohttp avec délai de garde de 4 s, alimenté par l'instantané ; le job
  reste enregistré et se suspend selon `host_machine_state`.
- Code mort supprimé : `network/web/api_handler.py`, `templates/monitor.html`, et
  `SystemStatus.get_cyclic_period()` qui lisait un champ inexistant.
- `requirements.txt` : `requests` retiré, `jinja2` et `aiohttp>=3.12.15,<3.14` requis.
- Jeton CSRF persistant (`utils/csrf.py`, `param/.csrf_token` en 0600, hors git) : un redémarrage
  du service n'invalide plus les pages laissées ouvertes.
- Rechargement volontaire d'une tâche : l'état sûr n'est plus repositionné, une sauvegarde de
  configuration ne fait donc plus clignoter la sortie concernée. L'état sûr reste appliqué sur
  panne, blocage et terminaison anormale.
- `SensorStats` sérialisé par un `RLock` et `get_all()` renvoyant une copie : plus de mise à jour
  perdue entre le fil des capteurs et la réinitialisation depuis l'IHM.

### Documentation

- Porte d'entrée, architecture, modèle de sûreté et matrice GPIO.
- Runbook d'incident, monitoring, installation, systemd, déploiement et sauvegarde.
- Références configuration, environnement, HTTP, `/status`, logs, capteurs et InfluxDB.
- Registre vivant des risques, roadmap, checklists, releases et ADR initiaux.
- Capture en lecture seule de la production et versionnement des artefacts systemd observés.
- Mise à jour complète après la refonte web : interface HTTP, schémas d'état, configuration,
  capteurs et InfluxDB, architecture, monitoring, vérification, registre des risques et roadmap.

## 2026-08-25 — Supervision et watchdog

**Code `61a5d7d` ; déployé et observé sur le Pi.**

- Superviseur de tâches, heartbeats, back-off et états sûrs.
- `Component.energized()` pour les sorties cycliques.
- Watchdog conditionné à la santé, notification systemd et statut enrichi.
- Huit tâches saines, aucun restart/stall lors du relevé live.

Cadence de caresse plafonnée à 30 secondes dans `61ad3df`, présent dans le dépôt local mais pas encore dans le commit de production relevé (`61a5d7d`).

## 2026-08-25 — Garde-fous immédiats

**Code `649eb20` ; déployé et vérifié matériellement.**

- Verrou d'instance avant tout accès GPIO.
- Écritures atomiques de configuration et statistiques.
- État sûr terminal sans `GPIO.cleanup()`.
- Repli chauffage et alarme persistante.
- Actions `/monitor` déplacées de GET vers POST avec contrôle Origin partiel.

## 2026-08-25 — Journalisation

**Code `fb26cd2` et correctifs suivants ; déployé.**

- Façade unique, niveaux configurables, rotation quotidienne et déduplication.
- Console SSE du processus courant, sans second `main.py`.
- Partage du contrôleur de capteurs au boot et logs des seuls écarts de configuration.
