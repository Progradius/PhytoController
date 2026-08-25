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

## Réexamen

Obligatoire lors de la migration HTTP, de tout changement de topologie réseau, d'un accès distant ou de l'ajout de nouveaux effets de bord.
