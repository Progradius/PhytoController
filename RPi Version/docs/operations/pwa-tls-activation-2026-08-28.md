# Activation TLS de production — 28 août 2026

**Nature** : changement d'exploitation réellement exécuté sur le Raspberry Pi de production.
**Application déployée** : commit `5520850c09ae478806a145a7ce389bf5cd89666c`.
**Origine canonique** : `https://phytocontroller.local/`.
**Voie de récupération conservée** : `http://192.168.1.15:8123/` au moment du relevé.
**Valeurs sensibles** : aucune clé privée ni aucun secret n'est reproduit dans ce document.

Ce relevé est daté. Il prouve l'état observé pendant l'activation ; la procédure vivante reste
[PWA locale et autorité TLS privée](pwa-local-tls.md).

## État initial

Avant l'intervention, `phyto.service` était `active/running` sous l'utilisateur `progradius`, seul
`0.0.0.0:8123` écoutait et `/api/v1/state` publiait :

```json
{"configured": false, "ready": false, "port": null}
```

Le répertoire `/etc/phyto/tls` ne contenait aucun certificat. L'unité ne chargeait que le drop-in
watchdog et possédait `CAP_SYS_ADMIN` et `CAP_SYS_RAWIO`, sans `CAP_NET_BIND_SERVICE`.

## Autorité et certificat créés hors du Pi

Une autorité dédiée `PhytoController Local Root CA` a été créée sur le poste d'administration dans
`/home/rpteamb/.local/share/phyto-ca`, hors du dépôt. Le répertoire porte le mode `0700` et les clés
privées le mode `0600`.

La clé `phyto-root-ca.key` n'a été transférée ni sur le Raspberry Pi, ni dans le dépôt, ni vers le
terminal client. Seuls le certificat public de la racine, le certificat serveur et la clé privée du
serveur ont été transférés au Pi. Les copies temporaires de transfert ont été supprimées après
installation.

Caractéristiques vérifiées du certificat serveur :

| Propriété | Valeur constatée |
|---|---|
| Sujet | `CN=phytocontroller.local` |
| Émetteur | `CN=PhytoController Local Root CA` |
| Validité | 28 août 2026 au 29 septembre 2027 |
| Usage étendu | `TLS Web Server Authentication` |
| SAN DNS | `phytocontroller.local`, `phytocontroller` |
| SAN IP | `10.42.0.1` |
| Vérification de chaîne | `OK` |

Empreinte SHA-256 du certificat public de l'autorité, à comparer avant toute installation client :

```text
8E:51:A4:42:39:B9:41:88:E7:42:4F:CC:EA:2D:97:5F:
5D:00:17:1C:3C:ED:13:9D:C1:53:4E:46:C9:06:61:A6
```

Une copie distribuable du seul certificat public a été déposée sur le poste d'administration dans
`C:\Users\RaphaelPERLES\Downloads\phyto-root-ca.crt`. Cette copie ne donne accès à aucune clé privée.

## Installation sur le Raspberry Pi

Les artefacts installés ont été relevés avec les propriétaires et modes suivants :

| Fichier | Propriétaire | Mode | Rôle |
|---|---|---:|---|
| `/etc/phyto/tls/server.crt` | `root:progradius` | `0644` | Certificat serveur public |
| `/etc/phyto/tls/server.key` | `root:progradius` | `0640` | Clé privée serveur lisible par le service |
| `/etc/phyto/tls/phyto-root-ca.crt` | `root:root` | `0644` | Certificat public de l'autorité |

Le drop-in versionné `deploy/phyto.service.d/pwa-tls.conf` a été installé sous
`/etc/systemd/system/phyto.service.d/pwa-tls.conf`, puis `systemctl daemon-reload` et
`systemctl restart phyto.service` ont été exécutés. L'environnement actif configure le port `443`
et les deux chemins serveur sous `/etc/phyto/tls`. L'unité possède désormais également
`CAP_NET_BIND_SERVICE`.

Le nouveau processus est entré dans l'état `active/running` le 28 août 2026 à 20:36:18 CEST, avec le
PID `385264` lors du relevé et `NRestarts=0`. Un PID est une preuve datée et ne doit pas être utilisé
comme identifiant durable.

## Vérifications après activation

| Contrôle | Résultat observé |
|---|---|
| Ports TCP | `0.0.0.0:443` et `0.0.0.0:8123` en écoute simultanée |
| HTTP `/health/ready` | `{"ready": true, "unhealthy": []}` |
| HTTPS `/health/live` | `{"live": true, "version": "5520850…"}` |
| Chaîne TLS | `Verify return code: 0 (ok)` |
| Nom d'hôte TLS | `phytocontroller.local` vérifié |
| État HTTPS publié | `configured=true`, `ready=true`, `port=443` |
| Santé du contrôle | `control_healthy=true` |
| Alarmes critiques | `critical_count=0` |
| Journal TLS | `HTTPS PWA prêt sur 0.0.0.0:443` |

