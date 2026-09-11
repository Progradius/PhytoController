# Mesures « après » de la remédiation web/mobile/PWA

Fichiers produits par `PHYTO_TEST_PYTHON=.venv/bin/python npm run measure:ui`
(`tests/ui/measure_pages.js`), à comparer aux mesures « avant » de
[`../audit-web-mobile-pwa-2026-09-09/`](../audit-web-mobile-pwa-2026-09-09/).

| Fichier | Contenu |
| --- | --- |
| `measures-apres-final.json` | 140 entrées : 12 pages de l'audit **plus les deux vues nommées par une acceptation** (`?view=releves`, `?view=analyser`), × 3 largeurs × 2 thèmes, avec les états ouverts, le zoom, la bannière hors ligne, le scénario d'alarme critique, les cibles nommées et les temps locaux |
| `contrastes-dark.json`, `contrastes-daylight.json` | paires texte/fond et limites de composants relevées page par page, avec leur ratio et leur verdict |
| `contrastes.md` | même relevé en tableau, plus la simulation deutéranopie/protanopie des palettes de séries |
| `apres-*.png` | captures « après » à 390 px, sombre et plein jour (R5.1, R5.2) |
| `history-niveaux-de-gris.png` | deux séries superposées en niveaux de gris (R5.2) |

## Traçabilité

* Commit de référence : **`8023123`**, arbre de travail des lots 1 à 5 **livré mais non commité**.
* Mesure exécutée le **11 septembre 2026**, sous WSL2, Chromium de Playwright.
* L'horodatage est la seule référence complète : le nom du fichier porte le commit, pas
  l'état exact de l'arbre.

## Hauteurs de document à 390 px, thème sombre

Fixture du script : une mère et six relevés. La fixture de l'audit (carnet « Mère audit
mobile », nourri) **n'est pas la même** : une page qui grandit ci-dessous n'a pas forcément
enflé, elle peut simplement afficher plus de contenu qu'à l'audit. Les acceptations chiffrées
du plan sont donc vérifiées séparément, sur la vue exacte qu'elles visent.

| Page | Avant (audit) | Après | Écart |
| --- | ---: | ---: | ---: |
| Tableau de bord (`/`) | 5 035 px | **2 514 px** | −50,1 % |
| Alarmes (`/alarms`) | 1 414 px | 844 px | −40,3 % |
| Historique (`/history`) | 844 px | 844 px | +0,0 % |
| Configuration (`/conf`) | 3 662 px | 3 854 px | +5,2 % |
| Console (`/console`) | 1 356 px | 967 px | −28,7 % |
| Cultures (`/cultures`) | 2 159 px | 2 852 px | +32,1 % |
| Solutions (`/cultures/solutions`) | 3 259 px | **1 881 px** | −42,3 % |
| Cycles (`/cultures/cycles`) | 2 275 px | 1 768 px | −22,3 % |
| Plages cibles (`/cultures/targets`) | 999 px | 1 600 px | +60,2 % |
| Éclairage (`/cultures/light`) | 2 762 px | 3 862 px | +39,8 % |
| Équipements (`/cultures/equipment`) | 3 313 px | 1 786 px | −46,1 % |
| Journal (`/cultures/journal`) | 1 250 px | 2 797 px | +123,8 % |

## Acceptations chiffrées du plan

Mesurées à 390 px, thème sombre, sur la vue exacte que chaque fiche nomme. Ces quatre lignes
se relisent directement dans `measures-apres-final.json` : les deux vues de Solutions font
partie des routes mesurées, il n'y a plus de sonde jetable entre la fiche et le chiffre.

| Fiche | Acceptation | Mesure | Verdict |
| --- | --- | ---: | --- |
| R1.2 | Tableau de bord ≤ 2 517 px | **2 514 px** | ✅ atteinte |
| R1.6 | Relevés à six entrées réduits d'au moins 40 % (3 259 px → ≤ 1 955 px) | **1 881 px** (`?view=releves`), −42,3 % | ✅ atteinte |
| R2.3 | Vue Analyser < 2 000 px | **1 754 px** (`?view=analyser`) | ✅ atteinte |
| R2.8 | Journal à 20 lignes réduit d'un tiers | 115 px par ligne | ⚠️ **non vérifiable** |

**R2.8 non vérifiable, et non maquillée** : l'acceptation compare un journal « à 20 lignes »
avant et après, mais les mesures de l'audit ne consignent **pas** le nombre de lignes
affichées — seulement une hauteur de page (1 250 px) sur un carnet dont la composition n'est
pas reproductible. Le « avant » à 20 lignes n'existe donc pas et ne peut pas être
reconstitué. Ce qui est mesurable aujourd'hui, et sert de référence à toute comparaison
future, est la **hauteur d'une ligne** : `115 px` par `.ui-journal-entry`. C'est une lacune
de l'instrumentation initiale, pas un résultat.

