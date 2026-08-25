# Sauvegarde et restauration

## Données vivantes

| Fichier | Contenu | Sensibilité |
|---|---|---|
| `param/param.json` | Configuration, Wi-Fi, InfluxDB, GPIO | Critique : secrets et sécurité physique |
| `param/sensor_stats.json` | Minimums et maximums de capteurs | Faible à moyenne |
| `logs/phyto.log*` | Diagnostic applicatif | Peut contenir topologie et événements |

Le script de déploiement sauvegarde les deux fichiers `param/` avant toute mise à jour. Ce mécanisme n'est pas une sauvegarde hors machine : une panne de carte SD peut détruire le dépôt et `~/phyto-backups` simultanément.

## Contrôle des sauvegardes de déploiement

```bash
find ~/phyto-backups -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort -r
```

Ne pas afficher le contenu de `param.json`. Contrôler permissions, taille raisonnable et validité sur une copie protégée.

## Politique recommandée

- conserver les vingt sauvegardes locales du script ;
- réaliser une sauvegarde chiffrée hors Pi avant chaque migration de schéma ou câblage ;
- conserver séparément les artefacts systemd et la documentation ;
- ne jamais placer les secrets dans un dépôt Git ordinaire ;
- tester périodiquement une restauration sur un environnement sans charges.

## Restauration

Une restauration peut changer les GPIO, consignes et identifiants. Avant de remplacer un fichier :

1. couper ou mettre en sécurité les charges ;
2. arrêter le service ;
3. sauvegarder le fichier actuel sous un nom horodaté et protégé ;
4. identifier explicitement la sauvegarde source ;
5. restaurer en conservant propriétaire et permissions ;
6. valider avec `AppConfig.load()` sans imprimer les valeurs ;
7. comparer les noms de champs et la matrice GPIO ;
8. redémarrer sous surveillance ;
9. vérifier `healthy`, alarmes, logs et sorties physiques.

Les commandes d'écrasement sont volontairement absentes de cette première version afin d'éviter une restauration sur une cible ambiguë. Elles seront ajoutées après exercice sur une copie et avec des chemins validés.

## Critère de réussite

Une sauvegarde n'est qualifiée que si elle peut restaurer configuration, statistiques et unité systemd sur un Pi de remplacement, avec secrets injectés séparément et vérifications matérielles avant raccordement des charges.
