# Changelog

Ce changelog commence avec la consolidation documentaire du 25 août 2026. L'historique antérieur reste disponible dans Git et dans `AUDIT-2026-08-25.md`.

Les mentions **code**, **déployé** et **vérifié matériellement** sont distinctes.

## Non publié

### Interface web et acquisition capteurs

**Code présent dans l'arbre de travail ; non commité, non déployé.** Vérifié par une passe de
fumigation HTTP hors matériel (aiohttp `TestClient`, stubs GPIO/I²C).

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
