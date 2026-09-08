# Plan — Gestion des cultures et carnet d'exploitation

Date : 7 septembre 2026.
Statut : besoin validé avec l'exploitant ; livraisons 1 à 3 implémentées sur
`feature/gestion-cultures`, vérifiées hors matériel, non déployées. Jalon 3 finalisé le 8 septembre 2026.
Ce document ne constitue pas une autorisation de déploiement.

## 1. Objectif et décisions validées

Compléter la conduite mécanique de la serre par le suivi des plantes : origines, stades,
durées, occupation des espaces, solutions nutritives, interventions, mesures et bilan de culture.
Le carnet doit remplacer le carnet papier et rester utilisable rapidement sur téléphone.

Décision centrale : **les stades sont déclaratifs et ne commandent aucun équipement**.
Passer en végétatif, en floraison ou en séchage ne modifie ni les horaires, ni les sorties,
ni la ventilation, ni les overrides. Les réglages restent dans la configuration existante.
Les propositions initiales d'application automatique ou planifiée de profils sont abandonnées
pour ce périmètre ; elles ne constituent pas un jalon futur implicitement autorisé.

Décisions fonctionnelles retenues :

- Deux espaces, associés respectivement aux éclairages 1 et 2.
- Pieds mères identifiés individuellement, conservés dans l'espace 1 et arrosés à la main.
- Un lot de semis ou de boutures se déplace, change de stade et se récolte dans son ensemble.
- Un lot de boutures peut provenir de plusieurs pieds mères ; conserver chaque origine et
  son effectif sans imposer une fiche individuelle à chaque bouture.
- Les semis et boutures commencent dans l'espace 1, puis le lot entier passe dans l'espace 2.
- L'espace 2 utilise un réservoir commun au lot. La coupe est suivie d'un séchage dans ce même
  espace, qui reste occupé jusqu'à sa libération explicite.
- Dans l'espace 1, les usages décrits sont les pieds mères arrosés manuellement, les semis et
  le bac unique de bouturage. Ne pas déduire une capacité physique ou une exclusion automatique
  entre mères et descendants : afficher l'occupation déclarée et permettre leur coexistence.
- Les références 18 h / 6 h en végétatif et 12 h / 12 h en floraison sont des repères de
  l'exploitation, modifiables et informatifs ; aucune prescription universelle n'est codée.
- Compteurs en jours et semaines, dates de début consultables, parcours conservé.
- Relevés, interventions, recettes réutilisables, notes, photos facultatives, rappels,
  courbes contextualisées, archives, export et sauvegarde font partie du périmètre retenu.
- L'analyse comparative détaillée des performances par pied mère reste ouverte pour une
  version ultérieure. Conserver la provenance dès la première version.

### Correspondance matérielle confirmée

| Identifiant existant | Affectation métier |
| --- | --- |
| `daily_1` | Éclairage de l'espace 1 |
| `daily_2` | Éclairage de l'espace 2 |
| `cyclic_1` | Pompe du réservoir de l'espace 2 |
| `cyclic_2` | Ventilation locale OU pompe du bac de bouturage de l'espace 1 |
| `motor` | Ventilation principale partagée entre les deux espaces |

La ventilation locale éventuelle sur `cyclic_2` est distincte de la ventilation principale.
Les affectations sont des métadonnées, jamais une modification de câblage. Conserver leurs
périodes de validité pour comprendre les anciennes interventions après une réaffectation.
Réutiliser les identifiants de `param/equipment_metadata.py`, sans créer de registre concurrent
des noms actuels : les noms courants restent détenus par ce magasin, le carnet garde l'historique
de ses associations et un libellé au moment de l'événement.

## 2. Modèle métier et règles

### Espaces, pieds mères et lots

Un espace représente un emplacement ; il ne représente ni une génération de plantes ni un stade.
Un pied mère a un identifiant stable, un nom distinct, une variété facultative, une date d'origine
éventuellement approximative, une date d'entrée en maintien et un état actif ou archivé.
Son archivage ne supprime pas les liens avec les lots descendants.

