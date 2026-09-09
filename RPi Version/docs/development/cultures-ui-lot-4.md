# Carnet de cultures — lot UI 4 : analyse et confort

Implémentation du lot 4 de l’[audit du 8 septembre 2026](audit-ui-cultures-2026-09-08.md).

La comparaison présente désormais une colonne par culture et des lignes communes :
stade, durées par stade, minimum/moyenne/maximum pH et EC, nombre de mesures, poids
sec et enseignements. Chaque durée ouverte porte « à ce jour » ; les périodes
approximatives sont signalées. Les statistiques couvrent les parcours propres aux
cultures, sans prétendre comparer des périodes ou effectifs identiques. Un stade
absent, un poids absent ou une mesure absente reste explicitement non renseigné.
Les détails datés des parcours restent consultables sous le tableau.

La recherche nom/variété du sélecteur traverse le carnet, avec 40 résultats par page
et jusqu’à quatre cultures sélectionnées conservées en plus. Les cases remplacent
le sélecteur multiple ; les choix affichés se filtrent immédiatement et le plafond
de quatre se voit avant soumission. La validation serveur conserve son plafond.
La recherche des cultures et des archives existante est maintenue. Les archives
montrent leur bilan renseigné et permettent d’ouvrir directement le bilan ou la
comparaison. La fiche récapitule aussi les durées et les dates de son parcours.

Les courbes de solutions et de climat offrent un curseur natif, des boutons de
44 px et un choix du point le plus proche au toucher. Un seul arrêt de tabulation
par curseur permet de parcourir une longue période sans traverser chaque point.
Le détail expose la date, la cible/période, les agrégations, les unités et les lacunes.
Un tableau équivalent est construit seulement à son ouverture, sur le même jeu de
points borné ; les valeurs des bandes de référence sont aussi accessibles en texte.
Les dessins ne relient toujours pas les périodes manquantes et la taille de leurs
graduations reste celle du lot 1. La sélection est conservée lors du redessin.

La galerie utilise un dialogue natif : précédent/suivant, flèches clavier, Échap,
légendes et lien vers le contexte quand il existe. La fermeture rend le focus au
lien d’origine. Une image indisponible laisse la navigation accessible. Sans support
du dialogue ou sans JavaScript, les liens directs aux images restent utilisables.
Les photos d’une comparaison sont désormais filtrées sur toutes les cultures
sélectionnées ; auparavant une sélection multiple ouvrait la galerie globale.
La borne existante de 100 photos et les limites PWA restent inchangées.

## Coût et invariants

Les statistiques pH/EC sont agrégées en SQL : une ligne retournée par culture, sans
export complet des relevés ni projection supplémentaire. Le prédicat d’association
est partagé avec le dernier relevé : cibles directes, alimentation datée, révision
courante non annulée et cas « avant » un renouvellement à la même seconde.
Les tests comparent ces résultats avec l’export de référence, y compris les absences
et les zéros, puis interdisent l’export sur le chemin de comparaison.

La page garde les projections globales et le catalogue des cibles de rappel qui
existaient déjà. Elle ne promet donc pas un coût constant pour un nombre illimité de
cultures. Les résultats du sélecteur, les graphiques, les photos et le détail horaire
sont bornés. Aucun schéma, acquisition, GPIO, régulation ou mécanisme de commande
n’est ajouté. Le nouveau script de consultation est versionné par empreinte et
inscrit dans l’allow-list des assets et dans le précache PWA.

## Banc de mesure

```bash
.venv/bin/python scripts/benchmark-cultures-analysis.py
```

Sur le Pi, utiliser `venv/bin/python3` à la place de `.venv/bin/python`.

Le script crée exclusivement une base temporaire synthétique : 44 cultures,
12 001 relevés et 729 jours, avec deux séries climatiques horaires lacunaires.
Il mesure cinq lectures et rendus Jinja pour une puis quatre cultures, et ferme et
supprime sa base. Il n’ouvre aucune base de production ni aucun serveur HTTP.

Mesures locales WSL du 9 septembre 2026, sous charge des tests navigateur :

