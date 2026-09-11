# Rejeu de la baseline `8023123` contre les mesures de l'audit (R0.1, écart E7)

Acceptation de la fiche R0.1 : « rejouer le script sur la baseline reproduit les hauteurs de
`measures.json` à ±2 % ».

**Verdict : atteinte.** Les 36 hauteurs de l'audit
(`../audit-web-mobile-pwa-2026-09-09/measures.json`) sont reproduites à ±2 % : 33 au pixel près,
3 entre −0,28 % et +1,44 %. Le nombre d'éléments DOM et la largeur de défilement le sont aussi
(36/36 à ±2 %), et axe retrouve la seule violation de l'audit à 390 px (`/console`,
`aria-prohibited-attr`).

* Mesures du rejeu : `rejeu-baseline-8023123.json` (72 entrées : 12 pages × 3 largeurs × 2 thèmes).
* Exécuté le 11 septembre 2026 à 08 h 22, sous WSL2, Chromium de Playwright, avec
  `tests/ui/measure_pages.js` (commité depuis en `7fb722b`) servant une extraction de
  `8023123` **non modifiée**.

## Reproduire

```bash
git worktree add --detach <dossier> 8023123
PHYTO_TEST_PYTHON=.venv/bin/python PHYTO_MEASURE_ROOT="<dossier>/RPi Version" \
  PHYTO_MEASURE_PERIMETRE=audit PHYTO_MEASURE_DIR=<sortie> npm run measure:ui
npm run measure:compare -- --fenetres-audit \
  docs/images/audit-web-mobile-pwa-2026-09-09/measures.json <sortie>/measures.json
git worktree remove <dossier>
```

`PHYTO_MEASURE_ROOT` fait lancer `tests/ui_server.py` **de l'arbre extrait**, dans son propre
répertoire : rien n'y est recopié. `PHYTO_MEASURE_PERIMETRE=audit` ne joue que la matrice des
36 visites, sur un carnet vide ; les scénarios annexes supposent des formulaires et des vues que
cette révision n'a pas.

## Résultat page par page (thème sombre)

| Route | Largeur | Audit | Rejeu | Écart | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| `/` | 320 | 5162 | 5162 | +0,00 % | ok |
| `/` | 390 | 5035 | 5035 | +0,00 % | ok |
| `/` | 1440 | 3246 | 3246 | +0,00 % | ok |
| `/alarms` | 320 | 1439 | 1456 | +1,18 % | ok |
| `/alarms` | 390 | 1414 | 1410 | −0,28 % | ok |
| `/alarms` | 1440 | 903 | 903 | +0,00 % | ok |
| `/conf` | 320 | 3870 | 3870 | +0,00 % | ok |
| `/conf` | 390 | 3662 | 3662 | +0,00 % | ok |
| `/conf` | 1440 | 2505 | 2505 | +0,00 % | ok |
| `/console` | 320 | 1376 | 1376 | +0,00 % | ok |
| `/console` | 390 | 1356 | 1356 | +0,00 % | ok |
| `/console` | 1440 | 1245 | 1245 | +0,00 % | ok |
| `/cultures` | 320 | 2344 | 2344 | +0,00 % | ok |
| `/cultures` | 390 | 2159 | 2159 | +0,00 % | ok |
| `/cultures` | 1440 | 1692 | 1692 | +0,00 % | ok |
| `/cultures/cycles` | 320 | 2577 | 2577 | +0,00 % | ok |
| `/cultures/cycles` | 390 | 2275 | 2275 | +0,00 % | ok |
| `/cultures/cycles` | 1440 | 1810 | 1810 | +0,00 % | ok |
| `/cultures/equipment` | 320 | 3799 | 3799 | +0,00 % | ok |
| `/cultures/equipment` | 390 | 3313 | 3313 | +0,00 % | ok |
| `/cultures/equipment` | 1440 | 2391 | 2391 | +0,00 % | ok |
| `/cultures/journal` | 320 | 1310 | 1310 | +0,00 % | ok |
| `/cultures/journal` | 390 | 1250 | 1250 | +0,00 % | ok |
| `/cultures/journal` | 1440 | 1155 | 1155 | +0,00 % | ok |
| `/cultures/light` | 320 | 2927 | 2927 | +0,00 % | ok |
| `/cultures/light` | 390 | 2762 | 2762 | +0,00 % | ok |
| `/cultures/light` | 1440 | 1738 | 1738 | +0,00 % | ok |
| `/cultures/solutions` | 320 | 3802 | 3802 | +0,00 % | ok |
| `/cultures/solutions` | 390 | 3259 | 3306 | +1,44 % | ok |
| `/cultures/solutions` | 1440 | 2038 | 2038 | +0,00 % | ok |
| `/cultures/targets` | 320 | 1203 | 1203 | +0,00 % | ok |
| `/cultures/targets` | 390 | 999 | 999 | +0,00 % | ok |
| `/cultures/targets` | 1440 | 900 | 900 | +0,00 % | ok |
| `/history` | 320 | 844 | 844 | +0,00 % | ok |
| `/history` | 390 | 844 | 844 | +0,00 % | ok |
| `/history` | 1440 | 900 | 900 | +0,00 % | ok |