Un lot porte un identifiant stable, un nom, un type d'origine (semis/boutures), un effectif initial,
un effectif courant, un parcours de stades et un historique d'occupation. Sa provenance comporte
une ou plusieurs lignes : mère identifiée ou origine de semences, effectif et détails facultatifs.
Une création à partir de plusieurs mères est une seule opération atomique.

Exemple de référence : « Lot septembre », trois boutures de Mère A et cinq de Mère B.
Huit plantes, deux origines, un compteur de stade, un transfert et une récolte communs.
Une perte est enregistrée avec sa date, son nombre, son motif facultatif et son origine si connue.
Elle change l'effectif courant sans effacer l'effectif initial. L'origine inconnue est admise ;
ne pas inventer une répartition des survivants entre mères.

Le fractionnement en sous-lots, les transferts partiels et les récoltes échelonnées ne sont pas
nécessaires à cette version. L'interface expose des opérations sur le lot entier. Un modèle avec
identifiants et relations explicites permettra une extension sans l'implémenter dès maintenant.

### Parcours et compteurs

Parcours proposés, avec saut d'étapes possible lors de la reprise d'une culture existante :

- Semis : germination → végétatif → floraison → séchage → terminé.
- Boutures : enracinement → végétatif → floraison → séchage → terminé.
- Pieds mères : maintien, prélèvements successifs, puis archivage.

Le prélèvement ou le semis, l'entrée dans un espace et le début d'un stade sont des événements
distincts. Un formulaire peut les enregistrer ensemble lorsque leurs dates coïncident.
Un transfert ne change pas le stade par défaut. Le nom « végétatif » ne signifie pas que
l'éclairage a effectivement fonctionné 18 heures.

Convention d'implémentation proposée : J0 à la date locale de début, J1 à la date locale suivante.
Afficher « Floraison · J23 · 3 semaines + 2 jours · semaine 4 en cours », avec date de début.
Il s'agit d'un âge calendaire, pas d'un nombre de périodes complètes de 24 h ; le préciser dans
l'aide. Stocker l'instant en UTC lorsqu'il est connu, le fuseau de l'exploitation et la précision
(`instant`, `date`, `approximative`). Une date seule ne doit pas devenir un horaire prétendument exact.
Les semaines complètes valent `jours // 7`, le reste `jours % 7`, la semaine en cours vaut
`jours // 7 + 1`. Tests indispensables autour de minuit et des changements d'heure.

Ne pas incrémenter un compteur quotidien : le calculer depuis les dates persistées.
Un redémarrage ne remet rien à zéro. Si l'heure du Pi n'est pas fiable, signaler le compteur
comme non fiable ; ne pas enregistrer silencieusement une date système douteuse.
À l'archivage, la durée du dernier stade est figée par sa date de fin.

Les transitions ont une date effective et une date de saisie distinctes. Une correction conserve
l'ancienne version, revalide la chronologie et recalcule les durées. Pas de stade courant futur
ni de transitions planifiées dans cette version ; utiliser une tâche de rappel pour une intention.

### Récolte, séchage et libération

« Récolter et commencer le séchage » enregistre la coupe du lot entier et ouvre le séchage,
avec dates distinctes si nécessaire. Le lot reste dans l'espace 2. Les éventuelles mesures de
solution postérieures ne lui sont plus attribuées comme alimentation active après la coupe.

« Terminer le séchage » clôt le stade et propose un bilan : poids sec total facultatif,
détail facultatif par origine, observations et enseignements pour le prochain cycle.
Proposer dans la même action « libérer l'espace », sans supposer que la fin du séchage signifie
que le matériel ou les plantes ont déjà été retirés. L'archivage conserve toutes les données.

### Réservoirs, préparations et recettes

Distinguer trois notions :

- Réservoir : contenant physique stable et affectation à un espace.
- Période de solution : contenu suivi entre deux renouvellements complets.
- Préparation : mélange daté, utilisé pour remplir un bac ou arroser manuellement des mères.

Une recette est un modèle réutilisable, avec nom, volume de référence, produits et doses.
Une préparation conserve une copie de ses ingrédients et quantités : modifier une recette plus
tard ne réécrit pas les interventions passées. Les unités sont explicites (`L`, `mL`, `g`, etc.).
Une multiplication proportionnelle selon le volume doit montrer les quantités avant validation ;
aucune conversion masse/volume sans donnée explicite, aucune recommandation automatique de dosage.

