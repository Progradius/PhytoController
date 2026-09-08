# Audit UI/UX du carnet de cultures — 8 septembre 2026

L'enjeu principal est de transformer un ensemble de formulaires métier en un carnet
qui aide à comprendre la situation et à réaliser la prochaine action. La couverture
fonctionnelle est riche ; la hiérarchie, la continuité du contexte et la simplicité
des saisies demandent une refonte. Une amélioration purement graphique serait insuffisante.

Audit et recommandations seulement : aucune modification du fonctionnement de
l'application, aucune intervention sur le Pi ou sur les données de production.

## Périmètre et preuves

- Référence examinée : `master`, `b628cf5`. Les 89 fichiers initialement signalés
  modifiés n'ont aucun écart avec Git lorsque les différences de fin de ligne sont ignorées.
- Lecture des sept templates du carnet, des sept scripts associés, du CSS commun,
  des vues, de la navigation globale, des parcours de tests et du serveur de test.
- Sept rubriques : cultures, solutions, cycles, plages cibles, éclairage, équipements,
  journal ; également fiche individuelle, archives, photos, rappels, corrections,
  exports et accès à la configuration. Les photos sont servies comme images : elles
  n'ont pas de page de consultation dédiée avec navigation propre.
- Navigation Chromium sur le serveur matériel-neutre `tests/ui_server.py`, avec
  configuration et base temporaires. Contrôles aux largeurs 1440, 393 et 320 px.
- Captures et axe sur les sept pages initiales aux trois largeurs. Scénario
  complémentaire avec un lot, une note, trois relevés, un rappel et un repère
  personnalisé ; fiche, solutions, cycles, journal et archives aux largeurs 393 et
  1440 px. Vérification complémentaire des solutions en thème plein jour.
- Suite Playwright des cultures sur bureau, mobile, mobile étroit et PWA :
  **52 réussites, 40 exclusions prévues par les tests, aucun échec**, durée 4,9 min.
  Les exclusions correspondent aux conditions de profil, pas à des échecs masqués.
- Aucun débordement horizontal de page ni violation axe dans les états analysés.
  Les tableaux à défilement interne restent un cas distinct.
- `CLAUDE.md` et `AGENTS.md` sont identiques.

Les [mesures des pages](../images/audit-ui-cultures-2026-09-08/mesures-pages.json)
et les [mesures des parcours](../images/audit-ui-cultures-2026-09-08/mesures-parcours.json)
sont conservées avec huit captures. Les données sont fictives.

Limites : aucune étude avec des utilisateurs, aucun essai physique sur téléphone
ou sous soleil, aucun lecteur d'écran, Safari/iOS ou Firefox exécuté dans cet audit.
Le thème plein jour a été vérifié sur la page solutions, pas exhaustivement sur
tous les états. Les performances d'un carnet de plusieurs années sur Raspberry Pi
ne sont pas qualifiées. Les tests climatiques navigateur utilisent un historique
sans agrégats ; les graphiques climatiques renseignés ont été examinés dans le code.
Les résultats axe ne constituent pas une certification WCAG.

## Ce qui est déjà utile et doit rester

- Suivi des origines, étapes et corrections rétrospectives ; historique des versions.
- Dates connues, approximatives et précises ; champs de mesures laissés vides.
- Préselection d'une culture depuis certains liens de sa fiche.
- Champs conditionnels déjà présents pour les origines et certaines opérations de solution.
- Recettes versionnées, calcul des quantités selon le volume et confirmation de la préparation.
- Conservation de la saisie après erreur réseau et idempotence de la nouvelle tentative.
- Actions de cycle filtrées selon le stade et l'état de la culture.
- Repères pH/EC datés et comparaison informative de l'éclairage.
- HTML sémantique, labels, navigation clavier native, thème plein jour, assets locaux.
- Consultation hors ligne datée et en lecture seule ; absence de rejeu des mutations.

