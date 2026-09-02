# PhytoController — Raspberry Pi

PhytoController est un contrôleur de serre pour Raspberry Pi. Il pilote deux sorties journalières, deux sorties cycliques, un moteur à quatre vitesses et un chauffage, lit plusieurs familles de capteurs, exporte les mesures vers InfluxDB et expose une interface web locale sur le port `8123`.

> **Avertissement de sécurité** — Ce logiciel commande des relais pouvant commuter du 230 V, un chauffage, un moteur et des électrovannes. Une erreur de polarité, de brochage ou de séquence d'arrêt peut provoquer une chauffe, une ventilation ou un arrosage non commandé. Couper et consigner l'alimentation des charges avant toute intervention sur le câblage. Les protections logicielles ne remplacent pas un thermostat ou fusible thermique, des résistances de rappel et des interlocks matériels.

## État du projet

La version Raspberry Pi requiert CPython 3.9 ou plus récent et Raspberry Pi OS/Linux. Le fonctionnement de production de référence utilise systemd. L'image Docker existe, mais elle ne constitue pas encore une procédure de production reproductible : elle dépend d'accès privilégiés au GPIO, à I²C, au réseau, à l'heure système et au watchdog.

Les garde-fous suivants sont implémentés dans le code courant :

- verrou d'instance pris avant tout accès GPIO ;
- sorties actives-BAS maintenues à HIGH et moteur actif-HAUT maintenu à LOW lors d'un arrêt contrôlé ;
- absence volontaire de `GPIO.cleanup()` afin de conserver les niveaux sûrs ;
- tâches métier supervisées, relancées avec back-off et état sûr préalable ;
- battements de cœur et watchdog conditionné à la santé applicative ;
- contexte `Component.energized()` pour garantir l'extinction des sorties cycliques ;
- écritures atomiques de la configuration et des statistiques ;
- arrêt du chauffage après lectures invalides répétées ou durée continue excessive ;
- actions de redémarrage et d'extinction accessibles uniquement par POST dans l'IHM.

Ces garanties ne couvrent pas encore tous les scénarios. La fenêtre électrique avant le lancement de Python, les GPIO moteur réservés, l'absence d'interlock thermique unique, les secrets présents dans `param.json` et plusieurs limites du serveur HTTP restent notamment ouverts. Voir le [registre des risques](docs/risk-register.md).

## Documentation

La porte d'entrée de la documentation est [docs/index.md](docs/index.md).