L'espace 2 comporte un réservoir partagé et une seule période de solution active à un instant.
Le bac de bouturage de l'espace 1 peut avoir sa propre période de solution. Les arrosages manuels
peuvent viser plusieurs mères en une saisie, liée à une préparation commune ; ne pas attribuer
à chaque mère le volume total comme si elle l'avait reçu seule.

Un renouvellement ferme l'ancienne période et ouvre la nouvelle dans une transaction. Un appoint
d'eau, un ajout de nutriments ou une correction pH reste dans la période existante.
Les liens entre solution et lot sont datés ; un changement de lot ne lui attribue pas les relevés
de son prédécesseur. Ne pas inventer un renouvellement parce qu'un lot a changé d'espace.

## 3. Carnet quotidien et visualisation

### Actions rapides

| Action | Données principales |
| --- | --- |
| Relever | Cible, date effective, pH et/ou EC, température/volume facultatifs, contexte avant/après intervention |
| Arroser | Mères ou lot concernés, préparation facultative, volume connu, note |
| Renouveler la solution | Réservoir, volume, ingrédients et quantités, pH/EC après préparation facultatifs |
| Faire un appoint ou corriger | Réservoir, type d'intervention, produit/quantité, mesures associées facultatives |
| Observer | Lot ou mère ou espace, texte, photos facultatives |
| Changer de stade / déplacer | Lot, date effective, nouvelle étape ou destination, commentaire facultatif |
| Récolter / terminer | Coupe, séchage, bilan et libération de l'espace |

La cible et la date courante sont préremplies ; pH et EC ne le sont jamais avec les dernières
mesures. Afficher celles-ci à côté avec leur âge. Autoriser la saisie d'une seule mesure,
plusieurs relevés par jour et une saisie rétrospective. Accepter la virgule décimale française.
Séparer valeur manquante et zéro, refuser NaN/infini et incohérences d'unités.
Stocker l'EC en mS/cm ; convertir explicitement une saisie en µS/cm (division par 1 000).
Ne pas convertir implicitement du TDS/ppm en EC. La compensation de température est une
information de l'instrument si renseignée, jamais une correction inventée par l'application.

La saisie rapide habituelle doit se faire sur téléphone dans un seul formulaire court.
Les détails de préparation n'encombrent pas le formulaire quotidien. Après succès, montrer
l'entrée enregistrée ; en cas d'échec, garder les champs et annoncer que rien n'est confirmé.

### Écrans prévus

- Tableau de bord actuel : résumé compact des deux espaces, occupants, stade et compteur,
  dernier relevé daté, raccourci de saisie ; préserver la lisibilité des alarmes de contrôle.
- `/cultures` : occupation des espaces, lots actifs, pieds mères et accès aux archives.
- Fiche lot : parcours, origines/effectifs, journal, courbes, solution liée et bilan.
- Fiche mère : identité, âge, maintien, arrosages, observations et lots descendants.
- Fiche réservoir : solution actuelle, âge, préparation, relevés et interventions précédentes.
- Carnet filtrable par période, cible et type ; archives consultables avec export.
- Recettes et rappels : écrans secondaires, accessibles depuis les actions correspondantes.

Les chemins détaillés seront adaptés aux conventions du serveur pendant l'implémentation.
Utiliser des identifiants stables dans les URL, pas les noms modifiables des plantes.

### Équipements et listes de vérification

Afficher ensemble stade déclaré, horaires réellement configurés et état opérationnel existant.
Présenter ventilation principale comme commune. Montrer les règles jour/nuit existantes quand
elles sont pertinentes, sans les assimiler au stade d'un lot ni les recalculer depuis celui-ci.
Un GPIO relu ne prouve pas à lui seul le fonctionnement physique d'une lampe ou d'une pompe.

Au passage en séchage, proposer une liste de vérification : éclairage, pompe, ventilation.
Chaque ligne mène aux réglages existants ; aucune case ni validation de stade n'agit sur une sortie.
Un écart au repère du stade est une information, pas une nouvelle alarme de contrôle bloquante.

### Courbes, rappels et bilan

