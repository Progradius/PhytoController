# Carnet de cultures — livraisons 1 et 2

Le menu **Cultures** ouvre `/cultures`. Sur téléphone, il se trouve dans **Plus** ; le tableau
de bord comporte aussi un résumé des deux espaces et un accès au carnet.

Le carnet conserve les données sans purge automatique, indépendamment de l'historique technique
de 72 h. Ses actions ne changent ni horaires, ni pompe, ni ventilation. Les réglages continuent
de se faire dans **Configuration**. Les relevés pH/EC, solutions, arrosages et recettes sont disponibles dans **Solutions, relevés et arrosages**. Les photos et rappels appartiennent au jalon 3.

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

Le carnet de cette livraison ne dispose pas encore de snapshots PWA pour ses fiches. Une page
déjà ouverte peut rester visible après une coupure, mais elle est ancienne ; la bannière PWA
et la désactivation des formulaires s'appliquent. Recharger après reconnexion pour actualiser
les fiches et les compteurs. Le résumé du tableau se rafraîchit chaque minute quand il est visible.

## Export et sauvegarde

La section en bas de page concerne le carnet complet, archives et révisions comprises :

- CSV : journal exploitable dans un tableur, avec dates, précision et détails JSON par événement.
- JSON versionné : toutes les tables et relations, destiné à l'interopérabilité et au diagnostic.
- SQLite : sauvegarde restaurable créée avec l'API de sauvegarde SQLite, cohérente avec le WAL.

Conserver régulièrement une sauvegarde SQLite hors du Pi et impérativement avant une migration
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
