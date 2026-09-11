# Carnet de cultures — passe « photos » (9 septembre 2026)

> Archivé le 11/09/2026 — bilan clos, conservé comme preuve ; ne plus le mettre à jour.

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

- **tout est indexé par contrôle, jamais par formulaire** : l'URL d'objet (`Map<contrôle, url>`,
  itérable pour le `pagehide`) et la zone (`WeakMap<contrôle, figure>`). Une indexation par
  formulaire, et une zone cherchée par `form.querySelector`, faisaient partager la même URL et la
  même `<figure>` à deux champs photo d'un même formulaire : le second aurait effacé l'aperçu du
  premier. Un conteneur posé par le gabarit n'est adopté que s'il est le **frère suivant** de ce
  champ-là, pour la même raison. La remise à zéro, elle, reste un événement du formulaire : une
  seule écoute, qui efface les aperçus de tous ses champs photo ;
- `URL.createObjectURL`, jamais `FileReader` en `data:` — sur 5 Mio, un data-URI coûte un tiers de
  mémoire en plus et ne se révoque pas. L'URL d'objet est révoquée au changement de fichier, à la
  remise à zéro du formulaire et au `pagehide` — sauf si celui-ci annonce une mise en cache
  arrière/avant (`event.persisted`) : la page peut revenir telle quelle, aperçus compris, et rien
  ne les recréerait ;
- un fichier dont le type n'est pas `image/*` n'a **pas** d'aperçu, et un `<img>` que le navigateur
  ne décode pas referme sa zone (écouteur `error`) : sans ces deux gardes, l'opérateur voit un
  cadre vide qu'il ne sait pas interpréter. Le refus de fond reste au serveur ;
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

`sendUpload` rend **exactement** les quatre formes de retour du contrat — hors ligne, occupé,
réponse HTTP, réseau/délai — que `send` produit aussi, celui-ci y ajoutant seulement le message
d'une exception inattendue : `load` → `{ok, status, data, aborted:false}` avec `data` issu d'un
`JSON.parse` protégé (`{error: REFUSED}` sinon) ; `error` →
`{ok:false, status:0, data:{error: NO_ANSWER}, aborted:false}` ; `timeout` et `abort` → idem avec
`aborted:true`. Le corps de l'exécuteur est entouré d'un `try/catch` qui résout la forme « réseau »
plutôt que de rejeter : un `open` ou un `send` qui lève (URL refusée, corps impossible à envoyer)
remonterait sinon une exception à des appelants qui n'attendent que ces quatre formes. Points
d'attention : `open` avant tout `setRequestHeader` ; `Content-Type: application/octet-stream`
**explicite**, sans quoi XHR déduirait `image/png` du `File` et le serveur répondrait 415 ; le
`File` envoyé tel quel, jamais un `FormData` ; écouteurs `xhr.upload` branchés avant `send` ; délai
`UPLOAD_TIMEOUT_MS` (45 s) partagé avec `submitBinary`, appliqué même si l'appelant n'en passe pas.

La clé d'idempotence et la signature de saisie sont calculées comme avant, dans `submitBinary`,
avant l'envoi : `sendUpload` ne les voit jamais.

### Rendu de la progression

Dans l'`<output>` du formulaire, à côté du texte d'état posé par l'appelant, qui n'est pas réécrit :
un `<progress max="100" aria-label="Progression de l'envoi de la photo">` d'abord **sans `value`**,
donc indéterminé. Le texte visible du pourcentage, lui, est un `<span aria-hidden="true">` posé
**hors** de l'`<output>`, en frère immédiat.

C'est le point corrigé après revue : un `<output role="status">` est une région `aria-live`
**atomique**, donc toute mutation de son sous-arbre la fait réannoncer *en entier*. Un span mis à
jour à chaque événement `progress`, fût-il `aria-hidden`, aurait donc fait annoncer la région à
chaque pour cent — exactement ce que le commentaire prétendait éviter. La `<progress>` est ajoutée
**une fois** (une annonce), et son avancement ne passe ensuite que par ses attributs `value` et
`aria-valuetext`, dont la mutation ne réveille pas la région ; le span, hors région, peut varier
librement. `upload.load` pose « Envoi terminé, enregistrement en cours… » — le serveur vérifie et
réencode l'image après réception, ce temps n'est pas de l'envoi.

