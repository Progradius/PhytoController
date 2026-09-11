# Mesures « après » de la remédiation web/mobile/PWA

Fichiers produits par `PHYTO_TEST_PYTHON=.venv/bin/python npm run measure:ui`
(`tests/ui/measure_pages.js`), à comparer aux mesures « avant » de
[`../audit-web-mobile-pwa-2026-09-09/`](../audit-web-mobile-pwa-2026-09-09/).

## Protocole

L'outil mesure **deux passes nominales**, et chaque entrée consigne la sienne (`carnet`) ainsi
que sa fenêtre (`viewport`) :

| Passe | Carnet | Ce qu'elle sert |
| --- | --- | --- |
| `vide` | serveur `tests/ui_server.py` neuf, aucune culture | la **seule** passe comparable à `measures.json` de l'audit, dont les 36 visites ont été faites ainsi |
| `rempli` | une mère, six relevés | les acceptations chiffrées portant sur des données, les vues `?view=`, les états ouverts et les scénarios |

Fenêtres, celles de l'audit : **320 × 844**, **390 × 844**, bureau **1440 × 900**. `height` est
le `scrollHeight` du document, qui ne descend jamais sous la hauteur de la fenêtre : une page
courte mesure la fenêtre, pas son contenu.

Que ce protocole reproduit bien l'audit est démontré dans
[`rejeu-baseline-8023123.md`](rejeu-baseline-8023123.md) : rejoué sur la baseline `8023123`,
l'outil retrouve les 36 hauteurs de l'audit à ±2 % (33 au pixel près). Les chiffres publiés ici
avant le 11 septembre 2026 après-midi suivaient un autre protocole (carnet rempli dès la
première page, fenêtres 320 × 568 et 1440 × 844) : ils ne sont pas repris, et les écarts qu'ils
attribuaient à « deux carnets différents » étaient un défaut de l'outil.

| Fichier | Contenu |
| --- | --- |
| `measures-apres-final.json` | 227 entrées : 12 pages de l'audit × 3 largeurs × 2 thèmes **sur les deux passes**, plus les deux vues nommées par une acceptation (`?view=releves`, `?view=analyser`), les états ouverts, le zoom, la bannière hors ligne, le scénario d'alarme critique, les cibles nommées, les temps locaux et le premier écran des acceptations |
| `rejeu-baseline-8023123.json`, `rejeu-baseline-8023123.md` | rejeu de la baseline contre les mesures de l'audit (acceptation de R0.1) |
| `contrastes-dark.json`, `contrastes-daylight.json` | paires texte/fond et limites de composants relevées page par page, avec leur ratio et leur verdict |
| `contrastes.md` | même relevé en tableau, plus la simulation deutéranopie/protanopie des palettes de séries |
| `apres-*.png` | captures « après » à 390 px, sombre et plein jour, passe `rempli` (R5.1, R5.2) |
| `history-niveaux-de-gris.png` | deux séries superposées en niveaux de gris (R5.2) |

## Traçabilité

* Commit mesuré : **`90d06c3`**, arbre propre.
* Mesure exécutée le **11 septembre 2026**, sous WSL2, Chromium de Playwright, un seul processus.
* Baseline de comparaison : `8023123` ; mesures de l'audit : `../audit-web-mobile-pwa-2026-09-09/`.

## Acceptations chiffrées du plan

| Fiche | Acceptation | Passe et fenêtre | Mesure | Verdict |
| --- | --- | --- | ---: | --- |
| R1.2 | tableau de bord : hauteur de la fixture **divisée par deux au moins** (audit 5 035 px → ≤ 2 517,5 px) | `rempli`, 390 × 844 | **2 520 px** (−49,9 %) | ❌ **manquée de 2,5 px** |
| R1.2 | idem, carnet vide | `vide`, 390 × 844 | **2 496 px** (−50,4 %) | ✅ atteinte |
| R1.6 | relevés à six entrées réduits d'au moins 40 % (audit : 7 001 px, `scenarios.json`, une mère et six relevés) | `rempli`, 390 × 844, `?view=releves` | **1 754 px** (−74,9 %) | ✅ atteinte |
| R2.3 | vue Analyser avec six relevés < 2 000 px | `rempli`, 390 × 844, `?view=analyser` | **1 779 px** | ✅ atteinte |
| R2.8 | journal à 20 lignes réduit d'un tiers | `rempli`, 390 × 844 | **115 px** par entrée ; page entière 2 651 px | ⚠️ **non vérifiable** |