Tracer pH et EC dans des graphiques séparés alignés dans le temps, avec repères des appoints,
renouvellements, corrections et stades. Montrer les points mesurés, les unités et les lacunes.
Ne pas lisser une rupture de renouvellement ni présenter une interpolation comme une mesure.
Relier les mesures avant/après à l'intervention correspondante lorsque ce lien est connu.

Les tendances restent descriptives : l'EC ne mesure pas la composition détaillée des nutriments.
Les plages cibles sont facultatives, définies par l'exploitant et historisées avec leur contexte.
Pas de diagnostic causal ni de dosage automatique à partir de pH/EC seuls.

Rappels configurables : relevé attendu, renouvellement à vérifier, opération ponctuelle ou
récurrente. États prévus/faits/reportés/annulés ; un rappel n'est jamais une commande.
Leur affichage dans l'application constitue le service de base. Conserver la règle PWA actuelle
qui réserve les notifications système aux alarmes de contrôle/critiques ; ne pas promettre de
notification de carnet application fermée. Une extension de cette règle nécessiterait un choix futur.

Conserver des synthèses climatiques à long terme à partir des snapshots existants : agrégats
horaires avec minimum, maximum, moyenne, nombre de valeurs valides et couverture observée.
Les mesures communes à la serre doivent rester étiquetées communes, sans inventer des capteurs
par espace. Les périodes de panne ou de valeurs non fiables ne deviennent pas des zéros.
Présenter ces agrégats sur la durée du cycle et une comparaison simple des cycles (durées,
mesures et bilan disponible). Aucune reconstitution garantie des données déjà purgées à 72 h.
L'analyse des performances par mère reste différée.

## 4. Persistance et intégration technique

### Constats du dépôt au moment du plan

- `model/DailyTimer.py` consomme les deux configurations indépendantes via le magasin partagé.
- `controllers/OperatorService.py` propose déjà `record_operator_note()`.
- `utils/operator_history.py` conserve les échantillons et événements 72 h ; sa purge supprime
  aussi les notes opérateur. Les alarmes résolues ont une autre rétention, de 30 jours.
- SQLite est déjà déporté vers un thread ; réutiliser ce principe sans coupler les nouvelles
  données à la purge technique ou aux décisions de contrôle.
- `network/web/server.py` impose actuellement 64 KiB par corps de requête, CSRF et origine.
- `network/web/pages.py` et les assets locaux fournissent le rendu avec CSP stricte.
- La PWA lit ses snapshots après échec réseau et ne rejoue aucune mutation.

### Architecture proposée

Créer un service auxiliaire de culture, une politique métier testable sans matériel et un
magasin SQLite dédié, par exemple `controllers/CultureService.py`, `model/culture.py` et
`utils/culture_store.py`. Les noms sont proposés ; conserver les conventions effectivement
rencontrées pendant l'implémentation. Base locale proposée : `param/cultures.sqlite3` ; photos
dans un répertoire dédié `param/culture_media/`, tous deux exclus de Git avec fichiers associés.

Le magasin est l'unique propriétaire des écritures, avec connexion SQLite détenue par un thread
dédié, requêtes paramétrées, clés étrangères, migrations versionnées et transactions métier.
Le service reçoit les snapshots disponibles pour les synthèses ; il ne déclenche aucune lecture
matérielle et ne s'exécute pas dans une boucle de régulation. Ses échecs ne dégradent ni
`control_healthy()` ni le watchdog. Prévoir file de travail bornée et délais maîtrisés.

Une indisponibilité du carnet doit être visible ; une écriture non persistée ne reçoit jamais
une réponse de succès. Sur corruption, conserver les fichiers récupérables et signaler l'échec,
sans présenter une base vide de remplacement comme un carnet intact. Le contrôle continue.

Le carnet ne lit ni n'écrit des secrets dans ses exports. Aucun changement de `param.json` pour
un stade, un nom, une note ou une recette ; `ConfigStore` reste seul écrivain de ce fichier.
Les associations de culture n'introduisent aucune dépendance de la régulation envers SQLite.

### Entités à prévoir

