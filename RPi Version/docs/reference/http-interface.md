# Interface HTTP

**Implémentation** : serveur `asyncio.start_server` artisanal, écoute `0.0.0.0:8123`.
**Contrainte** : LAN de confiance uniquement, aucune authentification.

| Méthode | Route | Effet | Réponse principale |
|---|---|---|---|
| GET | `/` ou `/index.html` | État général | HTML 200 |
| GET | `/conf` | Formulaire contenant la configuration | HTML 200 |
| POST | `/conf` | Mutations, sauvegarde, reconfiguration partielle | HTML 200 |
| GET | `/monitor` | Mesures, aucun effet de bord | HTML 200 |
| POST | `/monitor` | Reset statistiques, reboot ou poweroff | 303 ; 403 si Origin différent |
| GET | `/console` | Console web | HTML 200 |
| GET | `/console/stream` | Historique et logs live SSE | Flux 200 |
| GET | `/status` | État et santé JSON | JSON 200 |
| GET | `/static/...` | Asset local | Fichier ou 404 |

## Règles de sécurité

- Aucun effet persistant ou destructeur derrière GET.
- Ne pas exposer le port sur Internet.
- `/conf` révèle actuellement des secrets et doit être limité au LAN.
- Le contrôle `Origin` protège seulement les actions `/monitor` venant d'un navigateur.
- Une requête sans `Origin`, telle que curl, est acceptée.
- `Host` n'est pas validé ; le DNS rebinding reste ouvert.
- `/static/` n'est pas confiné ; ne pas considérer le serveur comme sûr face à un client hostile.
- Les tailles et délais de requêtes ne sont pas encore suffisamment bornés.

## Configuration POST

Le formulaire utilise les alias Pydantic, y compris des noms imbriqués comme `DailyTimer1_Settings.enabled`. Les conversions int/float évitent certaines exceptions, mais les mutations ne sont pas revalidées intégralement avant sauvegarde. L'API de configuration ne doit donc pas être automatisée comme une API stable.

## Actions monitor

- les clés `reset_*` effacent une statistique ;
- `reboot=1` appelle `sudo reboot` ;
- `poweroff=1` appelle `/sbin/shutdown -h now` ;
- POST réussi applique Post/Redirect/Get vers `/monitor`.

## Cible

Séparer :

- `/health/live` : processus HTTP vivant ;
- `/health/ready` : superviseur sain, code non-2xx sinon ;
- routes UI ;
- configuration authentifiée ou strictement filtrée ;
- statiques confinés ;
- limites, timeouts et en-têtes robustes.
