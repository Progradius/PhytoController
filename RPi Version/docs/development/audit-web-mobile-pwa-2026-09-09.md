# Audit UI/UX web, mobile et PWA — 9 septembre 2026

Le produit possède un socle web solide et une richesse métier réelle. Sa priorité d'évolution est
la réduction du coût de lecture et de navigation sur téléphone, puis la qualification du cycle de vie
PWA. Une modernisation des parcours et de la présentation peut s'appuyer sur l'architecture actuelle.
Une migration vers une SPA ou un framework n'est pas justifiée par les problèmes observés.

## Périmètre, méthode et limites

Audit du tableau de bord, alarmes, historique, configuration, console, accueil du carnet, fiche culture,
solutions, cycles, plages cibles, éclairage, équipements, journal, erreurs et fonctionnement PWA.
Lecture des gabarits, CSS, JavaScript, routes, tests et documentation ; inspection de captures et du DOM
dans Chromium ; contrôle axe ; parcours avec données fictives ; confrontation à des sources officielles.

Point de départ Git : `641a7ef`, arbre propre à la première lecture. Des modifications parallèles sont
apparues pendant l'audit dans les fichiers Solutions, API et infrastructure Playwright. Elles ne sont
pas des modifications de cet audit. Les résultats sont ceux des captures et scénarios conservés,
pas une certification de chaque version ultérieure de l'arbre. Le serveur Python de test a été démarré
avant ces changements ; les fichiers statiques et gabarits ont pu être relus pendant les navigations.

Les manipulations ont utilisé `tests/ui_server.py`, une configuration temporaire, des capteurs simulés
et une base de carnet temporaire. Aucun accès au Pi, aucune modification de configuration de production,
aucune commande matérielle. Les valeurs répétées des capteurs et les états de conduite inconnus sur les
captures appartiennent à cette fixture : ce ne sont pas des défauts diagnostiqués sur la serre.

Trois largeurs : 320 et 390 px, hauteur 844 px ; bureau 1440 × 900. La matrice initiale contient
36 visites, soit 12 pages à trois largeurs. Les scénarios complémentaires couvrent une mère avec six
relevés, sa fiche, ses cycles, les thèmes sombre et plein jour, une consultation hors ligne et un
historique simulé. Le contrôle des pages a principalement été réalisé avec les service workers bloqués ;
le scénario hors ligne a été réalisé avec un vrai service worker activé sur l'origine loopback.

Les mesures de hauteur portent sur les documents complets et ne sont pas des temps de tâche. Une
capture pleine page place la barre fixe à la hauteur du viewport initial : elle ne signifie pas que la
navigation se répète au milieu du document. Les mesures initiales n'incluent pas le bandeau HTTP LAN,
car localhost est un contexte sécurisé pour le navigateur.

**Non qualifiés ici** : iPhone/iPad physiques, VoiceOver/TalkBack, clavier virtuel réel, encoches réelles,
installation avec certificat local, téléphone à faible mémoire, performance sur Pi et Wi-Fi de serre,
mise à jour PWA pendant une saisie, plusieurs fenêtres et perte du stockage navigateur. Les cas de
chauffage, coupure et redémarrage sont revus côté interface et dans les tests existants ; aucune
qualification électrique n'est revendiquée. Il s'agit d'un audit expert, pas d'une étude auprès
d'utilisateurs ni d'une déclaration complète de conformité WCAG.

## Résultats vérifiés

| Vérification | Résultat | Portée |
| --- | --- | --- |
| Largeur des 36 documents | Aucun débordement horizontal global mesuré | Les zones internes défilantes et les états non ouverts restent à examiner séparément |
| Axe sur les 12 pages à 390 px, sombre | 11 sans violation détectée ; Console avec `aria-prohibited-attr` | Tags WCAG 2 A/AA, 2.1 AA, 2.2 AA |
| Fiche, solutions et cycles remplis | Aucune violation détectée dans les états audités | Une mère, six relevés |
| Solutions plein jour, journal plein jour, historique rempli | Aucune violation détectée | Ne certifie pas tous les contrastes et états possibles |
| Tests existants `dashboard.spec.js`, mobile et PWA Chromium | **28 réussites, 4 exclusions**, 13,5 s | Exclusions conditionnelles prévues ; pas la suite UI complète |
| Consultation de Solutions hors ligne | Page datée disponible, commandes désactivées | Les filtres GET sont également désactivés |
| Console, seconde vérification | Même erreur ARIA reproduite | Défaut absent de la liste des pages du test axe général |

