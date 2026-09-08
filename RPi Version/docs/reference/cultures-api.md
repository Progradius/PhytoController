# API du carnet de cultures (v1, livraisons 1 et 2)

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
`interventions` (200 dernières pour le sélecteur), `chart`, `stages`, `chart_aggregated` et
`chart_truncated`. Les clients plus spécialisés peuvent retrouver une intervention ancienne
par pagination du journal et utiliser son UUID.

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
page du journal après une saisie rétrospective.

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
