# Plan — Compléments et corrections du carnet de cultures après audit

Date : 8 septembre 2026.
Statut : plan de travail issu de l’audit ; implémentation non commencée.
Branche auditée : `feature/gestion-cultures`, référence `58e97e6`.
Plan de référence : [Gestion des cultures et carnet d’exploitation](gestion_cultures_plan.md).

Ce document organise la correction des écarts constatés entre le plan de référence et
les livraisons 1 à 3. Il ne constitue pas une autorisation de déploiement sur le Pi.
Les validations historiques restent acquises pour les scénarios exercés ; elles ne
constituent pas une validation des scénarios manquants décrits ici.

## 1. Objectif et état initial

Rendre les parcours promis utilisables dans la durée : reprise d’une culture existante,
correction d’un carnet ancien, consultation complète des cycles, lecture hors ligne,
observations transversales et contexte historique des réglages et des mesures.

L’audit a confirmé la présence des trois livraisons :

| Livraison | Commit | État à la date de l’audit |
| --- | --- | --- |
| Cultures et parcours | `3ac74e5` | Socle livré ; reprise historique à compléter dans l’interface |
| Solutions et relevés | `f845293` | Routine livrée ; correction ancienne et fonctionnalités à compléter |
| Photos, rappels et cycles | `58e97e6` | Socle livré ; cycles longs, PWA et vérifications à compléter |

Validation refaite pendant l’audit : 273 tests Python réussis, 62 avertissements de
dépréciation ; 92 tests Playwright réussis, 38 exclusions prévues ; branche propre,
`git diff --check` sans erreur et instructions `AGENTS.md`/`CLAUDE.md` identiques.

Deux expériences sur bases temporaires ont confirmé les limites suivantes :

- Après 201 interventions supplémentaires, un relevé ancien reste consultable mais son
  intervention associée n’est plus proposée par le formulaire de correction.
- Avec 12 000 agrégats horaires, la restitution conserve seulement 10 000 points. La page
  de test correspondante pèse 5 278 958 octets, au-delà des 4 194 304 octets admis par le
  cache PWA. Cette version de la page ne peut donc pas être conservée hors ligne.

## 2. Invariants à préserver

- Stades, observations, plages cibles, repères, associations et vérifications restent
  déclaratifs : aucun GPIO, changement d’horaire, override ou dosage automatique.
- `ConfigStore` reste seul écrivain de `param.json`. Les données du carnet restent dans
  son magasin dédié ; aucune modification des fichiers de configuration machine.
- Le service de culture consomme les snapshots existants, sans nouvelle acquisition,
  sans accès SQLite dans l’event loop et sans participation au watchdog.
- Les absences et valeurs non fiables ne deviennent jamais des zéros. Les graphiques
  distinguent mesures, agrégats, lacunes, renouvellements et contexte.
- Toutes les écritures métier sont transactionnelles, avec validation, conflits
  compréhensibles et idempotence des nouvelles tentatives explicites.
- Le hors ligne est une consultation datée, après échec réseau uniquement. Aucune
  mutation mise en attente ou rejouée ; aucune notification système issue du carnet.
- Les exports restent sans secrets ni injection CSV. Les textes libres ne sont pas
  recopiés dans les logs. CSRF, origine, Host, CSP et limites de requêtes sont conservés.
- Les évolutions de schéma conservent les données existantes et une sauvegarde préalable.
  Une restauration est vérifiée sur copie isolée, base et médias compris.

## 3. Ordre de livraison et traçabilité des écarts

Chaque lot doit être implémenté, testé et documenté avant d’être coché. Les priorités
expriment l’ordre de travail, pas un retrait des lots suivants du périmètre.

| Lot | Priorité | Écart traité | Jalon concerné |
| --- | --- | --- | --- |
| A | 1 | Correction de relevés liés à une intervention ancienne | 2 |
| B | 1 | Consultation intégrale des cycles longs et taille des pages PWA | 3 |
| C | 2 | Ajout rétrospectif des étapes connues d’un parcours | 1 |
| D | 2 | Correction et annulation des vérifications déclaratives | 3 |
| E | 2 | Plages cibles pH/EC facultatives et historisées | 2 |
| F | 2 | Repères d’éclairage et rapprochement avec l’état opérationnel | Transversal |
| G | 2 | Associations d’équipements avec périodes de validité | Transversal |
| H | 2 | Journal transversal filtrable et observations d’espace | 1 à 3 |
| I | Clôture | Validation consolidée, restauration et documentation | Tous |

Avant la première évolution de schéma, définir les migrations nécessaires aux lots D à H.
Chaque version doit correspondre à un état utilisable du logiciel. Ne pas modifier une
migration déjà livrée pour y ajouter les besoins d’un lot ultérieur.