Les premiers lancements Chromium ont été bloqués par le bac à sable. Les résultats ci-dessus sont ceux
de la relance autorisée, pas ceux de ces échecs d'environnement. Aucun fichier Python n'a été modifié
par l'audit ; la suite pytest complète n'a pas été relancée.

Preuves : [mesures des 36 visites](../images/audit-web-mobile-pwa-2026-09-09/measures.json),
[scénarios avec données](../images/audit-web-mobile-pwa-2026-09-09/scenarios.json),
[vérifications complémentaires](../images/audit-web-mobile-pwa-2026-09-09/finalchecks.json),
[journal des tests ciblés](../images/audit-web-mobile-pwa-2026-09-09/tests-dashboard.log).
Le libellé `history-rempli` dans `scenarios.json` correspond à une première interception neutralisée par
le service worker : cet état était encore indisponible. La mesure valide de l'historique rempli est
dans `finalchecks.json`, réalisée dans un contexte séparé sans service worker ; la capture a été remplacée.

## Maturité actuelle

| Dimension | Appréciation qualitative | Enjeu principal |
| --- | --- | --- |
| Cohérence graphique | Bonne base | Réduire la typographie décorative dans les informations métier |
| Adaptation à la largeur mobile | Bonne sur les pages examinées | Passer du réagencement responsive à des parcours réellement courts |
| Hiérarchie opérationnelle | À améliorer | Mettre l'urgence, le contexte et l'action avant les explications |
| Formulaires et prévention d'erreur | Déjà avancées | Simplifier les longues saisies, mieux protéger les interruptions mobiles |
| Accessibilité | Bon socle, qualification incomplète | Corriger Console et étendre les contrôles aux états ouverts et aides techniques |
| Analyse et graphiques | Fonctionnellement riche | Alléger la présentation et harmoniser l'exploration tactile |
| Hors ligne | Politique adaptée au contrôleur | Rendre la disponibilité lisible et conserver les outils de lecture locale |
| Installation et cycle de vie PWA | Partiels | iPhone, changement de version, stockage, notifications et diagnostic |
| Performance terrain | Non qualifiée par cet audit | Mesurer Pi + téléphone + réseau réel avec un carnet représentatif |

## Ce qu'il faut conserver

- Rendu serveur, ressources locales, liens directs, sections et fonctionnement sans dépendance Internet.
- Palette commune, variables CSS, police système pour le corps, boutons principaux de 44 px minimum,
  champs à 16 px, thème plein jour persistant, focus visible, lien d'évitement et réduction des animations.
- Barre basse mobile, prise en compte de la zone sûre inférieure, dialogues natifs et liens de diagnostic.
- Distinction entre état demandé, appliqué et relu ; affichage des absences ; explication des alarmes.
- Confirmation des commandes critiques, sauvegarde par section, garde de saisie et aperçu des réglages.
- Navigation partagée du carnet et contexte conservé ; formulaires communs, erreurs au champ,
  idempotence et reprise explicite après réponse perdue ; suggestions sans validation automatique.
- Courbes du carnet explorables au toucher et au clavier, tableaux équivalents, lacunes conservées,
  galerie et retours au contexte. Plusieurs manques des audits précédents sont désormais corrigés.
- Mode hors ligne daté, absence de file de commandes, absence de rejeu et absence de notification issue
  d'une vieille copie. Ces choix sont particulièrement adaptés à une interface de contrôle physique.

## État des lieux par page

### Tableau de bord

**Constat mesuré.** À 390 px, document de 5 035 px. Le titre « Climat actuel » commence à y=514,
« Actionneurs » à y=941, « Capteurs actifs » à y=2 803 et « Cultures en cours » à y=4 329.
Le climat est déjà résumé ; les six équipements et les trois cartes capteurs de la fixture allongent
ensuite fortement la page. Les cartes répètent notamment état, motif, prochaine transition et conduite
normale. [Capture](../images/audit-web-mobile-pwa-2026-09-09/dashboard-390.png).

**Effet UX.** Les éléments existent, mais l'opérateur doit parcourir beaucoup de contenu pour passer de
la surveillance à une tâche du carnet. Le premier écran renseigne moins vite qu'il ne pourrait.

