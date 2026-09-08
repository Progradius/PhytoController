# API du carnet de cultures (v1, livraisons 1 à 3)

Toutes les routes sont locales, dynamiques et `no-store`. Les POST exigent le jeton existant
`X-CSRF-Token`, le Host autorisé et la même origine que le serveur. Corps JSON limité à 64 KiB.
Les actions sont déclaratives, sans accès GPIO et sans écriture de configuration.

## Lecture

| Requête | Contenu |
| --- | --- |
| `GET /api/v1/cultures?archives=0&offset=0` | Jusqu'à 40 cultures actives, total, occupation des deux espaces et catalogue des mères |
| `GET /api/v1/cultures?archives=1&offset=0` | Jusqu'à 40 cultures archivées ; occupation indépendante de l'archivage |
| `GET /api/v1/cultures/{id}?offset=0` | Fiche projetée, périodes, origines, descendants et 40 événements avec anciennes révisions |
| `GET /api/v1/cultures/export?format=json` | Export `phyto-cultures`, version de schéma, date et toutes les tables |
| `GET /api/v1/cultures/export?format=csv` | Journal complet, révisions comprises, UTF-8 avec BOM |
| `GET /api/v1/cultures/export?format=sqlite3` | Sauvegarde cohérente SQLite téléchargeable |

Les réponses comprennent le fuseau et la fiabilité de l'horloge. L'âge comporte `days`, `weeks`,
`remaining_days`, `week`. Les occupations du détail contiennent des clés UTC de comparaison ;
ce ne sont pas des heures effectivement observées quand la précision était une date seule.
Les dates d'événements conservent leur valeur et leur `precision` originales.

## Création : `POST /api/v1/cultures`

Exemple fictif de reprise d'un lot de semis déjà en floraison :

```json
{
  "operation": "create",
  "request_id": "identifiant-unique-de-la-saisie",
  "kind": "lot",
  "name": "Lot septembre",
  "variety": "Variété A",
  "origin_type": "seed",
  "origins": [{"label": "Semences A", "count": 8}],
  "origin_at": "2026-08-01",
  "origin_precision": "date",
  "stage": "floraison",
  "stage_at": "2026-08-15",
  "stage_precision": "date",
  "space": "space_2",
  "space_at": "2026-08-10",
  "space_precision": "date"
}
```

Une mère utilise `kind=mother`, `stage=maintien`, `space=space_1`, aucune origine et un nom
distinct des autres mères, archives comprises. Pour un lot de boutures : `origin_type=cutting`
et une ligne par mère `{ "mother_id": "uuid", "count": 3 }`. Maximum 50 origines et 10 000 plantes
par origine. Création, origines et événements initiaux forment une seule transaction.

Les précisions acceptées sont `date`, `approximative` (date ISO) et `instant` (ISO avec fuseau).
Ne pas envoyer de date future. En absence d'horloge synchronisée, `confirm_date: true` est requis
après vérification opérateur ; le manque de fiabilité reste enregistré.

## Événements et corrections

```json
{
  "operation": "event",
  "request_id": "autre-identifiant-unique",
  "subject_id": "uuid-du-lot",
  "version": 1,
  "kind": "note",
  "effective_at": "2026-09-07",
  "precision": "date",
  "payload": {"note": "Observation de la journée"}
}
```

