# Carnet de cultures — livraisons 1 à 3

Le menu **Cultures** ouvre `/cultures`. Sur téléphone, il se trouve dans **Plus** ; le tableau
de bord comporte aussi un résumé des deux espaces et un accès au carnet.

Le carnet conserve les données sans purge automatique, indépendamment de l'historique technique
de 72 h. Ses actions ne changent ni horaires, ni pompe, ni ventilation. Les réglages continuent
de se faire dans **Configuration**. Les relevés pH/EC, solutions, arrosages et recettes sont disponibles dans **Solutions, relevés et arrosages**. Les photos, rappels et comparaisons sont accessibles dans **Cycles et rappels**.

## Commencer avec une culture existante

1. Ajouter les pieds mères avec des noms distincts, une variété facultative et leurs dates connues.
2. Créer un lot de semis ou de boutures. Pour les boutures, ajouter une origine par mère avec
   son effectif, par exemple trois de Mère A et cinq de Mère B.
3. Renseigner séparément la date d'origine (semis/prélèvement), le début du stade actuel et
   l'entrée dans l'espace actuel. Une culture déjà en floraison peut commencer directement à
   ce stade dans le carnet ; son passé inconnu n'est pas inventé.
4. Choisir « Date approximative » lorsque nécessaire. Le premier jour est J0 ; à la date locale
   suivante le compteur indique J1. J23 correspond à 3 semaines + 2 jours, semaine 4 en cours.

Le fuseau des compteurs, enregistré dans le carnet à sa création, est Europe/Paris. Les dates
simples restent des dates. Lorsqu'une heure est saisie, le formulaire utilise le fuseau de
l'appareil de saisie et transmet l'instant UTC ; celui-ci est affiché dans le fuseau du carnet,
avec son décalage UTC dans le journal. Les dates d'origine et du parcours sont affichées au
format jour/mois/année ; les formulaires et l'API conservent les valeurs exactes.
Les jours calendaires sont calculés dans le fuseau du carnet, changements d'heure compris.
Si le Pi ne dispose pas de preuve de synchronisation, les compteurs sont signalés à vérifier
et une confirmation explicite des dates est exigée pour enregistrer.

## Compléter le passé d'une culture reprise

Une culture créée directement « en floraison » n'a pas ses étapes antérieures. La section
« Compléter le parcours passé » de sa fiche les ajoute après coup, sans toucher au stade
courant ni à la clôture. Elle reste disponible sur une fiche en séchage ou archivée.

1. « Ajouter une étape passée » ne propose que les stades du parcours **antérieurs** au stade
   courant et encore absents. Quand la liste est vide, tout est renseigné.
2. « Ajouter un déplacement passé » complète une occupation manquante, par exemple l'espace 1
   avant l'entrée dans l'espace 2. Le lot entier occupe l'espace indiqué à partir de cette date,
   jusqu'au déplacement suivant déjà enregistré.
3. Chaque étape garde sa date effective, sa précision (date connue, approximative ou heure
   connue), son fuseau et sa date de saisie. Elle apparaît dans le journal et se corrige comme
   toute autre entrée, ses versions précédentes conservées.
4. La date doit être strictement antérieure au début du stade courant : à date égale, l'ordre du
   parcours serait ambigu. Une chronologie impossible ou un conflit d'occupation de l'espace 2
   est refusé en bloc — aucune étape n'est écrite et le formulaire conserve la saisie.
5. Après enregistrement, le stade courant et son compteur sont inchangés ; l'attribution des
   solutions et arrosages est recalculée selon les dates d'occupation corrigées.

Le parcours affiche la durée de chaque période, en jours calendaires du fuseau du carnet, avec
la même convention que les compteurs. La période en cours est comptée jusqu'à aujourd'hui.

## Conduire le parcours

Ouvrir la fiche du lot pour déclarer un nouveau stade, déplacer l'ensemble ou noter une perte.
Un transfert conserve le stade et sa date de début. Les parcours progressent dans cet ordre :

