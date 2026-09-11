# Faire évoluer le cadre de développement de PhytoController

> **Statut : proposition de référence pour une implémentation future, non implémentée par ce document.**
> **Date de l’état des lieux : 11 septembre 2026.**
> **Périmètre : `RPi Version/`, avec CI à la racine Git `PhytoController/`.**
> **Origine : comparaison demandée par le propriétaire avec le harness de DanceFlow (`deci`), puis demande explicite d’intégrer la création d’un design system.**
> **Responsable de l’arbitrage : propriétaire du projet.** L’ordre proposé ci-dessous n’est pas une autorisation de déploiement ou de modification matérielle.

## 1. Objet et usage de cette référence

Ce document conserve le contexte, les observations, les recommandations et les critères de sortie permettant d’amener PhytoController à un niveau de maîtrise comparable à celui recherché dans DanceFlow : travail efficace avec des agents IA, robustesse, traçabilité et évolutivité.

Il sert de référence de cadrage et de base aux futurs plans de réalisation. Il ne remplace ni les instructions courantes, ni la roadmap, ni le registre des risques. Les recommandations ne deviennent des règles projet qu’après leur adoption explicite et leur intégration dans les documents canoniques concernés.

Avant toute implémentation :

1. Relire `AGENTS.md`, `CLAUDE.md`, l’index documentaire et les documents spécialisés du périmètre.
2. Relire le code et la configuration actuels : les observations ci-dessous sont datées.
3. Examiner l’état Git, les travaux concurrents et la vraie racine du dépôt.
4. Identifier les recommandations déjà réalisées, devenues inutiles ou contredites par une nouvelle décision.
5. Créer un plan de lot borné, avec exclusions, preuves attendues et critères de clôture.
6. Mettre à jour la roadmap ou le suivi existant plutôt que créer un second suivi concurrent.

**Décision recommandée : transposer la chaîne de preuves et les mécanismes de cohérence de DanceFlow, sans recopier son volume de règles ni sa pile technique.** Phyto peut atteindre une maîtrise comparable avec un dispositif plus petit et adapté à un contrôleur physique.

## 2. Contexte de l’examen et limites de preuve

### 2.1 Demande initiale

Le propriétaire considère le cadre de DanceFlow comme une référence pour la gestion de projets avec des agents IA et souhaite déterminer ce qui doit être transposé dans PhytoController. Il a ensuite souligné l’absence apparente de design system dans Phyto : ce sujet fait partie intégrante de la recommandation, et non d’une amélioration cosmétique optionnelle.

La comparaison a été menée avec deux agents Sol et un agent Terra, sous orchestration et recoupement des conclusions. Cette organisation décrit l’examen effectué ; elle ne prescrit pas trois agents pour les futurs travaux.

### 2.2 Environnements observés

- Source de comparaison : `C:\Users\RaphaelPERLES\deci`.
- Cible : `C:\Users\RaphaelPERLES\PhytoController\RPi Version`.
- Vraie racine Git cible : `C:\Users\RaphaelPERLES\PhytoController`.
- Les chemins WSL correspondants commencent par `/mnt/c/Users/RaphaelPERLES/`.
- La version ESP32 voisine est hors périmètre : aucune synchronisation automatique avec elle.

### 2.3 Ce qui a été examiné

Instructions agents, documentation, risques, roadmap, tâches, scripts, tests, configuration de livraison, fondations CSS, macros Jinja et qualification UI. L’absence de CI a été vérifiée à la vraie racine Git, pas seulement dans `RPi Version/`.

Aucun accès au Pi de production, aucune qualification électrique, aucune lecture de secrets et aucune modification applicative n’ont été effectués pour l’état des lieux. Les suites applicatives de Phyto n’ont pas été exécutées pendant cet examen. Des modifications préexistantes étaient présentes dans le working tree : l’observation locale ne doit pas être assimilée à un audit d’un commit immuable.

Trois vérifications ciblées du harness DanceFlow ont été exécutées pendant l’examen :

| Vérification | Résultat observé |
|---|---|
| `scripts/check-guard-wiring.sh` | `rc=0`, 65 gardes inspectées, 6 dettes connues |
| `scripts/test-check-guard-wiring.sh` | `rc=0`, 12 scénarios sur 12 |
| `scripts/test-ci-guard-ledger.sh` | `rc=0`, 15 scénarios sur 15 |

Ces résultats prouvent ces contrôles à cet instant, pas la correction globale de DanceFlow ou de Phyto. Les nombres cités dans ce document sont des observations datées, jamais des seuils ou numéros à recopier dans un futur plan.

### 2.4 Discipline de lecture

Distinguer systématiquement :

- **Présent dans le dépôt** : mécanisme ou test lu.
- **Exécuté pendant l’examen** : commande et résultat effectivement observés.
- **Preuve historique documentée** : qualification rapportée par un document antérieur.
- **Recommandé** : proposition non encore réalisée.
- **À vérifier** : hypothèse qui ne justifie aucune correction à elle seule.

L’index Phyto distingue déjà implémenté, déployé, vérifié matériellement et ouvert/reporté. Cette distinction doit être conservée.

## 3. État des lieux comparatif

