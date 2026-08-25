# Politique de sécurité

PhytoController commande des équipements physiques. Une vulnérabilité peut avoir des conséquences électriques, thermiques ou hydrauliques ; traiter les signalements avec une priorité supérieure à celle d'une application web ordinaire.

## Périmètre actuel

- La version Raspberry Pi est maintenue dans cette arborescence.
- L'interface web est conçue pour un LAN de confiance uniquement.
- Le port 8123 ne doit pas être exposé sur Internet.
- L'absence d'authentification, les secrets historiques dans `param.json`, le confinement statique et les limites HTTP sont des risques connus, suivis dans `docs/risk-register.md`.

## Signaler un problème

Ne pas publier publiquement :

- mot de passe Wi-Fi ou InfluxDB ;
- copie de `param/param.json` ;
- adresse, nom de base ou topologie permettant un accès non autorisé ;
- procédure directement exploitable contre une installation active avant coordination.

Un signalement utile contient, après masquage : commit, composant, impact, préconditions, scénario minimal, état physique observé, logs pertinents et proposition de mitigation immédiate.

Le dépôt ne définit pas encore d'adresse privée dédiée aux signalements. Utiliser un canal privé convenu avec le propriétaire du déploiement jusqu'à l'ajout d'un contact officiel.

## Incident actif

En présence d'un chauffage, moteur ou arrosage incontrôlé, couper d'abord la puissance concernée et suivre `docs/operations/incident-runbook.md`. Ne pas retarder la mise en sécurité pour collecter des preuves.

## Secrets

Les identifiants historiquement versionnés doivent être considérés comme compromis. Leur retrait futur du fichier courant ne remplacera pas leur rotation. Aucun secret réel ne doit être ajouté à un exemple, test, log, issue ou commit.
