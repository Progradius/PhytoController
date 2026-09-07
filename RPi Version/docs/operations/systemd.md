# Exploitation systemd et watchdog

**Statut** : unité, drop-in et propriétés effectives capturés en lecture seule sur le Pi le 25 août 2026.

## Contrat applicatif

`PuppetMaster` appelle `sd_notify(READY=1)` après l'enregistrement et le démarrage des tâches. Le watchdog envoie `WATCHDOG=1` seulement lorsque le superviseur est sain.

Les paramètres doivent respecter :

```text
MAX_SILENCE_SECONDS = 300 s
WatchdogSec         > 300 s
WatchdogSec observé = 600 s
période de caresse  <= 30 s lorsque le système est sain
```

Le plafond de 30 secondes évite qu'un contrôle de santé défavorable isolé place immédiatement l'intervalle entre deux caresses au bord du timeout. Une panne doit persister pendant le délai systemd ; le superviseur tente d'abord la récupération.

## Drop-in vérifié

```ini
[Service]
Type=notify
NotifyAccess=main
WatchdogSec=600
Restart=always
```

L'unité principale observée est versionnée dans `deploy/phyto.service` et le fragment dans `deploy/phyto.service.d/watchdog.conf`. Les propriétés effectives étaient : service actif, `Type=notify`, `Restart=always`, `RestartSec=5`, `WatchdogUSec=10min`, `NRestarts=0`.

L'unité principale utilise `User=progradius`, le venv du dépôt, `PHYTO_RUN_MODE=service`,
`PHYTO_HW_WATCHDOG=0` et les capacités ambiantes historiques `CAP_SYS_ADMIN CAP_SYS_RAWIO`.
Le drop-in PWA ajoute `CAP_NET_BIND_SERVICE` pour le port HTTPS 443 et les chemins du certificat ;
il réénumère explicitement les trois capacités après remise à zéro de la liste. Voir
[PWA locale et TLS](pwa-local-tls.md). systemd tient parallèlement le watchdog matériel avec
`RuntimeWatchdogSec=15`; l'application utilise donc la voie de notification systemd.

## Contrôles

```bash
systemctl cat phyto.service
systemctl show phyto.service \
  -p Type -p NotifyAccess -p WatchdogUSec -p Restart \
  -p MainPID -p ActiveState -p SubState -p StatusText -p NRestarts
journalctl -u phyto -b --no-pager -o cat
curl -fsS http://127.0.0.1:8123/status | jq '{healthy, heater_alarm, tasks}'
```

Attendu au boot :

- journal de lancement des tâches supervisées ;
- notification « service prêt » ;
- watchdog systemd actif, ou voie matérielle explicitement journalisée ;
- `healthy=true` ;
- compteurs initiaux de relance et blocage à zéro.

## Arrêt contrôlé

```bash
sudo systemctl stop phyto
```

Attendu : watchdog désarmé si la voie `/dev/watchdog` est utilisée, génériques HIGH, moteur LOW, aucune invocation de `GPIO.cleanup()` et broches conservées comme sorties.

## Limitations

- Une tâche métier malsaine cesse les caresses, mais `/status` peut encore répondre 200.
- Un `WatchdogSec` trop court redémarrerait avant la récupération interne.
- Sans `Type=notify`, la voie systemd est inactive ; `/dev/watchdog` peut être déjà détenu par systemd.
- Un redémarrage ne garantit pas les niveaux pendant le reset sans protection matérielle.
- Les capacités ambiantes sont larges et doivent être réduites après inventaire précis des opérations privilégiées.