| Dimension | Phyto observé au 11 septembre 2026 | Évolution recommandée |
|---|---|---|
| Instructions agents | `AGENTS.md` et `CLAUDE.md` identiques, 564 lignes et environ 49 Ko chacun | Noyau court, lectures spécialisées, contrôle automatique du miroir |
| Documentation | Index, architecture, sûreté, exploitation, références, décisions, archives | Garder l’organisation ; préciser responsabilités et déclencheurs de revue |
| Pilotage | Roadmap, registre des risques, tâches et plans détaillés | Rôle unique par support et reprise de session structurée |
| Tests Python | Politique climatique, faux GPIO, configuration, persistance, supervision, HTTP | Exécution automatique et traçabilité des invariants |
| Tests web | Tests JS, Playwright, PWA, macros, accessibilité et mesures | Portes adaptées au périmètre et au coût |
| CI | Aucun workflow versionné trouvé à la racine Git | Priorité du socle de livraison |
| Hooks agents/Git | Aucun harness de hooks versionné ou hook Git actif identifié dans la cible | Scripts portables et CI d’abord ; intégrations outils ensuite |
| Lint et typage | Aucun linter configuré ; aucune porte de typage/couverture identifiée | Introduction progressive après mesure |
| Architecture | Contraintes décrites et certaines protections dans les doubles de test | Quelques règles transversales exécutables |
| Invariants | Modèle de sûreté et scénarios déjà riches | Relier contrat, preuve, détection et qualification |
| Déploiement | Verrou, contrôles de santé, commit chargé et rollback | Compatibilité des données, restauration et manifeste de release |
| Matériel | Procédure supervisée séparée et limites explicites | Préserver la distinction logique/électrique/charge |
| UI | Tokens, thèmes et huit macros partagées testées | Design system formalisé, catalogue et adoption |
| Agents concurrents | Consignes documentaires, ressources potentiellement partagées | Périmètres disjoints, artefacts isolés et responsable d’intégration |

### 3.1 Forces à préserver

- La politique `components/climate_policy.py` est un noyau déterministe testable sans matériel.
- `ConfigStore` est le propriétaire de la configuration et utilise une écriture atomique.
- `utils/runtime_paths.py` sépare les données vivantes du checkout lorsque `PHYTO_DATA_DIR` est configuré.
- Le contrôleur distingue les tâches qui gouvernent le watchdog des services auxiliaires.
- Les tests hors matériel utilisent des fichiers temporaires et un faux GPIO.
- Les opérations HTTP dangereuses ne sont pas des navigations GET.
- Les procédures distinguent état logiciel, déploiement et observation matérielle.
- Le registre des risques exige une preuve de réduction ; une ancienne case cochée ne suffit pas.
- Les macros UI ont déjà des exemples documentés et des tests de rendu, d’échappement et de contrat.
- Les qualifications mobile/PWA et les mesures existantes constituent un investissement à conserver.

### 3.2 Limites importantes

L’absence de CI est explicitement ouverte dans [la roadmap](../roadmap.md). Les tests, le miroir et la checklist restent donc principalement dépendants de l’exécution locale par chaque contributeur.

La documentation est riche, mais les responsabilités et fréquences de revue restent à préciser. Les instructions agents mélangent règles stables, architecture détaillée et histoire des incidents. Le cadre doit réduire le coût de compréhension sans retirer les invariants matériels essentiels.

Les limites de boot, brochage, protections indépendantes, secrets et hypothèse LAN sont déjà décrites dans [le registre des risques](../risk-register.md). Ce document ne les déclare ni corrigées ni nouvellement découvertes.

### 3.3 Une conclusion écartée pendant le recoupement

La lecture isolée de `deploy/phyto.service` pourrait faire conclure à tort que le watchdog systemd n’est pas raccordé. Le dépôt contient aussi `deploy/phyto.service.d/watchdog.conf`, qui définit `Type=notify`, `NotifyAccess=main` et `WatchdogSec=600`. [La documentation systemd](../operations/systemd.md) décrit la composition et ses propriétés effectives historiquement observées.

**Ne pas transformer cette fausse piste en ticket de correction.** La recommandation correcte est un test du contrat composé : unité, drop-ins, installation et propriétés effectives. Plus généralement, la provenance doit couvrir le mécanisme entier avant de conclure.

## 4. Ce qu’il faut importer de DanceFlow

Le meilleur point d’entrée dans le dépôt de référence est `docs/AI_DELIVERY_OS.md`. Il explique la chaîne de preuves avec davantage de recul que l’accumulation de prescriptions dans les instructions agents.

### 4.1 Finding falsifiable avant correction

Pour un bug, conserver une fiche courte :

```text
Claim       X fait Y quand Z.
Provenance  Fichier et symbole lus dans cette session ; commande et sortie observée.
Prédiction  Si la claim est vraie, la commande C rendra le résultat observable R.
Exécution   C exécutée ; sortie, code de retour et conclusion confirmé/réfuté/indéterminé.
```

Une hypothèse sans observation peut déclencher une investigation, pas une modification préventive du code de production. Un numéro de ligne ancien sert à localiser, pas à prouver.

### 4.2 F2P et P2P

- **F2P — fail-to-pass** : même test vu rouge avant et vert après, avec codes de retour et résumés. L’échec doit venir du comportement visé.
- **P2P — pass-to-pass** : chemins voisins et contrepoids restés verts. Ils empêchent un correctif qui désactive entièrement la fonction.
- Une erreur d’import, de compilation, d’environnement ou de fixture n’est pas une preuve du bug métier.
- Le test doit vérifier un effet observable, pas seulement réciter son setup ou constater l’appel d’un mock.