**R1.2, franchie de 2,5 px sur la passe remplie, et dite telle quelle.** La mesure du
11 septembre à 16 h donnait 2 517 px, soit 0,5 px sous le plafond. Le correctif du défilement
horizontal au zoom 200 % (`90d06c3`, E11 : `<wbr>` dans la marque, `min-width` sur la barre
mobile, repli de `.hero` et de `.config-layout`) ajoute **3 px** au tableau de bord — 2 520 px —
et fait franchir le plafond de 2,5 px, soit **0,1 %**. Sur le carnet vide, la page tient
(2 496 px). Aucune de ces deux lignes n'est arrondie en sa faveur : « divisée par deux » se
lit ici sur une page dont la hauteur dépend de la fixture d'équipements, et l'écart est du
même ordre qu'une ligne de texte qui se replie. C'est un dépassement réel, pas une régression
d'ergonomie ; le rendre acceptable demanderait soit de retirer 3 px à la page, soit de
constater que le plafond exact (5 035 / 2) n'est plus le bon repère.

**R1.6, la base du calcul.** L'acceptation compare « avec six relevés » : la seule mesure de
l'audit dans cet état est `solutions-remplies` de `scenarios.json`, 7 001 px à 390 px, relevée
sur la fiche filtrée d'une mère du carnet de l'audit. La page mesurée ici n'est pas filtrée et
son carnet est la fixture du script : **les deux carnets ne sont pas identiques**, et l'écart de
−74,9 % ne doit pas se lire au pour-cent près. Contre la page à vide de l'audit (3 259 px), la
même vue donne −46,2 %.

**R2.8 non vérifiable, et non maquillée.** L'acceptation compare un journal « à 20 lignes »
avant et après, mais les mesures de l'audit ne consignent pas le nombre de lignes affichées —
seulement une hauteur de page (1 250 px) sur un journal vide. Le « avant » à 20 lignes n'existe
pas et ne peut pas être reconstitué. Ce qui est mesurable, et sert de référence à toute
comparaison future, est la **hauteur d'une entrée** : `115 px` par `.ui-journal-entry` à 390 px.

## Premier écran (390 × 844, mesuré)

« Dans le premier écran » = la boîte **entière** de l'élément tient, à la position d'arrivée,
dans la fenêtre moins les barres fixes qui la recouvrent. À 390 × 844 la barre de navigation
mobile occupe le bas : la zone utile va de **0 à 779 px**. Un élément de moins de 2 px de côté
ou masqué par un `clip-path` ne compte pas comme affiché (les textes `.visually-hidden` en ont
une boîte de 1 × 1 px), et un défilement non nul à l'arrivée est un échec en soi : le
défilement relevé est de **0 px** sur les cinq scénarios et les trois largeurs.

| Fiche | Élément | Passe | Position | Verdict |
| --- | --- | --- | ---: | --- |
| R1.1 | alarme la plus grave, action conseillée, « Diagnostiquer », « Acquitter » | serveur `critical`, carnet vide | 382–407, 473–522, 529–576, 668–716 | ✅ les quatre |
| R1.2 | état de conduite, fraîcheur, température, humidité, alarmes actives | `rempli` | 218–257, 187–207, 478–570, 478–570, 627–648 | ✅ les cinq |
| R1.8 | nom, espace, stade, âge, « Saisir un relevé », « Observation / photo » | `rempli` | 239–264, 280–305 (les trois faits), 321–365 (les deux actions) | ✅ les six |
| R2.7 | « Appliqué maintenant », plage applicable, source | `rempli`, `/cultures/targets?target=<mère>` | 684–709, 715–740, 741–763 | ✅ les trois |
| R2.8 / E5 | recherche du journal, titre « Opérations du carnet » | `rempli` | 359–406, 732–758 | ✅ les deux |
| R2.8 / E5 | **première entrée du journal** | `rempli` | 829–944 | ❌ sous le premier écran |

Le titre « Opérations du carnet » est donc bien remonté au-dessus de la ligne de flottaison
(écart E5), mais la première entrée du journal commence à 829 px, soit 50 px sous la limite de
la zone utile : la lire demande un défilement. Aucune acceptation ne l'exige ; le fait est consigné tel quel.

R2.7 est mesuré **avec une cible consultée** portant une plage directe : sans cible, la section
n'affiche qu'un état vide, et la mesure ne dirait rien de l'acceptation.

## Hauteurs de document à 390 px, thème sombre

