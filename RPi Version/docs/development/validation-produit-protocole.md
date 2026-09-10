# Validation produit avec les opérateurs

Protocole R4.3 du [plan de remédiation](remediation-web-mobile-pwa-2026-09-09.md).
État au 10 septembre 2026 : **sessions et décisions produit à réaliser**.

## Organisation

Prévoir au moins deux opérateurs dont un peu familier de l'application. Utiliser
un téléphone sur le simulateur `tests/ui_server.py` avec données fictives. Les
commandes physiques exigent [la procédure supervisée](hardware-validation.md).
Fixer le commit et conserver le même scénario de départ entre participants.

Lire seulement l'objectif de la tâche, sans nommer le bouton à utiliser. Déclencher
le chronomètre à la fin de l'énoncé ; l'arrêter lorsque le participant annonce la
fin. Une aide de l'observateur transforme le résultat en « avec aide ». Demander
ensuite ce qui est enregistré, ce qui reste local et ce que fera le contrôleur.
Ne pas compter une tâche non implémentée ou non exécutée comme une réussite.

| Tâche | Énoncé à lire | Réussite observable |
| --- | --- | --- |
| P01 | Dites si la serre va bien et si les données sont récentes | État, fraîcheur et éventuelle alarme compris en moins de 5 s |
| P02 | Expliquez cette alarme et indiquez la prochaine action | Problème, conséquence et conseil trouvés ; acquittement distinct de résolution |
| P03 | Coupez temporairement cet équipement et expliquez sa reprise | Bonne cible, durée et conséquence comprises ; confirmation explicite |
| P04 | Modifiez cette consigne de température | Bonne section ; normalisations comprises ; sauvegarde confirmée |
| P05 | Enregistrez ce pH et cette EC sur cette culture | Bonne cible, valeurs et date ; résultat retrouvé après enregistrement |
| P06 | Ajoutez une observation avec une photo | Photo choisie et aperçu vu ; une seule observation enregistrée |
| P07 | Marquez ce rappel fait puis reportez le suivant | Bons rappels ; date de report comprise ; distinction rappel/alarme |
| P08 | Comparez ces deux cultures | Deux bonnes cibles, période comprise, absence distinguée de zéro |
| P09 | Retrouvez une intervention passée | Recherche utilisée, bonne opération et contexte identifiés |
| P10 | Consultez une copie sans réseau puis revenez en ligne | Date de copie et lecture seule comprises ; reprise sans rejeu |

## Fiche d'observation

| Participant anonyme | Familiarité | Appareil / OS | Commit | Tâche | Durée (s) | Sans aide / avec aide / échec | Erreur / abandon | Compréhension après tâche |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| À renseigner | — | — | — | P01–P10, une ligne par tâche | — | Non exécuté | — | — |

Objectifs : 90 % de réussite sans aide sur les tâches fréquentes, accès à l'action
principale en un geste depuis le bon contexte, zéro ambiguïté enregistré/brouillon,
vivant/copie et acquittement/résolution. Publier le dénominateur : tâches exécutées,
réussites sans aide et exclusions motivées. Deux participants donnent un signal
produit ; ils ne démontrent pas une représentativité statistique.

## Décisions à documenter après les sessions

| Option | Preuve attendue | Décision actuelle |
| --- | --- | --- |
| Cinq destinations mobiles | Mesure à 320 px et besoin observé d'Historique | Quatre destinations recommandées |
| Sélecteur compact des rubriques | Derniers onglets régulièrement ignorés | Non activé |
| Recherche de réglage avancé | Difficulté d'orientation observée | Non activée |
| Chargement à la demande de Configuration | Mesures Pi/téléphone représentatives | Aucune décision sans mesure terrain |

Pour chaque changement décidé : lier les observations, écrire la fiche R-x.y
complémentaire et rejouer la tâche après correction. Reporter les résultats dans
le plan et [la grille de qualification](qualification-mobile-pwa.md).
