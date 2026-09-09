# Carnet de cultures — passe « photos » (9 septembre 2026)

Reliquat de la ligne « Photos » de l'audit, laissé de côté par les lots UI 2 et 4 et explicitement
renvoyé à une passe dédiée par le plan de remédiation du lot 4. Deux manques : l'aperçu local avant
envoi n'existait que sur la fiche, et la progression d'un envoi binaire se réduisait à un texte
d'état figé. Aucune route, aucune persistance et aucun message serveur ne changent ici.

## Conception

### Aperçu local posé par le socle

L'aperçu est branché dans `register` (`network/web/static/js/culture_forms.js`), sur **tout**
contrôle `type="file"` dont l'attribut `accept` vise des images. Les trois formulaires photo du
carnet — observation d'une fiche (`data-culture-observation`), photo d'une entrée
(`data-photo-form`), photo d'une observation d'espace (`data-journal-photo`) — le reçoivent donc
sans qu'aucune page ne l'écrive, et un quatrième formulaire l'aurait gratuitement.

Le conteneur est un `<figure class="culture-photo-preview" data-culture-photo-preview hidden>`
inséré après le `<label>` enveloppant, comme le message d'erreur : un élément placé *dans* le label
entrerait dans le nom accessible du champ. Le gabarit peut le poser lui-même ; aucun ne le fait
plus, la `<div>` de `cultures.html` a été retirée.

Décisions :

- `URL.createObjectURL`, jamais `FileReader` en `data:` — sur 5 Mio, un data-URI coûte un tiers de
  mémoire en plus et ne se révoque pas. L'URL d'objet est révoquée au changement de fichier, à la
  remise à zéro du formulaire et au `pagehide` ;
- branchement idempotent (`WeakSet`) : `register` est rejoué par `showErrors` et après un clonage
  de ligne d'origine ;
- attribut `data-culture-photo-preview`, et **pas** `data-culture-preview`, déjà pris par le
  tableau de bord (`tests/ui/visual.spec.js`) ;
- l'aperçu n'émet rien et ne met rien en attente : c'est une lecture du fichier local déjà choisi.

`PhytoCultureForms.clearPreview(form)` est exposé ; `cultures.js` a perdu sa copie locale (une
vingtaine de lignes) et l'appelle après un enregistrement réussi.

### Progression réelle par `XMLHttpRequest`

`fetch` ne rend pas la progression d'un corps **envoyé**. `submitBinary` passe donc par
`XMLHttpRequest`, mais sa signature et son contrat ne bougent pas : les appelants
(`cultures.js`, `culture_cycles.js`, `culture_journal.js`) sont inchangés.

Pour éviter deux copies des gardes, celles de `send` ont été extraites dans `withGuards(form, run)`
— hors ligne, envoi déjà en vol, désactivation des seuls boutons `[type="submit"]` non déjà
désactivés (propriété `disabled`, jamais `aria-disabled`, qui n'empêcherait pas le clic), `finally`
symétrique. `send` (chemin JSON et prévalidation) et le nouveau `sendUpload` s'y appuient tous deux.

`sendUpload` rend **exactement** les quatre formes de retour de `send` : `load` →
`{ok, status, data, aborted:false}` avec `data` issu d'un `JSON.parse` protégé (`{error: REFUSED}`
sinon) ; `error` → `{ok:false, status:0, data:{error: NO_ANSWER}, aborted:false}` ; `timeout` et
`abort` → idem avec `aborted:true`. Points d'attention : `open` avant tout `setRequestHeader` ;
`Content-Type: application/octet-stream` **explicite**, sans quoi XHR déduirait `image/png` du
`File` et le serveur répondrait 415 ; le `File` envoyé tel quel, jamais un `FormData` ; écouteurs
`xhr.upload` branchés avant `send`.

La clé d'idempotence et la signature de saisie sont calculées comme avant, dans `submitBinary`,
avant l'envoi : `sendUpload` ne les voit jamais.

### Rendu de la progression

Dans l'`<output>` du formulaire, à côté du texte d'état posé par l'appelant, qui n'est pas réécrit :
un `<progress max="100" aria-label="Progression de l'envoi de la photo">` d'abord **sans `value`**,
donc indéterminé, et un frère `<span aria-hidden="true">`.

Le pourcentage n'est porté que par `value`, `aria-valuetext` et ce span masqué : l'`<output>` est
une région `aria-live`, et faire varier son texte accessible à chaque événement la ferait annoncer
en boucle. `upload.load` pose « Envoi terminé, enregistrement en cours… » — le serveur vérifie et
réencode l'image après réception, ce temps n'est pas de l'envoi. Les deux éléments sont retirés
dans le `finally`, quelle que soit l'issue et avant que l'appelant ne pose son message.