**Recommandation.** Un haut de page compact avec état de la serre, fraîcheur, température/RH et cible ;
puis les anomalies et interventions prioritaires. Présenter les équipements normaux en lignes compactes
avec développement au toucher, en gardant les coupures actives et anomalies développées. Afficher un
accès aux tâches du jour avant le détail de tous les capteurs. Conserver des liens visibles « Voir les
équipements » et « Toutes les mesures ». Ne jamais cacher un défaut parce qu'une carte est repliée.

### Alarmes

**Constat mesuré.** À 390 px, le titre « Notifications locales » est à y=429 et l'état de la liste à
y=1 131 sans alarme. Le bloc de notifications et quatre filtres verticaux précèdent les occurrences.
Le gabarit utilise le même ordre quand des alarmes existent ; leur position exacte dépend des bandeaux.
[Capture](../images/audit-web-mobile-pwa-2026-09-09/alarms-390.png).

**Recommandation prioritaire.** Ordre proposé : résumé court → alarme la plus importante → liste →
filtres avancés repliables → préférences de notification. Chaque occurrence doit exposer immédiatement
le problème, la conséquence et l'action conseillée. Expliquer « Acquitter = signaler que vous avez vu
l'alarme ; cela ne corrige pas la panne ». Garder « Active, acquittée » distinct de « Résolue ».
La vue filtrée annonce déjà son actualisation au rechargement : conserver cette honnêteté et proposer
un bouton explicite d'actualisation si cette vue reste statique.

### Historique

**Acquis.** Périodes 24/48/72 h, bilan opérationnel, couvertures/lacunes, capteurs et actionneurs,
exploration clavier/pointeur, tableau de synthèse, annotations, vrai état d'indisponibilité.
Le scénario rempli mesure 3 903 px sur mobile.
[Capture](../images/audit-web-mobile-pwa-2026-09-09/history-rempli.png).

**À améliorer.** Le tracé canvas emploie des textes de 10–11 px (`history.js`), plus petits que les
14 px retenus pour certaines courbes du carnet. Le détail utilise une infobulle fixe proche du toucher ;
son confort avec le doigt et le clavier virtuel reste à qualifier. Les nombreuses légendes expliquent
bien la donnée mais alourdissent la lecture.

**Recommandation.** Trois ou quatre indicateurs résumés avant les tracés ; sélection claire d'un
indicateur ; détail sélectionné affiché sous le graphique sur téléphone ; texte des axes lisible ;
explications techniques dépliables. Harmoniser le vocabulaire et les gestes avec le carnet sans
imposer de fusion technique entre canvas et SVG. Tester le défilement vertical pendant un toucher sur
graphique et la conservation du point choisi au changement de taille.

### Configuration

**Acquis.** Modes Simple/Avancé, sections indépendantes, aperçu d'application, erreurs liées aux champs,
protection de sortie, barre de saisie mobile et accès direct depuis les équipements.

**Constat.** Le mode simple reste un formulaire de 3 662 px dans la fixture. Les horaires sont composés
de champs séparés ; plusieurs ensembles doivent être relus avant l'enregistrement. Le bloc de
normalisation des réglages peut annoncer des changements additionnels importants.
[Capture](../images/audit-web-mobile-pwa-2026-09-09/conf-390.png).

**Recommandation.** Regrouper visuellement « Jour/nuit », « Éclairage », « Climat » avec résumés
compacts ; conserver l'unité de sauvegarde existante du mode simple. Avant la sauvegarde, rendre très
lisible « valeurs modifiées → valeurs appliquées », y compris les normalisations. Ajouter une recherche
de réglage en mode avancé si les essais utilisateurs confirment la difficulté d'orientation. Tester
les décimales françaises, horaires, clavier virtuel et barre de sauvegarde sur de vrais téléphones.
Une barre fixe supplémentaire ne doit jamais masquer le dernier champ ou son erreur.

### Accueil du carnet et fiche culture

**Acquis.** Agenda du jour, tâches et rappels, origines, distinction démarrage/reprise d'une culture,
actions métier autorisées, observation/photo, bilan et traçabilité. Les liens de rubrique conservent
le contexte ; le journal possède désormais recherche et raccourcis de période.

