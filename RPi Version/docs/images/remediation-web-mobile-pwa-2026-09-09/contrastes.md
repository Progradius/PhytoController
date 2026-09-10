# Rapport de contrastes et de perception des couleurs (R5.2)

Produit par `npm run measure:ui` le 2026-09-10T22:20:23.432Z.

Seuils : 4,5:1 pour le texte courant, 3:1 pour le grand texte (≥ 24 px, ou ≥ 18,66 px en gras)
et pour la limite visible des composants de saisie contre la surface qui les entoure
(WCAG 1.4.11). Le fond effectif est composé en remontant les ancêtres. Une paire marquée
« ~ » traverse un dégradé : il est approché par sa couche solide, les dégradés du dépôt
étant des teintes de 2 à 18 % posées sur un aplat. Les contrôles de moins de 4 px de côté
(radios CSS masquées) ne sont pas comptés : leur affordance visible est leur `label`.

## Thème `dark`

138 paires distinctes mesurées, 0 sous le seuil.

Aucune paire sous le seuil.

## Thème `daylight`

135 paires distinctes mesurées, 0 sous le seuil.

Aucune paire sous le seuil.

## Palette de séries en deutéranopie et protanopie

Simulation Machado (2009), sévérité 1,0, en RVB linéaire ; écart ΔE (CIE76) entre séries.
Un ΔE faible signale deux séries que la couleur seule ne sépare plus : elles doivent rester
distinguées par le tracé (plein, tirets, pointillés) et par leur marqueur.

### Thème `dark` — groupe `history`

`--chart-0` #50e38a · `--chart-1` #7abdff · `--chart-2` #ffc252 · `--chart-3` #bd7aff · `--chart-4` #e56c6c · `--chart-5` #8ee2eb

| Vue | ΔE minimal | Paire la plus proche |
| --- | ---: | --- |
| normale | 34.9 | `--chart-1` / `--chart-5` |
| deuteranopie | 15.2 | `--chart-0` / `--chart-4` |
| protanopie | 23.7 | `--chart-0` / `--chart-2` |

### Thème `dark` — groupe `solutions`

`--blue` #75baff · `--amber` #f5bd4f · `--red` #ff6b6b · `--green` #50e38a · `--muted` #a0b9aa

| Vue | ΔE minimal | Paire la plus proche |
| --- | ---: | --- |
| normale | 46.3 | `--blue` / `--muted` |
| deuteranopie | 12.8 | `--red` / `--green` |
| protanopie | 20.1 | `--red` / `--muted` |

### Thème `daylight` — groupe `history`

`--chart-0` #0b7c3d · `--chart-1` #1466b8 · `--chart-2` #703e00 · `--chart-3` #752b82 · `--chart-4` #cc0029 · `--chart-5` #197176

| Vue | ΔE minimal | Paire la plus proche |
| --- | ---: | --- |
| normale | 41.6 | `--chart-1` / `--chart-3` |
| deuteranopie | 15.3 | `--chart-2` / `--chart-4` |
| protanopie | 15.5 | `--chart-2` / `--chart-4` |

### Thème `daylight` — groupe `solutions`

`--blue` #075ea8 · `--amber` #7a4b00 · `--red` #b42323 · `--green` #0b7c3d · `--muted` #4f685a

| Vue | ΔE minimal | Paire la plus proche |
| --- | ---: | --- |
| normale | 38.1 | `--green` / `--muted` |
| deuteranopie | 6.6 | `--amber` / `--red` |
| protanopie | 16.5 | `--amber` / `--green` |