- Semis : germination, végétatif, floraison, séchage.
- Boutures : enracinement, végétatif, floraison, séchage.
- Mères : maintien, notes et prélèvements (création des lots descendants), puis archivage.

Une perte diminue l'effectif restant, jamais l'effectif initial. L'origine de la perte est
facultative ; aucune répartition des survivants entre mères n'est inventée si elle est inconnue.
La même mère ne peut pas apparaître deux fois dans les origines d'un lot : regrouper son effectif.

L'espace 1 peut accueillir les mères et leurs descendants. Un seul lot occupe l'espace 2 sur
une période donnée. Cette règle est vérifiée aussi lors des corrections de dates anciennes.

## Récolter et terminer

L'action **Récolte** enregistre la coupe du lot entier et le début du séchage dans l'espace 2.
Vérifier séparément l'éclairage, la pompe Cyclic 1 et la ventilation principale commune.
Aucun équipement n'est commandé par la fiche de culture.

**Fin du séchage** enregistre le bilan et le poids sec total facultatif (grammes, virgule acceptée).
Cocher la libération uniquement si le lot a été retiré. Sinon il est archivé mais l'espace reste
occupé ; l'action **Libération** reste disponible depuis sa fiche. La durée de séchage est figée
à sa date de fin. L'archivage d'une mère ne supprime jamais ses liens avec ses descendants.

## Notes, corrections et erreurs

Les notes sont datées, peuvent être rétrospectives et acceptent plusieurs lignes. Depuis une
entrée du journal, ouvrir **Corriger cette entrée** pour ajuster date, contenu ou annuler une
erreur. Les anciennes versions restent consultables et exportées ; le motif est facultatif.
Une correction qui rend le parcours incohérent est refusée en entier.

La correction de l'origine permet de changer sa date, une mère attribuée par erreur ou un effectif
initial mal saisi ; les anciennes valeurs restent dans les révisions. Les pertes réelles ont leur
action dédiée. Le changement de nom ou de variété se fait avec **Identité**, également historisé.
Aucun effacement de culture n'est proposé.

Un autre onglet peut rendre la fiche périmée. Le serveur refuse alors d'écraser la nouvelle
version ; la saisie reste visible et un lien ouvre la fiche actualisée dans un nouvel onglet.
Si une réponse réseau est perdue, réessayer **sans changer les champs** : la même clé de requête
permet de retrouver l'enregistrement au lieu de le dupliquer. Ne pas fermer la page contenant
une saisie non confirmée. Aucun formulaire n'est enregistré ou envoyé automatiquement hors ligne.

Dans la PWA, les pages du carnet déjà consultées peuvent être relues après un échec réseau,
avec leur date de capture et une bannière de lecture seule. Le cache est borné à 20 pages et
40 photos consultées, avec 4 Mio maximum par réponse ; leur disponibilité hors ligne dépend
du stockage du navigateur. Les formulaires restent désactivés et aucune commande n'est rejouée.
Recharger après reconnexion pour actualiser les fiches et les compteurs. Le résumé du tableau se rafraîchit chaque minute quand il est visible.

## Export et sauvegarde

La section en bas de page concerne le carnet complet, archives et révisions comprises :

- CSV : journal exploitable dans un tableur, avec dates, précision et détails JSON par événement.
- JSON versionné : toutes les tables et relations, destiné à l'interopérabilité et au diagnostic.
- SQLite : sauvegarde restaurable créée avec l'API de sauvegarde SQLite, cohérente avec le WAL.

Le bouton **Télécharger la sauvegarde complète ZIP** inclut aussi les photos et un manifeste
d’empreintes SHA-256. Une base SQLite seule ne contient pas les fichiers photo ; sa restauration
est refusée si elle en référence. JSON et CSV restent des exports, sans import automatique.

Conserver régulièrement une sauvegarde complète ZIP hors du Pi et impérativement avant une migration
de schéma. Le fichier vivant est `param/cultures.sqlite3` avec ses annexes `-wal` et `-shm`.
Git les ignore. Le script de déploiement ne remplace pas une sauvegarde du carnet.