Pour une nouvelle fonctionnalité, définir le contrat avant l’implémentation. Pour un correctif, prouver la reproduction sur le comportement antérieur. Une mutation ciblée peut vérifier la sensibilité du test ; elle ne doit pas contaminer un working tree partagé.

### 4.3 PROUVER, DÉTECTER et QUALIFIER

- **PROUVER** : le logiciel respecte le contrat dans les conditions testées.
- **DÉTECTER** : une anomalie est observée et signalée au canal prévu.
- **QUALIFIER** : la plateforme, les GPIO, les relais ou les charges se comportent comme attendu au niveau réellement observé.

Une alarme testée ne prouve pas une coupure physique. Une lecture GPIO ne prouve pas le changement de contact d’un relais. Une observation après READY ne qualifie pas la fenêtre électrique de boot.

Statuts minimaux : réussi, échoué, non exécuté, indéterminé. Un contrôle non exécuté ou sans résultat ne bénéficie jamais du vert d’un contrôle voisin ou d’une ancienne campagne.

### 4.4 Une classe d’erreur devient une contrainte durable

Lorsqu’une propriété violée peut être décrite sans nommer l’entité, rechercher un point d’accès unique, une règle d’architecture, un test de contrat ou une garde CI.

La règle doit accepter un cas sain voisin et rejeter le défaut visé. Si le motif sain et le motif fautif ont la même syntaxe, éviter les heuristiques et allowlists sans fin : reformuler l’architecture ou garder une preuve comportementale.

### 4.5 Tester les gardes et leur câblage

Pour chaque garde : cas fautif, cas sain, périmètre vide et code de sortie fiable. Pour les contrôles qui doivent découvrir un périmètre non vide, zéro élément mesuré doit empêcher une conclusion favorable.

Lorsque le nombre de gardes le justifiera, ajouter une petite méta-garde vérifiant que chacune possède un auto-test et un chemin d’exécution en CI. Ne pas copier immédiatement les dizaines de gardes SaaS de DanceFlow.

## 5. Validation commune et CI

### 5.1 Cible

Créer une commande canonique, par exemple `scripts/verify.sh`, appelée aussi par la CI. Ce nom est proposé, pas existant au titre de ce chantier.

| Profil proposé | Usage | Vérifications |
|---|---|---|
| Rapide | Boucle de développement | Tests ciblés, contrôles statiques et gardes concernés |
| Complet hors matériel | Intégration | Pytest, tests JS, documentation et architecture |
| UI | Modifications web | Macros, JS, Playwright pertinent, accessibilité |
| Release | Préparation de livraison | Validation complète, compatibilité et contrats de déploiement |
| Matériel supervisé | Changements physiques | Procédure séparée, jamais automatiquement incluse dans les autres profils |

### 5.2 Premier socle

Réutiliser les commandes existantes :

- `python3 -m pytest` ;
- `npm run test:js` ;
- Playwright selon le périmètre ;
- `diff -u CLAUDE.md AGENTS.md` ;
- vérification de diff adaptée à l’intervalle Git effectivement validé.

La CI doit être créée à la racine `PhytoController/.github/workflows/` si GitHub Actions est retenu, avec un répertoire de travail explicite `RPi Version/`. Adapter les filtres de chemins sans oublier les scripts ou configurations situés à la racine. Un `git diff --check` sur un checkout CI propre ne suffit pas à examiner un commit : viser le diff approprié.

Qualifier l’installation depuis un clone propre et un environnement neuf. Les venv locaux existants ne prouvent pas cette reproductibilité. Vérifier les contraintes de dépendances liées au GPIO sans accéder au matériel réel.

Préserver les protections des tests navigateur contre les écritures vers une cible externe. Utiliser des bases, ports et répertoires temporaires isolés. Une exclusion volontaire pour protéger une cible réelle est un résultat non exécuté, pas une preuve fonctionnelle.

### 5.3 Verdict et artefacts

Chaque résultat doit identifier : commande, périmètre, commit ou état source, environnement, identifiant de run, code de sortie, nombre de tests exécutés/échoués/exclus et chemins des rapports.

Les contrôles indépendants peuvent tous tourner avant une synthèse finale. Le verdict final doit échouer si une vérification requise échoue, manque ou ne produit pas son artefact attendu. L’agrégation ne doit pas transformer `continue-on-error` en succès global.

Interdire les conclusions sur un code de lancement en arrière-plan ou un pipe qui masque l’échec. Éviter les chemins de rapport partagés entre sessions.

### 5.4 Lint, types, couverture et mutations

Introduire lint et vérification de format dans un lot dédié, sans reformater arbitrairement le dépôt en même temps. Mesurer avant de choisir les règles, les périmètres et une éventuelle baseline.

Étendre progressivement le typage des frontières et des noyaux métier. Choisir et qualifier l’outil compatible avec le projet au moment de l’implémentation.

Mesurer la couverture avant de fixer un seuil. Favoriser branches et transitions critiques ; ne pas imposer immédiatement un pourcentage global arbitraire. Une couverture élevée de code trivial ne compense pas un invariant mal testé.