Ces éléments sont une première intelligence métier. Ils restent dispersés et ne
composent pas encore un parcours homogène.

## Constats prioritaires

P1 désigne les changements nécessaires avant de qualifier l'expérience de claire
et intuitive. P2 désigne les améliorations de profondeur et de confort. Cette
priorisation concerne l'expérience du carnet, pas une criticité électrique.

| Priorité | Constat et preuve | Effet | Recommandation |
| --- | --- | --- | --- |
| P1 | Navigation locale différente sur chaque page, noms variables, liens de rubrique mélangés aux ancres. `cultures.html:36`, `culture_solutions.html:58`, `culture_cycles.html:16`. | L'utilisateur doit réapprendre où aller ; certaines rubriques nécessitent un retour à l'accueil. | Navigation commune, rubrique active, contexte visible, séparation des sous-sections de page. |
| P1 | Reproduction : solutions filtrées sur le lot → lien « Cycles et rappels » → URL sans `subject`, sélection vide. | Perte réelle de contexte ; comparaison vide et rappels redevenus globaux. | Propager le contexte compatible dans les liens, l'URL et le retour après saisie. Prévoir explicitement le passage à une vue globale. |
| P1 | Sur mobile, les plages enregistrées commencent à 2 030 px ; le journal à 1 461 px, même à vide. | Le contenu attendu est repoussé par les formulaires et les explications. | Lecture en premier ; création à la demande ; filtres compacts ; détails techniques repliés. |
| P1 | Avec un lot sélectionné, les rappels commencent à 1 936 px ; ils arrivent après comparaison et climat. | Une échéance en retard n'est pas visible à l'ouverture du carnet. | Synthèse « Aujourd'hui » et rappels dans la fiche ; comparaison dans une vue distincte. |
| P1 | La fiche expose cinq accordéons de même poids en floraison ; « Ajouter au carnet » commence à 1 131 px. | Aucune action quotidienne ne ressort. | Actions principales « Relevé », « Observation / photo », puis « Changer de stade » selon le contexte ; opérations rares dans un menu explicite. |
| P1 | Correction d'un repère existant de 960 minutes : changer le stade de végétatif à floraison remplace le champ par 720. Reproduit sans enregistrer la correction. `culture_light.js:18-30`. | Une modification de contexte peut modifier une durée personnalisée à l'insu de l'utilisateur avant validation. | Préserver les valeurs existantes ; proposer un bouton « Utiliser 12 h / 12 h » au lieu d'appliquer implicitement le préréglage. |
| P1 | Graphiques SVG de 600 unités réduits sur téléphone ; hauteur rendue des graduations observée : 9 px. Points renseignés par un `title`, sans interaction tactile ou clavier dédiée. `culture_solutions.js:179-239`. | Les courbes sont difficiles à lire et explorer sur téléphone ; axe ne détecte pas cette difficulté. | Taille de texte stable, détail au toucher et au clavier, tableau équivalent et légende explicite. |
| P1 | Erreurs dans un `output` après le formulaire ; pas d'association explicite aux champs dans les scripts du carnet. | Recherche de l'erreur coûteuse dans les longs formulaires. | Résumé d'erreur, erreur au champ, `aria-invalid` et `aria-describedby`, focus vers le premier problème ; validation métier serveur conservée. |
| P2 | Les enregistrements rechargent la page ; certaines vues reviennent à une ancre, la fiche culture navigue sans ancre. | Perte de repères après action ; risque pour les autres formulaires ouverts et non enregistrés. | Retour visuel vers l'entrée créée, confirmation persistante, protection des saisies non terminées. Le risque multi-formulaire est identifié dans le code, pas reproduit ici. |
| P2 | Nombreuses métadonnées affichées à chaque entrée : identifiants, version, heure de saisie, contexte d'équipements. | L'observation et les valeurs utiles sont noyées. | Ligne synthétique et détails de traçabilité à la demande ; conserver les données et leur provenance. |
| P2 | Les champs de portée équipement/éclairage restent affichés même lorsqu'ils ne s'appliquent pas. | L'utilisateur doit comprendre quelles valeurs seront utilisées ou ignorées. | Afficher seulement culture, espace ou réservoir selon la portée ; aperçu de la déclaration. |
| P2 | L'accueil mobile place « Cultures » dans « Plus » ; les archives gardent le titre « Cultures » et l'occupation actuelle au-dessus des archives. | Accès indirect à une fonction quotidienne et confusion entre présent et passé. | Accès direct au carnet à étudier dans la navigation globale ; titre Archives, recherche et bilan historique dédiés. |

