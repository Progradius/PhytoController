# Carnet de cultures — lot UI 2, parcours quotidiens

Réalisation du lot 2 de l’audit UI du 8 septembre 2026. Le périmètre est celui des parcours
quotidiens : accueil « Aujourd’hui », fiche complète, saisie guidée, création et reprise,
observation et photo, erreurs associées aux champs. Aucune migration, aucune persistance
nouvelle, aucune commande d’équipement, aucune donnée de production touchée ; le DDL du
schéma 4 est intact.

Organisation : conception par un agent, challengée sur dix points avant exécution (collision
de la clé `today`, triade d’actions, rappels actionnables, accessibilité du socle d’erreurs,
retour de focus, création sans JavaScript, photos, archives, ordre des validations, manques),
puis six lots de travail sur des fichiers disjoints, vérifiés et commités un par un, et une
revue indépendante du diff complet avant clôture.

## Comportement livré

- **Accueil.** Un bloc « Aujourd’hui » ouvre `/cultures` : rappels en retard, du jour et
  terminés aujourd’hui, avec « Fait » et « Reporter » directement depuis la carte (la date de
  report n’apparaît qu’au choix du report ; sans JavaScript elle reste visible), le nombre de
  rappels à venir, les cinq dernières opérations du journal transversal avec un seul lien
  chacune, trois raccourcis (relevé, observation, nouvelle culture) et une recherche locale
  dans la liste. Un carnet vide propose « Ajouter ma première culture ». Les archives ont leur
  titre et n’affichent ni agenda ni occupation actuelle. À 393 px, le premier rappel en retard
  est visible sans défilement.
- **Fiche.** Un en-tête permanent (nom, variété, espace, stade et âge du stade, effectif),
  puis la triade « Relevé » (lien vers la saisie de solutions avec cible et intention
  présélectionnées), « Observation / photo » et une action de parcours contextuelle (stade
  suivant, déplacement, récolte, fin de séchage, archivage, libération) issue de la règle pure
  `fiche_actions`. Les autres opérations sont repliées. Cinq vues locales par ancres : Synthèse
  (parcours, origines, rappels du sujet, vérifications pertinentes), Journal (entrées avec
  traçabilité repliée), Relevés (dernier relevé, y compris sur une fiche archivée), Photos
  (toutes les photos du sujet), Bilan. Après un enregistrement, l’entrée créée reçoit le
  focus et la mention « Entrée ajoutée ».
- **Observation et photo.** Un seul formulaire, deux requêtes : la note est enregistrée,
  puis la photo est rattachée à la révision renvoyée. Aperçu avant envoi, progression, et échec
  partiel géré : la note reste enregistrée, la photo seule peut être réessayée ; si la fiche a
  changé entre-temps, un lien propose de la recharger.
- **Solutions.** Quatre intentions en tête (mesurer, arroser, renouveler, ajouter de l’eau)
  conservent la cible et la période ; `?kind=` présélectionne le type d’une saisie neuve, jamais
  d’une correction, et ouvre la saisie. Ancres locales vers réservoirs, courbes et journal.
- **Création et reprise.** « Je démarre une culture » ou « Elle est déjà en cours ». En mode
  démarrage, le premier stade du parcours et la date d’origine sont repris ; jamais une date
  n’est inventée. La bascule rend les trois dates indépendantes. Un récapitulatif avant
  validation est reconstruit depuis les champs, sans réordonnancement ni région vivante.
- **Erreurs au champ.** Les API cultures, solutions et journal renvoient `field` (attribut
  `name` du contrôle) et `index` pour les listes répétées. Ce n’est **pas** le cas de toutes
  les API du carnet : plages cibles, éclairage, équipements, vérifications et photos refusent
  encore sans `field`, leur message n’est alors rattaché à aucun contrôle (remédiation R3.3 du
  [plan du 9 septembre](remediation-ui-cultures-lots-2-3-2026-09-09.md)). Le socle `culture_forms.js` rend un résumé `role="alert"`
  avec un lien par champ, marque le contrôle (`aria-invalid`, `aria-describedby` fusionné puis
  restauré), ouvre les replis et place le focus ; la saisie n’est jamais effacée. Une seule
  erreur est remontée par requête ; la prévalidation de la création suit l’ordre du formulaire.
- **Règles pures.** `allowed_actions`, `stage_options`, `first_stage`, `creation_stages`,
  `fiche_actions` et `reminder_buckets` vivent dans `model/` ; le gabarit n’a plus de condition
  d’action ni de rang de stade, le script ne choisit plus de stade. Le bloc « Aujourd’hui » se
  calcule dans `_overview` sans projection supplémentaire.