| Entité logique | Rôle |
| --- | --- |
| Espaces et associations d'équipements datées | Emplacements, références au catalogue existant |
| Mères, lots, origines et variations d'effectif | Identité, filiation et nombres traçables |
| Occupations et périodes de stade | Où et à quelle étape se trouve une culture |
| Réservoirs, périodes de solution, associations aux cultures | Attribution temporelle des relevés |
| Recettes, préparations et ingrédients figés | Réutilisation sans modification rétroactive |
| Événements et cibles multiples | Journal commun et interventions sur plusieurs mères |
| Relevés et contexte d'intervention | Valeurs normalisées, dates et lien avant/après |
| Pièces jointes | Métadonnées, chemins internes, empreintes et liens aux événements |
| Rappels | Échéances, récurrences et accomplissements |
| Agrégats climatiques | Synthèses durables avec qualité et couverture |
| Révisions et clés d'idempotence | Corrections traçables et protection contre les doublons |

Privilégier colonnes et relations explicites pour les champs interrogés. Réserver JSON aux détails
optionnels versionnés ; éviter un unique champ texte pour toutes les données agronomiques.
Vues courantes et événement correspondant sont mis à jour dans une même transaction.
Conserver date effective, date de saisie, précision temporelle et version de l'enregistrement.
Empêcher chevauchements incohérents de stades, effectifs négatifs, origines inexistantes,
affectations de solution contradictoires et occupation simultanée de l'espace 2 par deux lots.

Les corrections préservent la version précédente et leur motif facultatif. L'annulation d'une
entrée erronée est visible, sans effacement silencieux. Verrouillage optimiste : une édition
depuis un onglet périmé reçoit un conflit compréhensible plutôt que d'écraser la nouvelle version.
Les POST de création acceptent une clé d'idempotence pour éviter les doublons sur double clic
ou nouvelle tentative explicite après une réponse perdue ; ce n'est pas une file hors ligne.

### HTTP, médias et mode hors ligne

Routes de lecture et mutations dédiées dans l'espace `/api/v1/cultures` ou équivalent ; conserver
POST pour les actions, CSRF, origine, Host autorisés, échappement et réponses dynamiques no-store.
Pagination des journaux et archives ; agrégation des longues courbes côté magasin.
Aucun texte de note, nom libre ou contenu de préparation recopié dans les logs console.

Les photos nécessitent une route spécifique : ne pas augmenter globalement la limite de 64 KiB.
Définir une limite bornée par photo (proposition initiale : 5 MiB, 4 photos par événement), limiter
aussi les dimensions décodées, vérifier réellement le format et réencoder les images acceptées
en JPEG/WebP, retirer les métadonnées EXIF et générer les noms côté serveur. Pas de SVG/HTML
téléversé ni de chemin fourni par le client. Décodage hors event loop. Prévoir stockage temporaire,
publication atomique et nettoyage borné des fichiers orphelins après interruption.
Une erreur photo ne doit pas laisser croire que la note et l'image sont toutes deux enregistrées.

En mode hors ligne : consultation datée des seuls snapshots prévus, bannière de lecture seule,
aucune commande ni entrée de carnet mise en attente/rejouée. Les champs d'un formulaire échoué
peuvent rester dans la page pour une nouvelle tentative explicite après reconnexion.

### Conservation, export et restauration

Aucune purge automatique des cultures, relevés, interventions et filiations. Les photos ont un
budget disque visible ; refuser un nouvel upload en cas de limite sans supprimer les anciennes.
Les archives gardent leurs références. Agrégats climatiques conservés pour couvrir les cycles.

Prévoir export CSV des relevés/interventions avec unités et dates, export JSON versionné des
relations complètes, et sauvegarde cohérente contenant base et médias avec manifeste/empreintes.
L'export CSV doit neutraliser les cellules textuelles interprétables comme formules de tableur.
Un CSV seul ne constitue pas une sauvegarde restaurable du carnet.

Utiliser l'API de sauvegarde SQLite et une stratégie explicite de cohérence des pièces jointes,
pas une copie naïve du fichier ouvert en WAL. Tester la restauration dans un emplacement isolé,
vérifier version, intégrité et médias avant tout remplacement explicite du carnet actif.
Documenter une procédure locale ; une interface d'import arbitraire n'est pas nécessaire en V1.
Sauvegarde avant migration, détection des schémas futurs et refus du carnet incompatible sans
empêcher le contrôleur de fonctionner. Une restauration du code ne doit pas effacer les données.