## 4. Lot A — Corriger les relevés anciens sans perdre leurs liens

Points d’entrée : `utils/culture_solution_store.py`,
`network/web/templates/culture_solutions.html`, `network/web/static/js/culture_solutions.js`.

- [ ] Toujours inclure l’intervention déjà associée à chaque relevé affiché en correction,
  même lorsqu’elle est absente des 200 interventions récentes.
- [ ] Permettre de retrouver une intervention ancienne avec une recherche ou une pagination
  bornée, contextualisée par cible et date ; ne pas charger tout le carnet dans un select.
- [ ] Conserver le lien existant lors d’une correction sans changement d’association.
- [ ] Rendre les liens vers les interventions consultables à travers la pagination et les
  filtres du journal, y compris lorsque la destination n’est pas sur la page courante.
- [ ] Préserver les règles avant/après, les transactions de renouvellement, les révisions
  et les conflits d’édition.

Critères d’acceptation :

- Un relevé lié, suivi de plus de 200 interventions sur plusieurs cibles, peut être corrigé
  uniquement sur son pH ou sa note sans perdre ni changer son association.
- Une intervention ancienne reste sélectionnable pour une saisie rétrospective.
- Une association incohérente est refusée sans écriture partielle ; le formulaire conserve
  les champs et une nouvelle tentative identique ne crée aucun doublon.
- Tests magasin et Playwright sur bureau et téléphone pour ces scénarios.

## 5. Lot B — Cycles longs et consultation PWA bornée

Points d’entrée : `utils/culture_cycle_store.py`, `network/web/culture_cycles.py`,
`network/web/templates/culture_cycles.html`, `network/web/static/js/culture_cycles.js`,
`network/web/static/service-worker.js`, `network/web/static/js/pwa.js`.

- [ ] Remplacer la coupe aux 10 000 derniers points par une restitution bornée couvrant
  l’ensemble du cycle : synthèse adaptée à sa durée et navigation vers le détail horaire.
- [ ] Effectuer l’agrégation et la pagination dans le magasin, avec requêtes bornées ; éviter
  de lire tout l’historique avant de tronquer une liste Python.
- [ ] Calculer les moyennes depuis les sommes et effectifs valides, sans moyenne non pondérée
  de moyennes horaires. Conserver min/max, nombres de valeurs et couverture explicite.
- [ ] Garder les capteurs distincts, les périodes manquantes visibles et le contexte commun
  à la serre. Documenter la convention des intervalles et des heures aux bords du cycle.
- [ ] Séparer les données nécessaires au graphique du tableau détaillé paginé afin de ne
  pas dupliquer des milliers de lignes dans le HTML initial.
- [ ] Garantir une synthèse de cycle consultable hors ligne dans les limites existantes.
  Définir précisément quels détails visités sont conservés et afficher leurs dates.
- [ ] Signaler l’indisponibilité d’un détail non conservé ; ne jamais présenter une synthèse
  partielle comme couvrant une période qui n’a pas été chargée.
- [ ] Conserver les bornes de stockage PWA, la priorité réseau et l’absence de cache des API.
  Une hausse arbitraire du plafond de taille ne suffit pas à traiter ce lot.

Critères d’acceptation :

- Un cycle de six mois avec plusieurs mesures horaires est consultable du début à la fin,
  avec accès au détail et sans perte des anciens agrégats en base.
- Les calculs sont vérifiés avec des heures de couvertures différentes, des valeurs nulles,
  des zéros réels, des interruptions et des changements d’heure.
- Une comparaison de quatre cycles reste bornée et explicite sur la granularité affichée.
- La synthèse visitée est disponible après coupure réseau, datée et en lecture seule ;
  les détails absents le signalent et aucune requête mutante n’est rejouée.
- Un test de taille de réponse et un parcours navigateur avec historique rempli protègent
  contre le dépassement reproduit lors de l’audit.
- Relever les temps de réponse et tailles obtenus sur une charge représentative hors matériel.
  Distinguer ces mesures de toute qualification future des performances sur le Pi.

## 6. Lot C — Compléter un parcours repris en cours de cycle

Points d’entrée : `model/culture.py`, `utils/culture_store.py`,
`network/web/templates/cultures.html`, `network/web/static/js/cultures.js`.

- [ ] Ajouter une action explicite pour renseigner une étape passée connue, distincte du
  changement de stade courant.
- [ ] Proposer les étapes admissibles à leur date effective, y compris sur une fiche déjà
  en floraison, en séchage ou archivée, sans imposer de modifier artificiellement sa clôture.
