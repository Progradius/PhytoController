# Qualification mobile et PWA

Protocole R4.1 du [plan de remédiation](remediation-web-mobile-pwa-2026-09-09.md).
État au 10 septembre 2026 : **qualification physique à exécuter**. Une émulation
Playwright, une capture ou un résultat axe ne vaut pas validation de Safari, du clavier
virtuel ni d'un lecteur d'écran sur appareil réel.

## Préparation et traçabilité

Utiliser le simulateur `tests/ui_server.py` et sa base temporaire pour les mutations.
Pour une intervention physique, appliquer [la procédure matérielle](hardware-validation.md).
Ne jamais charger un carnet de benchmark dans la base de production.

Consigner pour chaque session : date, opérateur, commit, modèle, version exacte du
système et du navigateur, URL, certificat et date d'expiration, mode navigateur ou
installé, orientation, taille de police et réseau. N'inscrire aucun secret.
Exécuter les scénarios une fois en portrait et une fois en paysage, puis répéter
les scénarios 1, 4, 5 et 9 avec zoom 200 % et grande police système.

Appareils attendus : Android/Chromium, iPhone Safari avec les versions iOS disponibles
(incluant iOS 26), iPad Safari et tablette Android. La disponibilité d'une version se
documente ; ne pas remplacer une case manquante par une réussite d'émulation.

## Scénarios et verdicts

Pour chaque ligne, créer une ligne de résultat **par appareil et orientation**. Les
dix tâches produit sont détaillées dans [le protocole opérateurs](validation-produit-protocole.md).

| ID | Manipulation | Critère observable |
| --- | --- | --- |
| Q01 | Exécuter les dix tâches produit | Durée, réussite sans aide, erreur et abandon consignés |
| Q02 | Approuver le certificat local puis installer | Bonne adresse, installation possible, icône et ouverture autonome |
| Q03 | Changer l'adresse réseau du simulateur/Pi de qualification | Message compréhensible ; ancienne copie clairement datée ; reconnexion à la nouvelle adresse |
| Q04 | Renouveler le certificat sur la cible de qualification | Procédure de confiance rejouable ; HTTP de secours disponible |
| Q05 | Modifier une saisie puis activer une nouvelle version depuis une seconde fenêtre | Aucune perte de saisie, aucun rechargement implicite de la fenêtre modifiée |
| Q06 | Mettre en veille puis revenir au premier plan | Fraîcheur réévaluée ; aucune notification issue d'une copie |
| Q07 | Effacer le stockage du site puis rouvrir | État hors ligne indisponible explicite ; fonctionnement connecté conservé |
| Q08 | Couper le réseau, puis simuler une connexion sans réponse | Copie datée après budget ; aucune mutation mise en attente ; HTTP 500 distinct d'une panne réseau |
| Q09 | Ouvrir le clavier sur le dernier champ de Configuration et d'un relevé, puis provoquer un refus | Champ, erreur et sauvegarde visibles ; focus non masqué par les barres fixes ou l'encoche |
| Q10 | Parcourir Tableau, Alarmes, Console, fiche, relevé et graphique avec VoiceOver/TalkBack | Noms, ordre de focus et sélection compréhensibles ; journal continu non annoncé |
| Q11 | Sélectionner un point puis tourner l'appareil | Même horodatage sélectionné, détail hors du doigt, défilement vertical possible |
| Q12 | Refuser notifications et stockage ; annuler l'installation | Aide adaptée et interface connectée utilisable |
| Q13 | Photo : caméra, photothèque, refus de taille, remplacement | Aperçu correct, limite expliquée, aucune observation dupliquée |
| Q14 | Fermer le navigateur après saisie d'un brouillon autorisé puis rouvrir | Restauration explicite ; aucune mesure, confirmation ou photo restaurée |
| Q15 | Ouvrir plusieurs pages puis provoquer une pression mémoire | Absence de promesse de conservation ; récupération compréhensible sans rejeu |

## Ce qui est déjà couvert en automatique

Un test Playwright ne clôt **jamais** une ligne de la grille : il ne qualifie ni Safari, ni
un lecteur d'écran, ni un vrai clavier virtuel, ni une encoche. Cette table dit seulement
où chercher la couverture existante, et ce qui reste entièrement manuel. Une case
« automatisé » signifie « la régression serait vue en intégration continue », pas « validé
sur appareil ».

