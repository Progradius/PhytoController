# Processus de release

## Préparation

1. Définir le contenu et les risques associés.
2. Vérifier compatibilité de `param.json` et dépendances.
3. Mettre à jour documentation, roadmap, registre et changelog.
4. Exécuter `python3 -m pytest`, puis les vérifications matérielles proportionnées si le changement
   touche les sorties, la supervision ou l'arrêt.
5. Préparer rollback et fenêtre d'intervention matérielle.

## Livraison

- branche distante fast-forward ;
- sauvegarde hors Pi pour les migrations sensibles ;
- déploiement par `scripts/deploy.sh` ;
- validation `healthy=true`, pas seulement HTTP ;
- contrôle physique des charges ;
- observation des logs et compteurs ;
- consignation du commit réellement déployé.

## Stabilisation

Surveiller au minimum une période représentative des fonctions modifiées. Pour un timer journalier ou une rotation de log, cela peut imposer d'attendre l'échéance réelle. Pour le thermique, vérifier les seuils et transitions, pas seulement le démarrage.

## Rollback

Déclencher si boot impossible, santé fausse persistante, sortie incohérente, erreur de schéma ou métrique de sécurité dégradée. Une migration matérielle nécessite un plan de retour câblage/configuration, pas seulement Git.

## Versionnement

Le dépôt n'utilise pas encore de tags ou SemVer documentés. Jusqu'à décision, le commit Git est l'identifiant de release. Le changelog distingue dépôt, déploiement et vérification matérielle.
