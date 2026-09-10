# Baseline web locale — 10 septembre 2026

Cette baseline mesure le rendu HTTP du serveur de test, sous WSL2, et ne qualifie ni le Raspberry Pi, ni un téléphone, ni le Wi-Fi de la serre. Elle sert à détecter une régression entre lots ; elle ne fournit donc pas de budget terrain ni de résultat LCP, INP ou CLS.

Commande exécutée, après activation des dépendances de développement :

```bash
.venv/bin/python scripts/benchmark-web-pages.py --output test-results/web-perf.json
```

Le script utilise un `TemporaryDirectory` par scénario, le serveur matériel-neutre de `tests/ui_server.py` et cinq lectures de chaque page. Chaque carnet contient trois mères actives dans l'espace 1, un relevé par mère et par jour, plus un rappel, une note et une photo synthétique par mère toutes les semaines. Aucun fichier de données vivant, GPIO, réseau extérieur ou navigateur n'est sollicité.

| Carnet | Relevés | Rappels | Photos |
| --- | ---: | ---: | ---: |
| 30 jours | 90 | 15 | 15 |
| 90 jours | 270 | 39 | 39 |
| 365 jours | 1 095 | 159 | 159 |

Résultat : Linux WSL2 (`6.6.114.1-microsoft-standard-WSL2`), CPython 3.11.2, 10 septembre 2026 20:23 UTC, après livraison des lots 1 à 5. Les temps sont la médiane de cinq réponses HTML, en ms ; la taille et le nombre d'éléments décrivent seulement le HTML initial.

| Page | 30 j — ms / KiB / éléments | 90 j — ms / KiB / éléments | 365 j — ms / KiB / éléments |
| --- | ---: | ---: | ---: |
| Tableau | 16,50 / 45,1 / 793 | 19,42 / 45,1 / 793 | 27,63 / 45,1 / 793 |
| Alarmes | 11,54 / 6,3 / 114 | 10,78 / 6,3 / 114 | 11,28 / 6,3 / 114 |
| Historique | 10,97 / 11,8 / 179 | 10,95 / 11,8 / 179 | 11,20 / 11,8 / 179 |
| Configuration | 18,22 / 151,0 / 2 245 | 18,32 / 151,0 / 2 245 | 18,95 / 151,0 / 2 245 |
| Console | 6,36 / 5,8 / 97 | 7,93 / 5,8 / 97 | 8,77 / 5,8 / 97 |
| Cultures | 13,50 / 34,0 / 560 | 18,88 / 34,0 / 559 | 28,35 / 33,9 / 555 |
| Solutions | 24,41 / 325,7 / 5 301 | 31,21 / 373,5 / 5 301 | 72,63 / 759,3 / 5 301 |
| Cycles | 15,17 / 56,6 / 890 | 17,38 / 129,7 / 2 042 | 19,22 / 157,2 / 2 451 |
| Plages cibles | 11,27 / 10,6 / 178 | 15,97 / 10,6 / 178 | 14,22 / 10,6 / 178 |
| Éclairage | 11,58 / 15,1 / 264 | 14,47 / 15,1 / 264 | 16,29 / 15,1 / 264 |
| Équipements | 14,12 / 11,2 / 227 | 13,54 / 11,2 / 227 | 13,69 / 11,2 / 227 |
| Journal | 22,21 / 53,9 / 933 | 21,19 / 52,6 / 917 | 25,24 / 53,9 / 933 |
| Fiche d'une mère | 19,32 / 45,4 / 725 | 21,94 / 82,0 / 1 285 | 44,10 / 222,3 / 3 383 |

Le maximum isolé n'est pas une cible : à 30 jours, la configuration a eu un maximum de 148,84 ms pour une médiane de 15,01 ms lors d'une exécution antérieure. Les décisions de chargement à la demande restent interdites sur cette seule base WSL : elles attendent la mesure Pi et téléphone du protocole de qualification.

## Mesures navigateur (même commit)

`PHYTO_TEST_PYTHON=.venv/bin/python npm run measure:ui`, 11 septembre 2026, après livraison de tous les lots, Chromium de Playwright, largeur 390 px, thème sombre. Le JSON complet est dans `docs/images/remediation-web-mobile-pwa-2026-09-09/`.

| Mesure | Valeur relevée | Comment elle est prise |
| --- | ---: | --- |
| Contenu principal visible (`/`) | 137 ms | `performance.now()` côté page dès que `main` est visible, **avant** axe |
| Ouverture d'un formulaire | 93 ms | du clic sur « Saisir » à la visibilité du premier champ du relevé |
| Première interaction sur graphique | 5 ms | du clic sur le dernier point tracé à la réécriture du détail de l'explorateur |
| Retour après enregistrement | 1 587 ms | de l'envoi d'un relevé valide au focus sur l'ancre `event-`/`entry-` |
| Mémoire JS | ~10 Mo | `performance.memory` ; `measureUserAgentSpecificMemory` exige une isolation cross-origin absente ici |