- [ ] Permettre de compléter un déplacement historique manquant lorsque le parcours et
  l’occupation peuvent être revalidés ; aucun déplacement partiel du lot.
- [ ] Préserver date effective, date de saisie, précision et fuseau, et revalider tout le
  parcours, les occupations et les liens aux solutions avant commit.
- [ ] Afficher les durées des périodes terminées dans le parcours et la comparaison des
  cycles, avec la même convention calendaire que les compteurs existants.

Critères d’acceptation :

- Créer un lot déjà en floraison dans l’espace 2, puis ajouter ses anciennes étapes connues
  et son occupation initiale dans l’espace 1 depuis le navigateur.
- Le stade courant reste floraison, son compteur reste exact et l’attribution des solutions
  est recalculée selon les dates d’occupation corrigées.
- Une chronologie impossible ou un conflit d’occupation est refusé atomiquement.
- Couvrir dates approximatives, instants, minuit, changements d’heure, horloge non fiable,
  onglet périmé et conservation des anciennes versions.

## 7. Lot D — Vérifications déclaratives corrigibles

Points d’entrée : `utils/culture_cycle_store.py`, `network/web/culture_cycles.py`,
`network/web/templates/culture_cycles.html`, `network/web/static/js/culture_cycles.js`.

- [ ] Ajouter révisions, motif et annulation visible aux listes de vérification.
- [ ] Préserver le contexte historique de la vérification : culture, espace, stade, date
  effective et date de saisie ; distinguer ce contexte du stade actuellement affiché.
- [ ] Définir le traitement d’une correction de parcours qui contredit une vérification
  déjà enregistrée : signaler le conflit ou demander sa correction, sans réécriture silencieuse.
- [ ] Appliquer version attendue et idempotence ; aucune case ne commande un équipement.
- [ ] Inclure toutes les versions dans l’export et l’exercice de restauration.

Critères d’acceptation : une case cochée par erreur peut être corrigée, une vérification
peut être annulée sans disparition de l’historique, un onglet ancien reçoit un conflit et
une modification rétrospective du parcours ne laisse pas un contexte contradictoire invisible.

## 8. Lot E — Plages cibles pH/EC facultatives et historisées

- [ ] Définir un modèle de plages cibles avec cible et période de validité explicites,
  version, précision temporelle et contexte de solution ou de culture.
- [ ] Définir et documenter la résolution du contexte quand un lot change d’espace ou de
  solution ; ne pas appliquer rétroactivement la plage actuelle aux anciennes mesures.
- [ ] Permettre la saisie d’une plage pH seule, EC seule ou des deux, ainsi que leur fin
  de validité, correction et annulation traçables.
- [ ] Accepter la virgule décimale, normaliser explicitement l’EC en mS/cm, refuser NaN,
  infini, minimum supérieur au maximum et périodes contradictoires.
- [ ] Afficher les plages contextualisées sur les courbes et dans les consultations/exportations.
  Ne fournir aucune plage par défaut, diagnostic causal, dosage ou alarme de contrôle.

Critères d’acceptation : deux périodes successives gardent leurs propres cibles après
modification ; une période sans cible reste sans cible ; renouvellement et changement de
lot ne mélangent pas les contextes ; corrections, migrations, exports et restauration sont testés.

## 9. Lot F — Repères d’éclairage et état opérationnel

- [ ] Ajouter des repères d’exploitation informatifs modifiables, notamment les références
  18 h / 6 h en végétatif et 12 h / 12 h en floraison prévues au plan.
- [ ] Conserver leur contexte et leurs versions ; ne pas les traiter comme une prescription
  universelle ou un profil à appliquer à la configuration.
- [ ] Présenter ensemble le stade déclaré, le repère applicable, les horaires effectivement
  configurés, l’activation et l’état opérationnel déjà disponibles.
- [ ] Montrer les règles jour/nuit pertinentes et la ventilation commune en réutilisant les
  sources existantes, sans nouveau calcul de régulation ni acquisition matérielle.
- [ ] Afficher un écart au repère comme information avec accès aux réglages existants.
  Préciser qu’un état GPIO ne prouve pas le fonctionnement physique d’un équipement.

Critères d’acceptation : modifier un repère ne change ni horaires ni sorties ; horaires
traversant minuit, équipement désactivé, état indisponible et consultation hors ligne sont
présentés correctement ; aucune alarme de contrôle nouvelle n’est créée.

## 10. Lot G — Affectations d’équipements datées

Points d’entrée : `param/equipment_metadata.py`, magasins de culture et vues du carnet.

- [ ] Conserver les identifiants et noms courants du catalogue existant comme source de
  vérité ; ajouter uniquement les associations métier historiques dans le carnet.