| Page | Audit (carnet vide) | Après, `vide` | Écart | Après, `rempli` |
| --- | ---: | ---: | ---: | ---: |
| Tableau de bord (`/`) | 5 035 | **2 496** | −50,4 % | 2 520 |
| Alarmes (`/alarms`) | 1 414 | 844 | −40,3 % | 844 |
| Historique (`/history`) | 844 | 844 | +0,0 % | 844 |
| Configuration (`/conf`) | 3 662 | 3 829 | +4,6 % | 3 829 |
| Console (`/console`) | 1 356 | 967 | −28,7 % | 967 |
| Cultures (`/cultures`) | 2 159 | 2 156 | −0,1 % | 2 852 |
| Solutions (`/cultures/solutions`) | 3 259 | 949 | −70,9 % | 1 754 |
| Cycles (`/cultures/cycles`) | 2 275 | 1 768 | −22,3 % | 1 768 |
| Plages cibles (`/cultures/targets`) | 999 | 1 654 | +65,6 % | 1 654 |
| Éclairage (`/cultures/light`) | 2 762 | 3 692 | +33,7 % | 3 862 |
| Équipements (`/cultures/equipment`) | 3 313 | 1 786 | −46,1 % | 1 786 |
| Journal (`/cultures/journal`) | 1 250 | 1 444 | +15,5 % | 2 651 |
| Solutions `?view=releves` | — | — | — | 1 754 |
| Solutions `?view=analyser` | — | — | — | 1 779 |

Les trois pages qui **grandissent** à carnet égal le font avec du contenu ajouté par la
remédiation, et non par enflure de présentation : Plages cibles porte désormais la section
« Appliqué maintenant » et sa cascade (+65,6 %), Éclairage les deux blocs « Déclaré » et
« Appliqué » (+33,7 %), le Journal l'index des copies hors ligne et la recherche dépliée
(+15,5 %), la Configuration ses groupes résumés (+4,6 %). Ces hausses sont des faits, pas des
acceptations : aucune fiche ne fixe de plafond sur ces quatre pages.

## Accessibilité, contrastes et perception des couleurs

* **axe** (`wcag2a`, `wcag2aa`, `wcag22aa`) : **0 violation** sur les **202** entrées qui portent
  une analyse axe, dans les deux thèmes. Les 25 entrées restantes des 227 n'en portent pas par
  construction : premier écran (15), cibles nommées (6) et temps locaux (3) relèvent de
  positions et de durées, pas du rendu d'une page ; la vingt-cinquième est le menu « Plus » à
  1 440 px, absent à cette largeur.
* **Contrastes** : **0 paire sous le seuil** dans les deux thèmes (**138** paires distinctes en
  sombre, **135** en plein jour).
* **Palettes de séries** (simulation Machado 2009, sévérité 1,0, ΔE CIE76, minimum entre deux
  séries d'un même groupe) :

  | Thème | Groupe | Vision normale | Deutéranopie | Protanopie |
  | --- | --- | ---: | ---: | ---: |
  | sombre | historique | 34,9 | **15,2** | 23,7 |
  | sombre | carnet | 46,3 | 12,8 | 20,1 |
  | plein jour | historique | 41,6 | **15,3** | 15,5 |
  | plein jour | carnet | 38,1 | **6,6** | 16,5 |

  Les encres de source du carnet restent les plus proches (6,6 en deutéranopie en plein jour) :
  c'est là que la forme du point et le tracé portent seuls la distinction — voir
  `history-niveaux-de-gris.png`.

## Autres relevés de la mesure

* **Cibles nommées** (R5.3, repère 44 px) : **aucun échec** sur les trois largeurs, ni dans le
  scénario nominal ni devant une alarme critique.
* **Bannière hors ligne** : réellement provoquée (service worker installé puis coupure) aux
  trois largeurs ; texte « HORS LIGNE — Données datant au mieux de … · non actualisées · lecture
  seule ».
* **Temps locaux** (poste de développement, pas le Pi) : première interaction sur graphique
  5 à 7 ms ; retour après enregistrement 207 ms à 1 592 ms.
* **Zoom 200 % de la police** : plus aucun débordement horizontal. Le `scrollWidth` vaut
  **exactement la largeur de la fenêtre** aux trois largeurs (320, 390 et 1 440 px), dans les
  deux thèmes. La mesure précédente relevait 464 px sur le tableau de bord à 320 et 390 px : le
  correctif `90d06c3` (écart E11) l'a supprimé, au prix de +3 px de hauteur sur cette page et de
  −25 px sur la Configuration.
* **Zoom 200 % à l'échelle** (`deviceScaleFactor: 2`, fenêtre CSS divisée par deux) : le
  document mesure 280 px pour 160 et 195 px de fenêtre. C'est le plancher `body { min-width:
  280px }` de `style.css`, franchi par construction sous 280 px de fenêtre CSS : on y mesure ce
  plancher déclaré, pas la capacité des pages à se replier. À 1 440 px (720 px CSS), aucun
  débordement.

## Reproduire

```bash
# Mesure complète (les deux passes, trois largeurs, deux thèmes)
PHYTO_TEST_PYTHON=.venv/bin/python PHYTO_MEASURE_DIR=<répertoire> npm run measure:ui

