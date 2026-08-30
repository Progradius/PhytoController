# PWA locale et autorité TLS privée

**Statut** : HTTPS déployé et vérifié sur le Raspberry Pi de production le 28 août 2026 ;
qualification PWA complète sur Android encore ouverte. Le relevé d'installation et ses limites sont
conservés dans [Activation TLS du 28 août 2026](pwa-tls-activation-2026-08-28.md).

**Origine canonique** : `https://phytocontroller.local/`.

**Compatibilité conservée** : `http://127.0.0.1:8123` et `http://<ip>:8123` restent actifs.

Le service worker et les notifications exigent une origine HTTPS authentifiée. L'autorité décrite
ici est privée et réservée à PhytoController : son installation sur Android lui donne le pouvoir de
faire approuver les certificats qu'elle signe. Sa clé racine ne doit donc jamais être copiée sur le
Raspberry Pi, dans Git, dans une sauvegarde applicative ou dans un terminal Android.

## 1. Créer l'autorité hors du Pi

Exécuter ces commandes sur le poste d'administration **depuis la racine du dépôt**, afin que
`deploy/pwa-tls-server.ext` soit résolu. Les clés et certificats sont écrits dans un répertoire
protégé situé **hors du dépôt**. Remplacer le chemin d'exemple par un emplacement chiffré ou amovible
réellement sauvegardé.

```bash
PWA_CA_DIR=/chemin/protege/phyto-ca
install -d -m 0700 "$PWA_CA_DIR"
umask 077

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$PWA_CA_DIR/phyto-root-ca.key"
openssl req -x509 -new -sha256 -days 3650 \
  -key "$PWA_CA_DIR/phyto-root-ca.key" \
  -out "$PWA_CA_DIR/phyto-root-ca.crt" \
  -subj '/CN=PhytoController Local Root CA' \
  -addext 'basicConstraints=critical,CA:TRUE,pathlen:0' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -addext 'subjectKeyIdentifier=hash'

openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 \
  -out "$PWA_CA_DIR/server.key"
openssl req -new -sha256 \
  -key "$PWA_CA_DIR/server.key" \
  -out "$PWA_CA_DIR/server.csr" \
  -subj '/CN=phytocontroller.local'
openssl x509 -req -sha256 -days 397 \
  -in "$PWA_CA_DIR/server.csr" \
  -CA "$PWA_CA_DIR/phyto-root-ca.crt" \
  -CAkey "$PWA_CA_DIR/phyto-root-ca.key" \
  -CAcreateserial \
  -extfile deploy/pwa-tls-server.ext \
  -out "$PWA_CA_DIR/server.crt"

openssl verify -CAfile "$PWA_CA_DIR/phyto-root-ca.crt" "$PWA_CA_DIR/server.crt"
openssl x509 -in "$PWA_CA_DIR/server.crt" -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in "$PWA_CA_DIR/phyto-root-ca.crt" -noout -fingerprint -sha256
```

Le certificat serveur couvre `phytocontroller.local`, `phytocontroller` et l'adresse fixe de secours
`10.42.0.1`. Ne pas ajouter une adresse DHCP tant qu'elle n'est pas réservée durablement.

## 2. Installer la chaîne publique et la clé serveur sur le Pi

Transférer `server.crt` et `server.key` par SSH ou support d'administration. Ne jamais transférer
`phyto-root-ca.key`.

```bash
sudo install -d -o root -g progradius -m 0750 /etc/phyto/tls
sudo install -o root -g progradius -m 0644 /chemin/transfert/server.crt /etc/phyto/tls/server.crt
sudo install -o root -g progradius -m 0640 /chemin/transfert/server.key /etc/phyto/tls/server.key
sudo install -o root -g root -m 0644 /chemin/transfert/phyto-root-ca.crt /etc/phyto/tls/phyto-root-ca.crt
```

Installer ensuite le drop-in versionné après comparaison avec l'unité active :

```bash
sudo install -d -m 0755 /etc/systemd/system/phyto.service.d
sudo install -o root -g root -m 0644 deploy/phyto.service.d/pwa-tls.conf \
  /etc/systemd/system/phyto.service.d/pwa-tls.conf
sudo systemctl daemon-reload
sudo systemctl restart phyto.service
```

L'unité principale reste volontairement sans configuration HTTPS : tant que ce drop-in et les
certificats ne sont pas installés, elle continue à n'exposer que HTTP `:8123` sans erreur TLS au
démarrage.

Le redémarrage applique les états GPIO sûrs prévus par l'application. Le préparer comme tout
redémarrage de production ; ne pas le lancer pendant une observation qui exige un PID stable.

## 3. Vérifier les deux transports

```bash
ss -ltn 'sport = :443 or sport = :8123'
curl -fsS http://127.0.0.1:8123/health/ready
curl --cacert /etc/phyto/tls/phyto-root-ca.crt \
  --resolve phytocontroller.local:443:127.0.0.1 \
  https://phytocontroller.local/health/live
openssl s_client -connect 127.0.0.1:443 -servername phytocontroller.local \
  -CAfile /etc/phyto/tls/phyto-root-ca.crt -verify_hostname phytocontroller.local </dev/null
systemctl show phyto.service -p AmbientCapabilities -p Environment
```

Une panne TLS doit laisser HTTP `:8123` et le contrôle actifs. `/api/v1/state` publie alors
`web.https.ready=false` et le journal contient une erreur sans contenu de clé.

## 4. Installer l'autorité sur Android

1. Transférer `phyto-root-ca.crt` par un canal d'administration.
2. Comparer son empreinte SHA-256 avec celle affichée sur le poste d'administration.
3. Dans les réglages Android, installer le fichier comme certificat d'autorité pour les applications.
4. Ouvrir `https://phytocontroller.local/` dans Chrome et vérifier l'absence d'interstitiel TLS.
5. Utiliser le bouton « Installer l'application » du tableau de bord.

Ne pas installer `server.key`, `phyto-root-ca.key` ni un fichier PKCS#12 sur le téléphone.

## 5. Renouvellement et retrait

Contrôler mensuellement l'échéance :

```bash
openssl x509 -in /etc/phyto/tls/server.crt -checkend 2592000 -noout
```

À moins de 30 jours, signer un nouveau certificat serveur avec la racine conservée hors Pi, remplacer
`server.crt`, puis redémarrer le service pendant une fenêtre planifiée. La racine Android reste valide.

En rollback vers une version antérieure à la PWA, HTTP `:8123` reste disponible mais `:443` disparaît.
La PWA peut continuer à montrer son dernier snapshot avec « hors ligne » ; la désinstaller ou effacer
les données du site dans Chrome pour supprimer cette coque locale.

## 6. État de la production

Depuis le 28 août 2026, le service de production écoute simultanément sur HTTP `:8123` et HTTPS
`:443`. Le certificat serveur couvre `phytocontroller.local`, `phytocontroller` et `10.42.0.1` et
expire le 29 septembre 2027. Le certificat public de l'autorité doit être installé sur chaque client
avant d'utiliser l'origine canonique sans avertissement.

La présence de HTTPS ne change pas le périmètre de sécurité : l'interface reste sans authentification
et ne doit être exposée qu'à un LAN de confiance. HTTP `:8123` reste volontairement actif comme voie
de compatibilité et de récupération.

Ne pas déduire de ce déploiement que toute la qualification PWA est terminée. Restent notamment à
exercer et consigner : la panne TLS contrôlée, le fonctionnement hors ligne et la reconnexion sur
Android, les notifications locales et le renouvellement du certificat. La clé racine conservée hors
du Pi doit également recevoir une sauvegarde chiffrée ou amovible vérifiée.