| `kind` | `payload` |
| --- | --- |
| `note` | `note` obligatoire, maximum 4 000 caractères |
| `stage` | `stage` : germination, enracinement, vegetatif, floraison ou maintien selon le parcours |
| `move` | `space` : space_1 ou space_2, lot entier |
| `loss` | `count`, `origin_id` facultatif (identifiant de ligne d'origine), `note` facultative |
| `harvest` | `note`, `drying_at` et `drying_precision` facultatifs ; séchage à la date de coupe par défaut, jamais avant |
| `finish` | `weight_g` facultatif (nombre fini, ≥0), `note`, `release` booléen, faux par défaut |
| `release` | Objet vide ; culture terminée |
| `archive` | `note` facultative ; pied mère seulement |
| `identity` | `name`, `variety` facultative |

La correction utilise `operation=correct`, `event_id`, la **version de la fiche**, la nouvelle
date/précision et le payload complet de l'événement. `cancelled: true` annule l'entrée ; sa
révision précédente demeure. `reason` facultatif, 500 caractères maximum. Le type d'événement
reste celui de l'entrée d'origine. `create` ne peut pas être ajouté ou annulé, mais sa date peut
être corrigée. Son payload peut également porter `origins` pour corriger les effectifs ou filiations :
conserver l'`id` de chaque ligne existante. Les anciennes valeurs sont conservées dans les révisions.
Le serveur rejoue le parcours et vérifie les occupations et filiations avant commit.

Succès : `{ "saved": true, "subject_id": "uuid", "version": 2 }`.
Une même clé avec le même corps retourne le résultat initial même après d'autres modifications ;
une même clé avec un corps différent est refusée. Réutiliser la même clé lors d'une réponse perdue.
Les contrôles d'idempotence et de version se font dans la transaction SQL, pas dans le navigateur.

Erreurs : `400` validation, `403` CSRF/origine, `404` fiche absente, `409` version ou clé en conflit,
`413` corps trop grand, `503` stockage incompatible/indisponible ou file auxiliaire saturée.
Les erreurs métier JSON portent `error`. Les erreurs des middlewares existants peuvent être texte
ou HTML selon Accept ; les clients ne doivent pas supposer du JSON pour tout refus.

### Étapes passées d'un parcours repris — `operation: "backfill"`

Renseigne les étapes **antérieures** connues d'une culture reprise en cours de cycle, sans
changer son stade courant ni sa clôture. Distincte de `event` : elle refuse toute étape qui
n'est pas dans le passé du stade affiché.

```json
{
  "operation": "backfill",
  "request_id": "identifiant-unique",
  "subject_id": "uuid-du-lot",
  "version": 3,
  "steps": [
    {"kind": "stage", "effective_at": "2026-06-05", "precision": "date",
     "payload": {"stage": "enracinement"}, "reason": "Carnet papier"},
    {"kind": "move", "effective_at": "2026-06-10", "precision": "instant",
     "payload": {"space": "space_1"}}
  ]
}
```

- `steps` : 1 à 12 étapes, écrites **toutes ou aucune** dans la transaction de la commande.
  Un refus ne laisse ni événement, ni clé dans `requests` : la même clé reste utilisable.
- `kind` vaut `stage` ou `move` uniquement. Récolte, fin de séchage, archivage et libération
  restent des événements de clôture, corrigés par `correct`.
- `precision` (`date`, `approximative`, `instant`), fuseau et date de saisie suivent les mêmes
  règles que `event` ; chaque étape devient un événement révisable et corrigible.
- Un `stage` doit figurer dans les étapes admissibles publiées par `GET /api/v1/cultures/{id}` :
  stades du parcours antérieurs au stade courant et encore absents. Un `move` vise `space_1` ou
  `space_2` (`space_1` seul pour un pied mère) et déplace le lot entier.
- La date effective doit être **strictement antérieure** au début du stade courant. À date égale,
  l'ordre ne dépendrait que de la séquence d'insertion : la commande est refusée (`400`).
- Le parcours entier, l'occupation des espaces et les intersections occupation/solution sont
  rejoués et revalidés avant commit ; l'attribution des solutions suit les occupations corrigées.
- `version` attendue et `request_id` s'appliquent comme pour `event` (`409` sur onglet périmé).
  Fonctionne aussi sur une fiche en floraison, en séchage ou archivée.

`GET /api/v1/cultures/{id}` porte pour cela :

```json
{"backfill": {"stages": ["germination", "vegetatif"],
              "spaces": ["space_1", "space_2"], "before": "2026-08-01"}}
```

`stages` vide signifie qu'aucune étape antérieure ne manque. `before` est le début du stade
courant, borne stricte des dates acceptées.

Chaque période de `subject.periods` porte désormais `duration`, calculée comme les compteurs
existants (`{"days", "weeks", "remaining_days", "week"}`, jours calendaires locaux). Une période
encore ouverte est comptée jusqu'à aujourd'hui. Ces périodes alimentent aussi la comparaison des
cycles.

## Persistance et compatibilité

Schéma SQLite initial 1 : `settings`, `subjects`, `origins`, `events`, `requests`.
`events` conserve chaque révision, la précision, la date de saisie, la fiabilité d'horloge et
le catalogue d'équipements connu lors de l'enregistrement. La vue courante est une projection
des dernières révisions ; elle n'est pas une seconde vérité mutable.

Les accès ont un thread unique, une file de huit travaux maximum, des transactions et
`synchronous=FULL`. Une déconnexion HTTP ne signifie pas que la transaction a été annulée.
Les clés d'idempotence sont conservées avec le carnet. Il n'y a aucune purge de 72 h.
Une version de schéma inconnue est refusée sans recréer la base. Toute évolution future exige
sauvegarde cohérente préalable et migration explicite, testée sur copie.

La restauration est une opération locale documentée dans `docs/operations/cultures.md` ; aucune
route d'import ou d'écrasement de base n'est exposée. Le JSON est un export, pas un format
d'import automatiquement accepté par cette version.


## Solutions et relevés — jalon 2

`GET /api/v1/cultures/solutions` accepte `target` (réservoir ou culture), `kind`,
`start` et `end` (dates locales inclusives), `offset`. Le journal contient 40 dernières
révisions par page, annulations visibles, avec `revisions`. Les cibles possibles sont
`reservoir_2` (espace 2), `cuttings_1` (bac de bouturage espace 1), ou les UUID des cultures.
La réponse fournit aussi `reservoirs`, `recipes`, `subjects`, `periods`, `links`, `latest`,
`interventions` (fenêtre de 200 pour le sélecteur, voir ci-dessous), `chart`, `stages`,
`chart_aggregated` et `chart_truncated`.

### Retrouver une intervention ancienne (lot A)

`interventions` contient les 200 interventions les plus récentes **plus** celles déjà associées
aux relevés de la page affichée : une correction ne peut donc jamais perdre son lien parce que
l'intervention est sortie de la fenêtre. Chaque élément porte `id`, `kind`, `effective_at`,
`reservoir_id`, `targets`, `target_label` (réservoir ou cultures visées), `cancelled` et
`linked`. La réponse ajoute `interventions_total`, `interventions_offset`, `interventions_search`
et `interventions_page` (taille de fenêtre, 200).

`GET /api/v1/cultures/solutions?interventions=<texte>[&interventions_offset=<n>]` bascule en
**recherche bornée** : la réponse ne contient alors que ce bloc d'interventions, sans journal,
courbe ni agrégat. Le texte (100 caractères au plus) est cherché, sans casse, dans le type, la
date effective, la cible et la référence ; `interventions_offset` pagine par 200 de la plus
récente à la plus ancienne. Un texte trop long renvoie 400, un offset hors bornes aussi. Aucune
requête ne charge tout le carnet dans un sélecteur.

`chart` couvre le filtre indépendamment de la pagination. Jusqu'à 1 000 entrées, chaque point
représente une mesure ; au-delà, regroupement par date locale, cible et période de solution :
`ph`/`ec` sont les moyennes, les champs suffixés `_min`, `_max`, `_count` décrivent l'étendue
et la couverture. Aucune valeur absente n'est convertie en zéro. Au maximum 2 000 groupes
récents sont rendus, avec indication explicite de troncature. `annotations` contient les
interventions du groupe ; `stages` les repères déclaratifs des cultures concernées.

`GET /api/v1/cultures/solutions/export` accepte les mêmes filtres (hors pagination) et exporte
un CSV tabulaire UTF-8/BOM, EC en mS/cm, températures en °C et volumes en L. Les colonnes
`targets` et `fed_subjects` séparent les cibles manuelles de l'attribution par solution.
Une ligne d'arrosage commun conserve son **unique volume total**, quel que soit le nombre de
mères. Les cellules textuelles pouvant être des formules sont neutralisées. Les dernières
révisions, y compris annulations, sont exportées ; les anciennes restent dans le JSON/SQLite
complet du carnet, maintenant de schéma 2.

### Enregistrer : `POST /api/v1/cultures/solutions`

Exemple fictif de renouvellement (aucune recommandation de produit ou dosage) :

```json
{
  "operation": "entry",
  "request_id": "cle-renouvellement-unique",
  "kind": "renewal",
  "reservoir_id": "reservoir_2",
  "effective_at": "2026-09-07",
  "precision": "date",
  "volume_l": "20,5",
  "ingredients": [{"product": "Produit saisi par l’exploitant", "quantity": 5, "unit": "mL"}],
  "ph": "6,1",
  "context": "after"
}
```

| Champ | Contrat |
| --- | --- |
| `operation` | `entry`, `correct` ou `recipe` |
| `kind` | `reading`, `renewal`, `water`, `topup`, `nutrient`, `ph` |
| `reservoir_id` / `targets` | Un réservoir **ou** un tableau d'UUID de cultures ; plusieurs cibles uniquement pour des mères (50 maximum) |
| `ph`, `ec` | Facultatifs, au moins un obligatoire pour `reading` ; zéro distinct de l'absence |
| `ec_unit` | `mS/cm` par défaut ou `µS/cm` (division par 1 000) ; aucun ppm/TDS |
| `temperature_c`, `volume_l` | Facultatifs ; volume strictement positif pour renouvellement/appoint |
| `context` | `independent` par défaut, `before`, `after` |
| `intervention_id` | UUID requis pour un relevé avant/après ; cibles identiques et ordre temporel compatible |
| `compensation` | `unknown`, `yes`, `no` : information de l'instrument seulement |
| `ingredients` | Maximum 40 objets `{product, quantity, unit}`, unités `mL`, `g`, `L`, `mg` |
| `note`, `reason` | Maximum 4 000 et 500 caractères respectivement ; jamais journalisés |

Les nombres sont finis, acceptent la virgule française et les chaînes numériques. Bornes de
validation : pH 0–14, EC normalisée 0–100 mS/cm, température −20–100 °C, volumes et quantités
0–1 000 000. Ce sont des limites de saisie, pas des plages agronomiques conseillées.

Les arrosages visent une culture ou plusieurs mères et peuvent conserver une préparation commune.
Les appoints d'eau ne contiennent pas de produits ; utiliser `nutrient` ou `ph` pour un ajout
quantifié. Les relevés associés à une préparation sont après intervention ; un relevé préalable
est une saisie distincte liée par `intervention_id`. Si un relevé **avant renouvellement** possède
la même date/heure que celui-ci, il appartient à la période précédente ; le relevé après appartient
à la nouvelle. Préciser l'heure pour distinguer deux renouvellements dans la même journée.

Un réservoir nécessite une déclaration initiale `renewal` avant les interventions/relevés.
Chaque renouvellement ferme l'ancienne période et ouvre la suivante atomiquement. Modifier
un parcours recalcule aussi les intersections solution/occupation ; celles-ci cessent à la
coupe, pas à la fin du séchage. Les mères ne sont jamais automatiquement alimentées par le bac.
Un arrosage postérieur à la coupe/archivage est refusé. Changer de lot ne renouvelle pas la solution.

### Recettes, préparation figée et corrections

`operation=recipe` utilise `name`, `volume_l` (volume de référence >0), `ingredients` non vide,
`request_id`. Pour une nouvelle version, envoyer aussi `id` et `version` courante.
Une préparation utilisant une recette transmet `recipe_id`, `recipe_revision`, `volume_l` et
les `ingredients` **déjà affichés à l'opérateur**, quantités multipliées par
`volume_l / volume_de_reference`. Le serveur vérifie cet aperçu puis conserve une copie.
Le changement de recette ne modifie aucune préparation enregistrée.

`operation=correct` exige `id`, `version` (révision de l'entrée) et la saisie complète.
Le type `kind` ne change pas. `cancelled=true` annule sans effacer ; `reason` documente la correction.
Toute la chronologie est revalidée : par exemple on ne peut pas annuler un renouvellement utilisé
par un relevé avant/après sans corriger d'abord ce lien. Les révisions passées sont conservées.

Succès : `{"saved": true, "id": "uuid", "version": 1}`. Idempotence, conflits, horloge incertaine,
CSRF, limite de corps et codes d'erreur suivent le contrat de création des cultures ci-dessus.
Les pages `/cultures/solutions?target=...` utilisent en plus `entry=uuid` pour ouvrir la bonne
page du journal après une saisie rétrospective ; les liens « Intervention … » du journal
emploient `?entry=uuid#entry-uuid` sans filtre, afin d'atteindre une destination absente de la
page ou du filtre courant.

Une correction (`operation: "correct"`) qui **ne mentionne pas** `intervention_id` ou `context`
conserve les valeurs de la révision précédente : corriger un pH seul ou une note seule ne perd
ni ne change l'association. Fournir `"intervention_id": null` reste le moyen explicite de
détacher un relevé. Une association incohérente (cibles, réservoir ou contexte avant/après
contradictoires) est refusée en bloc, sans écriture partielle, et une nouvelle tentative
identique ne crée aucun doublon.

### Schéma 2 et migration

Les tables supplémentaires sont `reservoirs`, `recipes`, `solution_entries`, `solution_targets`,
`solution_periods`, `solution_links`. Les préparations sont portées par les interventions datées,
avec volume et ingrédients figés ; un arrosage multiple possède une seule préparation.
Les champs interrogés ont des colonnes explicites ; seul le détail des ingrédients est en JSON.
Les périodes et liens sont des projections reconstruites dans la transaction du carnet.

L'ouverture d'une base de version 1 crée une sauvegarde cohérente
`cultures.sqlite3.before-v2.sqlite3` avant la migration transactionnelle. Si ce chemin existe déjà
avec une base toujours en version 1, le carnet refuse de l'écraser : vérifier cette sauvegarde
et résoudre la tentative précédente selon le guide. Une base de version 2 n'est pas rétrocompatible
avec le code du jalon 1. Le script de restauration accepte des sauvegardes 1 ou 2 et produit
uniquement une copie isolée ; une copie 1 est migrée lors de son ouverture par le nouveau code.

## Cycles, photos et rappels — jalon 3 (schéma 3)

Toutes les mutations gardent CSRF, origine, idempotence et confirmation explicite de date si
l'horloge est incertaine. Les codes 400, 409 et 503 suivent les contrats précédents.
Les actions restent déclaratives et n'écrivent ni configuration ni GPIO.

| Route | Contenu |
| --- | --- |
| `GET /cultures/cycles` | Comparaison, climat, vérifications, rappels, galerie et sauvegarde |
| `GET /api/v1/cultures/cycles` | Données correspondantes ; `subject` répétable (quatre maximum), `offset`, `reminder` pour retrouver sa page |
| `POST /api/v1/cultures/cycles` | Rappel, suivi ou vérification déclarative |
| `POST /api/v1/cultures/photos` | Envoi binaire borné lié à une révision d'événement |
| `GET /cultures/photos/{photo_id}` | JPEG validé, `no-store` |
| `GET /api/v1/cultures/bundle` | ZIP complet : SQLite cohérent, photos, manifeste SHA-256 |

La réponse cycles contient `subjects`, `summaries`, `reminders`, `reminder_total`, `offset`,
`media`, `storage`, `today`, `timezone` et `clock_reliable`. Une seule culture sélectionnée filtre
ses rappels/photos ; sinon leur vue est globale. Les rappels sont paginés par 40, les actifs avant
les clos, et incluent leurs anciennes `revisions`. La galerie montre au plus 100 photos récentes.
Le détail de culture inclut les photos de tous les événements de sa page de journal, même anciens.

### Rappels

Création ou édition avec `operation=reminder`, `request_id`, `target` (UUID de culture ou
`reservoir_2`/`cuttings_1`), `title` (160 caractères), `due_date` (date ISO, 2000–2100),
`interval_days` (entier 0–366), `note` (4 000 caractères maximum). Une édition ajoute `id`
et `version`, conserve les versions antérieures et refuse un rappel déjà clos.

Suivi avec `operation=reminder_action`, `request_id`, `id`, `version`, `action` parmi
`done`, `postponed`, `cancelled`, et une note facultative. Pour `postponed`, `due_date`
est obligatoire et strictement ultérieure à l'ancienne échéance. Pour `done`, une récurrence
positive crée atomiquement une occurrence fille calculée depuis le jour local d'accomplissement,
avec `parent_id`. Aucun rattrapage automatique des occurrences manquées.

Réponse : `saved`, `id`, `version`, `next_id` (UUID de l'occurrence suivante ou `null`).
Un rappel déjà clos refuse une autre action, sauf répétition de la même clé d'idempotence.
Il n'existe aucune notification système de carnet.

### Vérifications et bilan

`operation=checklist` reçoit `request_id`, `subject_id`, `version` du lot courant,
`effective_at` (date sans heure), `checks` contenant exactement les trois booléens
`lighting`, `pump`, `ventilation`, et `note` facultative. Le lot doit être actif ; la date
ne peut précéder le jour local du début de son stade courant. La saisie conserve l'espace,
le stade et les cases sans modifier la version du parcours. Réponse : `saved`, `id`.

L'événement existant `finish` accepte dans son `payload` les champs supplémentaires `lessons`
(4 000 caractères) et `origin_weights` (liste `{origin_id, weight_g}`). Les origines doivent
appartenir au lot, sans doublon ; leur somme ne dépasse pas `weight_g` total lorsqu'il est saisi.
Les anciennes révisions du bilan restent consultables.

### Envoi et conservation des photos

Le corps est binaire `application/octet-stream`, avec le jeton CSRF habituel et
`X-Culture-Metadata` contenant un objet JSON encodé comme `encodeURIComponent(JSON.stringify(...))` :
`request_id`, `subject_id`, `event_id`, `event_revision`, `caption` facultative (500 caractères),
`confirm_date` si nécessaire. L'événement doit appartenir à la culture et ne pas être annulé.
Une révision dépassée reçoit 409. L'empreinte des octets reçus participe à l'idempotence.
Réponse : `saved`, `id` de photo, `subject_id`.

La limite de 5 Mio est vérifiée même sans `Content-Length` ; réception limitée à 30 secondes,
métadonnées à 7 000 caractères. La limite JSON globale reste 64 Kio. Erreurs spécifiques :
413 (taille), 415 (type de corps), 408 (réception trop lente), 400 (photo invalide).

JPEG/PNG/WebP seulement, sans animation, au plus 20 millions de pixels et 8 192 pixels par côté.
Après décodage et orientation, un JPEG RGB de 1 600 pixels maximum est réencodé sans métadonnées.
Quatre images par événement toutes révisions confondues, 5 000 images et 256 Mio au total,
avec réserve disque de 128 Mio. Pas de suppression silencieuse des images référencées.
Les fichiers internes orphelins de plus de 24 h sont nettoyés par lots d'au plus 40 à l'ajout.

### Synthèses, migration et restauration

`CultureService` lit un snapshot par minute, avec traitement dans le thread du magasin.
Les statistiques horaires utilisent exclusivement les valeurs finies, activées, de qualité
`normal` ; le snapshot applique déjà la fraîcheur. Les données absentes/dégradées n'alimentent
pas les valeurs numériques. `valid_count`, `observed_count` et `coverage=valid_count/60`
explicitent la couverture. Les zéros fiables comptent. Aucune acquisition matérielle supplémentaire.
L'horloge non fiable suspend les ajouts ; les minutes répétées sont dédoublonnées.

Chaque synthèse contient `subject`, `periods`, `measures` pH/EC, `checklists`, `climate` et
`climate_detail`. Le climat est commun à la serre ; les heures de bord ne sont pas découpées
à la minute du cycle. Les données purgées de l'historique technique ne sont pas reconstituées.

### Synthèse climatique bornée et détail horaire paginé (lot B)

`climate` couvre **tout** le cycle, du premier au dernier agrégat horaire possible, à une
granularité choisie d'après sa durée : la plus fine de `heure` (3 600 s), `jour` (86 400 s),
`semaine` (604 800 s) ou `quatre semaines` (2 419 200 s) telle que le nombre de périodes reste
sous `MAX_SUMMARY_BUCKETS = 200`. Champs : `granularity_seconds`, `granularity_label`,
`bucket_count`, `sensor_count`, `gap_count`, `gaps_shown`, `truncated`, `start`, `end`,
`start_at`, `end_at` et `points`.

**Convention d'intervalle.** Une période commence à un multiple entier de sa durée depuis
l'époque Unix, exactement comme la clé `hour` de `climate_hours` : `bucket = hour - (hour % pas)`.
La convention est donc **UTC** et invariante au changement d'heure — un seau `jour` est un jour
UTC (jamais un jour local de 23 ou 25 h) et un seau `semaine` commence un **jeudi 00:00 UTC**.
Les heures aux bords du cycle ne sont pas découpées : l'heure qui contient le début du cycle et
celle qui contient sa fin sont incluses entières, mais la période de bord ne compte que les
heures effectivement comprises dans le cycle. `span_hours` donne ce nombre d'heures et sert de
dénominateur aux couvertures ; une première ou dernière période est donc légitimement partielle.

Chaque point porte `sensor`, `label`, `unit`, `hour` (début du seau), `at` (ISO UTC), `minimum`,
`maximum`, `mean`, `valid_count`, `observed_count`, `hours` (heures agrégées présentes),
`span_hours`, `coverage = valid_count / (60 × span_hours)`,
`hour_coverage = hours / span_hours` et `missing`. La moyenne vaut
`SUM(total) / SUM(valid_count)` calculé en SQL : jamais une moyenne non pondérée de moyennes
horaires. `MIN`/`MAX` ignorent les absences. Une période sans agrégat est rendue avec
`missing: true`, `mean: null`, `minimum: null` et des effectifs à zéro — **une lacune, jamais
une valeur nulle**. Les capteurs restent distincts : un point par capteur et par période.
`gaps_shown: false` (ou `truncated: true`) signale que le plafond de points a empêché de
matérialiser toutes les lacunes ; l'interface l'annonce alors explicitement.

`climate_detail` n'est renseigné que pour une **sélection d'une seule culture** ; il vaut `null`
lors d'une comparaison, dont chaque synthèse affiche sa granularité. Il contient `rows`
(agrégats horaires bruts, `mean`, `coverage = valid_count / 60`, `at`), `total` (nombre
d'agrégats en base sur la fenêtre du cycle), `offset`, `page` (60), `previous` et `next`.
L'agrégation, le comptage et la pagination sont faits en SQL borné (`GROUP BY` sur le seau,
`LIMIT`/`OFFSET`) : l'historique n'est jamais lu entièrement pour être ensuite tronqué.

Paramètres de requête supplémentaires sur `GET /cultures/cycles` et
`GET /api/v1/cultures/cycles` : `climate_offset` (entier 0 à 10 000 000, aligné sur la page et
ramené à la dernière page s'il dépasse le total) et `climate_at` (epoch UTC en secondes, 0 à
4 102 444 800, qui positionne la page contenant cet instant). Une valeur hors bornes ou non
entière renvoie 400. Aucun agrégat n'est supprimé ni modifié par ces lectures.

Le schéma 3 ajoute `reminders`, `culture_checklists`, `climate_hours`, `climate_minutes`,
`culture_media`. Les migrations 1 → 2 → 3 sont successives, chaque migration d'une base existante
ayant sa sauvegarde exclusive `.before-v2.sqlite3` ou `.before-v3.sqlite3`.

Le ZIP porte un manifeste `format=phyto-cultures-bundle`, `version=1`, `created_at`,
`files` associant chaque chemin à `size` et `sha256`. La base et les médias sont exportés dans
le même travail du thread propriétaire. La base est limitée à 128 Mio pour cet export.
JSON et SQLite comprennent les références photo, mais seuls les ZIP incluent les images.
Le script `restore-cultures.py --bundle` vérifie puis publie un dossier isolé ; la restauration
SQLite seule accepte les schémas 1, 2 et 3, mais refuse une base qui référence des photos.
Voir le [guide de restauration](../operations/cultures.md#restaurer-une-sauvegarde-complète-sur-copie).

La PWA conserve seulement les pages et photos déjà consultées, datées et bornées en cache,
après succès réseau. Un échec de transport autorise leur lecture seule ; une réponse HTTP
d'erreur ne présente pas silencieusement une ancienne page comme actuelle. Les API restent
hors cache et aucune mutation n'est stockée ou rejouée.

## Schéma 4 et migration

Le schéma 4 est livré **en une seule fois**, avant les lots D à H, pour ne pas retoucher une
migration déjà appliquée. Son DDL est figé dans `utils/culture_schema_v4.py` et n'est plus modifié.

Tables ajoutées : `culture_targets` (plages cibles pH/EC), `culture_light_targets` (repères
d'éclairage), `culture_equipment_links` (affectations d'équipements datées) et `space_events`
(observations d'espace). Elles naissent **vides** : la migration n'invente ni plage par défaut,
ni repère standard, ni date de réaffectation passée.

Tables recréées avec copie intégrale des lignes :

- `culture_checklists` devient versionnée (`PRIMARY KEY(id, revision)`) et gagne `reason`,
  `cancelled`, `equipment_context` ainsi que le contexte de saisie `stage_at`, `stage_precision`
  et `subject_version`. Les lignes migrées prennent la révision 1, `precision='date'` — la seule
  précision que le schéma 3 utilisait — et gardent ces trois colonnes de contexte à `NULL` :
  l'information n'existait pas et n'est pas reconstituée. `clock_reliable` reste `NULL` (inconnu).
- `culture_media` gagne `owner_kind` (`event` ou `space_event`) et deux paires de clés étrangères
  mutuellement exclusives, contrôlées par des `CHECK` et par `PRAGMA foreign_key_check`. Les
  photos existantes deviennent `owner_kind='event'`. Aucun nom de fichier ne change.

Colonne ajoutée : `solution_entries.equipment_context`, `'{}'` valant « catalogue inconnu à la
saisie » pour l'existant. Les saisies neuves y copient le catalogue courant, comme `events`.

Vue ajoutée : `culture_journal`, projection en `UNION ALL` des révisions courantes de `events`,
`solution_entries` et `space_events`, **une ligne par opération** (les cibles sont jointes à la
demande, un arrosage partagé compte donc pour 1). C'est une vue et non une table : une copie
serait une seconde vérité à resynchroniser après chaque correction rétrospective. Elle est
**exclue de l'export** — ses trois sources y figurent déjà — alors que les quatre tables
nouvelles en font partie. Le champ `schema_version` de l'export JSON vaut 4.

Index ajoutés au bénéfice des lectures bornées : `culture_checklists_subject`,
`culture_checklists_recorded`, `culture_targets_window`, `culture_targets_dates`,
`culture_light_scope`, `culture_equipment_window`, `culture_equipment_scope`,
`space_events_space`, `space_events_sort`, `culture_media_owner`, `culture_media_space`,
`events_sort`, `solution_entries_sort`, `solution_targets_subject`, `solution_entries_kind`
et `climate_hours_hour`.

Procédure d'ouverture d'un carnet de version 1, 2 ou 3 : sauvegarde cohérente
`cultures.sqlite3.before-v4.sqlite3` (une par version traversée, `.before-v2` et `.before-v3`
comprises), puis `PRAGMA foreign_keys=OFF` **hors transaction** — indispensable pour recréer une
table enfant, et sans effet à l'intérieur d'une transaction —, `BEGIN IMMEDIATE` suivi du DDL,
`PRAGMA foreign_key_check` **dans** la transaction, `PRAGMA user_version=4`, `COMMIT`, puis
`PRAGMA foreign_keys=ON` dans un `finally`. Une référence pendante ou toute autre erreur provoque
un `ROLLBACK` : la base reste en version 3, intacte, et la sauvegarde `.before-v4.sqlite3`
subsiste. Elle bloque volontairement une nouvelle tentative jusqu'à vérification humaine — voir
le [guide d'exploitation](../operations/cultures.md#lever-une-sauvegarde-before-v4-après-migration-interrompue).
Un `user_version` supérieur à 4 est refusé sans aucune écriture ni retour arrière.

`restore_copy` accepte les schémas 1, 2, 3 et 4. Pour une sauvegarde de version 4 elle exige en
plus la présence de la vue `culture_journal` : une base de version 4 sans elle est un schéma
partiel, pas une base restaurable. Les validateurs de chaque lot sont rejoués à la restauration.
`scripts/restore-cultures.py` est inchangé : il délègue entièrement.

### Lot D — vérifications

Les vérifications sont versionnées (`PRIMARY KEY(id, revision)`) : la ligne courante d'une
vérification est sa révision maximale, exactement comme les rappels et les événements.
Aucune case ne commande d'équipement ; les trois liens de la page ouvrent les réglages existants.

Deux opérations s'ajoutent à `checklist` sur `POST /api/v1/cultures/cycles` :

| Opération | Champs | Effet |
| --- | --- | --- |
| `checklist_correct` | `request_id`, `id`, `version`, `checks`, `note`, `reason`, `effective_at` facultatif | Nouvelle révision non annulée |
| `checklist_cancel` | `request_id`, `id`, `version`, `reason` | Nouvelle révision `cancelled=1` |

`version` est la **révision courante** de la vérification, pas la version du parcours :
une valeur différente, ou d'un autre type qu'un entier, répond `409` (`CultureConflict`).
`reason` est obligatoire (1 à 500 caractères) : une correction sans motif ne se relit pas.
Une annulation n'accepte que son motif et une vérification annulée n'est plus révisable ;
elle reste restituée avec son drapeau, son motif et toutes ses révisions antérieures.
L'idempotence par `request_id` est celle de `_aux_transaction` : rejouer la même clé rend le
même résultat sans créer de deuxième révision. Réponse : `saved`, `id`, `revision`.

Une correction réenregistre le contexte réel à sa date effective (`space`, `stage`,
`stage_at`, `stage_precision`, `subject_version`) ; contrairement à une saisie neuve elle
n'exige pas que la date suive le début du stade courant — sinon une case cochée par erreur
deviendrait incorrigible dès que le lot progresse. Une date antérieure à l'origine reste refusée.

Chaque entrée rendue par `GET /api/v1/cultures/cycles` porte `revisions` (versions
antérieures, croissantes) et le contexte enregistré à la saisie, distinct du stade affiché
aujourd'hui. Les lignes migrées du schéma 3 ont `stage_at`, `stage_precision` et
`subject_version` à `NULL` : la page affiche « contexte non enregistré ».

Le conflit avec une correction rétrospective du parcours est **dérivé à la lecture**, jamais
stocké : le magasin rejoue `project()` et compare `(space, stage)` de la vérification au
contexte réel à sa date effective.

```json
{"conflict": {"expected_stage": "vegetatif", "expected_space": "space_2",
              "recorded_stage": "germination", "recorded_space": "space_1"},
 "conflict_unknown": false}
```

`conflict_unknown: true` remplace le verdict quand `subject_version` est nul ou quand la date
précède la première période : aucun rapprochement n'est possible et rien n'est inventé.
Une vérification annulée n'affirme plus rien, donc ne peut pas être en conflit. Rien n'est
réécrit automatiquement : l'opérateur lève le conflit par une correction ou une annulation.

`_validate_checklists` (rejoué par `restore_copy`) exige des révisions `1..n` sans trou ni
doublon par `id`, des cases et un drapeau d'annulation dans `{0, 1}`, des précisions parmi
`date`, `approximative` et `instant`, et interdit qu'une révision annulée soit suivie d'une
révision active. Toutes les révisions, annulations comprises, figurent dans l'export JSON.

### Lot E — plages cibles

Plages de référence **facultatives** pour la lecture des relevés. Elles ne commandent rien : ni
dosage, ni consigne, ni alarme de contrôle. Aucune plage par défaut n'existe, ni en base ni à
l'affichage : une mesure sans plage applicable est restituée sans bande de référence.

`GET /cultures/targets` — page de saisie et d'historique.
`GET /api/v1/cultures/targets?target=&scope=&offset=` — révisions courantes filtrées (`target` :
identifiant de culture ou de réservoir ; `scope` : `subject` ou `reservoir`), 40 par page, chaque
plage portant ses `revisions` antérieures.
`POST /api/v1/cultures/targets` — deux opérations, idempotentes par `request_id` :

- `operation: "target"` — création (sans `id`) ou correction (`id` + `version`, qui doit être la
  révision courante, sinon **409**). Champs : `target`, `label`, `stage`, `ph_min`, `ph_max`,
  `ec_min`, `ec_max`, `ec_unit` (`mS/cm` par défaut, `µS/cm` converti à l'écriture), `start_at`,
  `start_precision`, `end_at`, `end_precision`, `note`, `reason`.
- `operation: "target_action"` — `action: "end"` (clôture de validité : `end_at`,
  `end_precision`) ou `action: "cancel"` (annulation, `reason` obligatoire).

`GET /api/v1/cultures/targets/export?format=csv` — export dédié des plages ; en-têtes
`ec_min_mS_cm` / `ec_max_mS_cm`, neutralisation CSV identique aux autres exports.

Validation : au moins une borne renseignée (une plage pH seule ou EC seule est légitime), virgule
décimale acceptée, NaN et infini refusés, `min <= max`, `end_sort_at > start_sort_at`. Une
correction ne remet jamais en vigueur une plage annulée. Deux plages courantes non annulées de
même cible ne peuvent pas se chevaucher : la transaction est refusée, rien n'est écrit.

**Règle de résolution du contexte** (`model.culture_targets.resolve_targets`, pure). Pour une
mesure `E` de clé `T = E.sort_at`, on retient les plages dont la révision courante n'est pas
annulée et dont la fenêtre couvre `T` (`start_sort_at <= T < COALESCE(end_sort_at, '9999')`),
dans cet ordre de **priorité stricte** :

1. `scope='subject'` pour un `subject_id` figurant dans `E.targets` (cibles directes) ;
2. `scope='subject'` pour un `subject_id` figurant dans `E.fed_subjects` (sujet alimenté par la
   solution à cette date, via `solution_links`) ;
3. `scope='reservoir'` pour `E.reservoir_id`.

- **Aucune rétroactivité** : c'est la fenêtre contenant `T` qui décide, jamais la plage courante
  du jour. Une mesure antérieure à toute plage n'a pas de cible.
- **Changement d'espace ou de solution** : la résolution se refait mesure par mesure. Un lot
  déplacé de `space_1` vers `space_2` cesse de recevoir la plage de `cuttings_1` et reçoit celle
  de `reservoir_2` à partir de l'instant de l'occupation, parce que `fed_subjects` est reconstruit
  sur les occupations réelles. Un renouvellement ne change pas la plage : elle est indépendante
  des périodes de solution.
- **Sans fusion** : la source retenue fournit ses quatre bornes ou rien. Un `ph_*` d'une source
  n'est jamais combiné avec un `ec_*` d'une autre — cela produirait une cible que personne n'a
  saisie. Quand plusieurs plages d'une même source s'appliquent (arrosage commun à deux mères
  ayant chacune la sienne), la plage commencée le plus tard est retenue et le champ `multiple`
  le signale ; les fenêtres n'interdisent le chevauchement que pour une même cible.
- `stage` est **informatif** : il n'entre pas dans la résolution, pour qu'une correction
  rétrospective de stade ne change pas l'applicabilité d'une plage passée.

Restitution : `GET /api/v1/cultures/solutions` attache à chaque relevé son champ `target`
(`{ph_min, ph_max, ec_min, ec_max, source, source_label, id, label, stage, multiple, …}`) ou
`null`, et fournit `chart_targets` : les bandes de référence des courbes, dérivées des plages
réellement résolues point par point. Une bande n'est jamais prolongée sur une période sans cible.
Un agrégat journalier ne porte une plage que si toutes ses mesures partagent la même. L'export
`GET /api/v1/cultures/solutions/export` gagne deux colonnes `ph_cible` et `ec_cible`, résolues à
la date de chaque relevé et vides en l'absence de cible (bornes EC en mS/cm).

### Lot F — repères d'éclairage

Repères d'exploitation **informatifs** : les enregistrer, les corriger, les clore ou les
annuler ne modifie ni `param.json`, ni une sortie, ni la régulation, et ne crée aucune alarme.
La page rapproche le repère des horaires **déjà configurés** en les lisant dans la
configuration distribuée (`server.config.daily_timer1/2`), sans nouveau calcul de régulation
ni acquisition matérielle.

| Requête | Contenu |
| --- | --- |
| `GET /cultures/light` | Page des repères, des horaires configurés et de l'état opérationnel |
| `GET /api/v1/cultures/light?scope=&target=&stage=` | Repères (200 au plus) avec révisions, cultures en place, repère applicable, horaires configurés, état opérationnel, écart |
| `POST /api/v1/cultures/light` | `light` (saisie ou correction), `light_close` (clôture), `light_cancel` (annulation) |

Un repère porte une portée `global`, `space` ou `subject`, un `stage` facultatif, un couple
`on_minutes` / `off_minutes` dont la somme vaut exactement **1440**, une fenêtre
`start_at`/`end_at` avec leur `precision`, une note et un motif. Conventions : `18/6` →
`1080/360`, `12/12` → `720/720`. Ces deux valeurs sont des **préremplissages de formulaire** ;
la base naît vide et aucun repère standard n'est supposé.

```json
{
  "operation": "light",
  "request_id": "identifiant-unique-de-la-saisie",
  "scope": "space",
  "space": "space_2",
  "stage": "floraison",
  "label": "Floraison 12/12",
  "on_minutes": 720,
  "off_minutes": 720,
  "start_at": "2026-08-01",
  "start_precision": "date"
}
```

Correction, clôture et annulation reprennent `id`, la `version` attendue (la révision
courante) et un `reason` obligatoire ; une version périmée renvoie **409**. Chaque écriture
crée une révision `revision + 1` et conserve les précédentes. L'idempotence passe par la table
`requests` existante (`request_id` + empreinte), comme les autres mutations du carnet.

Résolution du repère applicable à une date : `subject` > `space` > `global` ; à portée égale un
repère dont le `stage` est renseigné l'emporte sur un repère sans stade, et il ne s'applique
qu'au stade déclaré. Fenêtres semi-ouvertes. **Aucun repère résolu ⇒ aucun écart affiché.**

Invariants revalidés avant chaque commit et rejoués par `restore_copy` : révisions `1..n` sans
trou, `on_minutes + off_minutes = 1440`, `end_sort_at > start_sort_at`, et fenêtres non
chevauchantes par `(portée, cible, stade)`. Un chevauchement est refusé sans rien écrire.

L'écart est calculé par `compare_light` sur les minutes d'éclairage : la plage configurée est
semi-ouverte, deux bornes égales valent **0 minute** (plage vide) et une plage traversant
minuit est comptée modulo 24 h — `19:00 → 07:00` vaut 720 minutes. L'écart est signé du point
de vue de la configuration et reste une information, avec un lien vers `/conf#daily-timer-N`.
La page présente aussi l'activation de chaque minuterie, la ventilation commune et les règles
jour/nuit issues des réglages existants, ainsi que l'état opérationnel déjà publié par les
boucles métier. Un état relu sur une broche GPIO ne prouve pas le fonctionnement physique d'un
équipement ; une publication absente est présentée comme **indisponible**, jamais comme un arrêt.

### Lot G — affectations d'équipements

Le catalogue `param/equipment_metadata.json` reste la **source de vérité** des identifiants et
des noms actuels ; le carnet n'y touche jamais et ne modifie ni câblage, ni broche, ni réglage.
Il n'ajoute que l'association métier historique, dans `culture_equipment_links`.

`GET /api/v1/cultures/equipment[?at=<date>][&equipment=<id>]` — catalogue courant en lecture
seule (`equipments[].current_name`, `current_usage`, `zone`, `out_of_service`), périodes
d'affectation par équipement avec leurs `revisions`, et, si `at` est fourni, la résolution
datée dans `resolved`. `at` est une date ISO (ou un instant avec fuseau) ; une date future est
refusée comme partout ailleurs dans le carnet.

`POST /api/v1/cultures/equipment` — quatre opérations, toutes idempotentes par `request_id` et
transactionnelles :

| `operation` | Champs | Effet |
| --- | --- | --- |
| `link` | `equipment_id`, `usage` (≤ 32 caractères), `scope` (`space`/`reservoir`/`greenhouse`), `space` ou `reservoir_id` selon la portée, `start_at`, `start_precision`, `end_at` facultatif, `source`, `note` | Nouvelle affectation en révision 1 |
| `correct` | `id`, `version`, mêmes champs (les champs omis conservent leur valeur) | Nouvelle révision |
| `close` | `id`, `version`, `end_at`, `end_precision` | Ferme la fenêtre ouverte |
| `cancel` | `id`, `version`, `reason` | Annule la période **sans** l'effacer |

`display_name` est la copie du libellé connu **à la saisie** : il n'est recopié du catalogue que
pour une affectation neuve ou un changement d'équipement, jamais rafraîchi par une correction ni
par un renommage ultérieur. Un `version` obsolète répond 409, une contradiction 400.

**Résolution d'un contexte à une date** (`model/culture_equipment.resolve_equipment`, pure ;
`CultureStore._equipment_context_at` pour les autres lots) — cascade stricte, fenêtres
semi-ouvertes `[début ; fin[` :

1. affectation courante non annulée couvrant la date → `provenance='link'`, avec la révision et
   la date de saisie de l'affectation ;
2. sinon, `equipment_context` porté par la saisie elle-même → `provenance='snapshot'`, présenté
   comme « contexte connu à la saisie du … » avec la date de **saisie**, jamais une date
   d'affectation ;
3. sinon → `provenance='unknown'`, « association inconnue à cette date ». Il n'y a **jamais** de
   repli sur le catalogue courant : un nom d'aujourd'hui n'est pas une association d'hier.

La migration 3 → 4 ne crée **aucune** ligne : les anciennes copies de catalogue restent des
contextes de saisie et ne deviennent pas des affectations datées.

Invariant rejoué par `_validate_equipment` et par `restore_copy` : révisions 1..n sans trou,
`equipment_id` dans `EQUIPMENT_IDS`, portée et cible cohérentes, fin postérieure au début, et
**deux affectations courantes non annulées du même équipement ne se recouvrent pas**. Un
équipement à deux usages successifs — le cas de `cyclic_2` — se saisit donc en fermant la
première période avant d'ouvrir la seconde.

La page `/cultures/equipment` expose le catalogue en lecture seule, la résolution d'une date et
les périodes corrigeables. Chaque intervention de `/cultures/solutions` affiche le contexte
résolu à sa propre date effective (`items[].equipment` dans `GET /api/v1/cultures/solutions`) ;
l'export CSV des relevés est inchangé.

### Lot H — journal et observations d'espace

Le journal transversal est la **vue** `culture_journal`, projection en `UNION ALL` des
événements de culture, des saisies de solution et des observations d'espace, **une ligne par
opération**. Les cibles sont jointes à la demande (`solution_targets`, `solution_links`) : un
arrosage de trois pieds mères reste une entrée et compte pour 1 dans les totaux. La vue est
exclue de `_export` — ses trois sources y figurent déjà.

`GET /api/v1/cultures/journal` — filtres facultatifs `start`, `end` (dates ISO ; la borne
haute est calendaire et exclusive, donc le dernier jour reste entier, heures comprises),
`target` (identifiant de culture, `space_1`/`space_2`, ou réservoir) et `type`
(`<source>:<genre>`, par exemple `event:note`, `solution:water`, `space_event:incident` ;
catalogue complet dans la réponse sous `types`). Pagination `offset` par 40, tri total
`(sort_at DESC, ordinal DESC, source, entry_id)` appliqué en SQL avec `LIMIT/OFFSET` et un
`COUNT(*)` séparé ; `focus=<identifiant d'opération>` renvoie directement le décalage de la
page contenant cette opération. Le filtre par cible passe par des `EXISTS` : la ligne reste
unique quel que soit le nombre de cibles satisfaisant le filtre. Seule la page renvoyée est
enrichie (libellés, cibles nommées, `link` vers la fiche ou les relevés, `photos`,
`revisions` des versions précédentes).

`POST /api/v1/cultures/journal` — observations d'espace, avec `request_id` obligatoire
(idempotence) et `confirm_date` si l'horloge n'est pas synchronisée.

```jsonc
{"request_id": "…", "operation": "space_event", "space": "space_2",
 "kind": "observation",            // observation | maintenance | incident
 "effective_at": "2026-09-01", "precision": "date", "note": "Bac vide désinfecté"}
{"request_id": "…", "operation": "correct", "id": "…", "version": 2,
 "note": "…", "effective_at": "2026-09-01", "reason": "Précision apportée",
 "cancelled": false}               // true annule en conservant la trace
```

La cible est **explicite** : aucune fausse plante n'est créée pour porter la note, et une
observation ne rejoint pas l'historique opérateur purgé à 72 h. `space` et `kind` ne se
corrigent pas (annuler puis ressaisir) : déplacer la cible d'une trace réécrirait l'histoire.
Une `version` erronée répond `409`, une clé de requête réutilisée avec un contenu différent
également. Une observation entièrement annulée reste légitime.

`POST /api/v1/cultures/journal/photos` — corps binaire et métadonnées
`X-Culture-Metadata` identiques aux photos de culture, avec `space_event_id` et
`space_event_revision` à la place de `subject_id`/`event_id`. Même voie d'écriture
(`media_add`), mêmes plafonds : 4 photos par observation, 5 Mio par envoi, réencodage JPEG
1 600 px sans métadonnées, budget `MAX_MEDIA_BYTES` et réserve `MIN_FREE_BYTES`. La table
`culture_media` porte deux paires de clés étrangères mutuellement exclusives
(`owner_kind`) ; ces photos sont incluses dans la sauvegarde ZIP et restaurées par
`restore_bundle`. Une photo ne peut jamais appartenir à la fois à un événement et à une
observation.

`GET /api/v1/cultures/journal/export?format=csv` — export du filtre courant : une ligne par
opération, colonne `cibles` sérialisée en JSON (jamais une ligne par cible), textes libres
neutralisés contre l'injection de formules (`= + - @ TAB CR` préfixés par `'`).

Validateur `validate_space_events` (rejoué par `_cycle_validate` et donc par `restore_copy`) :
révisions 1..n sans trou par identifiant, `payload` JSON décodable et conforme, espace, genre
et précision connus.

Limite connue : le rattachement d'un relevé « avant renouvellement » saisi à l'instant exact
du renouvellement suit, pour le filtre par sujet alimenté, la période ouverte à cet instant.
La page des solutions reste la référence pour ce cas de bord.
