# ADR-0003 — Interface web LAN-only sans authentification

**Statut** : accepté avec risques ouverts. **Date** : 25 août 2026.

## Contexte

L'IHM est destinée à un LAN domestique et ne possède pas d'authentification. Elle expose configuration, logs, reboot et extinction.

## Décision actuelle

- Port 8123 limité au LAN par l'exploitation.
- Aucune action destructive derrière GET.
- Actions monitor en POST, contrôle `Origin` et Post/Redirect/Get.
- Pas d'authentification ajoutée lors de la phase de garde-fous.

## Conséquences

La simplicité est conservée, mais DNS rebinding, clients locaux, fuite des secrets dans `/conf`, traversal statique et DoS restent ouverts. Le port ne doit jamais être publié sur Internet.

## Suite factuelle — 26 août 2026

La **décision** est inchangée : LAN-only, sans authentification. Plusieurs risques qu'elle laissait
ouverts ont en revanche été fermés par la refonte web (`7d455e4`, `ad39de2`, déployée et vérifiée) :

- DNS rebinding : `Host` validé, 421 hors liste ;
- fuite des secrets dans `/conf` : plus aucune valeur sensible rendue ;
- traversée statique : liste blanche exacte de chemins ;
- absence de limites HTTP : corps, ligne et en-têtes plafonnés ;
- effets de bord : routes POST dédiées, jeton CSRF persistant, contrôle d'`Origin`.

**Restent ouverts** : l'absence d'authentification et le transport en clair. Le port ne doit
toujours pas être publié sur Internet.

## Réexamen

Obligatoire lors de la migration HTTP, de tout changement de topologie réseau, d'un accès distant ou de l'ajout de nouveaux effets de bord.