Utiliser d’abord des mutations ciblées sur les décisions critiques, puis envisager une campagne périodique si sa valeur et son coût sont démontrés. Une baseline de dette doit refuser la croissance et être abaissée lorsqu’une dette est résolue.

## 6. Instructions agents et organisation documentaire

### 6.1 Noyau commun court

Conserver dans les instructions toujours chargées : périmètre RPi/ESP32, commandes canoniques, invariants matériels essentiels, protection des données/secrets, règles Git/concurrence, exigences de preuve et table de lecture par zone.

| Zone | Lectures obligatoires proposées |
|---|---|
| GPIO, moteur, chauffage | Modèle de sûreté, matrice GPIO, protocole matériel |
| Supervision et watchdog | Architecture runtime, systemd, tests concernés |
| Configuration et SQLite | Contrats de données, migrations, sauvegarde/restauration |
| HTTP et commandes | Contrat API, modèle LAN, protections des mutations |
| Templates/CSS/JS | Design system, contribution UI, qualification navigateur |
| Déploiement | Release, rollback, qualifications et risques ouverts |

À court terme, garder les miroirs exacts et ajouter leur contrôle automatique. Ensuite, les raccourcir identiquement en déplaçant les détails vers les références existantes. Ne pas laisser un outil perdre les règles de sûreté lors de cette opération.

### 6.2 Conserver la structure Phyto

Garder `architecture/`, `development/`, `operations/`, `reference/`, `hardware/` et `decisions/`. La règle DanceFlow d’un `docs/` presque plat n’apporte pas de bénéfice établi ici.

Définir un rôle par support :

- index : orientation, sources de vérité et responsabilités ;
- roadmap : priorités et dépendances ;
- registre des risques : impact, état, prochaine action, preuve de réduction ;
- tâches : index courant des travaux et détail d’exécution ;
- ADR : décisions structurantes et conditions de réexamen ;
- références métier : contrats et comportements ;
- archives : preuves historiques non utilisées comme état courant.

Attribuer aux documents sensibles un responsable et un déclencheur de revue. Préférer une mise à jour liée à un changement réel, complétée par une revue périodique ciblée, à une date avancée mécaniquement.

Contrôler automatiquement les liens locaux, miroirs et exemples vérifiables. Ne pas prétendre qu’un check de métadonnées garantit la vérité sémantique d’un document.

### 6.3 Contrats métier

Consolider dans les références existantes les règles de modes climatiques, mesures, forçages, carnet et migrations actuellement dispersées. Ajouter des identifiants stables lorsque plusieurs tests ou documents doivent citer une même règle. Ne pas créer un deuxième récit du modèle de sûreté.

## 7. Continuité des chantiers et orchestration

### 7.1 Fiche de reprise

Pour un chantier de plusieurs sessions, utiliser un document court avec :

```yaml
statut: propose # puis actif, en-pause ou clos selon adoption
chantier: slug-du-chantier
resync: AAAA-MM-JJ
perimetre:
  - chemins/concernes
```

Puis : objectif, exclusions, état réel, décisions, preuves F2P/P2P, difficultés, déploiement, qualification et prochaine action précise. Les preuves longues sont liées, pas recopiées partout.

Une clôture doit reloger explicitement les travaux ouverts. Les compteurs mobiles (migrations, ADR, invariants) sont relus au démarrage, jamais réservés à partir des chiffres de ce document.

### 7.2 Artefacts et archives

Un rapport courant peut avoir un nom stable avec historique Git. Une qualification matérielle ou une preuve de release doit rester identifiable par date, commit et configuration non sensible. Ne pas effacer la traçabilité utile des qualifications au nom d’une règle générique de réduction des fichiers.

### 7.3 Travail multi-agent

Fonctionnement recommandé : un responsable de lot ; délégation seulement sur tâches réellement indépendantes ; relecteur au contexte frais pour invariants physiques, autorisations ou migrations critiques ; responsable d’intégration pour les registres partagés.

Chaque brief précise objectif, fichiers autorisés, exclusions, budget, résultat attendu et interdiction de sous-délégation non demandée. Le testeur indépendant reçoit le contrat et la preuve du finding, pas le correctif souhaité.

Isoler bases, ports, artefacts et index/working trees selon les outils. Sérialiser les modifications des index documentaires et registres communs. Ne pas utiliser les hooks propres à un outil comme unique protection du projet : scripts et CI doivent rester la couche commune.

## 8. Matrice des invariants et architecture

### 8.1 Relier les sources existantes

Ajouter une matrice compacte reliant le modèle de sûreté, les risques et les tests. Un fichier proposé est `docs/reference/invariants.md`, à confirmer sans dupliquer les sources existantes.

Colonnes : identifiant, contrat et modes concernés, niveau de criticité, code responsable, tests PROUVER, mécanisme DÉTECTER, qualification requise, dernière preuve, limite résiduelle, risque associé.