Exercice de restauration vers une copie **nouvelle**, avec des chemins explicitement choisis :

```bash
.venv/bin/python scripts/restore-cultures.py /tmp/cultures.sqlite3 /tmp/carnet-verifie.sqlite3
```

L'outil vérifie version, intégrité SQLite, références et règles métier, puis publie une copie
avec permissions 0600. Il refuse le chemin du carnet actif et toute destination existante.
Il ne modifie ni la source ni le contrôleur. Une erreur ne déclenche aucune base vide de remplacement.

Pour une restauration effective, préparer d'abord cette copie, prévoir une fenêtre d'exploitation,
arrêter le service selon la procédure opérationnelle existante, conserver l'ensemble du carnet
actuel et de ses annexes sous un nom de sauvegarde, puis faire installer explicitement la copie
vérifiée avec le propriétaire approprié. Ne jamais écraser un fichier SQLite ouvert ni lui laisser
les annexes WAL d'une autre base. Le script fourni réalise uniquement la vérification sur copie.

## Limites du périmètre livré

Le suivi concerne des lots entiers. Il n'y a ni fractionnement, ni récolte partielle, ni classement
des mères par performance. Les affectations matérielles confirmées restent fixes dans les vues ;
le catalogue courant des équipements est copié dans chaque événement lors de sa saisie pour
garder les noms/usages connus à ce moment. Cela ne reconstitue pas une affectation matérielle
ancienne à partir d'une date d'intervention rétrospective.

Une panne du carnet est signalée dans ses pages, mais ne modifie jamais la santé du contrôle
ni le watchdog. Une corruption ou un schéma futur est conservé, puis refusé.


## Routine quotidienne : solutions et relevés

Depuis une fiche de culture, **Solutions, relevés et arrosages** ouvre le carnet filtré sur cette
culture. Depuis le tableau de bord, **Saisir un relevé** préremplit le réservoir de l'espace.
La page `/cultures/solutions` présente les deux bacs, la date et l'âge de leur solution,
les cultures alimentées, une saisie rapide, puis le journal, les courbes et les recettes.

Pour reprendre une solution déjà en service, choisir **Renouvellement**, sa date connue ou
approximative et son volume. Les produits sont facultatifs si le mélange initial est inconnu.
Cela ouvre la période suivie : il n'est pas nécessaire d'attendre le prochain changement d'eau.

Pour un relevé quotidien, choisir la cible et saisir **pH et/ou EC**. Les dernières valeurs restent
à côté avec leur date et un âge indicatif, mais les champs sont vides. La virgule est acceptée.
Choisir mS/cm ou µS/cm selon l'instrument ; le carnet stocke l'EC en mS/cm. Les ppm/TDS ne sont
pas convertis. Température de solution, volume observé, compensation par l'instrument et note
sont facultatifs. Plusieurs relevés par jour et les saisies rétrospectives sont possibles.

Pour renouveler, faire un appoint, ajouter des nutriments ou corriger le pH, sélectionner l'action.
Un renouvellement commence une nouvelle période ; les autres interventions conservent la solution.
Le volume d'un appoint est le volume **ajouté**, celui d'un renouvellement le volume **préparé**.
Les mesures saisies avec l'intervention peuvent être marquées **Après intervention**. Pour suivre
l'avant/après, enregistrer aussi un relevé distinct et choisir l'intervention associée.
Deux renouvellements le même jour nécessitent une heure pour les distinguer.

Pour arroser les mères, choisir **Arrosage**, la première mère, puis déplier **Autres mères**.
Renseigner le volume total distribué si connu. Ce volume reste commun : le carnet n'affirme pas
que chaque mère a reçu ce total. Le bac de bouturage n'attribue jamais automatiquement ses
mesures aux mères, qui sont arrosées manuellement.

## Réutiliser une recette