Les liens de 18–22 px observés constituent une piste d'amélioration tactile, pas
automatiquement une violation WCAG : les exceptions de texte courant et d'espacement
doivent être prises en compte.

## Recommandations par page et parcours

| Page ou parcours | Évolution recommandée | Point à préserver |
| --- | --- | --- |
| Accueil `/cultures` | Bloc Aujourd'hui, occupation synthétique, rappels à échéance, dernières observations, trois raccourcis de saisie ; recherche des cultures. Au premier lancement, bouton « Ajouter ma première culture ». | État des espaces déclaré ; distinguer occupation et réglages physiques. |
| Fiche `/cultures/{id}` | Véritable dossier : synthèse, chronologie, relevés, photos et bilan. Nom, espace, stade, âge du stade et effectif en tête. Actions adaptées au stade. | Origines multi-mères, révisions et possibilités de correction du parcours. |
| Création et reprise | Deux entrées « Je démarre une culture » / « Elle est déjà en cours ». Regrouper identité/origine puis situation actuelle. Frise récapitulative avant validation. | Aucune date historique inventée ; précision approximative explicite. |
| Changement de stade, récolte et clôture | Parcours guidé montrant état avant/après, date et effet sur occupation/alimentation. Proposer ensuite les vérifications pertinentes. | Aucun changement automatique des horaires, sorties ou réglages. Clôture et libération restent distinguées. |
| Solutions et relevés | Choix d'intention visible : mesurer, arroser, renouveler, ajouter de l'eau. Cible en tête, date compacte modifiable, valeurs regroupées. Courbes et journal accessibles sans traverser la saisie. | Mesures non préremplies ; volume total unique d'un arrosage commun ; contexte avant/après conservé. |
| Recettes et préparation | Espace dédié, recherche et dernière recette utilisée proposée explicitement ; volume puis quantités et confirmation. | Préparation figée avec version de recette, sans dosage recommandé automatiquement. |
| Cycles et comparaison | Sélection par recherche et cases à cocher, maximum quatre expliqué ; comparaison alignée par indicateur ou âge du stade, pas seulement des cartes empilées. | Absences visibles, unités et périodes comparables, climat commun à la serre identifié. |
| Rappels et vérifications | Liste Aujourd'hui / En retard / À venir / Terminés. Boutons « Fait » et « Reporter » ; nouvelle date uniquement en cas de report. Dans la fiche, vérifications pertinentes au stade. | Accomplissement réel explicite, récurrence selon le contrat actuel, conflits historiques et absence de notification système. |
| Photos | Observation et ajout de photo dans un même parcours, aperçu avant envoi, progression, reprise d'erreur, galerie avec légendes et retour à la fiche. | Propriétaire exclusif, quotas, réencodage, limites de taille et absence de métadonnées. Gérer l'échec partiel note enregistrée/photo refusée. |
| Plages pH/EC | Voir d'abord la plage applicable à la cible/date ; ajouter ou modifier à la demande. Explication « Cette plage vient de… ». | Résolution historique stricte, sans fusion ni plage implicite, stade informatif. |
| Éclairage | Comparaison lisible « Repère : 18 h / Configuré : 12 h / Écart : −6 h ». Saisie en heures et minutes ; préréglages explicites. | Séparer repère, minuterie active, commande et vérification physique. |
| Équipements | Affectations actuelles lisibles, frise des périodes, action « Changer l'usage à partir du… ». Catalogue technique secondaire. | Contexte à la date de l'événement, pas le catalogue actuel utilisé pour réécrire le passé. |
| Journal transversal | Chronologie au premier plan, regroupement par jour, filtres rapides 7/30 jours et culture/espace, aperçu des mesures et photos. Un lien principal pertinent par entrée. | Une ligne par opération, arrosages partagés non dupliqués, observations d'espaces sans fausses cultures. |
| Archives et bilan | Recherche, variété, dates, durée par stade, poids si renseigné, enseignements ; comparaison de cycles terminés. | Pas de poids déduit d'une absence ; occupation persistante d'une archive signalée. |
| Exports et sauvegarde | Une entrée cohérente « Exporter / sauvegarder » distinguant CSV du filtre et ZIP complet avec photos. | Export SQLite seul clairement nommé comme n'incluant pas les fichiers photo ; restauration isolée. |
| Erreur / indisponible / hors ligne | Message bref, date de dernière consultation, action de retour ou nouvel essai, saisie conservée clairement décrite. | Aucune mutation mise en attente ou rejouée ; aucune suggestion fraîche à partir d'une page périmée. |

