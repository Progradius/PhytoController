# Validation matérielle des sorties

**Public** : exploitant et développeur intervenant sur le Raspberry Pi.
**Nature** : procédure volontaire sous surveillance, jamais appelée par `pytest` ou le déploiement.

La suite automatisée prouve les décisions et les niveaux **logiques** avec un faux GPIO. Elle ne prouve
ni la tension réellement présente, ni le câblage, ni la polarité d'une carte relais, ni l'état pendant
la fenêtre de boot. Cette procédure complète la suite lorsqu'un changement touche GPIO, chauffage,
moteur, minuteurs, supervision ou arrêt.

## Préconditions obligatoires

1. Identifier le commit, la configuration vivante et le schéma effectivement câblé sans recopier les
   secrets de `param.json` dans le relevé.
2. Ouvrir une fenêtre de maintenance et prévenir les personnes présentes.
3. Couper et consigner l'alimentation des charges haute tension. Commencer sans charge, puis relais
   seuls ; ne reconnecter un équipement qu'après validation de son canal.
4. Vérifier BCM, broche physique, direction, fonction alternative, pull externe et absence de collision
   dans [`../hardware/gpio-matrix.md`](../hardware/gpio-matrix.md).
5. Préparer un moyen de coupure indépendant. Le chauffage doit rester protégé par un dispositif
   thermique matériel ; le logiciel n'est pas une protection unique acceptable.

## État sûr avant essai

Arrêter le service, puis relever toutes les sorties avec `pinctrl`. L'arrêt contrôlé doit laisser les
broches en mode sortie :

```text
Daily 1/2, Cyclic 1/2, chauffage : HIGH = OFF (actif-BAS)
Moteur vitesses 1 à 4             : LOW  = OFF (actif-HAUT)
```

Ne jamais appeler `GPIO.cleanup()` : il rendrait les broches flottantes. Ne jamais recopier les lignes
historiques `gpio=N=op,dh` de `notes`, dangereuses pour les relais moteur actifs-HAUT.

Si une seule broche n'est pas dans l'état attendu, interrompre la procédure, maintenir les charges
consignées et traiter l'écart avant tout ordre ON.

## Relais actifs-BAS

Tester un seul canal à la fois, toujours sans charge au premier passage :

1. confirmer HIGH et relais ouvert au repos ;
2. demander ON et confirmer LOW puis fermeture du relais ;
3. demander OFF et confirmer HIGH puis ouverture ;
4. injecter une exception ou annuler le travail pendant une fenêtre `energized()` ;
5. confirmer le retour terminal à HIGH ;
6. répéter pour les sorties journalières, cycliques et le chauffage.

Pour le chauffage, ne jamais prolonger artificiellement l'essai pour atteindre la limite de deux
heures avec une charge réelle : cette durée est couverte par la politique pure. La vérification
matérielle porte sur la coupure effective et la cohérence entre ordre, GPIO et relais.

## Moteur actif-HAUT

Pour chaque vitesse de 1 à 4 :

1. confirmer les quatre GPIO à LOW ;
2. demander la vitesse et confirmer qu'une seule broche passe HIGH ;
3. changer directement vers une autre vitesse et observer le passage intermédiaire des quatre broches
   à LOW avant le nouveau HIGH ;
4. demander l'arrêt et confirmer les quatre LOW ;
5. ne jamais poursuivre si deux relais sont fermés simultanément.

L'interlock matériel reste requis : une séquence logicielle correcte ne protège pas contre un défaut de
carte, un état de boot ou deux contacts mécaniquement collés.

## Supervision et arrêt

1. Injecter une panne bornée dans un travail de contrôle et confirmer : alarme, état sûr, back-off puis
   relance.
2. Effectuer un reload volontaire à consigne inchangée et confirmer l'absence de clignotement dû au
   superviseur ; les `finally` métier restent responsables de libérer une sortie temporairement ON.
3. Envoyer SIGTERM au service et confirmer les niveaux terminaux : génériques HIGH, moteur LOW.
4. Redémarrer sans charge et relever les niveaux de la mise sous tension à READY. Une observation après
   READY seulement ne qualifie pas la fenêtre de boot.

## Reconnexion et preuve

Reconnecter les charges une par une. Pour chaque canal, consigner :

- date, opérateur, commit et version de configuration non sensible ;
- BCM et broche physique ;
- état attendu et état lu au repos, ON, OFF, exception/annulation et arrêt ;
- preuve `pinctrl` ou mesure électrique ;
- type de relais et polarité constatée ;
- limite non couverte et décision de rollback éventuelle.

Une preuve sans charge ne qualifie pas la charge ; une preuve relais seul ne qualifie pas le moteur ou
le chauffage. Chaque étape doit rester réversible et la précédente doit être concluante avant de
continuer.