| Contrat candidat | Preuve logicielle | Détection | Qualification |
|---|---|---|---|
| Seconde instance sans effet GPIO | Vrai démarrage avec faux GPIO | Refus explicite | Comportement du service |
| Annulation d’une activation temporaire | Point d’entrée annulé, état final vérifié | Écart d’état signalé | Niveaux et relais sous supervision |
| Configuration refusée sans mutation active | Disque et mémoire inchangés | Erreur sans secret | Reconfiguration représentative |
| Capteur invalide et reprise | Séquences de défaut et récupération | État dégradé et alarme | Chaîne capteur/actionneur |
| Conservation des données en migration | Migration et restauration sur copie | Version/intégrité | Exercice de récupération |
| Panne du contrôleur observable | Test des signaux de santé | Surveillance externe | Perte du processus/Pi sur banc |

Ne pas inventer un invariant plus large que le métier. En particulier, l’exclusion chauffe/ventilation thermique comporte des distinctions de modes : `RENOUVELER` et `DESHUMIDIFIER` peuvent légitimement coexister avec la chauffe en hiver. Voir [la stratégie de vérification](verification.md).

### 8.2 Premières règles transversales candidates

- Accès GPIO confinés aux adaptateurs explicitement autorisés.
- Absence de `GPIO.cleanup()` dans le code applicatif.
- Politique climatique pure, sans réseau, disque, horloge implicite ou GPIO.
- Écritures de configuration réservées au propriétaire canonique.
- Chemins des données persistantes passant par la résolution centrale, avec exceptions documentées comme les logs.
- Routes mutatrices soumises aux protections requises.
- Enregistrement explicite des tâches critiques et de leur état sûr.
- Cohérence de l’ensemble unité systemd/drop-ins/installation.

Privilégier AST Python, analyse de configuration ou inspection de registre runtime selon la propriété. Une regex générale sur le code peut produire des faux positifs structurels.

La présence d’un appel à `beat()` ne prouve pas son accessibilité ; la présence de `safe_state` ne prouve pas son effet. Doubler les règles de forme par des tests de panne au vrai point d’entrée.

### 8.3 Frontières à protéger

Préserver les décisions métier testables, les adaptateurs matériels, la composition au démarrage, la validation aux frontières HTTP et la présentation dans les macros. Le carnet et ses médias ne doivent pas devenir des dépendances critiques de la boucle de régulation.

`network/web/server.py` dépassait 2 000 lignes lors de l’examen. Ce constat invite à examiner ses responsabilités au contact des évolutions ; il ne justifie pas une réécriture globale fondée sur la taille seule. Extraire par domaine avec les tests de comportement associés.

Mesurer les budgets de durée, mémoire, stockage et blocage de l’event loop pour les fonctions auxiliaires. Les budgets observés sur WSL ne valent pas qualification sur le Pi.

## 9. Design system Phyto

### 9.1 Diagnostic

Il n’existait pas de design system complet formalisé/catalogué lors de l’examen, mais les fondations sont déjà présentes :

- `network/web/static/css/style.css` : tokens, sombre/plein jour, focus, formulaires, boutons, adaptations aux préférences d’accessibilité ;
- `network/web/templates/macros/ui.html` : huit primitives de présentation ;
- `docs/development/contributing.md` : exemples et contrats d’utilisation ;
- `tests/test_ui_macros.py` : rendu minimal/complet, StrictUndefined, échappement, CSP, attributs et exemples documentés ;
- `tests/ui/qualification.spec.js` : pages témoins et axe ;
- `tests/ui/measure_pages.js` : mesures de pages, états, cibles et accessibilité.

Les huit macros observées sont `compact_header`, `empty_state`, `alarm_summary`, `equipment_row`, `journal_entry`, `field_group`, `chart_detail` et `network_state`. Elles sont déjà utilisées ; il ne faut pas les remplacer pour recréer une bibliothèque.

### 9.2 Cible technique

Créer `docs/development/design-system.md` comme contrat canonique et une galerie locale sur données fictives, idéalement portée par l’environnement de test. Conserver Jinja, CSS custom properties et JavaScript progressif. React, shadcn ou Storybook ne sont pas des prérequis.

- CSS : fondations et styles partagés.
- Macros : structures HTML et sémantique accessibles, sans décision métier.
- Attributs `data-*` : raccordement des comportements JavaScript.
- Services/routes : décisions, validation et commandes explicites.
- Aucune mutation implicite dans une macro ou un lien GET.

La formalisation ne doit pas être couplée à une refonte visuelle totale.

### 9.3 Contrat opérateur

| Sujet | Règle à formaliser |
|---|---|
| Mesure | Valeur, unité, origine, fraîcheur et qualité distinctes |
| Absence | État explicite ; jamais converti en zéro |
| Actionneur | Distinguer consigne, commande, lecture GPIO et observation physique disponible |
| Alarme | Problème, conséquence, action possible ; couleur non exclusive |
| Commande physique | Préconditions, effet attendu, durée, résultat et voie de sortie |
| Hors-ligne | Copie consultable datée ; aucune illusion de contrôle temps réel |
| Formulaire | Erreurs, modifications non enregistrées, sauvegarde et récupération cohérentes |
| Graphique | Unités, légende, séries distinguables, détails accessibles |
| Thème | Contraste et lisibilité en sombre et plein jour |
| Mobile | Cibles, zoom, navigation et actions prioritaires adaptés au terrain |
| Aide | Explication contextuelle proportionnée au risque et à la fréquence d’usage |

La règle SaaS « toute feature possède un tour guidé » devient ici « toute fonction fournit l’aide contextuelle nécessaire à son usage sûr ». Une confirmation explicative au moment d’une commande peut être plus utile qu’un parcours guidé.