Ne pas convertir automatiquement les anciennes notes techniques en événements structurés :
leur cible est inconnue et leur rétention courte. Une reprise manuelle des notes encore disponibles
peut être proposée ; signaler que les données déjà purgées ne peuvent pas être reconstituées.

## 5. Parcours de référence à livrer

1. **Première utilisation en cours de cycle** : créer Mère A et Mère B, puis un lot déjà en
   floraison dans l'espace 2, dater les étapes connues, marquer les dates approximatives,
   renseigner la solution actuelle et commencer les relevés sans attendre le cycle suivant.
2. **Boutures multi-origines** : créer un lot de 3 + 5 boutures, noter une perte, enregistrer
   l'enracinement, déplacer le lot entier. Les mères restent en place et conservent leur journal.
3. **Semis** : créer huit semis dans l'espace 1, suivre germination et végétatif, transférer
   l'ensemble dans l'espace 2, puis déclarer la floraison sans changement d'horaire automatique.
4. **Routine solution** : saisir pH/EC, corriger, relever après correction, puis voir les deux
   points et l'intervention. Renouveler avec la recette précédente, adaptée et figée pour ce jour.
5. **Arrosage des mères** : une préparation, plusieurs destinataires, une opération, aucune
   duplication du volume total dans les bilans par mère.
6. **Récolte et séchage** : couper tout le lot, conserver l'occupation de l'espace 2, vérifier
   manuellement les réglages, suivre le séchage, saisir le bilan et libérer l'espace.
7. **Correction** : corriger une date ou un relevé avec historique de révision ; un onglet ancien
   ne peut pas écraser la correction et une répétition de requête ne double pas l'intervention.
8. **Indisponibilité** : carnet inaccessible ou disque plein, message explicite et contrôle
   inchangé ; retrouver ensuite les données confirmées et restaurer une sauvegarde sur copie.

## 6. Livraisons et ordre d'implémentation

Chaque jalon doit être utilisable, testé et documenté. Les cases suivent le travail livré ou restant.
Le déploiement sur le Pi se prépare séparément avec sauvegarde et autorisation de l'exploitant.

### Jalon 1 — Cultures, parcours et carnet durable

- [x] Définir schéma, migrations, magasin dédié, erreurs et sauvegarde/restauration minimale.
- [x] Créer espaces, mères, lots multi-origines et reprise de cultures déjà commencées.
- [x] Implémenter effectifs, stades, dates, compteurs, transferts entiers et occupation.
- [x] Implémenter coupe, séchage, fin et archivage avec bilan texte/poids facultatif.
- [x] Ajouter journal texte, corrections traçables et actions idempotentes.
- [x] Ajouter vue cultures, fiches, résumé du tableau de bord et liens aux réglages existants.
- [x] Exporter le carnet et documenter conservation et restauration dès cette première livraison.

Réalisation : `model/culture.py`, `utils/culture_store.py`, `network/web/cultures.py` et leurs
templates/assets. Le magasin expose les opérations auxiliaires directement : aucun service
supplémentaire ni job supervisé de régulation n'est nécessaire à ce jalon. Schéma initial 1,
refus des versions inconnues, migrations futures explicitement requises. Les affectations fixes
réutilisent les identifiants existants ; chaque événement conserve le catalogue connu à sa saisie.
Guide : `docs/operations/cultures.md`. API : `docs/reference/cultures-api.md`.

Validation de clôture du jalon 1, le 7 septembre 2026 après reprise de l'interruption :

- `.venv/bin/python -m pytest -q` : 241 tests réussis ; avertissements de dépréciation
  Pydantic/aiohttp existants, aucun échec.
- `PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --workers=2` : 84 tests réussis,
  26 exclusions prévues selon les profils ; références visuelles et accessibilité validées.
- Les parcours mutateurs du carnet possèdent chacun une base temporaire par worker :
  leurs occupations de l'espace 2 ne se chevauchent plus entre profils de navigateur.