- [Vue d'ensemble de l'architecture](docs/architecture/overview.md)
- [Modèle de sûreté](docs/architecture/safety-model.md)
- [Matrice GPIO](docs/hardware/gpio-matrix.md)
- [Runbook d'incident](docs/operations/incident-runbook.md)
- [Registre des risques](docs/risk-register.md)
- [Roadmap](docs/roadmap.md)
- [Audit historique du 25 août 2026](AUDIT-2026-08-25.md)
- [Politique de sécurité](SECURITY.md)
- [Changelog](CHANGELOG.md)

`AGENTS.md` et `CLAUDE.md` contiennent les règles détaillées destinées aux agents de développement. Ils ne remplacent pas les procédures d'exploitation humaines.

## Démarrage

Installation des dépendances Python :

```bash
pip install -r requirements.txt
```

Lancement manuel sur le Raspberry Pi :

```bash
sudo python3 main.py
```

Lancement sous systemd :

```bash
PHYTO_RUN_MODE=service python3 main.py
```

Le fonctionnement de production doit préférer une unité systemd configurée avec `Type=notify`, `NotifyAccess=main`, `Restart=always` et un `WatchdogSec` supérieur au silence maximal du superviseur. La configuration installée sur le Pi doit être capturée et versionnée lors du prochain lot documentaire ; les commandes ci-dessus ne constituent pas à elles seules une installation de production.

Interface web :

```text
http://<adresse-du-pi>:8123
```

La PWA locale utilise, après installation d'une autorité privée sur le terminal Android :

```text
https://phytocontroller.local/
```

Elle ajoute l'installation sur l'écran d'accueil, une fenêtre autonome, les raccourcis Tableau de
bord/Historique/Alarmes, la dernière vue connue explicitement marquée hors ligne et des notifications locales
tant qu'elle reste active. HTTP `:8123` demeure la voie de compatibilité et de récupération. Voir
[PWA locale et TLS](docs/operations/pwa-local-tls.md).

Routes principales :

- `/` : tableau de bord orienté action, rafraîchi toutes les 5 secondes ;
- `/history` : graphiques détaillés sur 24, 48 ou 72 heures ;
- `/conf` : configuration, une section validée et enregistrée à la fois ;
- `/console` : flux des logs du processus courant ;
- `/api/v1/state` : état complet versionné en JSON ;
- `/api/v1/alarms/active` : alarmes actives en mémoire pour la PWA ;
- `/health/live` et `/health/ready` : sondes de disponibilité et de santé (`503` si une tâche est en défaut) ;
- `/status` : ancien format JSON, conservé pour les scripts existants.

Les actions destructrices (réinitialisation de statistique, redémarrage, extinction) sont des routes `POST` dédiées, protégées par un jeton CSRF, un contrôle d'`Origin` et une confirmation explicite dans le navigateur. `/monitor` n'est plus qu'une redirection de compatibilité.

L'interface ne possède **aucune authentification** et doit rester strictement limitée à un réseau local de confiance. Le port `8123` ne doit pas être publié sur Internet. Le serveur valide l'en-tête `Host` (adresses privées, `localhost`, `<nom>.local`, plus `PHYTO_ALLOWED_HOSTS`), ce qui ferme le DNS rebinding mais ne remplace pas un filtrage réseau.

Détail complet : [interface HTTP](docs/reference/http-interface.md) et [schémas d'état JSON](docs/reference/status-schema.md).

## Configuration et données sensibles

La configuration vivante est chargée depuis `param/param.json`. Ce fichier contient actuellement des identifiants Wi-Fi et InfluxDB en clair et reste suivi par Git :

- ne jamais copier son contenu dans un log, une issue, un rapport ou une demande d'assistance ;
- ne jamais utiliser ses valeurs réelles dans un exemple documentaire ;
- considérer les identifiants historiquement versionnés comme compromis ;
- planifier leur sortie vers un fichier d'environnement protégé, puis leur rotation.

Les statistiques sont persistées dans `param/sensor_stats.json`. Les deux fichiers sont sauvegardés puis restaurés par `scripts/deploy.sh` lors d'un déploiement normal.

## Déploiement

Le script de déploiement est conçu pour être exécuté depuis le Raspberry Pi de production :

```bash
./scripts/deploy.sh
```

Il sauvegarde la configuration vivante, récupère le code, vérifie sa compilation avant de couper le
service, puis redémarre. Le succès exige pendant 15 secondes continues : service actif,
`/health/live`, `/health/ready` en 200, `control_healthy=true`, commit chargé identique à la cible et
aucune alarme critique. Tout échec déclenche le rollback automatique, qualifié avec les mêmes critères.

## Vérification

La validation automatisée sans matériel repose sur `pytest` :

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

La suite emploie uniquement une configuration fictive, des répertoires temporaires et un faux GPIO
enregistrant chaque transition. Elle ne nécessite ni root, ni réseau externe, ni Raspberry Pi ; les
tests HTTP ouvrent seulement un socket loopback éphémère et ne lancent aucune commande système. Elle couvre la politique climatique, les passages jour/nuit et minuit, le magasin de
configuration, les polarités GPIO, le superviseur et les protections HTTP.

Elle ne remplace pas une qualification électrique. Toute modification de GPIO, chauffage, moteur,
timer, arrêt ou watchdog doit aussi suivre le protocole supervisé de
[`docs/development/hardware-validation.md`](docs/development/hardware-validation.md) et décrire les
transitions attendues au démarrage, en régime nominal, sur exception, sur annulation et à l'arrêt.
Il n'y a toujours pas de linter configuré.

## Licence

Les fichiers source déclarent une licence AGPL-3.0. Le texte complet de licence doit encore être ajouté depuis une source officielle et validé par le propriétaire ; voir la roadmap.