- [ ] Modéliser les périodes de validité des associations aux espaces/réservoirs et les
  changements d’usage, notamment les deux usages possibles de `cyclic_2`.
- [ ] Résoudre le contexte d’un événement à sa date effective et conserver la provenance
  du contexte ainsi que sa date de saisie.
- [ ] Préserver les anciennes copies de catalogue. Lors de la migration, les identifier
  comme contexte connu à la saisie, sans inventer de dates de réaffectation passées.
- [ ] Rendre les périodes consultables et corrigeables avec révisions et validation des
  contradictions ; ne modifier ni câblage ni réglages d’équipement.

Critères d’acceptation : après changement d’usage de `cyclic_2`, une intervention
rétrospective retrouve l’association connue pour sa date ; si elle est inconnue, l’interface
le signale. Renommer un équipement ne réécrit pas les anciens libellés enregistrés.

## 11. Lot H — Journal transversal et observations d’espace

- [ ] Ajouter une consultation paginée filtrable par période, cible et type couvrant notes,
  pertes, stades, déplacements, récoltes et interventions structurées.
- [ ] Conserver les liens vers fiches, solutions, photos, corrections et versions précédentes.
  Une entrée multi-cibles reste une opération unique dans le journal global et ses totaux.
- [ ] Ajouter une cible d’observation explicite pour chaque espace, sans créer une fausse
  plante pour porter la note et sans déplacer les notes dans l’historique purgé à 72 h.
- [ ] Permettre les photos facultatives sur ces observations avec les mêmes limites,
  validations, sauvegardes et règles de consultation que les autres photos.
- [ ] Permettre correction et annulation traçables, pagination stable, export du filtre et
  accès daté en lecture seule aux pages effectivement conservées par la PWA.
- [ ] Préserver les filtres et les champs en cas d’échec, et neutraliser les textes dans les CSV.

Critères d’acceptation : retrouver les observations d’un espace même vide, les interventions
d’une mère et les événements d’un lot archivé sur une période choisie ; vérifier absence de
doublon des arrosages partagés, liens à travers la pagination et restauration base/photos.

## 12. Lot I — Validation consolidée et clôture

- [ ] Pour chaque changement Python, exécuter la suite pytest complète conformément aux
  instructions du dépôt ; ajouter les tests métier des nouveaux scénarios et des régressions.
- [ ] Exécuter les parcours Playwright concernés pendant les lots, puis la suite complète
  sur bureau, téléphone, écran étroit, paysage et profil PWA à la clôture.
- [ ] Vérifier accessibilité, clavier, champs conservés après erreur, conflits, double clic,
  réponse perdue et absence de rejeu hors ligne avec des carnets remplis.
- [ ] Tester chaque chemin de migration supporté, son interruption, le refus d’écriture,
  le schéma futur, la corruption et la conservation des données antérieures.
- [ ] Refaire une sauvegarde/restauration ZIP sur copie isolée avec données anciennes et
  nouvelles, révisions, liens, plages, associations, vérifications, rappels et photos.
- [ ] Vérifier que toutes les actions de culture laissent la configuration et les GPIO
  inchangés, et qu’une panne du carnet ne dégrade pas la santé du contrôle.
- [ ] Actualiser le guide illustré, le contrat API, la procédure de sauvegarde/restauration,
  la roadmap et le plan de référence pour refléter exactement la livraison finale.
- [ ] Vérifier `git diff --check` et `diff -u CLAUDE.md AGENTS.md` ; toute modification des
  instructions doit être identique dans les deux fichiers.
- [ ] Consigner pour chaque lot son commit, ses tests, ses résultats et ses limites résiduelles.

La clôture exige que chaque écart A à H ait une preuve de réalisation et de validation,
ou un retrait explicite du périmètre validé par l’exploitant. Une limite ajoutée dans un guide
ne suffit pas à transformer une exigence non livrée en exigence satisfaite.

## 13. Hors périmètre et suivi

Les exclusions du plan initial restent inchangées : commande des équipements par stade,
dosage automatique, fractionnement et récoltes partielles, classement de performance par mère,
cloud, comptes utilisateurs, commandes hors ligne et nouveaux capteurs/GPIO.

La préparation et l’autorisation du déploiement restent séparées. Ce plan ne demande aucune
intervention sur le Pi pour commencer les corrections et leur validation hors matériel.

| Lot | Statut | Commit de livraison | Validation / limites |
| --- | --- | --- | --- |
| A | À faire | — | — |
| B | À faire | — | — |
| C | À faire | — | — |
| D | À faire | — | — |
| E | À faire | — | — |
| F | À faire | — | — |
| G | À faire | — | — |
| H | À faire | — | — |
| I | À faire | — | — |