## Accessibilité, contrastes et perception des couleurs

* **axe** (`wcag2a`, `wcag2aa`, `wcag22aa`) : **0 violation** sur les 130 relevés qui portent une analyse axe (les 10 autres
  entrées — cibles nommées, temps locaux, menu — n'en portent pas).
* **Contrastes** : **0 paire sous le seuil** dans les deux thèmes (138 paires distinctes en
  sombre, 135 en plein jour).
* **Palette de séries de l'historique**, après remaniement (simulation Machado 2009,
  sévérité 1,0, ΔE CIE76) :

  | Thème | Vision normale | Deutéranopie | Protanopie |
  | --- | ---: | ---: | ---: |
  | sombre | 34,9 | **15,2** | 23,7 |
  | plein jour | 41,6 | **15,3** | 15,5 |

  Le minimum était de **1,7** en deutéranopie avant remaniement : deux séries y étaient
  littéralement la même couleur. Les encres de source du carnet restent plus proches
  (6,6 en deutéranopie en plein jour) ; c'est là que la forme du point et le tracé portent
  seuls la distinction — voir `history-niveaux-de-gris.png`.

## Captures avant / après (R5.1, R5.2)

390 px, page entière. Les « avant » sont celles de l'audit du 9 septembre 2026.

| Page | Avant | Après (sombre) | Après (plein jour) |
| --- | --- | --- | --- |
| Tableau de bord | [`dashboard-390.png`](../audit-web-mobile-pwa-2026-09-09/dashboard-390.png) | `apres-dashboard-390-sombre.png` | `apres-dashboard-390-plein-jour.png` |
| Alarmes | [`alarms-390.png`](../audit-web-mobile-pwa-2026-09-09/alarms-390.png) | `apres-alarms-390-sombre.png` | `apres-alarms-390-plein-jour.png` |
| Solutions — vue Analyser | [`cultures-solutions-390.png`](../audit-web-mobile-pwa-2026-09-09/cultures-solutions-390.png) et [`solutions-plein-jour.png`](../audit-web-mobile-pwa-2026-09-09/solutions-plein-jour.png) | `apres-solutions-analyser-390-sombre.png` | `apres-solutions-analyser-390-plein-jour.png` |
| Historique | [`history-rempli.png`](../audit-web-mobile-pwa-2026-09-09/history-rempli.png) | `apres-history-390-sombre.png` | `apres-history-390-plein-jour.png` |

Les captures « avant » de Solutions et de l'Historique ont été prises sur le carnet de
l'audit, plus fourni que la fixture du script : elles montrent le **traitement visuel**
d'alors — typographie, densité, couleurs des séries — et ne sont pas comparables au pixel
près pour la hauteur. Pour la hauteur, ce sont les tableaux ci-dessus qui font foi.

Reproduire les captures :

```bash
PHYTO_TEST_PYTHON=.venv/bin/python PHYTO_MEASURE_WIDTHS=390 \
  PHYTO_MEASURE_SCREENSHOTS=1 PHYTO_MEASURE_DIR=<répertoire> npm run measure:ui
```

## Comparaison

```bash
npm run measure:compare -- \
  docs/images/audit-web-mobile-pwa-2026-09-09/measures.json \
  docs/images/remediation-web-mobile-pwa-2026-09-09/measures-apres-final.json
```

Le comparateur (`scripts/compare-measures.py`) confronte les entrées **nominales**
(`state` absent ou `page`) en **thème sombre** (`theme` absent ou `dark`) — le fichier de
l'audit ne porte ni `state` ni `theme`, leur absence vaut donc « page » et « dark ». Il rend
un tableau Markdown et sort avec un code non nul au-delà de ±2 %.

Face à l'audit, il sort **non nul** : c'est attendu et voulu, puisque les pages ont été
refaites et que les deux carnets diffèrent. Le comparateur sert à détecter une régression
entre deux mesures **comparables** — deux lots successifs, ou une même page avant et après
une correction —, pas à faire coïncider deux carnets différents.

Reproductibilité vérifiée : deux exécutions complètes du script à neuf minutes d'intervalle
donnent **+0,00 %** sur 31 des 36 couples (route, largeur). Les cinq couples restants sont
exactement les pages dont le gabarit a été modifié entre les deux exécutions. Le bruit propre
à l'outil est donc nul à l'arrondi du pixel.