Le « retour après enregistrement » tombe à **558 ms** à 1 440 px et reste à ~1 580 ms à 320 et 390 px : l'écart n'est pas une lenteur de la page étroite mais le coût du repli mobile, à mesurer sur appareil avant toute conclusion.

Chaque largeur enregistre un relevé **distinct**. Trois saisies identiques déclenchent légitimement le panneau « Vérification avant enregistrement » du rapprochement de relevés ressemblants, qui prend le focus à la place de l'ancre : la mesure ne chronométrait alors plus un enregistrement nominal. C'était un défaut de la mesure, pas du carnet — une ressemblance n'est jamais une interdiction, elle demande une confirmation.

Aucune de ces valeurs n'est un LCP, un INP ou un CLS : ce sont des durées de bout en bout mesurées dans un navigateur piloté, sur une machine de développement.

## Budgets — **provisoires**, à confirmer sur Pi et téléphone (R4.2)

Ces budgets sont dérivés de la mesure WSL ci-dessus, avec une marge explicite. Ils servent à **détecter une régression entre deux lots**, pas à qualifier le terrain : un Raspberry Pi et un téléphone sur le Wi-Fi de la serre sont plus lents, et aucun de ces chiffres ne doit être présenté comme une performance utilisateur. Les repères Web Vitals (LCP ≤ 2,5 s, INP ≤ 200 ms, CLS ≤ 0,1) restent des repères, pas des résultats : rien ici ne les mesure.

Règle de dérivation, écrite pour être rejouable : **budget = médiane WSL × 3, arrondi au palier supérieur**, le facteur 3 couvrant l'écart de puissance attendu du Pi sans prétendre l'avoir mesuré.

| Grandeur | Médiane WSL (365 j) | Budget provisoire | Portée |
| --- | ---: | ---: | --- |
| Réponse HTML, page courante | 19 ms | **60 ms** | toute page hors Solutions et fiche |
| Réponse HTML, Solutions à 365 j | 73 ms | **250 ms** | la page la plus lourde du carnet |
| Réponse HTML, fiche à 365 j | 44 ms | **150 ms** | fiche d'une mère très nourrie |
| Éléments du HTML initial, Configuration | 2 245 | **2 500** | seuil au-delà duquel la question du chargement à la demande se rouvre |
| Contenu principal visible, `/` | 137 ms | **500 ms** | mesure navigateur, pas un LCP |
| Ouverture d'un formulaire | 93 ms | **400 ms** | clic → premier champ visible |
| Première interaction sur graphique | 5 ms | **100 ms** | clic → détail réécrit |
| Retour après enregistrement | 1 587 ms | **3 000 ms** | envoi → focus sur l'ancre |
| Poids HTML, Solutions à 365 j | 759 KiB | **1 000 KiB** | HTML initial seul, hors assets |

**Ce que ces budgets ne décident pas.** Le chargement à la demande de `/conf` reste indécidé : la fiche R4.2 le conditionne explicitement à une mesure Pi et téléphone. Un dépassement de budget sur WSL ouvre une enquête ; il ne justifie pas à lui seul un découpage de page.

## Mesurer sur le Pi de qualification (R4.2)

Les deux outils acceptent une cible externe, en **lecture seule** :

```bash
PHYTO_UI_BASE_URL=http://adresse-du-pi:8123 npm run measure:ui
.venv/bin/python scripts/benchmark-web-pages.py --base-url http://adresse-du-pi:8123 \
    --subject-id <identifiant-de-fiche> --output test-results/web-perf-pi.json
```

Dans ce mode, `benchmark-web-pages.py` n'émet que des `GET`, ne fabrique aucun carnet et **refuse** `--days` : générer les 30/90/365 jours supposerait d'écrire dans la base visée. `measure_pages.js` bloque de son côté toute méthode autre que `GET`/`HEAD` et toute origine tierce, et marque `skipped` les états qui exigeraient une mutation ou une coupure réseau provoquée.

Le carnet représentatif se prépare donc **avant**, et jamais sur la base vivante : restaurer une sauvegarde vers une **copie isolée** avec [`scripts/restore-cultures.py`](../../scripts/restore-cultures.py) (`--bundle` pour une archive complète), puis servir cette copie. `scripts/restore-cultures.py` ne publie jamais que vers une copie nouvelle. Charger un carnet de benchmark dans la base de production est interdit — voir [le protocole de qualification](qualification-mobile-pwa.md).

Ce fichier reste la baseline **locale**. La baseline terrain — Pi, téléphone, Wi-Fi de la serre — n'est pas encore relevée ; quand elle le sera, elle sera publiée dans un fichier distinct pour qu'aucun tableau ne laisse croire qu'un chiffre WSL vaut un chiffre de serre.

La mesure navigateur complémentaire est `npm run measure:ui`. Elle conserve hauteur, largeur de défilement, positions de titres, DOM exécuté, axe WCAG A/AA/2.2 AA, mémoire lorsque Chromium l'expose et visibilité de `main`. Elle n'établit pas LCP/INP, et ne peut pas qualifier sans appareil réel le clavier virtuel, l'encoche, VoiceOver/TalkBack, l'installation PWA, une coupure Wi-Fi réelle, ou la mémoire d'un téléphone.