### 9.4 Tokens et catalogue

Compléter les fondations : couleurs par rôle, typographie et nombres, espacements, densité, rayons, élévations, focus, couches d’affichage, mouvement, responsive et états.

Les tokens actuels sont partiellement nommés par couleur. Introduire des alias compatibles, par exemple action principale, danger, avertissement, focus et mesure périmée. Migrer les consommateurs avant de retirer les noms historiques. Ne pas modifier simultanément toute la palette.

Chaque entrée du catalogue indique : nom, usage, non-usage, variantes, états, API macro/classes, exemple rendu, obligations d’accessibilité, tests, consommateurs et exceptions.

Candidats à inventorier : boutons/liens d’action, champs/aides/erreurs, badges de statut, bannières, cartes/en-têtes et confirmations. Une répétition de HTML ne prouve pas à elle seule qu’une nouvelle primitive est nécessaire.

### 9.5 Adoption complète

1. Inventorier les occurrences existantes.
2. Classer : primitive réutilisable, disposition ou exception métier.
3. Définir le contrat et les tests.
4. Implémenter ou compléter la primitive.
5. Migrer toutes les occurrences réellement équivalentes dans le même lot.
6. Documenter les exceptions et reports avec les fichiers concernés.
7. Vérifier les parcours consommateurs et actualiser le catalogue.

Une primitive officielle utilisée sur deux pages pendant que les autres conservent des variantes divergentes n’est pas une adoption achevée.

### 9.6 Validation du design system

Réutiliser et étendre les preuves existantes :

- rendu minimal et complet sous StrictUndefined ;
- autoéchappement, compatibilité CSP, absence de logique inline interdite ;
- sémantique HTML/ARIA, clavier, focus et annonces ;
- exemples documentés exécutables ;
- pages témoins et axe ;
- sombre et plein jour ;
- formats étroits, téléphone, bureau et zoom 200 % ;
- mouvement réduit et couleurs forcées lorsque pertinents ;
- états nominal, vide, erreur, en cours, hors-ligne et donnée périmée ;
- interactions réelles, pas seulement captures ou classes CSS.

Distinguer la cible produit de confort **44 px** du critère WCAG 2.2 AA **24 px**, avec les exceptions prévues par ce dernier. Les seuils ne sont pas interchangeables.

Ajouter une garde légère catalogue/exemples/tests. Ne mécaniser les interdictions ad hoc que lorsqu’un motif est étroit et fiable. Réserver les mesures complètes aux moments utiles si leur coût gêne la boucle quotidienne ; les changements de primitives partagées nécessitent une validation des consommateurs.

## 10. Livraison, données, exploitation et sécurité

### 10.1 Conserver les bons mécanismes

`scripts/deploy.sh` possède déjà verrou exclusif, validation préalable, sauvegardes ciblées, contrôle du service, liveness/readiness, santé du contrôle, commit chargé, alarmes critiques et stabilité continue, puis rollback du code avec qualification.

Renforcer ce chemin existant plutôt que créer un second déploiement concurrent.

### 10.2 Contrat de release et de migration

Une release devrait relier commit, versions des données/configuration, résultats de validation, configuration système attendue et preuves de qualification requises.

**Rollback Git et rollback de données sont distincts.** Pour une migration SQLite ou de configuration : tester des copies représentatives, vérifier la compatibilité avec l’ancien code, définir la récupération et conserver les sauvegardes nécessaires. Reprendre la discipline de compatibilité de DanceFlow sans importer Flyway ou les noms `TM{N}`.

Le carnet possède déjà une sauvegarde cohérente SQLite avec médias et manifeste. Les copies locales et `.before-vN` ne remplacent pas une sauvegarde hors machine. Voir [sauvegarde/restauration](../operations/backup-and-restore.md).

Exercer la restauration vers une destination isolée et l’installation d’un second Pi. Une procédure relue n’est pas une procédure qualifiée.

### 10.3 Observabilité

Conserver liveness et readiness distinctes. Évaluer fraîcheur des mesures, silence des tâches, stockage et santé des fonctions auxiliaires sans transformer toute panne UI/Influx en panne de régulation.

La disparition complète du Pi doit être détectée depuis un autre système. Vérifier les alertes jusqu’au canal opérateur attendu ; une métrique seule ne constitue pas une notification.

### 10.4 Nouvelles gardes opérationnelles

Une nouvelle garde de déploiement peut commencer en avertissement afin de vérifier ses faux positifs sur une livraison saine. Enregistrer responsable, cas fautif de test, preuve saine réelle et condition de promotion vers le blocage.

**Cette politique ne s’applique pas aux protections physiques existantes.** Elle ne justifie ni de désarmer un état sûr, ni d’autoriser une commande dangereuse, ni de garder indéfiniment un contrôle qualifié en avertissement.

### 10.5 Limites matérielles et réseau

Les qualifications boot, relais, charges et protections indépendantes restent supervisées selon [le protocole matériel](hardware-validation.md). Aucun test logiciel ne remplace ces observations.

Conserver l’hypothèse LAN explicite. Une évolution vers accès distant ou plusieurs profils opérateur doit réexaminer authentification, autorisation, privilèges du service et exposition des commandes. CSRF/Origin/Host ne constituent pas une identité utilisateur.