Le renommage de la navigation globale (« Aujourd’hui · Cultures · Journal · Ressources »)
reste à valider sur des parcours représentatifs ; les suggestions et prévalidations relèvent
du lot 3, la comparaison alignée, les courbes tactiles et la galerie du lot 4.

## Corrections après revue indépendante

- Création d’un lot en séchage hors de l’espace 2 : refus désormais rattaché au champ
  « Espace actuel » avec le message de la projection.
- Dernier relevé absent sur une fiche archivée ou au-delà de la 40ᵉ culture : `detail`
  porte maintenant `latest_reading`.
- `index` d’erreur désaligné quand le client filtrait les origines ou les produits avant
  l’envoi : le rang envoyé est traduit vers le rang affiché.
- Les formulaires de rappel et de photo pilotés par `culture_cycles.js` n’adoptaient pas le
  socle d’erreurs ; ils y passent entièrement, comme la convention l’annonçait.
- Reprise d’une photo refusée en 409 : lien « Recharger la fiche » au lieu d’un réessai
  condamné.
- Conflit 409 affiché dans l’état du formulaire au lieu du résumé ; corrigé.
- Rappel en retard hors écran à 393 px : rappels avant les raccourcis, liens de rubrique
  sous l’agenda, mise en page mobile resserrée.
- Documentation alignée sur le code : `stage_options_full`, coût réel de l’agenda, clé
  d’idempotence unique par formulaire, route statique du socle, API sans `field`, recopie qui
  cesse au basculement, limite « bouture » sans JavaScript.
- Accessibilité et style : bordure des `textarea` refusés, message d’erreur dans le label
  (sous son champ, même en grille), cibles de 44 px sur les replis du carnet, récapitulatif
  masqué sans script.

## Validation

Validation locale sur les bases temporaires du serveur sans matériel ; les tests mutateurs
refusent une cible `PHYTO_UI_BASE_URL` externe. Aucun essai ni déploiement sur le Pi.

- Python : `601 passed` (référence du lot 1 : 363), dont les tests d’équivalence des
  actions sur 126 états, des champs d’erreur, de l’agenda et de l’ordre de prévalidation.
- Playwright, suite du carnet (lots A à H, lot UI 1, lot UI 2, visuel) avec un serveur par
  test, un worker par profil :

  | Profil | Résultat |
  | --- | --- |
  | desktop-chromium | 36 réussites, 0 échec |
  | mobile-chromium | 31 réussites, 0 échec |
  | mobile-etroit | 26 réussites, 0 échec |
  | mobile-paysage | 24 réussites, 0 échec |
  | pwa-chromium | 10 réussites, 0 échec |

  Les écarts entre profils sont des exclusions déclarées par les tests (mutations réservées
  à certains formats, PWA en lecture seule), pas des échecs masqués.
- Captures pleine page produites hors dépôt aux largeurs 1 440, 393 et 320 px, thèmes normal
  et plein jour, sur sept états : accueil vide, accueil renseigné (rappels en retard et du
  jour, note, relevé), fiche renseignée, création, solutions avec intention, fiche archivée,
  archives. Données fictives. La barre mobile fixe apparaît à la position du viewport initial
  dans une capture pleine page ; ce n’est pas une barre supplémentaire.

- Spec `tests/ui/cultures_ui_lot_2.spec.js` : accueil vide et renseigné, rappel actionnable
  et visible à 393 px, fiche renseignée et archivée, observation avec photo et échec partiel,
  erreur au champ, conflit 409, intentions des solutions, création dans les deux modes, axe et
  absence de débordement sur quatre pages en thèmes normal et plein jour, y compris l’état
  d’erreur.
- `diff -u CLAUDE.md AGENTS.md` vide ; `git diff --check` vide ; `pyflakes` sans alerte
  nouvelle ; aucun script ni style inline ; aucun accès SQLite hors du thread du magasin ;
  schéma 4 et `param/` intacts.

Limites : aucune étude avec des utilisateurs, aucun téléphone physique, lecteur d’écran,
Safari/iOS ni Firefox ; une seule erreur remontée par requête ; sans JavaScript, la ligne
« bouture » d’un lot reste masquée (limite antérieure au lot).

**Le carnet ne fonctionne pas sans JavaScript.** Aucun formulaire du carnet ne porte
d’attribut `method` ni `action` : tout passe par `fetch` depuis `culture_forms.js`. Sans
script, les pages restent lisibles et les champs restent visibles — c’est tout ce que
garantissent les mentions « sans JavaScript » ci-dessus — mais **aucune saisie n’est
envoyable**. Un repli natif serait un choix d’architecture à décider séparément, pas une
propriété du lot 2.