| ID | Couverture automatisée | Fichier | Reste à faire sur appareil |
| --- | --- | --- | --- |
| Q01 | — | — | Les dix tâches, chronométrées, avec opérateurs |
| Q02 | — | — | Certificat approuvé, installation, icône, ouverture autonome |
| Q03 | — | — | Changement d'adresse réseau réel |
| Q04 | — | — | Renouvellement TLS |
| Q05 | Deux fenêtres et mise à jour pendant une saisie | `tests/ui/pwa_remediation.spec.js` | Idem sur iOS/Safari installé |
| Q06 | — | — | Veille et retour au premier plan |
| Q07 | — | — | Effacement du stockage du site |
| Q08 | Bannière hors ligne, lecture seule, aucune commande activable (profil `pwa-chromium`) ; verdict de connexion et 500 ≠ panne réseau | `tests/ui/qualification.spec.js`, `tests/ui/pwa_connexion.spec.js` | Coupure Wi-Fi réelle, réseau sans réponse d'un vrai routeur |
| Q09 | Focus non masqué par les barres fixes sur `/conf` et sur un relevé, **par mesure de recouvrement**, clavier virtuel simulé par un viewport réduit de 300 px | `tests/ui/qualification.spec.js` | Clavier virtuel réel, encoche, barre d'URL rétractable |
| Q10 | — (axe ne teste aucune aide technique) | — | VoiceOver et TalkBack sur Tableau, Alarmes, Console, fiche, relevé, explorateur |
| Q11 | — | — | Rotation avec un point sélectionné |
| Q12 | Refus du stockage local sans perte de page | `tests/ui/pwa_connexion.spec.js` | Refus de notifications, annulation d'installation |
| Q13 | Caméra, photothèque et reprise pilotent le même champ ; un seul aperçu | `tests/ui/cultures_ui_photos.spec.js` | Prise de vue réelle, refus de taille sur un fichier d'appareil |
| Q14 | Brouillon restauré explicitement | `tests/ui/pwa_remediation.spec.js` | Fermeture réelle du navigateur |
| Q15 | — | — | Pression mémoire sur un téléphone |
| — | États ouverts et refusés, dialogue de coupure (axe vert, focus piégé) | `tests/ui/qualification.spec.js` | — |
| — | Zoom 200 % : aucun défilement horizontal, cibles ≥ 24 px (projet `mobile-zoom`) | `tests/ui/qualification.spec.js`, `playwright.config.js` | Zoom navigateur réel et grande police système |

Le profil `mobile-zoom` de `playwright.config.js` rend un Pixel 5 en `deviceScaleFactor: 2`
sur un viewport de largeur divisée par deux : c'est la mise en page qu'un zoom de page à
200 % impose. Un `deviceScaleFactor` seul ne changerait que la densité, donc ne testerait rien.

La mesure hors suite `npm run measure:ui` (`tests/ui/measure_pages.js`) relève en plus, pour
chaque page et chaque thème, les états `formulaire_releve_ouvert`, `formulaire_releve_refuse`,
`menu_plus_ouvert`, `zoom_200_police`, `zoom_200_echelle`, `banniere_hors_ligne` et
`alarme_critique`, ainsi que les cibles nommées de R5.3. Elle n'assortit ces relevés d'aucune
assertion : elle documente, la suite qualifie.

## Grille à remplir

Copier une ligne par couple scénario/appareil ; `NE` = non exécuté, `OK` = accepté,
`KO` = écart reproductible. Joindre captures ou notes sans données personnelles.

| Date | Commit | Appareil / OS / navigateur | Mode / orientation | Scénario | Verdict | Mesure / preuve | Écart et fiche R-x.y |
| --- | --- | --- | --- | --- | --- | --- | --- |
| À renseigner | — | Android/Chromium | Navigateur + installé | Q01–Q15, à détailler | NE | — | — |
| À renseigner | — | iPhone/Safari | Navigateur + installé | Q01–Q15, à détailler | NE | — | — |
| À renseigner | — | iPad/Safari | Navigateur + installé | Q01–Q15, à détailler | NE | — | — |
| À renseigner | — | Tablette Android | Navigateur + installé | Q01–Q15, à détailler | NE | — | — |

La qualification ne peut être clôturée avant remplissage des scénarios critiques,
revue des écarts et report de leurs fiches dans le plan. Un appareil indisponible
reste une limite nommée, jamais une réussite.