Dans **Recettes réutilisables**, créer un nom, un volume de référence et les produits avec leurs
quantités et unités. Lors d'une préparation, choisir cette recette et renseigner le volume prévu.
Le carnet affiche les quantités proportionnelles ; vérifier puis cocher la confirmation avant
l'enregistrement. Une modification de recette crée une nouvelle version. Les anciennes
préparations gardent leurs ingrédients, doses et unités ; aucune conversion masse/volume n'est faite.

## Lire et corriger l'historique des solutions

Les filtres portent sur la cible, le type et la période. Les courbes pH et EC sont séparées,
avec le même axe temporel, des points sans interpolation et les repères d'interventions/stades.
Les ruptures de renouvellement restent explicites. Au-delà de 1 000 entrées filtrées, les moyennes
journalières affichent leur étendue min/max et leur nombre de mesures, séparément pour chaque
solution et cible. Les détails sont accessibles au survol et dans le journal ; les repères ont
une liste textuelle. L'affichage est limité à 2 000 groupes récents, avec indication visible ;
réduire la période ou exporter pour aller au-delà. Aucune donnée n'est purgée par cette limite.

**Corriger cette saisie** permet de modifier date, mesures, ingrédients ou d'annuler une erreur.
L'ancienne révision reste consultable. Une correction incompatible avec un relevé avant/après
est refusée entièrement ; corriger d'abord les liens concernés. Les associations aux lots sont
recalculées à partir de leur occupation effective. Après la coupe, les mesures de solution
n'apparaissent plus comme alimentation du lot en séchage. Un nouveau lot ne récupère pas les
relevés de son prédécesseur, même lorsque la solution n'a pas été renouvelée entre les deux.

Après succès, la page ouvre l'entrée, même rétrospective. En cas d'échec, garder la page ouverte
et réessayer sans modifier la saisie pour vérifier le même enregistrement. La reconnexion ne
rejoue rien. Les courbes sont descriptives et ne proposent aucun diagnostic ou dosage.

### Relevés liés à une intervention ancienne

Le sélecteur **Intervention associée** propose les 200 interventions les plus récentes et,
toujours, celle déjà associée au relevé corrigé, même vieille de centaines de saisies. Corriger
seulement le pH ou la note conserve donc le lien et son contexte avant/après ; le retirer demande
de choisir explicitement « Sans lien ».

Pour une saisie rétrospective, le champ **Retrouver une intervention ancienne** cherche par type,
date, cible ou référence, et les boutons **Plus récentes** / **Plus anciennes** parcourent la
liste par 200. Le nombre de résultats et la tranche affichée sont annoncés sous le champ. Si la
recherche n'aboutit pas (réseau), l'association en cours reste conservée dans le formulaire.

Dans le journal, le lien **Intervention …** d'un relevé ouvre l'intervention même si elle n'est
pas sur la page courante ou est exclue par les filtres : il rouvre le journal sans filtre à la
bonne page.

Le bouton **Exporter les relevés et interventions CSV du filtre** produit des colonnes avec
unités explicites, préparation, cibles et notes. Il conserve une ligne par saisie commune,
annulations comprises. Les anciennes révisions sont dans l'export complet JSON/SQLite.

## Migration du jalon 1 au jalon 2

La première ouverture d'une base de schéma 1 crée automatiquement
`param/cultures.sqlite3.before-v2.sqlite3` par l'API SQLite, puis migre en une transaction.
Cette copie est ignorée par Git, comme le carnet actif ; en conserver une copie hors du Pi.
Une sauvegarde préalable déjà présente n'est jamais écrasée. Si une tentative a été interrompue
et que la base est encore en version 1, faire vérifier/restaurer cette sauvegarde vers une copie
isolée avec le script ci-dessus, conserver les fichiers de diagnostic, puis résoudre la tentative
avant de relancer l'ouverture. Aucun fichier corrompu n'est remplacé par une base vide.

Le code du jalon 1 refuse une base de version 2. Un retour arrière du code nécessite donc une
restauration **explicite et supervisée** de la sauvegarde antérieure et perdrait les saisies du
jalon 2 absentes de cette copie. Exporter/sauvegarder d'abord le carnet actuel. Aucun déploiement
ou remplacement du carnet de production n'est effectué par les validations automatisées.