- Dates lisibles sur les fiches, parcours et révisions ; décalage UTC explicite pour les
  instants, avec tests du passage de minuit et des deux heures locales identiques en automne.
- Syntaxe JavaScript, `git diff --check` et synchronisation `CLAUDE.md`/`AGENTS.md` vérifiés.

Sortie : parcours semis et boutures multi-mères jusqu'à l'archivage, reprise après redémarrage,
aucune modification des horaires/configurations/GPIO provoquée par les actions de culture.

### Jalon 2 — Solutions, relevés et interventions structurées

- [x] Réservoirs, périodes de solution, préparations et liens temporels aux cultures.
- [x] Saisie rapide pH/EC, température/volume facultatifs et unités explicites.
- [x] Arrosage de plusieurs mères, renouvellements, appoints et corrections avant/après.
- [x] Recettes réutilisables avec ingrédients figés dans les préparations enregistrées.
- [x] Courbes annotées, filtres et exports tabulaires.

Sortie : une routine quotidienne complète remplace le carnet papier ; les courbes restent
interprétables après renouvellement, correction rétrospective et changement de lot.

Validation hors matériel du jalon 2 (8 septembre 2026) :

- `.venv/bin/python -m pytest -q` : 260 tests réussis ; avertissements Pydantic/aiohttp existants.
- Recettes figées, arrosage multi-mères sans multiplication des volumes, normalisation EC,
  corrections et annulations transactionnelles, liens temporels coupés à la récolte.
- Migration 1 → 2 avec sauvegarde préalable, simulation de migration interrompue, stockage
  refusant les écritures, restauration sur copie et conservation des révisions.
- Courbes du filtre complet, agrégats journaliers par cible et solution après 1 000 entrées,
  pagination indépendante, CSV neutralisant les formules de tableur.
- Suite Playwright complète : 89 tests réussis, 31 exclusions prévues, avec
  `PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --workers=1 --timeout=60000`.
- Parcours Playwright du jalon 2 validés sur bureau, téléphone étroit, téléphone et paysage ;
  contrôles d’accessibilité, pannes réseau, idempotence et absence de rejouement hors ligne.
- Référence visuelle du tableau de bord actualisée pour les raccourcis « Saisir un relevé ».
- Syntaxe JavaScript, `git diff --check` et miroirs `AGENTS.md`/`CLAUDE.md` vérifiés.

### Jalon 3 — Photos, rappels et synthèses de cycle

- [x] Photos bornées, validation, gestion du disque, sauvegarde et restauration des médias.
- [x] Rappels dans l'application, récurrences, report et accomplissement explicites.
- [x] Listes de vérification de stade, sans commandes embarquées ni nouvelles alarmes de contrôle.
- [x] Agrégats climatiques durables depuis snapshots existants, qualité et couverture visibles.
- [x] Bilan enrichi et comparaison simple entre cycles, consultation PWA en lecture seule.
- [x] Guide d'exploitation illustré, export complet et exercice de restauration sur copie.

Sortie : cycle consultable de bout en bout avec contexte, pièces jointes et bilan ; interruptions
réseau, stockage et redémarrages ne produisent ni perte silencieuse ni action matérielle.

Validation de clôture du jalon 3, le 8 septembre 2026 après reprise :

- Suite Python complète : 273 tests réussis, 62 avertissements de dépréciation Pydantic/aiohttp.
- Suite navigateur : 130 cas, 90 réussites, 38 exclusions prévues et deux échecs de sélecteur
  sur le volet de fin de séchage. Sélecteur corrigé, puis les deux parcours bureau/téléphone
  relancés avec succès : les 92 cas applicables ont été validés.
- Photos et rappels sur bureau/320 px, accessibilité axe, PWA datée sans rejeu de POST,
  références visuelles du tableau de bord et de l'historique vérifiées.
- Restauration ZIP sur nouvelle copie : comparaison de toutes les tables et d'une photo,
  refus d'archives altérées, incomplètes ou à chemin extérieur ; outil CLI également exercé.
- Vérification datée le jour d'un changement de stade horodaté corrigée et testée.
- Publication de la restauration synchronisée avant retrait du marqueur d'incomplétude.
- Guide illustré, contrat API et procédure de sauvegarde mis à jour ; instructions miroirs
  synchronisées. Aucune intervention sur le Pi ni configuration machine modifiée.