# Captures publiées : passe « rempli », fichiers sans suffixe `-carnet-vide`
PHYTO_TEST_PYTHON=.venv/bin/python PHYTO_MEASURE_WIDTHS=390 \
  PHYTO_MEASURE_SCREENSHOTS=1 PHYTO_MEASURE_DIR=<répertoire> npm run measure:ui
#   390-dark-_.png                              → apres-dashboard-390-sombre.png
#   390-dark-_alarms.png                        → apres-alarms-390-sombre.png
#   390-dark-_history.png                       → apres-history-390-sombre.png
#   390-dark-_cultures_solutions-view-analyser.png → apres-solutions-analyser-390-sombre.png
#   (idem `390-daylight-…` → `…-390-plein-jour.png`)

# Capture en niveaux de gris publiée (le test écrit sinon dans les résultats Playwright)
PHYTO_TEST_PYTHON=.venv/bin/python npm run measure:capture-gris
```

## Comparaison

```bash
# Contre l'audit : passe « carnet vide », la seule comparable (défaut du comparateur).
# `--fenetres-audit` déclare l'hypothèse « ce fichier suit les fenêtres de l'audit » ; sans
# elle, une fenêtre connue d'un seul côté rend chaque ligne non comparable.
npm run measure:compare -- --fenetres-audit \
  docs/images/audit-web-mobile-pwa-2026-09-09/measures.json \
  docs/images/remediation-web-mobile-pwa-2026-09-09/measures-apres-final.json

# Entre deux mesures de la remédiation, sur le carnet rempli
npm run measure:compare -- --carnet rempli <avant>.json <après>.json
```

Le comparateur (`scripts/compare-measures.py`) confronte les entrées **nominales**
(`state` absent ou `page`) en **thème sombre**, sur la passe demandée. Il refuse de comparer
deux fenêtres différentes **et** une fenêtre connue d'un seul côté, refuse une entrée sans
carnet consigné hors de `--carnet vide`, écrit dans son pied les hypothèses de protocole
retenues, rend un tableau Markdown et sort avec un code non nul au-delà de ±2 %.

Face à l'audit, il sort **non nul** : 29 des 36 lignes dépassent ±2 %, ce qui est le résultat
recherché — les pages ont été refaites. Les sept lignes qui tiennent dans ±2 % sont `/history`
aux trois largeurs, `/cultures` aux trois largeurs et `/alarms` à 1 440 px.

## Captures avant / après (R5.1, R5.2)

390 px, page entière. Les « avant » sont celles de l'audit du 9 septembre 2026.

| Page | Avant | Après (sombre) | Après (plein jour) |
| --- | --- | --- | --- |
| Tableau de bord | [`dashboard-390.png`](../audit-web-mobile-pwa-2026-09-09/dashboard-390.png) | `apres-dashboard-390-sombre.png` | `apres-dashboard-390-plein-jour.png` |
| Alarmes | [`alarms-390.png`](../audit-web-mobile-pwa-2026-09-09/alarms-390.png) | `apres-alarms-390-sombre.png` | `apres-alarms-390-plein-jour.png` |
| Solutions — vue Analyser | [`cultures-solutions-390.png`](../audit-web-mobile-pwa-2026-09-09/cultures-solutions-390.png) et [`solutions-plein-jour.png`](../audit-web-mobile-pwa-2026-09-09/solutions-plein-jour.png) | `apres-solutions-analyser-390-sombre.png` | `apres-solutions-analyser-390-plein-jour.png` |
| Historique | [`history-rempli.png`](../audit-web-mobile-pwa-2026-09-09/history-rempli.png) | `apres-history-390-sombre.png` | `apres-history-390-plein-jour.png` |

Les captures « avant » de Solutions et de l'Historique ont été prises sur le carnet de l'audit,
plus fourni que la fixture du script : elles montrent le **traitement visuel** d'alors —
typographie, densité, couleurs des séries — et ne sont pas comparables au pixel près pour la
hauteur. Pour la hauteur, ce sont les tableaux ci-dessus qui font foi.