## Photos d'un événement

Sur la fiche d'une mère ou d'un lot, ouvrir l'ajout de photo sous l'événement concerné,
choisir le fichier, ajouter une légende facultative puis enregistrer. La photo reste liée à
la révision de cet événement ; corriger le journal n'efface pas l'image passée. Le journal
paginé donne accès aux photos anciennes, même au-delà des 100 images de la galerie des cycles.

Les formats acceptés sont JPEG, PNG et WebP non animés : 5 Mio par envoi, 20 mégapixels et
8 192 pixels par côté au maximum, quatre photos par événement. Le serveur vérifie le contenu,
redresse l'orientation puis crée un JPEG de 1 600 pixels maximum sans métadonnées incorporées.
Le fichier original n'est pas conservé. Les légendes restent dans le carnet et ses exports.

Le budget global est de 256 Mio et 5 000 photos avec une réserve disque de 128 Mio.
En cas de refus, aucune ancienne photo n'est supprimée pour faire de la place. L'état du stockage
est visible en bas de **Cycles et rappels**. Une réponse perdue ne prouve pas un échec : garder
le fichier et les champs sélectionnés puis réessayer la même saisie pour éviter un doublon.

## Rappels et vérifications

Dans `/cultures/cycles`, ouvrir **Créer un rappel**, choisir la culture ou le réservoir,
le titre et l'échéance. Une récurrence de zéro signifie ponctuel ; sinon saisir de 1 à 366 jours.
Les états sont **Prévu**, **Reporté**, **Fait** et **Annulé**, avec historique des changements.
Un report exige une échéance ultérieure. Marquer un rappel récurrent fait crée une seule
prochaine occurrence, calculée depuis la date réelle d'accomplissement. Annuler ne crée rien.

![Rappels sur écran étroit, avec données de démonstration](../images/cultures-jalon3-rappels-mobile.png)

Les rappels s'affichent dans cette page ; ils ne produisent aucune notification système.
Un rappel clos reste consultable. Une nouvelle tentative identique ne crée pas de deuxième
occurrence ; une modification depuis un onglet périmé reçoit un conflit.

Pour un lot sélectionné, la liste des équipements renvoie aux réglages existants de son espace
et de la ventilation commune. Elle s'ouvre lors du séchage si aucune vérification n'existe.
Enregistrer la date, les cases vérifiées et une note conserve le stade et l'espace déclarés
à cet instant. Les cases ne commandent aucun équipement et ne constituent pas une preuve
électrique. La date du changement de stade peut être utilisée même si celui-ci est horodaté.

## Lire et comparer les cycles

Sélectionner jusqu'à quatre cultures dans **Comparer les cycles**, puis afficher les cycles.
La vue rassemble parcours datés, effectifs, bilan, statistiques pH/EC et climat commun à la serre.
Le bilan de fin de séchage accepte des enseignements pour le prochain cycle et des poids secs
facultatifs par origine ; leur somme ne peut pas dépasser le total lorsqu'il est renseigné.
Les mesures détaillées restent accessibles dans les solutions contextualisées.

![Comparaison et accès au carnet sur bureau, données de démonstration](../images/cultures-jalon3-cycles-bureau.png)

Le service de culture prélève chaque minute une copie des acquisitions existantes, sans lire
les capteurs. Seules les valeurs activées, finies et de qualité normale contribuent au minimum,
maximum et à la moyenne. Une absence ou une mesure dégradée compte comme une minute observée
sans valeur fiable ; zéro reste une vraie valeur. Le statut du snapshot inclut sa fraîcheur.

Les agrégats horaires survivent à la purge de l'historique technique et aux redémarrages.
La couverture est le nombre de minutes fiables divisé par 60, y compris pour une heure partielle.
Les heures au bord d'un cycle peuvent inclure des minutes extérieures à celui-ci.
Aucune donnée antérieure à l'activation n'est reconstituée. Une horloge non fiable suspend la
synthèse. Les courbes restent descriptives, sans dosage ni diagnostic causal automatique.

