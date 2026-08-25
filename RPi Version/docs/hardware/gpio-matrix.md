# Matrice GPIO, polarités et collisions

**Public** : câblage, mise en service, exploitation et développement.
**Source du relevé** : section `GPIO_Settings` du `param/param.json` versionné au commit `61ad3df`.
**Dernière vérification documentaire** : 25 août 2026.
**Attention** : cette matrice décrit la configuration du dépôt à cette date. Vérifier la configuration vivante du Pi et le câblage avant toute intervention.

## Matrice actuelle

| Fonction | Champ | BCM | Broche physique | Direction | Polarité / état sûr | État capteur associé |
|---|---|---:|---:|---|---|---|
| I²C SDA déclaré | `i2c_sda` | 21 | 40 | Configurée ailleurs selon pilote | Non piloté par `Component` | BME280 actif |
| I²C SCL déclaré | `i2c_scl` | 22 | 15 | Conflit potentiel | Non piloté par `Component` | BME280 actif |
| DS18B20 | `ds18_pin` | 4 | 7 | Entrée 1-Wire | Pull-up 4,7 kΩ normalement requis | Désactivé |
| HC-SR04 trigger | `hcsr_trigger_pin` | 26 | 37 | Sortie | Repos LOW attendu | Désactivé |
| HC-SR04 echo | `hcsr_echo_pin` | 27 | 13 | Entrée | Niveau d'entrée à adapter au Pi | Désactivé |
| Daily timer 1 | `dailytimer1_pin` | 5 | 29 | Sortie | Actif-BAS, sûr HIGH | — |
| Daily timer 2 | `dailytimer2_pin` | 18 | 12 | Sortie | Actif-BAS, sûr HIGH | — |
| Cyclic timer 1 | `cyclic1_pin` | 27 | 13 | Sortie | Actif-BAS, sûr HIGH | — |
| Cyclic timer 2 | `cyclic2_pin` | 22 | 15 | Sortie | Actif-BAS, sûr HIGH | — |
| Chauffage | `heater_pin` | 23 | 16 | Sortie | Actif-BAS, sûr HIGH | — |
| Moteur vitesse 1 | `motor_pin1` | 25 | 22 | Sortie | Actif-HAUT, sûr LOW | — |
| Moteur vitesse 2 | `motor_pin2` | 8 | 24 | Sortie | Actif-HAUT, sûr LOW | — |
| Moteur vitesse 3 | `motor_pin3` | 7 | 26 | Sortie | Actif-HAUT, sûr LOW | — |
| Moteur vitesse 4 | `motor_pin4` | 1 | 28 | Sortie | Actif-HAUT, sûr LOW | — |

## Collisions détectées

La configuration actuelle contient des doublons que le modèle Pydantic n'interdit pas :

| BCM | Affectations | Situation actuelle | Risque |
|---:|---|---|---|
| 27 | Echo HC-SR04 et cyclic timer 1 | HC-SR04 désactivé | Activer HC-SR04 ferait partager une entrée capteur et une sortie relais |
| 22 | I²C SCL déclaré et cyclic timer 2 | BME280 déclaré actif | La valeur `i2c_scl` n'est pas utilisée pour ouvrir `/dev/i2c-1`, mais la documentation/configuration est incohérente et GPIO22 pilote une sortie active-BAS |

Le contrôleur I²C ouvre `/dev/i2c-1`, dont les broches conventionnelles du Raspberry Pi sont BCM 2 et BCM 3. Les champs `i2c_sda=21` et `i2c_scl=22` ne constituent donc pas une description fiable du bus effectivement utilisé. Ils ne doivent pas servir à recâbler le système sans vérification sur le Pi.

La cible est un registre central de broches validant l'unicité, la direction, la polarité, la fonction alternative et l'état sûr avant tout accès GPIO.

## GPIO moteur à migrer

Les broches moteur actives-HAUT 1, 7 et 8 sont problématiques au boot :

- BCM 1 est `ID_SC`, réservé à l'identification HAT et potentiellement piloté par le firmware ;
- BCM 7 et 8 portent les fonctions SPI CE1/CE0 ;
- GPIO 0 à 8 ont des pulls par défaut défavorables à des relais actifs-HAUT ;
- plusieurs relais pourraient être sollicités avant l'initialisation Python.

La migration de la vitesse 4 de BCM 1 vers BCM 16 est déjà proposée dans `tasks/todo.md`. Une migration complète devrait privilégier quatre GPIO généraux supérieurs ou égaux à 9, sans fonction alternative active et avec pull-down externe.

## Niveaux sûrs

```text
Sorties journalières : HIGH = OFF
Sorties cycliques    : HIGH = OFF
Chauffage            : HIGH = OFF
Moteur vitesses 1–4  : LOW  = OFF
HC-SR04 trigger      : LOW  = repos
```

Les lignes historiques `gpio=N=op,dh` présentes dans `notes` ne doivent pas être copiées. Elles forceraient notamment HIGH les sorties moteur actives-HAUT et commanderaient les relais. De plus, sous Raspberry Pi OS Bookworm, la configuration active se trouve normalement dans `/boot/firmware/config.txt`, pas dans l'ancien `/boot/config.txt`.

## Checklist avant modification d'une broche

1. Couper et consigner l'alimentation des charges.
2. Identifier BCM et numéro physique ; ne jamais les confondre.
3. Relever le pull et les fonctions alternatives au boot.
4. Vérifier que la broche n'apparaît dans aucune autre affectation.
5. Déterminer si la charge est active-BAS ou active-HAUT.
6. Définir le niveau sûr au boot, en fonctionnement et à l'arrêt.
7. Vérifier les résistances externes de rappel.
8. Modifier la configuration de référence et la copie vivante du Pi selon une procédure contrôlée.
9. Tester sans charge, puis avec relais, puis avec équipement.
10. Vérifier au `pinctrl` l'état de toutes les broches avant et après arrêt du service.
11. Mettre à jour cette matrice, le schéma électrique et le registre des risques.

## Preuve matérielle disponible

Le 25 août 2026, un arrêt réel du service a montré que les neuf sorties de puissance restaient configurées en sorties :

- génériques à HIGH ;
- moteur à LOW.

Cette preuve confirme l'arrêt contrôlé du code corrigé. Elle ne prouve pas l'état pendant la fenêtre de boot, après un reset brutal ou après une modification future du câblage.