La barre est créée **à l'intérieur** de `withGuards`, par la fabrique `onStart` que `submitBinary`
passe à `sendUpload`, et retirée dans le `finally` du même bloc, quelle que soit l'issue et avant
que l'appelant ne pose son message. Créée avant les gardes, comme au premier jet, un envoi refusé
parce qu'un autre est déjà en vol — ou parce que la page est hors ligne — en fabriquait une
seconde.

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
| T3 | Changement de fichier (desktop seul) | Une seule `<img>`, `src` différente ; la `<figure>` d'aperçu est le **frère suivant du `<label>` du champ**, et le nom accessible du champ reste « Photo » seul |
| T4 | Envoi retenu par `page.route` | Pendant l'envoi : `<progress>` présent, visible, indéterminé, et le texte de l'`<output>` reste celui de l'appelant |
| T5 | `route.abort("failed")` | Résumé `.culture-form-errors[role="alert"]`, légende conservée, aperçu conservé, bouton `toBeEnabled()` ; **et** l'absence de `<progress>` après un envoi terminé en échec |
| T6 | axe-core, aperçu affiché et envoi en cours | Zéro violation sur `/cultures/journal` |
| T7 | Second envoi pendant le premier (desktop seul) | Une seule **création** de `<progress>` pour deux `requestSubmit()`, comptée par un `MutationObserver` |

Ce que ces tests ne prouvent pas, dit franchement :

- T3 ne vérifie pas la révocation de l'URL précédente : elle n'est pas observable depuis la page.
  Seuls l'absence d'empilement et le changement d'URL le sont ; le reste relève de la lecture du
  socle ;
- **T4 ne prouve rien du retrait de la barre.** Son assertion finale arrive après le retour au
  journal (`toHaveURL(/#entry-/)`), donc sur un document rechargé où aucune `<progress>` n'a jamais
  existé : toute implémentation, y compris une qui ne retire rien, la passerait. Le retrait est
  prouvé par T5, où l'envoi échoue **sans** navigation, et par la fin de T7 ;
- l'assertion de fratrie ajoutée à T3 prouve le **placement** de la zone (frère suivant du label,
  hors du nom accessible), pas l'indexation par contrôle : aucun formulaire du carnet ne porte deux
  champs photo, donc aucun test ne peut aujourd'hui distinguer une zone cherchée par
  `form.querySelector` d'une zone mémorisée par champ. C'est une garde pour le formulaire à venir,
  vérifiée par lecture du socle ; le jour où un second champ photo apparaît, la spec doit ouvrir
  les deux aperçus et vérifier qu'ils coexistent ;
- T7 compte une *création*, pas un état. La barre d'un second envoi refusé par `busy` serait
  retirée par le `finally` de ce même envoi : aucune assertion d'état, à aucun instant stable, ne
  la verrait. Seul un observateur de mutations sépare « créée une fois » de « créée deux fois puis
  retirée » — c'est ce qui rend la garde de création (barre posée après `withGuards`) réellement
  discriminée. Le second départ passe par `form.requestSubmit()` et non par un clic : le bouton
  d'envoi est `disabled` pendant le premier envoi, et un `click()` ne partirait pas ;
- aucun test ne vérifie qu'un lecteur d'écran n'annonce pas chaque pour cent : ni Playwright ni
  axe-core n'observent le flux d'annonces d'une région `aria-live`. Ce point repose sur la règle
  d'atomicité de `role="status"` et sur la lecture du socle — la `<progress>` ajoutée une seule
  fois, le texte variable hors de la région.

**Preuve par mutation.** En retirant temporairement l'en-tête `Content-Type` de `sendUpload`
(hors commit, restauré ensuite), T1 échoue : la galerie reste à `0` image, le serveur ayant
répondu 415. L'assertion sur l'ancre `#entry-` a été retirée du test à cette occasion — elle
passait malgré la mutation, l'observation ayant déjà posé une ancre : elle ne prouvait rien.

Comptes après la revue indépendante : `tests/test_http_server.py` → 76 passés.
`cultures_ui_photos.spec.js` → **7 passés** en `desktop-chromium` (T7 ajouté), 5 passés + 2 ignorés
(T3 et T7, tous deux réservés au bureau) en `mobile-etroit`. `cultures_ui_lot_2.spec.js` en
`desktop-chromium` → 19 passés, 1 ignoré, inchangé par la correction.

**Preuve par mutation de T7.** La création de la barre remise **avant** `withGuards` (hors commit,
restaurée ensuite), T7 échoue sur le compte de créations : `Expected: 1 / Received: 2`. La garde
est donc réellement discriminée, ce qu'aucune assertion d'état ne faisait.

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
  convertir la prévalidation aurait touché le parcours nominal d'enregistrement sans rien y gagner ;
- un second envoi demandé pendant le premier est bien refusé par la garde `busy`, mais les pages
  posent leur message d'état (`status(form, …)`, qui réécrit l'`<output>`) **avant** d'appeler
  `submitBinary` : la barre de l'envoi encore en vol disparaît alors de l'écran, sans que l'envoi
  s'arrête. Le cas demande un `requestSubmit()` scripté — le bouton est `disabled` — et la
  réparation appartiendrait aux appelants, pas au socle : ne pas la déplacer ici sans traiter les
  trois pages ensemble.