Volontairement absents : aucun `form.reset()` (la légende et le fichier restent en place, donc la
clé d'idempotence aussi), aucune désactivation du champ fichier ni de la légende pendant l'envoi
(cela croiserait la garde de saisie en cours de `pwa.js`), aucun `beforeunload` supplémentaire,
aucun bouton d'annulation, aucune reprise et aucun rejeu.

## Résultat CSP / `blob:` — un défaut du lot 2 mis au jour

La politique de sécurité de contenu servait `img-src 'self' data:`, **sans** `blob:`. L'aperçu du
lot UI 2, qui repose sur `URL.createObjectURL`, était donc bloqué en production : l'`<img>` existait
et était « visible », mais vide. La spec du lot 2 ne vérifiait que `toBeVisible()`, ce qui passait.

Preuve, obtenue par une sonde Playwright jetable sur le carnet temporaire :

```
SONDE {"src":"blob:http://","nw":0,"complete":true}
["error: Loading the image 'blob:http://127.0.0.1:39123/fe276eb4-…' violates the following
  Content Security Policy directive: \"img-src 'self' data:\". The action has been blocked."]
```

Correctif : `img-src 'self' data: blob:` dans `network/web/server.py`. Un `blob:` ne désigne qu'un
objet créé par le document lui-même, n'ouvre aucune origine tierce et ne rend rien exécutable —
`script-src` reste `'self'` seul. `tests/test_http_server.py` vérifie désormais la directive et
qu'aucune autre directive ne gagne `blob:`.

La nouvelle spec assert `naturalWidth > 0` : c'est cette assertion, et non la visibilité, qui
sépare une image décodée d'un `<img>` cassé. Toute vérification d'aperçu future doit la reprendre.

## Tests

`tests/ui/cultures_ui_photos.spec.js`, sur les quatre profils Chromium (`desktop-chromium`,
`mobile-chromium`, `mobile-etroit`, `mobile-paysage`) ; `pwa-chromium` est exclu comme pour les
autres parcours mutateurs. `PNG_1x1` a été remonté dans `tests/ui/culture_fixtures.js` et est
partagé avec la spec du lot 2.

| # | Scénario | Ce qu'il prouve |
| --- | --- | --- |
| T1 | Photo réelle par la route binaire depuis le journal | La galerie de l'entrée passe de 0 à 1 image, légende comprise |
| T2 | Aperçu sur les trois formulaires | `img[alt]` non vide, `naturalWidth > 0`, **aucun** POST vers `/api/v1/cultures` |
| T3 | Changement de fichier (desktop seul) | Une seule `<img>`, `src` différente |
| T4 | Envoi retenu par `page.route` | `<progress>` présent, visible, indéterminé ; le texte annoncé reste celui de l'appelant ; barre retirée ensuite |
| T5 | `route.abort("failed")` | Résumé `.culture-form-errors[role="alert"]`, légende conservée, aperçu conservé, barre retirée, bouton `toBeEnabled()` |
| T6 | axe-core, aperçu affiché et envoi en cours | Zéro violation sur `/cultures/journal` |

T3 ne vérifie pas la révocation de l'URL précédente : elle n'est pas observable depuis la page.
Seuls l'absence d'empilement et le changement d'URL le sont ; le reste relève de la lecture du
socle.

**Preuve par mutation.** En retirant temporairement l'en-tête `Content-Type` de `sendUpload`
(hors commit, restauré ensuite), T1 échoue : la galerie reste à `0` image, le serveur ayant
répondu 415. L'assertion sur l'ancre `#entry-` a été retirée du test à cette occasion — elle
passait malgré la mutation, l'observation ayant déjà posé une ancre : elle ne prouvait rien.

Comptes : `python3 -m pytest` → 822 passés. `cultures_ui_photos.spec.js` → 6 passés en
`desktop-chromium`, 5 passés + 1 ignoré (T3) sur chacun des trois profils mobiles.
`cultures_ui_lot_2.spec.js` en `desktop-chromium` → 19 passés, 1 ignoré (état d'avant la passe).

## Limites assumées

- 413 (taille), 415 (type de corps) et 408 (réception trop lente) répondent du **texte**, pas du
  JSON : ces refus se présentent avec le message générique du socle. Le changer relève de la
  chaîne serveur des photos, hors périmètre de cette passe ;
- un envoi ne peut pas être annulé, ni repris, ni mis en file : c'est une décision, pas un oubli —
  une file de photos hors ligne rejouées plus tard réintroduirait des mutations différées, que la
  PWA du carnet refuse par principe ;
- le pourcentage n'est pas observable sous `page.route` : Chromium n'émet aucun événement
  `xhr.upload` pour une requête interceptée avant la pile réseau. T4 vérifie donc l'état posé par
  le socle, pas un chiffre — ce qui était de toute façon la règle, un seuil chiffré étant instable ;
- le chemin JSON reste sur `fetch` : seul l'envoi binaire avait besoin de la progression, et
  convertir la prévalidation aurait touché le parcours nominal d'enregistrement sans rien y gagner.