## Architecture d'information proposée

Navigation principale du carnet : **Aujourd'hui · Cultures · Journal · Ressources**.

- Aujourd'hui réunit les actions et échéances des cultures et espaces suivis.
- Cultures ouvre la liste, les fiches et les archives ; comparer est une action de liste.
- Journal permet la recherche transversale, les relevés, observations et interventions.
- Ressources contient réservoirs/solutions, recettes, plages, éclairage, affectations
  et sauvegarde, avec des raccourcis contextuels depuis les fiches.

Cette organisation doit être validée sur des parcours représentatifs avant de
renommer toutes les pages. Les URLs actuelles peuvent rester accessibles ; les liens
profonds et la PWA doivent continuer à fonctionner.

La fiche garde des vues locales : **Synthèse · Journal · Relevés · Photos · Bilan**.
Elle affiche constamment sa culture et offre un moyen clair de changer de culture.
Une navigation vers un réservoir doit expliciter le changement de contexte.

Les éléments courants tiennent dans une synthèse compacte. Les métadonnées de
traçabilité et explications avancées restent consultables dans des détails dédiés.
Ce principe de dévoilement progressif sert la compréhension ; ajouter des accordéons
partout sans hiérarchiser les actions reproduirait le problème actuel.

## Intelligence utile à introduire

La première version devrait utiliser les faits du carnet et des règles déterministes,
explicables et testables. Elle peut déjà rendre le produit beaucoup plus serviable.