Le serveur a donc été validé localement sur le Pi avec la chaîne complète et le nom canonique.
L'opérateur a ensuite confirmé que l'accès était fonctionnel. Cette confirmation ne remplace pas la
qualification détaillée de Chrome Android, du mode hors ligne, de la reconnexion et des notifications.

## Impact sur l'observation de 48 heures en cours

Le redémarrage nécessaire à l'activation a remplacé le PID de référence `381022` par `385264` alors
que `scripts/observe-jalon2-operator-quality.sh` était en cours. L'observateur est resté actif, mais
son contrôle compare chaque échantillon au PID initial et doit enregistrer
`main_pid_modifie`. La fenêtre commencée le 28 août 2026 à 18:07:22 UTC ne pourra donc pas être
acceptée comme une observation continue sans redémarrage.

Cette invalidation concerne la continuité formelle de la preuve de 48 heures, pas la santé actuelle
du contrôleur : après l'activation, le service, la régulation, HTTP et HTTPS étaient tous sains.

Décision opérateur du 28 août 2026 : ne pas relancer immédiatement. Un nouveau redéploiement est
prévu. Juste avant celui-ci, arrêter proprement l'observateur actuel par `SIGTERM`, attendre l'écriture
de son résumé interrompu, redéployer, valider le service, nettoyer ou archiver uniquement cette
preuve invalidée, puis lancer une nouvelle fenêtre complète avec les références du nouveau
déploiement. La séquence générique est décrite dans
[Déploiement et rollback](deployment-and-rollback.md#redéployer-pendant-une-observation-jalon-2).

### Suite exécutée après le redéploiement

Le redéploiement suivant a installé le commit `b26d2b127098c3cf2521f9f725ebc99b5397dd3b`
(`fix(web): stabiliser la hauteur des graphiques`) et démarré `phyto.service` le 28 août 2026 à
20:57:20 CEST avec le PID initial `387866` et `NRestarts=0`.

L'ancien observateur, PID `381479`, a ensuite reçu `SIGTERM` et s'est terminé proprement. Son résumé
porte `status=interrupted`, une durée réelle de 3 076 s, 51 échantillons, 22 échecs attendus et zéro
avertissement. Les types d'échec sont `main_pid_modifie` et `commit_processus_inattendu`. La preuve
n'a pas été détruite : elle a été déplacée vers :

```text
/home/progradius/phyto-observations/invalidated/
jalon2-operateur-qualite-20260828T180722Z
```

Après validation du nouveau service — dix tâches saines, zéro restart/stall, aucune erreur ou alarme
critique, HTTP et HTTPS prêts — une nouvelle observation a été lancée :

| Référence | Valeur |
|---|---|
| PID observateur initial | `388349` |
| PID service de référence | `387866` |
| Commit attendu | `b26d2b127098c3cf2521f9f725ebc99b5397dd3b` |
| Début | 28 août 2026 à 18:59:28 UTC |
| Fin attendue | 30 août 2026 à 18:59:28 UTC |
| Durée demandée | 172 800 s |
| Preuves | `/home/progradius/phyto-observations/jalon2-operateur-qualite-20260828T185928Z` |

Le premier échantillon est `OK` : commit et PID attendus, `healthy=true`,
`control_healthy=true`, HTTPS `configured=true/ready=true`, aucun échec et aucun avertissement. La
fenêtre ne sera néanmoins qualifiée qu'après sa durée complète et la lecture de son `summary.json`.

## Actions restant ouvertes

- sauvegarder `phyto-root-ca.key` dans un emplacement chiffré ou sur un support amovible protégé, puis
  vérifier qu'une restauration est possible ;
- installer `phyto-root-ca.crt` sur chaque client en comparant l'empreinte ci-dessus ;
- exercer une panne TLS contrôlée pendant une fenêtre prévue et prouver que HTTP et la régulation
  restent disponibles ;
- qualifier Chrome Android, l'installation PWA, le fonctionnement hors ligne, la reconnexion et les
  notifications ;
- ~~laisser la nouvelle observation opérateur/qualité aller jusqu'au 30 août 2026 à 18:59:28 UTC sans
  redémarrage ni changement de commit, puis examiner son résumé~~ — **fait** : fenêtre close à
  l'heure prévue, 172 800 s, 2 864 échantillons, 0 échec, aucun redémarrage ni changement de commit ;
  HTTPS est resté `ready=true` sur toute la fenêtre. Résumé examiné dans le
  [relevé de clôture](jalon2-observation-operateur-2026-08-30.md) ;
- renouveler le certificat serveur avant le 29 septembre 2027, avec une alerte opérationnelle au
  moins 30 jours avant l'échéance.

## Retour arrière HTTPS

En cas de défaut TLS, conserver les certificats pour diagnostic et retirer ou neutraliser uniquement
le drop-in `pwa-tls.conf`, puis recharger systemd et redémarrer le service pendant une fenêtre
maîtrisée. HTTP `:8123` doit rester accessible. Ne jamais supprimer la clé racine hors Pi dans le
cadre d'un simple rollback applicatif : elle est nécessaire au renouvellement et au retrait maîtrisé
de la confiance client.