**Constat mesuré.** La fiche d'une mère avec six relevés mesure 4 325 px. Son nom est à y=412,
« Que faire maintenant ? » à y=983, après l'introduction, les navigations, les métadonnées et les aides.
Les explications sur le calcul d'âge et les règles de traçabilité sont dans le parcours de lecture.
[Capture](../images/audit-web-mobile-pwa-2026-09-09/fiche-remplie.png).

**Recommandation.** En tête : nom, espace, stade et âge en une synthèse ; puis action principale
« Saisir un relevé » et « Observation / photo ». Garder les aides utiles sous ces actions. Déplacer
les règles de calcul dans « Comprendre ces dates », les corrections et le backfill dans un accès
secondaire explicite. Faciliter le retour à la liste avec sa position et ses filtres.
Le bilan et les archives doivent rester accessibles sans monopoliser la lecture quotidienne.

### Solutions et relevés

**Constats mesurés.** 3 259 px à vide ; 7 001 px avec six relevés d'une mère. La page regroupe
actions de saisie, réservoirs, filtres, deux graphiques, légendes détaillées, export, lignes de journal,
contexte et recettes. Le volume d'information reste élevé même sans mesure. Dans la fixture, une
valeur EC calculée (`1.4 + 0.05`) apparaît en décimales binaires longues : le gabarit affiche les nombres
bruts. Les véritables saisies manuelles n'ont pas toutes ce problème, mais la restitution doit le gérer.
[État vide](../images/audit-web-mobile-pwa-2026-09-09/cultures-solutions-390.png),
[six relevés, plein jour](../images/audit-web-mobile-pwa-2026-09-09/solutions-plein-jour.png).

**Recommandation.** Trois vues de consultation et action clairement identifiées : Saisir, Relevés,
Analyser. Au sein d'une cible sélectionnée, montrer d'abord cette cible et son dernier relevé. Les
réservoirs globaux peuvent être repliés dans cette vue. À vide, une explication courte et une action
de première saisie suffisent ; ne pas occuper deux grands graphiques avec leurs légendes complètes.
Compacter chaque relevé en date, cible, pH, EC, anomalie éventuelle ; mettre le contexte historique
et les références techniques dans « Détails ». Formater à la présentation selon une précision métier
explicite et avec virgule française, sans arrondir ni modifier les valeurs persistées.

### Cycles et rappels

**Constat.** Les rappels, comparaisons, climats, vérifications, photos et sauvegardes cohabitent sur
la même page. 2 275 px à vide et 3 705 px avec une culture dans le scénario.

**Recommandation.** Donner un accès immédiat aux rappels du jour et séparer visuellement « À faire »
de « Comparer ». Conserver les gestes directs Fait/Reporter déjà présents, le plafond de comparaison
et les absences explicites. Placer l'export complet dans un espace de sauvegarde clairement repérable.
Les rappels du carnet ne doivent pas être confondus avec les alarmes système ou leurs notifications.

### Plages cibles, éclairage, équipements

**Acquis.** Règles temporelles explicites, historique des révisions et séparation entre déclarations
du carnet et configuration réellement appliquée.

**Constats.** L'éclairage mesure 2 762 px et les équipements 3 313 px à vide. Sur Équipements, le
catalogue courant précède le contexte à une date (y=1 170), puis les affectations (y=1 548).

**Recommandation.** Choisir d'abord espace/culture et date, puis présenter « déclaré dans le carnet »
et « appliqué maintenant » avec leurs libellés respectifs. Placer les règles de résolution dans un
développement consultable, en conservant une indication courte près de la valeur. Sur Équipements,
faire des affectations la vue principale et replier le catalogue de référence. Sur Plages, mettre
en avant la plage actuellement applicable, sa source et sa période, sans créer de fusion entre sources.

### Journal

**Acquis.** Recherche libre, filtre par cible, raccourcis 7/30 jours, observations d'espace, contexte
historique et export du filtre. Les anciennes recommandations d'ajouter ces recherches ne sont plus
des manques actuels.

**Recommandation.** Faire de la chronologie une vue lisible de l'activité : date, opération, cible,
résumé et photo éventuelle. Détails de résolution et de révision au second niveau. Proposer un accès
visible à la recherche sur les carnets volumineux ; garder les filtres et le contexte au retour.

### Console, erreurs et actions système