### Cycles longs : synthèse complète et détail horaire

La courbe et le tableau ne montrent plus « les derniers points » : la synthèse couvre **tout**
le cycle, à un pas choisi d'après sa durée — heure, jour, semaine ou quatre semaines — de façon
que le nombre de périodes affichées reste borné. Le pas retenu est écrit en toutes lettres au
dessus de la courbe, avec le nombre de périodes et le nombre de périodes sans agrégat.

Les périodes sont alignées sur l'horloge **UTC** (un « jour » est un jour UTC), comme la clé
horaire des agrégats : un changement d'heure ne déplace donc aucune période et ne crée pas de
journée de 23 ou 25 heures. Les périodes du tout début et de la toute fin du cycle ne comptent
que leurs heures comprises dans le cycle ; leur couverture est calculée sur ce nombre d'heures.

La moyenne d'une période vient des sommes et des effectifs fiables, jamais d'une moyenne de
moyennes horaires : une heure avec une seule minute fiable ne pèse pas autant qu'une heure
complète. Une période sans agrégat reste une **lacune** : elle est marquée d'un trait sous l'axe
et d'aucun point, jamais d'un zéro. Chaque capteur garde sa propre courbe.

Le tableau **Détail horaire paginé** donne les agrégats heure par heure, 60 par page, avec le
nombre total conservé en base. Seule la page affichée est chargée : la page de cycles ne
contient plus des milliers de lignes. Le détail n'apparaît que si **une seule** culture est
sélectionnée ; en comparaison de deux à quatre cycles, chaque synthèse indique sa granularité et
propose un lien pour ouvrir le détail d'une culture. Les agrégats anciens ne sont jamais
supprimés par ces affichages, et la sauvegarde complète continue de tout conserver.

### Consulter un cycle hors ligne

Le carnet reste **réseau d'abord** : une page datée n'est relue qu'après un échec réseau. Le bloc
**Pages du carnet conservées hors ligne** liste les pages du carnet réellement conservées avec
leur date de conservation ; une page de détail horaire y figure avec le premier agrégat qu'elle
montre. Les limites existantes sont inchangées : au plus 20 pages du carnet et 4 Mio par page,
40 photos consultées, et aucune donnée d'`/api/` mise en cache.

Sont conservées **les pages effectivement visitées** : la synthèse d'un cycle si elle a été
ouverte, et chaque page de détail horaire réellement consultée. Hors ligne, un lien vers une page
non conservée est barré et suivi de « non conservé hors ligne » ; il ne tente aucune requête.
La synthèse affichée hors ligne est celle de la dernière visite et couvre la même période qu'alors ;
sa date figure dans la bannière « HORS LIGNE — données datant de… — lecture seule ». Aucune
saisie n'est mise en attente ni rejouée, et le carnet ne déclenche aucune notification système.

## Restaurer une sauvegarde complète sur copie

Télécharger le ZIP et le conserver hors du Pi, puis choisir un dossier de destination inexistant :

```bash
.venv/bin/python scripts/restore-cultures.py --bundle /tmp/cultures-complet.zip /tmp/carnet-verifie
```

L'outil contrôle le manifeste, les tailles, chemins, empreintes, références SQLite et images,
puis crée `cultures.sqlite3` et `culture_media/` ensemble dans cette nouvelle destination.
Il refuse toute destination existante et le répertoire du carnet actif. Un arrêt pendant la
publication peut laisser `.restauration-incomplete` : cette copie ne doit pas être utilisée ;
conserver le diagnostic et recommencer vers un autre dossier neuf.

L'exercice automatisé `test_photos_idempotence_limite_evenement_et_sauvegarde` crée quatre photos,
exporte un ZIP, restaure une copie, la rouvre et compare toutes les tables ainsi que les octets
d'une photo. Il exécute aussi l'outil en ligne de commande sur une seconde destination.
Les archives altérées, incomplètes et contenant un chemin extérieur sont refusées.
Cela vérifie la restauration sur copie ; le remplacement du carnet actif reste une opération
supervisée selon la procédure précédente, avec la base **et** son répertoire de médias.