Le registre et `SECURITY.md` portent les risques connus sur secrets historiquement versionnés et privilèges. Ne pas confondre retrait de Git et rotation, ni utiliser le Dockerfile de développement comme preuve de confinement de production.

## 11. Plan d’intégration proposé

L’ordre ci-dessous concerne le harness logiciel. Il ne reporte pas les qualifications matérielles prioritaires déjà ouvertes. Les charges sont relatives, pas des engagements calendaires.

| Lot | Objectif | Dépendances | Charge |
|---|---|---|---|
| 0 | Revalider le point de départ et borner le chantier | Aucune | Faible |
| 1 | Validation commune et CI | Lot 0 | Moyenne |
| 2 | Instructions et reprise de session | Lot 0 ; contrôles du lot 1 | Faible à moyenne |
| 3 | Design system Phyto | Inventaire immédiat ; CI pour adoption | Moyenne à importante |
| 4 | Invariants et architecture | Lots 1/2 | Moyenne |
| 5 | Release, migration et récupération | Lots 1/4 et environnement de qualification | Moyenne à importante |
| 6 | Typage, couverture, mutations et budgets | Mesures des lots précédents | Progressive |

### Lot 0 — Revalidation

- [ ] Lire les instructions et l’état Git actuel, identifier les travaux concurrents.
- [ ] Vérifier les constats datés, notamment CI, scripts, macros et qualifications existantes.
- [ ] Relever les versions supportées et qualifier l’environnement de test.
- [ ] Rattacher le chantier au suivi courant ; décider périmètre, exclusions et ordre réel.
- [ ] Vérifier les risques physiques urgents séparément.

**Sortie :** un plan reflète le dépôt actuel, pas seulement cette proposition.

### Lot 1 — Validation reproductible

- [ ] Qualifier l’installation hors matériel depuis un clone propre.
- [ ] Définir les profils et leur sélection de tests.
- [ ] Créer la commande commune et le workflow racine.
- [ ] Contrôler le miroir et le diff pertinent.
- [ ] Conserver rc, décomptes et rapports propres au run.
- [ ] Tester échec applicatif, contrôle absent, sélection vide et cas sain.
- [ ] Vérifier la garde de cible externe et l’isolation des tests.
- [ ] Mettre à jour contribution et vérification.

**Sortie :** un environnement neuf exécute les vérifications sans GPIO réel ; aucune absence de preuve requise ne devient verte.

### Lot 2 — Instructions et continuité

- [ ] Raccourcir les miroirs sans perdre les invariants de sûreté.
- [ ] Ajouter la table des lectures obligatoires par périmètre.
- [ ] Clarifier index, roadmap, risques, tâches, décisions et archives.
- [ ] Définir la fiche de reprise et les preuves de clôture.
- [ ] Vérifier les liens et les exemples concernés.
- [ ] Faire reprendre un petit chantier par une session neuve à partir de la fiche.

**Sortie :** la session suivante retrouve état réel, preuves et prochaine action sans reconstruire l’histoire.

### Lot 3 — Design system

- [ ] Inventorier tokens, macros, styles et occurrences ad hoc.
- [ ] Écrire le contrat opérateur et le catalogue initial.
- [ ] Créer une galerie isolée sur données fictives.
- [ ] Introduire les rôles sémantiques compatibles.
- [ ] Choisir une première famille de primitives selon l’inventaire.
- [ ] Tester puis migrer toutes ses occurrences équivalentes.
- [ ] Consigner exceptions et reports nommés.
- [ ] Vérifier deux thèmes, formats utiles, clavier, zoom et états dégradés.
- [ ] Étendre par familles avec critères d’adoption identiques.

**Sortie :** catalogue et code concordent ; les primitives choisies sont entièrement adoptées et les consommateurs vérifiés. La création du seul document ne clôt pas ce lot.

### Lot 4 — Invariants et règles d’architecture

- [ ] Relier les contrats existants à PROUVER/DÉTECTER/QUALIFIER.
- [ ] Choisir quelques invariants critiques et leur oracle.
- [ ] Renforcer leurs tests et contrepoids au vrai point d’entrée.
- [ ] Faire relire les preuves critiques dans un contexte frais.
- [ ] Ajouter les premières règles structurelles avec cas fautifs/sains.
- [ ] Tester la composition systemd et non l’unité seule.
- [ ] Câbler gardes et auto-tests en CI.

**Sortie :** les défauts visés rougissent, les cas sains restent acceptés et les limites de preuve sont explicites.

### Lot 5 — Release et récupération

- [ ] Définir le manifeste de release et les compatibilités.
- [ ] Tester migrations et restauration sur copies.
- [ ] Organiser la sauvegarde hors machine selon les contraintes réelles.
- [ ] Qualifier les fichiers système et le démarrage effectif sur environnement adapté.
- [ ] Exercer les refus de santé et la récupération sans mettre les charges en danger.
- [ ] Consigner preuves opérateur et risques résiduels.

**Sortie :** une version et ses données sont récupérables dans l’environnement qualifié ; aucune promesse de rollback ne repose seulement sur Git.

### Lot 6 — Renforcement progressif