| Sélection | Lecture médiane / maximum | Rendu Jinja médian / maximum | HTML | Points climatiques |
| --- | --- | --- | --- | --- |
| 1 culture | 45,7 / 63,7 ms | 10,6 / 123,3 ms | 134 683 octets | 210 |
| 4 cultures | 167,2 / 186,3 ms | 12,9 / 13,4 ms | 438 943 octets | 840 |

Mesures sur le **Pi aarch64, Python 3.11.2**, avec le code du lot 4 transféré dans
`/tmp/phyto-analysis-lot4.t2uWjf` et une base synthétique temporaire indépendante :

| Sélection | Lecture médiane / maximum | Rendu Jinja médian / maximum | HTML | Points climatiques |
| --- | --- | --- | --- | --- |
| 1 culture | 203,0 / 212,1 ms | 17,2 / 408,6 ms | 134 682 octets | 210 |
| 4 cultures | 759,3 / 762,5 ms | 33,4 / 33,5 ms | 438 942 octets | 840 |

Le premier rendu inclut la compilation du template, d’où son coût supérieur. Ces
mesures portent sur SQLite, les projections et Jinja, pas sur le transfert réseau
ni le navigateur. Les [mesures brutes](cultures-ui-lot-4-mesures.json) sont conservées.
Le service `phyto` est resté `active/running`, PID 816102 inchangé avant/après ; le
benchmark n’a chargé que sa base synthétique, supprimée à la fermeture.

Le téléphone physique et un lecteur d’écran réel restent des validations manuelles
distinctes des profils Chromium, du toucher/clavier automatisé et d’axe.

## Validation automatisée

- **800 tests Python réussis**, avec les avertissements de dépréciation existants.
- Suite navigateur complète : 250 réussites, 103 exclusions prévues, deux échecs
  initiaux. Le test PWA utilisait encore « Enregistrer le suivi » alors que les
  rappels proposent « Fait » et « Reporter » depuis les lots précédents : ses deux
  assertions, hors ligne puis en ligne, contrôlent désormais les deux boutons.
  Le contrôle axe des pages principales avait dépassé 20 s sous charge ; il passe
  avec un seul worker, sans modifier son délai ni ses assertions.
- Après reprise : **252 scénarios distincts validés**, 103 exclusions prévues.
  Le scénario PWA vérifie toujours zéro mutation rejouée et aucune API en cache.
- Reprise du lot 4 enrichi : **12 réussites, 3 exclusions PWA prévues**. Comparaison
  des absences et d’un vrai zéro, axe en thèmes sombre/plein jour, clavier et toucher,
  tableau différé à 2 000 points, galerie avec image chargée puis indisponible,
  précédent/suivant, Échap et retour du focus.
- Dernière reprise comparaison + PWA : **5 réussites, 5 exclusions prévues**.
- `git diff --check` et miroir `CLAUDE.md` / `AGENTS.md` sans écart.

Les scénarios d’interception HTTP du lot 4 s’exécutent sur bureau, mobile, 320 px
et paysage, hors service worker ; le comportement PWA est exercé par les scénarios
spécifiques existants. Toutes les écritures navigateur restent dans les bases
temporaires isolées de la fixture, jamais sur une cible externe.

```bash
.venv/bin/python -m pytest -q
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test --workers=2
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures_ui_lot_4.spec.js --workers=2
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures.spec.js tests/ui/dashboard.spec.js --project=pwa-chromium --workers=1 --grep 'cycles : PWA datée|les pages principales'
PHYTO_TEST_PYTHON=.venv/bin/python npx playwright test tests/ui/cultures.spec.js tests/ui/cultures_ui_lot_4.spec.js --workers=1 --grep 'cycles : PWA datée|comparaison alignée'
```

## Captures de validation

- [Comparaison sur bureau](../images/cultures-ui-lot-4/comparaison-bureau.png).
- [Comparaison sur mobile en plein jour](../images/cultures-ui-lot-4/comparaison-mobile-plein-jour.png).
- [Courbe et tableau sur mobile](../images/cultures-ui-lot-4/courbes-mobile.png).

Les données sont fictives. Les captures pleine page montrent la barre mobile fixe
à la position du viewport initial ; ce n’est pas une seconde barre dans la page.
