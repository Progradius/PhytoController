# Installation sur Raspberry Pi

**Statut** : procédure de référence provisoire, dérivée du dépôt ; la reconstruction complète sur un Pi vierge reste à exercer.
**Cible observée le 25 août 2026** : Debian 12 Bookworm aarch64, noyau Raspberry Pi 6.12.93, Python 3.11.2 et systemd.

## Préconditions de sécurité

- Ne raccorder aucune charge 230 V pendant l'installation logicielle.
- Identifier les deux polarités dans le [modèle de sûreté](../architecture/safety-model.md).
- Vérifier le câblage contre la [matrice GPIO](../hardware/gpio-matrix.md).
- Prévoir les protections externes avant une exploitation sans surveillance.
- Ne jamais réutiliser les exemples historiques `gpio=N=op,dh` du fichier `notes`.

## Paquets et interfaces

Le système utilise au minimum :

- Python et `venv` ;
- GPIO Raspberry Pi ;
- I²C `/dev/i2c-1` ;
- éventuellement 1-Wire ;
- NetworkManager et `nmcli` ;
- `timedatectl` ;
- `ping` ;
- systemd avec notification et watchdog ;
- `curl`, Git et les outils usuels d'exploitation.

Le Pi observé possède `/dev/gpiomem`, `/dev/i2c-1` et les modules `i2c_bcm2835`, `i2c_dev`, `w1_gpio` et `w1_therm`. `/boot/firmware/config.txt` active `dtparam=i2c_arm=on` et `dtoverlay=w1-gpio`. Le `Dockerfile` ne doit pas être utilisé comme liste d'installation de production.

Versions Python observées : Pydantic 2.11.3, requests 2.32.3, RPi.GPIO 0.7.1, smbus2 0.5.0, aiohttp 3.11.18, Jinja2 3.1.6 et Rich 14.0.0. Elles constituent un relevé, pas encore un lock de dépendances.

## Installation applicative

Exemple de séquence, sous l'utilisateur de service non-root :

```bash
git clone <depot> ~/PhytoController
cd ~/PhytoController/'RPi Version'
python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r requirements.txt
venv/bin/python3 -m compileall -q -x '(venv|\.git|__pycache__|lib/sensors)' .
```

La production utilise l'utilisateur `progradius` et le chemin `/home/progradius/PhytoController/RPi Version`. Cet utilisateur appartient notamment aux groupes `sudo`, `netdev`, `spi`, `i2c` et `gpio`.

## Configuration

`param/param.json` est actuellement requis au boot. Il contient des secrets et ne doit pas être construit à partir d'un exemple avec des valeurs de production.

Avant démarrage :

1. créer ou restaurer le fichier avec permissions restrictives adaptées ;
2. vérifier toutes les affectations GPIO ;
3. désactiver les capteurs non câblés ;
4. valider sans afficher le contenu :

```bash
venv/bin/python3 -c 'from param.config import AppConfig; AppConfig.load(); print("configuration valide")'
```

L'outil `initial_setup_tool.py` écrit relativement au répertoire courant. Dans son état actuel, l'exécuter depuis `param/` ou déplacer explicitement le résultat vers `param/param.json` après vérification.

## Configuration système

La configuration déployée et vérifiée le 25 août 2026 contient ce drop-in :

```ini
[Service]
Type=notify
NotifyAccess=main
WatchdogSec=600
Restart=always
```

L'unité et le drop-in observés sont recopiés sous `deploy/`. Avant installation sur une autre machine, revoir les chemins, l'utilisateur et les capacités `CAP_SYS_ADMIN`/`CAP_SYS_RAWIO`, qui sont larges. Comparer avec les fichiers actifs au lieu de les écraser aveuglément.

Après installation ou modification :

```bash
sudo systemctl daemon-reload
sudo systemctl start phyto
systemctl status phyto --no-pager
curl -fsS http://127.0.0.1:8123/status | jq '{healthy, heater_alarm, tasks}'
```

## Mise en service progressive

1. Démarrer sans charges et vérifier une seule instance.
2. Vérifier la configuration de toutes les broches au `pinctrl`.
3. Arrêter le service et confirmer génériques HIGH, moteur LOW, broches toujours en sortie.
4. Tester les relais seuls, charge de puissance coupée.
5. Tester chaque charge indépendamment et sous surveillance.
6. Tester perte de capteur, annulation d'un cycle et SIGTERM.
7. Vérifier `/status`, les logs, la rotation et systemd.
8. Raccorder les charges définitives seulement après validation et consignation des résultats.

## Critère de fin

L'installation n'est qualifiée qu'après une reconstruction exercée, une preuve GPIO boot/arrêt et une comparaison de l'unité systemd installée avec les artefacts versionnés.