**Défaut vérifié.** `console.html` donne un `aria-label` à un `<pre>` sans rôle permettant ce nom.
Axe signale `aria-prohibited-attr`, impact « serious ». Corriger la sémantique avec une région nommée
appropriée et le contenu préformaté à l'intérieur ; ne pas transformer tout le flux en annonce live
permanente. Étendre le test d'accessibilité existant à Console.

La Console offre déjà pause, suivi, niveau, composant, recherche et copie/export. Sur mobile, regrouper
les actions secondaires et réserver davantage de hauteur au journal. L'export est utile pour diagnostiquer
à distance. Prévoir les erreurs de presse-papiers, surtout en HTTP.

Les pages d'erreur possèdent un retour au tableau ; elles pourraient proposer aussi une reprise
contextuelle et un réessai lorsque pertinent. Le suivi de redémarrage et les confirmations constituent
un acquis. Les formulations « état GPIO relu » ou « sonde de vie » peuvent être placées en détail,
avec un résumé immédiat compréhensible. [Erreur 404](../images/audit-web-mobile-pwa-2026-09-09/error-404.png).

## Navigation, design et accessibilité transversale

### Navigation mobile

`base.html` expose Tableau, Alarmes, Historique, Plus ; Cultures est dans Plus. Pour un usage mêlant
surveillance et carnet quotidien, cela ajoute un geste récurrent. Proposition à éprouver :
**Serre · Cultures · Alarmes · Plus**, avec Historique accessible depuis Serre et Plus. Une barre à cinq
destinations est envisageable sur les tailles suffisantes, mais doit rester utilisable à 320 px.
Le choix final dépend de la fréquence réelle des tâches, qui n'a pas été observée auprès d'utilisateurs.

Les sept rubriques du carnet défilent horizontalement sous 480 px. Conserver l'onglet actif visible
au chargement et au retour, indiquer la possibilité de défiler et envisager un sélecteur de rubrique
plus compact si les essais révèlent que les derniers onglets sont ignorés. Éviter d'ajouter simultanément
barre fixe haute, barre de saisie et barre basse sans mesurer l'espace utile.

### Présentation

Conserver l'identité végétale et le mode plein jour. La police Visitor apporte une marque distinctive,
mais son emploi dans les petits libellés, badges et groupes d'équipements nuit à la lecture rapide.
La réserver principalement à la marque ; utiliser une police système et des chiffres tabulaires pour
les valeurs, dates et durées. Réduire les majuscules, les microtextes et les répétitions.

Plusieurs liens secondaires ont une hauteur de 18 à 25 px : « Saisir un relevé », raccourcis locaux,
liens de réglage et exports. Viser une zone tactile de 44–48 px pour les actions autonomes fréquentes.
Cela est une cible de confort : WCAG 2.2 AA fixe 24 × 24 px avec exceptions, notamment d'espacement
et de liens dans le texte. Une hauteur inférieure à 44 px n'est donc pas une violation automatique.
Les radios CSS de 1 px relevés par le script ont des labels cliquables : ils ne sont pas comptés comme
défauts de taille sans mesurer ces labels. [Règle W3C et exceptions](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).

Ne pas utiliser la couleur seule ; les états textuels existants sont à conserver. Revoir la lisibilité
du plein jour dehors et la distinction des séries pour différents types de perception des couleurs.
Le thème manuel est un choix valable ; un mode « Système » serait une option, pas une correction urgente.

### Qualification accessible et mobile