- [ ] Mesurer lint, typage, couverture et durée des suites.
- [ ] Définir les premières règles et seuils sur données mesurées.
- [ ] Ajouter mutations ciblées puis campagnes périodiques si utiles.
- [ ] Qualifier les budgets de performance sur Pi.
- [ ] Suivre faux positifs, instabilités et coût des gardes.
- [ ] Retirer les contrôles redondants ou inefficaces après analyse.

**Sortie :** les garanties progressent sans rendre la boucle quotidienne impraticable.

## 12. Ce qu’il ne faut pas transposer tel quel

- Pile Java/Spring, React/shadcn, Flyway, Stripe ou multi-tenancy.
- Wrappers Gradle/Windows/WSL spécifiques à DanceFlow.
- Dossier documentaire plat imposé sans bénéfice.
- Multiplication des registres, compteurs et rapports concurrents.
- Centaines de lignes d’histoire dans le contexte systématiquement chargé.
- Dizaines de gardes SaaS sans classe d’erreur correspondante dans Phyto.
- Orchestration multi-agent permanente ou évaluation indépendante pour chaque petite retouche.
- Pourcentages de couverture copiés sans mesure de la cible.
- Tour guidé obligatoire là où une aide contextuelle suffit.
- Interdiction globale chauffe/moteur contraire aux modes métier.
- Politique fail-open étendue aux protections physiques.
- Qualification de production déduite d’un test simulé ou d’une ancienne preuve.

## 13. Mesurer l’efficacité du cadre

Observer quelques indicateurs simples, sans créer un système de reporting autonome :

- temps jusqu’à la première validation utile ;
- durée des profils et fréquence des tests instables ;
- faux positifs et contournements des gardes ;
- nombre de reprises de session nécessitant une reconstruction manuelle ;
- défauts trouvés après intégration ou livraison ;
- invariants critiques sans preuve ou détection actuelle ;
- temps consacré à entretenir le harness par rapport au travail produit.

Une règle nouvelle doit diminuer un problème observable. Le nombre de documents, tests ou agents n’est pas une mesure de maîtrise. Une méta-garde peut vérifier qu’un contrôle tourne ; elle ne prouve pas que le contrôle exprime le bon besoin.

## 14. Références pour l’implémentation

### Sources Phyto

- [Index documentaire](../index.md)
- [Instructions agents](../../AGENTS.md) et [miroir](../../CLAUDE.md)
- [Roadmap](../roadmap.md), [risques](../risk-register.md), [tâches](../../tasks/todo.md), [leçons](../../tasks/lessons.md)
- [Architecture](../architecture/overview.md) et [modèle de sûreté](../architecture/safety-model.md)
- [Matrice GPIO](../hardware/gpio-matrix.md) et [qualification matérielle](hardware-validation.md)
- [Contribution](contributing.md), [checklist](safe-change-checklist.md), [vérification](verification.md)
- [Décisions](../decisions/README.md)
- [Déploiement](../operations/deployment-and-rollback.md), [systemd](../operations/systemd.md), [sauvegarde/restauration](../operations/backup-and-restore.md), [monitoring](../operations/monitoring.md)
- [Remédiation UI](remediation-web-mobile-pwa-2026-09-09.md), [qualification mobile/PWA](qualification-mobile-pwa.md), [baseline de performance](web-perf-baseline-2026-09-10.md), [validation produit](validation-produit-protocole.md)
- [Tokens CSS](../../network/web/static/css/style.css), [macros](../../network/web/templates/macros/ui.html), [tests des macros](../../tests/test_ui_macros.py), [qualification navigateur](../../tests/ui/qualification.spec.js)

### Sources DanceFlow à consulter si le dépôt voisin est disponible

Les chemins suivants sont relatifs à `deci/`. Phyto ne doit pas dépendre de leur présence pour se construire ou se valider.

- `docs/AI_DELIVERY_OS.md` : méthode et limites de la chaîne de preuves.
- `AGENTS.md`, `CLAUDE.md`, `tasks/lessons.md` : règles, continuité et mécanisation.
- `design_system_rules.md` : contrat UI, catalogue et adoption complète.
- `scripts/ci-guard-step.sh`, `scripts/ci-guard-verdict.sh` : agrégation des vrais verdicts.
- `scripts/check-guard-wiring.sh` et son auto-test : gardes testées et câblées.
- `scripts/guard-wiring-baseline.tsv` : dette distincte des exceptions.
- `scripts/check-tasks-hygiene.sh`, `scripts/check-tasks-lifecycle-guard.sh` : cycle de vie des travaux.
- `.github/workflows/ci.yml` : articulation des contrôles, pas modèle à copier intégralement.

### Sources externes consultées pour la recommandation

- [Anthropic — Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) : découpage et continuité par artefacts.
- [Anthropic — Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) : séparation génération/évaluation, critères de sortie et coût de l’orchestration.
- [Google SRE — Monitoring](https://sre.google/workbook/monitoring/) : surveillance et tests des alertes.
- [GOV.UK Design System — Components](https://design-system.service.gov.uk/components/) : recommandations d’usage et exemples de composants.
- [W3C — Target Size (Minimum), WCAG 2.2](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum) : minimum de 24 px et exceptions, distinct de la cible produit de 44 px.

Ces sources étayent les principes généraux ; elles ne certifient pas les dépôts inspectés. Vérifier leur actualité si elles déterminent un choix d’outil ou une norme lors de l’implémentation.