| Situation | Assistance proposée | Condition de confiance |
| --- | --- | --- |
| Relevé ouvert depuis une fiche | Préselection de la culture ; réservoir associé proposé si la relation est connue à la date saisie. | Afficher la source et permettre le changement ; ne pas déduire une association de la seule présence dans un espace. |
| Réservoir/équipement sans affectation certaine | « Association inconnue à cette date » et action pour la renseigner. | Aucune reconstruction silencieuse du passé à partir des noms actuels. |
| Culture reprise en cours | Demander le stade actuel, puis proposer de compléter seulement les étapes manquantes. | Dates inconnues conservées comme telles ; étapes antérieures strictement avant le stade courant. |
| Passage en floraison ou séchage | Proposer les vérifications adaptées au nouvel état, avec leurs liens. | La suggestion n'enregistre pas une vérification réalisée et ne change pas de réglage. |
| Rappel arrivé à échéance | Carte visible avec échéance, cible, « Fait » et « Reporter ». | Recalcul à la date courante fiable, dédoublonnage et absence d'alarme de contrôle. |
| Nouveau relevé comparable | Présenter le précédent à côté du champ et l'écart à la plage choisie par l'opérateur. | Champ vide ; même cible/contexte/période pertinents ; aucune interprétation agronomique certaine d'une variation isolée. |
| Relevé ancien | « Dernier relevé saisi il y a 3 jours », éventuellement « fréquence de suivi dépassée ». | La seconde formulation exige une fréquence configurée ; trois jours seuls ne prouvent aucun problème. |
| Saisie potentiellement répétée | Montrer l'entrée ressemblante et demander de vérifier. | Autoriser une vraie seconde mesure ; distinguer rapprochement heuristique et idempotence technique. |
| Date incompatible ou espace occupé | Expliquer le conflit avec la culture et la période concernées, puis proposer de corriger la date ou le contexte. | Prévalidation alimentée par le serveur ; validation finale toujours autoritaire en cas de concurrence. |
| Récolte terminée | Proposer poids, enseignements, photos finales, puis libération de l'espace si elle a réellement eu lieu. | Poids facultatif, pas de libération implicite. |

Chaque suggestion devrait porter une cible, un motif, les faits datés qui la
justifient, une action et une condition d'expiration. Limiter les suggestions visibles
aux quelques éléments les plus utiles ; distinguer « À faire », « À vérifier » et
« Information manquante ». Éviter les scores de santé globaux sans base fiable.

Les recommandations et prévalidations métier devraient réutiliser les projections
et modèles purs existants. Une API de contexte peut alimenter l'interface sans
dupliquer les règles dans sept scripts. Les données auxiliaires ne doivent pas
alourdir les boucles de contrôle ni introduire une nouvelle acquisition.

Une IA générative peut constituer une évolution ultérieure : synthèse sourcée d'un
cycle, recherche en langage naturel ou transformation d'une note en proposition
de saisie. Toute extraction reste un brouillon confirmé. Il faut alors définir le
mode local/distant, le coût et la confidentialité ; le fonctionnement du carnet doit
rester complet sans ce service. Le gain immédiat vient surtout de la contextualisation,
des bons choix par défaut et de l'explication des conséquences.

## Direction visuelle et accessibilité

Conserver l'identité végétale et le thème plein jour. Hiérarchiser davantage : un
titre de contexte compact, des nombres utiles, une action principale, puis des
groupes clairement séparés. Réserver les cartes aux objets et groupes de sens ;
éviter une succession de grandes boîtes identiques pour toutes les fonctions.

- Formulaires bureautiques de largeur maîtrisée, champs logiquement regroupés et
  boutons dimensionnés à leur fonction. Vue mobile pensée en premier.
- Cibles tactiles importantes d'au moins 44 × 44 px comme objectif de confort.
  WCAG 2.2 AA prévoit 24 × 24 px ou les exceptions applicables ; ne pas confondre
  cet objectif de confort avec le minimum normatif.
- Statuts exprimés par texte et symbole en plus de la couleur.
- Graphiques à taille de texte stable, légende par source/période, sélection d'un
  point au toucher et au clavier, synthèse textuelle et tableau des données.
- Préserver les lacunes, les agrégations et les bandes datées. Une courbe globale
  ne doit pas relier arbitrairement plusieurs cultures ou solutions.
- Message d'erreur près du champ, focus contrôlé, confirmation perceptible après
  navigation et protection du contenu sous les barres mobiles fixes.
- Photos consultables avec précédent/suivant et retour au contexte, sans dépendre
  du bouton précédent du navigateur après ouverture du fichier image.

