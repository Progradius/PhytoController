# API du carnet de cultures (v1, livraison 1)

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