## Les trois écarts résiduels, dans la tolérance

L'audit est parti de `641a7ef` et ses mesures ont été prises pendant que des modifications
parallèles arrivaient dans l'arbre (audit, « Périmètre, méthode et limites »). Aucune révision
ne reproduit donc les 36 visites au pixel : un rejeu de `641a7ef` par le même outil donne
`/alarms` et `/cultures/solutions` **au pixel**, mais `/` à 320 px à −4,77 % (hors tolérance) ;
`8023123` donne `/` au pixel et les trois écarts ci-dessous. Les deux révisions encadrent
l'arbre de l'audit.

* **`/alarms`, +1,18 % à 320 px et −0,28 % à 390 px.** Sonde au navigateur sur les deux
  révisions : sous `641a7ef`, `#notification-status` reste sur « Vérification de la
  compatibilité… » (21 px) ; sous `8023123`, il aboutit à « Permission refusée. Réactivez les
  notifications depuis les réglages du site dans Chrome. » (62 px à 320, 42 px à 390). Le titre
  « Aucune occurrence » descend d'autant (+42 et +21 px). Le verdict est posé par le JavaScript
  PWA modifié par `8023123` lui-même (« propriétaire unique du verdict de connexion ») :
  l'audit a mesuré `/alarms` avant ce correctif.
* **`/cultures/solutions`, +1,44 % à 390 px.** Seule la section « Journal et courbes »
  grandit (+48 px sur « Recettes réutilisables », titres précédents inchangés). La seule
  modification de cette section entre les deux révisions est `9136e40` (légende des courbes
  calculée par mesure, texte d'absence plus long sous chacune des deux figures), postérieure au
  début de l'audit ; `641a7ef` reproduit la hauteur au pixel.

Aucun des trois ne dépend de l'horloge : ni la date du jour, ni un horodatage n'y figurent.

## Causes des écarts de l'outil précédent, et correction

Avant ce rejeu, l'outil ne pouvait pas reproduire l'audit, pour deux raisons **de protocole**
prouvées par des rejeux de contrôle sur la même baseline :

| Contrôle sur `8023123` | Lignes hors ±2 % | Détail |
| --- | ---: | --- |
| Protocole de l'audit (carnet vide, fenêtres 320 × 844, 390 × 844, 1440 × 900) | 0 / 36 | tableau ci-dessus |
| Carnet **rempli** (une mère, six relevés) avant les pages, comme le faisait l'outil | 12 / 36 | `/cultures` +31,2 à +43,9 %, `/cultures/journal` +137,3 à +174,2 %, `/cultures/light` +15,6 à +21,0 %, `/cultures/solutions` +108,7 à +132,9 % |
| Fenêtre 320 × **568**, celle de l'outil | 2 / 12 | `/console` −13,66 %, `/history` −12,80 % |
| Fenêtre 1440 × **844**, celle de l'outil | 2 / 12 | `/console` −3,13 %, `/history` −6,22 % |

1. **Carnet.** Les 36 visites de l'audit ont été faites sur le carnet **vide** d'un
   `tests/ui_server.py` neuf ; la mère « Mère audit mobile » et ses six relevés n'appartiennent
   qu'aux scénarios complémentaires (`scenarios.json`). L'outil créait sa mère **avant** les
   pages : ses mesures nominales n'étaient donc pas comparables à celles de l'audit, et la
   lecture « les deux carnets diffèrent » du `README.md` de ce dossier en venait.
   `measure_pages.js` mesure désormais d'abord les 12 pages sur le carnet vide (`carnet: "vide"`),
   puis remplit le carnet pour les vues d'acceptation et les scénarios (`carnet: "rempli"`).
2. **Fenêtre.** `height` vaut `scrollHeight`, qui ne descend jamais sous la hauteur de la
   fenêtre, et la console se dimensionne sur elle. L'audit mesurait 320 et 390 px sur 844 px
   de haut et le bureau en 1440 × 900 ; l'outil utilisait 320 × 568 et 1440 × 844. Il reprend
   les fenêtres de l'audit et consigne la sienne dans `viewport`.

`scripts/compare-measures.py` compare par défaut la passe au carnet vide (`--carnet`), déclare
**non comparable** une ligne dont les fenêtres diffèrent ou n'est consignée que d'un côté, et
refuse une entrée sans carnet consigné hors de `--carnet vide`. Le fichier de l'audit ne
consigne ni l'un ni l'autre : `--fenetres-audit` déclare l'hypothèse qui le rend comparable,
et le rapport l'écrit.