Références : [WCAG 2.2, taille minimale des cibles](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html),
[identification des erreurs](https://www.w3.org/WAI/WCAG22/Understanding/error-identification.html),
[alternatives aux graphiques complexes](https://www.w3.org/WAI/tutorials/images/complex/),
[NN/g, dévoilement progressif](https://www.nngroup.com/articles/progressive-disclosure/).

## Ordre de réalisation recommandé

| Lot | Résultat attendu | Taille relative | Validation de sortie |
| --- | --- | --- | --- |
| 1 — Cohérence et défauts | Navigation commune, contexte conservé, valeurs personnalisées préservées, textes simplifiés, lecture avant création, graduations lisibles. | Moyenne | Parcours fiche → relevé → cycles → retour avec même contexte ; correction de stade sans changement de durée implicite ; captures mobile et plein jour. |
| 2 — Parcours quotidiens | Accueil Aujourd'hui, fiche complète, saisie guidée, création/reprise et observation/photo cohérentes. | Grande | Réaliser les tâches quotidiennes sans chercher une rubrique technique ; tester états vide, renseigné, archivé et conflit. |
| 3 — Assistance contextuelle | Suggestions expliquées, prévalidation, échéances, détection de saisies ressemblantes, transitions accompagnées. | Grande | Règles pures testées ; aucun automatisme silencieux ; suggestions obsolètes retirées après changement de données ; validation serveur finale. |
| 4 — Analyse et confort | Comparaison alignée, courbes tactiles, galerie, bilan et recherche. | Moyenne à grande | Utilisation clavier/tactile, données lacunaires et longues périodes ; requêtes bornées et temps de rendu sur Pi. |

Ces tailles sont relatives, pas un engagement calendaire. Un premier prototype
devrait couvrir Aujourd'hui, une fiche et une saisie de relevé sur téléphone, avec
des données représentatives. Il permettrait de valider l'organisation avant de
répercuter les composants sur les sept rubriques.

Objectifs à mesurer lors de cette validation, et non résultats déjà acquis :

- Identifier la culture, son stade et la prochaine action en moins de 10 secondes.
- Enregistrer un pH/EC depuis une fiche en moins de 30 secondes, sans ressaisir la cible.
- Atteindre les rappels à échéance immédiatement depuis l'accueil du carnet.
- Comprendre un conflit de date et savoir le résoudre sans lire la documentation.
- Retrouver l'entrée créée et les valeurs enregistrées après chaque validation.
- Zéro valeur mesurée ou historique inventée par une aide à la saisie.
- Validation manuelle clavier, lecteur d'écran et téléphone réel en plus d'axe.

Les premiers lots peuvent majoritairement rester dans les vues, templates, CSS et
scripts. Les nouveaux besoins persistants (préférences de suivi, état durable d'une
suggestion, brouillons) doivent être conçus explicitement ; s'ils étendent le carnet,
ils nécessitent un schéma 5, sans retoucher le DDL figé du schéma 4. Les nouveaux
brouillons éventuels doivent rester distincts d'un enregistrement accepté et ne
jamais être envoyés automatiquement au retour du réseau.

## Captures de référence

- [Accueil mobile](../images/audit-ui-cultures-2026-09-08/accueil-mobile.png)
- [Fiche renseignée sur mobile](../images/audit-ui-cultures-2026-09-08/fiche-mobile.png)
- [Plages cibles sur mobile](../images/audit-ui-cultures-2026-09-08/plages-mobile.png)
- [Cycle avec rappel sur mobile](../images/audit-ui-cultures-2026-09-08/cycles-mobile.png)
- [Journal renseigné sur bureau](../images/audit-ui-cultures-2026-09-08/journal-bureau.png)
- [Solutions en plein jour](../images/audit-ui-cultures-2026-09-08/solutions-plein-jour.png)
- [Équipements sur bureau](../images/audit-ui-cultures-2026-09-08/equipements-bureau.png)
- [Éclairage sur mobile](../images/audit-ui-cultures-2026-09-08/eclairage-mobile.png)

Les captures pleine page incluent la barre de navigation fixe à la position du
viewport initial ; sa présence au milieu d'une longue image n'est pas une barre
supplémentaire dans le document.
