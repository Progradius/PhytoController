# Observation watchdog du jalon 1 — clôture du 28 août 2026

**Objet** : qualification continue du découplage entre santé globale et santé du contrôle avant le
déploiement du jalon opérateur suivant. **Commit observé** : `e91b021`. **Watchdog systemd** : armé à
600 s par dérogation opérateur documentée. **Méthode** : lecture seule par
`scripts/observe-jalon1-watchdog.sh`, une sonde par minute pendant 48 h.

## Résultat formel

Le fichier `summary.json` produit sur le Raspberry Pi porte `status=accepted` :

| Preuve | Résultat |
|---|---:|
| Début UTC | 26 août 2026, 11:36:57 |
| Fin UTC | 28 août 2026, 11:36:57 |
| Durée demandée / réelle | 172 800 s / 172 800 s |
| Échantillons | 2 868 |
| Échantillons en échec | **0** |
| Échantillons avec avertissement | **0** |
| Redémarrages systemd | **0** |
| Changement de PID, boot ou watchdog | **aucun** |

À la clôture, `phyto.service` est resté `active/running`, `NRestarts=0`, toutes les tâches sont
vivantes et saines, `/health/ready` répond 200, `healthy=true`, `control_healthy=true` et le journal
ne contient aucune entrée de niveau WARNING ou supérieur sur la fenêtre.

Les 2 868 échantillons ont conservé une heure synchronisée, les trois mesures BME280 en état `ok`,
aucun actionneur périmé et `tracking=ok` pour toutes les sorties. Les niveaux GPIO relevés à la fin
correspondent aux états demandés, avec une seule vitesse moteur active.

## Événements expliqués et limite

Des rechargements volontaires de minuteries ont eu lieu pendant la fenêtre. Ils ont coupé ou repris
les sorties conformément aux modifications demandées, sans restart, stall, erreur ni écart de suivi.
Ils qualifient le rechargement à chaud mais signifient que la configuration n'est pas restée
strictement constante.

Le chauffage est resté désactivé et le moteur en mode manuel à la vitesse 2. Cette observation valide
la continuité du contrôle, les minuteries, l'acquisition et le suivi demandé/réel ; elle ne qualifie
pas les règles thermiques dynamiques. Leur essai est reporté au TODO d'activation consigné dans la
[roadmap](../roadmap.md#arbitre-thermique).

## Décision de passage

La condition documentaire « ne pas déployer le jalon 2 avant une fenêtre jalon 1 terminée et
acceptée » est satisfaite. Le lot suivant peut être déployé en conservant `Sensor_Quality.mode =
observe`, puis doit suivre la surveillance décrite dans
[Déploiement et rollback](deployment-and-rollback.md#observation-du-lot-opérateur-pwa-et-qualité-capteurs).