Étendre les tests aux formulaires ouverts et refusés, dialogues, menus, états hors ligne, grandes tailles
de texte, zoom/reflow, clavier et focus sous les barres fixes. Compléter axe par VoiceOver et TalkBack.
Le critère « focus non entièrement masqué » et la taille minimale font partie de WCAG 2.2 ; la cible
produit doit être encore plus confortable que le minimum. [Norme WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## PWA : état des lieux et améliorations

### Installation et prise en main

Manifest avec identité stable, mode standalone, icônes 192/512, maskable et raccourcis : présent.
Le bouton d'installation n'est révélé qu'après `beforeinstallprompt` et uniquement sur le tableau.
La documentation TLS détaille Android ; l'interface ne fournit pas de guide iPhone équivalent.

Créer une page « Application sur ce téléphone » accessible depuis Plus : état HTTPS, aide d'installation
adaptée à la plateforme, état installé, lecture hors ligne, notifications, version. Sur les navigateurs
sans invite exploitable, montrer une aide adaptée et vérifiée sur la version réelle du système.
Safari continue d'évoluer : iOS/iPadOS 26 permet d'ouvrir les sites ajoutés à l'accueil comme web apps.
Il faut tester le parcours courant plutôt que promettre un bouton Chrome universel.
[Documentation WebKit Safari 26](https://webkit.org/blog/17333/webkit-features-in-safari-26-0/).

La confiance dans le certificat local est une étape réelle d'adoption. L'interface peut guider vers
la procédure d'administration et identifier l'adresse correcte ; elle ne peut pas installer elle-même
une autorité de confiance. Qualifier Android et iOS, changement d'adresse réseau et renouvellement TLS.

### Hors ligne et réseau lent

La politique réseau d'abord et les copies datées sont adaptées. La reproduction sur Solutions montre
que `setControlsDisabled()` désactive **tous** les contrôles dans les formulaires, y compris les
filtres GET et les curseurs éventuels placés dans un formulaire.
[Capture](../images/audit-web-mobile-pwa-2026-09-09/solutions-offline.png).

Ne pas réactiver aveuglément les GET : ils peuvent demander une vue absente du cache. Distinguer
les outils locaux de lecture (recherche dans les lignes chargées, exploration, sélection locale) des
requêtes serveur et des mutations. Garder les premiers utilisables, expliquer les secondes et bloquer
les mutations. Afficher « Filtre limité aux données conservées » si un filtrage local est ajouté.

L'index des pages conservées existe sur Cycles mais reste peu visible. L'exposer dans l'espace PWA
avec date, limites, liste des vues disponibles et lien vers le carnet. La page `/offline` ne propose
actuellement que Tableau, Alarmes et Historique. Ajouter un accès au carnet conservé, sans faire croire
que toutes ses pages sont disponibles.

Le service worker emploie `fetch()` sans délai applicatif dans les navigations et le préchargement.
Les API ont des délais, mais un Wi-Fi qui garde une connexion sans répondre peut laisser la navigation
attendre longtemps avant le repli. **Risque identifié par lecture, durée non reproduite ici.** Définir
un budget d'attente et un timeout de transport ; utiliser alors la copie datée seulement après cet échec
de transport. Tester également les réponses HTTP 500, distinctes d'une panne réseau.

### Mise à jour et stockage

`service-worker.js` active immédiatement la nouvelle version (`skipWaiting`, `clients.claim`) et
supprime les anciens caches. `pwa.js` n'offre pas de cycle explicite de version disponible/activation.
**Risque de cycle de vie**, pas incident de perte de données reproduit : une ancienne page ouverte,
une nouvelle version et le retrait des caches doivent être testés ensemble, notamment après coupure réseau.

Prévoir une indication de version et « Mise à jour disponible » ; activation/rechargement à un moment
compatible avec les saisies. Éviter un rechargement forcé pendant un formulaire. Tester deux fenêtres,
retour de veille et ancien document hors ligne. Le cycle de mise à jour du navigateur est documenté
par [web.dev](https://web.dev/learn/pwa/update).

L'initialisation attend `navigator.serviceWorker.ready` avant de brancher notifications et polling
global. Quand un worker tarde à s'activer, ces capacités peuvent rester en attente. Isoler les
améliorations PWA pour que l'interface connectée continue son initialisation ; tester l'installation
incomplète et un stockage refusé. Sur le parcours sans worker des mesures initiales, le statut
« Vérification de la compatibilité… » ne constitue pas une preuve de panne en production.

### Saisies interrompues

Les gardes de sortie existent, mais les saisies restent principalement en mémoire de page.
Sur mobile, `beforeunload` n'est pas un filet garanti lors de la fermeture du processus ou de l'application.
[Comportement documenté par MDN](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event).

Envisager des brouillons **strictement déclaratifs** pour les notes et formulaires du carnet :
« Brouillon sur cet appareil, non enregistré », restauration explicite, expiration, suppression,
revalidation de cible/date/version et aucune soumission automatique. Ne jamais restaurer implicitement
une mesure comme une nouvelle acquisition, une confirmation, une vérification cochée, un secret ou une
commande de contrôle. Les photos demandent une stratégie distincte de taille et de confidentialité.
Il s'agit d'une évolution produit à concevoir, pas d'une réactivation des mutations hors ligne.

### Notifications

Opt-in, déduplication et absence de notifications depuis des snapshots : acquis. Le texte précise déjà
l'absence de garantie application fermée. Mais le poller ne travaille que si le document est visible :
« tant que la PWA reste active » peut être compris comme « encore ouverte en arrière-plan ».
Préciser « lorsque l'application est ouverte au premier plan et connectée », avec la limite liée au
système. L'aide de permission refusée cite actuellement Chrome même sur les autres navigateurs.

Ne pas présenter ce mécanisme comme une alerte distante permanente. Le Web Push sur iOS suit un autre
parcours, notamment pour les applications ajoutées à l'écran d'accueil ; son existence dans la
plateforme ne signifie pas que le contrôleur l'implémente.
[WebKit, Web Push sur iOS/iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/).

## Performance et maintenabilité

Le rendu serveur, les ressources locales, le chargement différé des photos, le polling sensible à la
visibilité et les requêtes bornées sont de bons choix. Les graphiques du carnet ont déjà bénéficié de
corrections de coût et d'une construction différée des tableaux. Ne pas réintroduire les anciennes
recommandations de recalcul comme si ces correctifs n'existaient pas.

Le total des fichiers CSS et JS présents est d'environ 343 Ko non compressés ; **ce n'est pas le poids
d'une page transférée**, toutes les ressources ne sont pas chargées partout. La configuration initiale
représente environ 2 120 éléments DOM dans la fixture : replier visuellement un formulaire ne supprime
pas son coût de parsing et d'initialisation. Mesurer avant de décider d'un chargement à la demande.

Établir des budgets sur Pi et téléphone représentatifs : réponse HTML, contenu principal visible,
interaction de graphique, ouverture d'un formulaire, retour après enregistrement, DOM et mémoire sur
un carnet à 30/90/365 jours. La longueur constatée justifie d'abord un travail de présentation ; elle
ne prouve pas à elle seule une lenteur.

Repères externes : LCP ≤ 2,5 s, INP ≤ 200 ms et CLS ≤ 0,1 au 75e percentile, séparés mobile/bureau.
Ces objectifs ne sont **pas des mesures obtenues par cet audit**. Sur une application LAN, utiliser
une instrumentation locale et des essais contrôlés, sans dépendre d'un service public d'analytics.
[Définition et seuils Core Web Vitals](https://web.dev/articles/vitals).

Définir quelques composants réutilisables dans les outils actuels : en-tête compact, état vide,
résumé d'alarme, ligne d'équipement, entrée de journal, groupe de champs, détail de graphique et état
réseau. Harmoniser les espacements et comportements plutôt que multiplier les exceptions CSS par page.

## Backlog priorisé

P1 = prochain lot, impact fréquent ou obstacle vérifié ; P2 = évolution structurante ; P3 = finition
ou amélioration facultative. Aucun P0 matériel n'est établi par cet audit d'interface.
Tailles relatives : S = correction localisée, M = plusieurs vues/états, L = parcours transversal à qualifier.

| ID | Priorité | Action | Taille | Critère d'acceptation |
| --- | --- | --- | --- | --- |
| UX-01 | P1 | Mettre les occurrences avant notifications/filtres | M | Première alarme critique et action visibles dans le premier écran utile du scénario mobile défini |
| UX-02 | P1 | Compacter le haut de tableau et les équipements normaux | M | État, fraîcheur, T/RH et alarme visibles sans défilement à 390 × 844 ; accès direct aux équipements |
| UX-03 | P1 | Accès direct Cultures dans la barre mobile | M | Depuis toute page, carnet en un geste ; focus, état actif et retour préservés à 320 px |
| UX-04 | P1 | Corriger le nom accessible de Console | S | Axe sans `aria-prohibited-attr`, région lisible au lecteur d'écran sans annonces continues |
| UX-05 | P1 | Installation guidée Android/iPhone | M | Aucun cul-de-sac quand l'invite est absente ; parcours testé sur appareils avec certificat approuvé |
| UX-06 | P1 | Rendre exacte la promesse des notifications | S | Premier plan/connexion explicités, aide de permission adaptée au navigateur |
| UX-07 | P1 | Alléger états vides et relevés de Solutions | M | À vide une action claire ; six relevés lisibles sans répétition systématique de la traçabilité |
| UX-08 | P1 | Formater les nombres affichés | S | Décimales françaises bornées, zéro distinct de l'absence, précision persistée inchangée |
| UX-09 | P2 | Replacer actions et contexte en tête de fiche | M | Nom/espace/stade et première action dans le premier écran du scénario nominal |
| UX-10 | P2 | Simplifier la lecture de Configuration | M | Sections compréhensibles, changements induits explicites, dernier champ et sauvegarde accessibles au clavier mobile |
| UX-11 | P2 | Harmoniser l'analyse tactile | M | Point choisi lisible hors du doigt, axes lisibles, défilement vertical possible, tableau accessible |
| UX-12 | P2 | Clarifier lecture hors ligne et index des copies | M | Recherche locale utilisable si proposée, couverture annoncée, mutations bloquées, accès carnet depuis `/offline` |
| UX-13 | P2 | Définir délais de navigation et indépendance de l'initialisation PWA | M | Réseau sans réponse : repli daté dans le budget défini ; worker défaillant : interface connectée utilisable |
| UX-14 | P2 | Cycle explicite de mise à jour PWA | L | Saisie ouverte + mise à jour + deux fenêtres + hors ligne : aucun rechargement destructeur implicite |
| UX-15 | P2 | Brouillons déclaratifs à restauration explicite | L | Arrêt du navigateur : note récupérable ; aucun rejeu, confirmation ou mesure inventée |
| UX-16 | P2 | Qualification Safari/iOS et aides techniques | M | Scénarios critiques sur appareils, VoiceOver/TalkBack, zoom, paysage et clavier virtuel |
| UX-17 | P2 | Mesures de performance terrain | M | Baseline et budgets reproductibles sur Pi/téléphone/carnet représentatifs |
| UX-18 | P3 | Lisibilité, cibles tactiles et vocabulaire | M | Actions fréquentes 44–48 px, textes métier lisibles, libellés cohérents et sans jargon inutile |
| UX-19 | P3 | Parcours photo mobile homogène | M | Prise de vue ou choix existant, aperçu, taille et refus compréhensibles, reprise de photo sans doublonner la note |

## Séquence de réalisation recommandée

1. **Lecture et urgence** : UX-01 à 04, 06 à 09, premières harmonisations de texte. Prototyper le
   tableau, Alarmes, la fiche et Solutions à 390 px puis 320 px ; vérifier les mêmes cas au bureau.
2. **Application mobile quotidienne** : configuration, exploration, installation et disponibilité
   hors ligne. Tester chaque parcours complet avec clavier virtuel et retour arrière.
3. **Cycle de vie et robustesse** : réseau lent, mise à jour, plusieurs fenêtres, interruption de saisie,
   stockage, reprise de veille. Les brouillons déclaratifs constituent un chantier explicite séparé.
4. **Qualification** : appareils réels, aides techniques, performance sur Pi et usages représentatifs.

Les estimations S/M/L sont comparatives ; elles ne constituent pas un engagement calendaire. Les lots
de navigation nécessitent moins de changement dorsal que les brouillons ou le cycle de mise à jour.

## Validation produit avant de parler d'« état de l'art »

Évaluer avec plusieurs opérateurs, dont au moins un peu familier du logiciel, les tâches suivantes :
comprendre l'état de la serre ; diagnostiquer une alarme ; couper temporairement un équipement et
comprendre sa reprise ; modifier une consigne ; saisir pH/EC sur la bonne cible ; observer et joindre
une photo ; marquer/reporter un rappel ; comparer deux cultures ; retrouver une intervention ;
consulter une copie hors ligne puis revenir en ligne. Les tâches de contrôle physique se font sur
simulateur ou selon la procédure matérielle supervisée du dépôt.

Objectifs initiaux à valider : état de la serre compris en moins de 5 s ; accès à la tâche principale
en un geste depuis le bon contexte ; 90 % de réussite sans aide sur les tâches fréquentes ; zéro
ambiguïté entre enregistré et brouillon, état vivant et copie, acquittement et résolution. Mesurer
durées, erreurs, abandons et compréhension, pas uniquement captures et scores automatiques.

La prochaine amélioration la plus rentable est de rendre les actions fréquentes immédiatement
accessibles et les détails consultables à la demande, tout en gardant visibles les exceptions qui
changent une décision. Le socle actuel permet de le faire progressivement avec des preuves de résultat.