### Hors périmètre de ces jalons

- Commande des équipements par stade, programmation automatique de transition, dosage automatique.
- Fractionnement de lots, déplacements ou récoltes partiels, fiche individuelle obligatoire des boutures.
- Analyse de performance par mère, diagnostic agronomique automatique, recommandations nutritives.
- Synchronisation cloud, comptes utilisateurs, commandes hors ligne et import automatique du carnet papier.
- Nouveaux capteurs, nouveaux GPIO et modification du contrôleur thermique ou du watchdog.

## 7. Vérification et critères transversaux

Tests métier avec horloge injectée, sans GPIO, réseau externe ni privilèges :

- Origines multiples, retrait d'une plante d'origine connue/inconnue, archive d'une mère référencée.
- Chronologie des stades et occupations, correction rétroactive, date seule/approximative,
  J0/J7/J23, minuit, changement d'heure, heure non fiable et redémarrage.
- Transfert sans remise à zéro, récolte entière, séchage conservant l'occupation et libération.
- Préparation figée malgré modification de recette, renouvellement atomique, bonne attribution
  temporelle des mesures, arrosage partagé sans double comptage.
- Conversion EC et virgule décimale, valeur absente versus zéro, contexte avant/après, lacunes.

Tests de persistance et HTTP : transactions interrompues, disque plein, corruption, migration,
schéma futur, idempotence, conflit d'édition, pagination, CSRF/origine, limites de corps,
échappement, export sans injection CSV et absence de texte libre/secrets dans les logs.
Tester réellement la restauration base + médias et la conservation indépendante de la purge 72 h.
Vérifier le refus des faux formats photo, dimensions excessives et chemins malveillants.

Tests d'intégration ciblés : toutes les actions de culture laissent la configuration de contrôle
inchangée et ne déclenchent aucun appel d'écriture GPIO ; une panne du service auxiliaire n'affecte
pas la santé du contrôle. Les agrégats ne provoquent aucune nouvelle acquisition matérielle.

Tests Playwright : parcours téléphone et bureau, saisie au clavier, libellés/erreurs accessibles,
absence de perte de champs après échec, double clic, navigation entre espaces, courbes avec peu
de données, données périmées et lecture seule hors ligne. Comparer les vues visuelles concernées.

Exécuter la suite pytest pour chaque modification Python comme requis par le dépôt et les tests
UI pertinents à chaque changement d'interface. Ne pas introduire de linter dans ce chantier.
L'absence de modification matérielle est une exigence du plan ; si une implémentation la remet
en cause, réévaluer le périmètre et appliquer la procédure de validation matérielle existante.

## 8. Documentation et points d'entrée pour l'implémentation

Mettre à jour la documentation utilisateur, le contrat API, les fichiers ignorés et le guide de
sauvegarde au fil des jalons. Ajouter la fonctionnalité dans `docs/roadmap.md` au démarrage de
l'implémentation en conservant les engagements existants. Ne pas modifier les fichiers de
configuration machine ni le projet ESP32. Si `AGENTS.md` ou `CLAUDE.md` doit être enrichi lors
de l'implémentation, appliquer exactement le même changement aux deux fichiers.

Références locales à relire avant réalisation :

- `param/equipment_metadata.py`, `param/config_store.py` et `utils/operational_state.py`.
- `controllers/OperatorService.py`, `utils/operator_history.py`, `controllers/sensor_catalog.py`.
- `utils/time_reliability.py`, `network/web/server.py`, `network/web/pages.py`.
- `network/web/static/js/pwa.js`, `network/web/static/service-worker.js` et tests UI existants.
- `docs/development/hardware-validation.md` si le périmètre matériel venait à changer.

Ce plan intègre les arbitrages de la conversation. Il ne reste pas de choix utilisateur bloquant
pour commencer le jalon 1. Les limites techniques proposées (médias, granularité des agrégats,
chemins internes) peuvent être ajustées sur mesure du Pi pendant l'implémentation, en documentant
le résultat et sans modifier les décisions fonctionnelles validées.