## Migration vers le jalon 3

À l'ouverture d'un carnet de version 2, une copie cohérente
`cultures.sqlite3.before-v3.sqlite3` est créée avant la migration transactionnelle en schéma 3.
Depuis la version 1, les deux migrations et leurs sauvegardes sont successives. Une sauvegarde
préalable existante n'est jamais écrasée. Le schéma 3 ajoute photos, rappels, vérifications et
agrégats ; les anciennes versions du code ne peuvent pas l'ouvrir. Sauvegarder le carnet complet
avant tout retour arrière : restaurer une ancienne copie perdrait les saisies ultérieures.

## Migration vers le schéma 4

À l'ouverture d'un carnet de version 1, 2 ou 3, une copie cohérente
`cultures.sqlite3.before-v4.sqlite3` est créée avant la migration transactionnelle. Depuis une
version plus ancienne, les sauvegardes `.before-v2.sqlite3`, `.before-v3.sqlite3` et
`.before-v4.sqlite3` sont produites successivement. La migration conserve toutes les
vérifications (elles deviennent la révision 1 d'une ligne versionnée), toutes les photos et
tous les relevés ; elle ne crée aucune plage cible, aucun repère d'éclairage et aucune
affectation d'équipement. Les anciennes versions du code ne peuvent pas ouvrir un carnet de
schéma 4 : sauvegarder l'ensemble avant tout retour arrière.

### Lever une sauvegarde `.before-v4` après migration interrompue

Une coupure pendant la migration laisse la base **intacte en version 3** et la sauvegarde
`cultures.sqlite3.before-v4.sqlite3` sur le disque. Au redémarrage suivant, le carnet refuse de
démarrer avec « Sauvegarde avant migration déjà présente ; vérifier cette copie avant de
réessayer. » C'est voulu : une tentative précédente doit être arbitrée par une personne, pas
écrasée en silence. La régulation, elle, n'est pas affectée — le carnet ne participe pas au
watchdog et `control_healthy()` reste vrai.

1. Arrêter le service : `sudo systemctl stop phyto`.
2. Constater l'état réel des deux fichiers, sans les modifier :
   `sqlite3 param/cultures.sqlite3 'PRAGMA user_version; PRAGMA quick_check;'` puis la même
   commande sur `param/cultures.sqlite3.before-v4.sqlite3`. Le carnet actif doit être en
   version 3 et la sauvegarde en version 3 également.
3. Copier la sauvegarde hors de `param/` (clé USB, poste d'exploitation) et la vérifier sur une
   destination isolée : `python3 scripts/restore-cultures.py <copie> /tmp/verification.sqlite3`.
   Cette commande ne touche jamais le carnet actif.
4. Comparer les volumes attendus (cultures, événements, relevés, vérifications, photos) entre le
   carnet actif et la copie vérifiée. Si le carnet actif est le plus complet, il est la référence.
5. Seulement alors, retirer la sauvegarde du répertoire de travail :
   `sudo mv param/cultures.sqlite3.before-v4.sqlite3 <archive hors serre>`. Ne jamais la
   supprimer sans en conserver une copie ailleurs.
6. Relancer : `sudo systemctl start phyto`. La migration reprend depuis le début, produit une
   nouvelle sauvegarde `.before-v4.sqlite3` et aboutit.

Si l'étape 2 montre un carnet actif déjà en version 4, la migration avait abouti : il ne reste
qu'à archiver la sauvegarde. Si `quick_check` n'est pas « ok », ne pas relancer le service :
restaurer une sauvegarde vérifiée selon la procédure de restauration sur copie ci-dessus.

Les captures de ce guide proviennent de la base temporaire des tests navigateur ; elles ne
montrent aucune donnée d'exploitation. Le jalon est validé hors matériel, sans déploiement Pi.
