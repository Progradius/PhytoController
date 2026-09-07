# Leçons — erreurs commises et règles qui en découlent

## 2026-08-26 — `compileall` ne prouve rien sur les noms

**Ce qui s'est passé.** Phase 3 déployée, service en échec au boot :
`NameError: name 'shared_config' is not defined` dans `network/network_handler.py`.
Un remplacement d'import scripté visait `from param.config import AppConfig`, mais la ligne du
fichier portait des espaces d'alignement (`from param.config       import AppConfig`). Le
remplacement n'a **rien fait, sans le dire**, et un patch suivant a supprimé la ligne d'origine :
module sans aucun import. Six redémarrages en boucle avant le rollback.

**Pourquoi ça n'a pas été vu.** La vérification s'arrêtait à `python3 -m compileall`. Un nom non
défini est une erreur d'**exécution**, pas de compilation : `compileall` retourne 0 sur un module
qui ne peut pas tourner une seconde.

**Règles.**
1. Sur cet arbre sans tests ni linter, la vérification minimale d'un changement Python est
   **`pyflakes` sur tout l'arbre**, pas `compileall`. Il attrape les noms non définis et les imports
   morts. Commande utilisée :
   `python -m pyflakes $(git ls-files '*.py' | sed 's|^RPi Version/||')`
   Objectif : **0 « undefined name »**. (Bonus réel : ce passage a révélé un défaut latent sans
   rapport, `SensorController` passant `config` au lieu de `self.config` à `VL53L0XHandler`.)
2. **Tout `str.replace()` de patch scripté doit être assorti d'un `assert motif in source`.** Un
   remplacement qui ne trouve pas son motif est un échec silencieux, et c'est exactement le mode de
   panne ci-dessus. Je l'avais fait pour certains patchs de la même session, pas pour celui-là.
3. Ne jamais faire porter à un remplacement de texte le soin de *déplacer* un import : ajouter la
   nouvelle ligne, puis supprimer l'ancienne, sont deux opérations dont la seconde ne doit être
   tentée que si la première a été vérifiée.

## 2026-08-28 — Un octet nul introduit par une édition de fichier

**Ce qui s'est passé.** Une modification de `network/web/static/js/config.js` a transformé
`entries.join(" ")` en `entries.join("\0")`. Le fichier restait syntaxiquement valide pour un
navigateur, `pytest` et `pyflakes` ne voient pas ce fichier, et rien n'a signalé la corruption.
Elle a été découverte parce que `grep` a répondu « binary file matches » sur un fichier `.js`.

**Pourquoi c'est grave ici.** Le montage `/mnt/c` (drvfs) est déjà connu pour corrompre les
fichiers lors d'écritures non atomiques. Un octet nul dans un asset servi par la PWA est un
fichier que le service worker met en cache et redistribue.

**Règles.**
1. Après toute écriture d'un fichier texte sous `/mnt/c`, vérifier qu'il ne contient **aucun octet
   nul** avant de committer :
   `python3 -c "import pathlib,sys; [print('NUL:',f) for f in sys.argv[1:] if b'\0' in pathlib.Path(f).read_bytes()]" $(git ls-files '*.py' '*.js' '*.css' '*.html' '*.md')`
2. `grep` qui répond « binary file matches » sur un fichier censé être du texte est un **signal de
   corruption**, jamais une curiosité à contourner avec `grep -a`.
3. Les assets statiques ne sont couverts par aucun test : leur vérification est manuelle et doit
   être explicite dans la liste de contrôle d'une livraison qui les touche.

## 2026-08-30 — Un détecteur dont le verdict dépend de la cadence d'échantillonnage

**Ce qui s'est passé.** Le détecteur de figement comparait chaque lecture à la **précédente**
(`abs(raw - last_raw_value) > epsilon`), la référence étant réavancée à chaque échantillon. Il
mesurait donc une *pente*, pas une valeur bloquée. À la cadence réelle de 10 s, une température
saine bouge de 0,01 °C pour un epsilon de 0,02 °C : `BME280T` et `BME280H` ont été déclarés
incohérents sur 17 % et 22 % de la fenêtre d'observation, et une dérive réelle de +0,32 °C étalée
sur 1 h 51 comptait comme figée. En mode `enforce`, c'était `REPLI_CAPTEUR` sur un cinquième du
temps, sur les deux mesures qui pilotent l'arbitre thermique.

**Pourquoi ça n'a pas été vu.** Les tests n'injectaient qu'une valeur **strictement constante** —
le seul signal que le bug ne cassait pas. Aucun test ne rejouait une dérive lente, et surtout aucun
ne vérifiait que le verdict ne dépend pas de la cadence de lecture.

**Règles.**
1. **Un diagnostic sur série temporelle doit être invariant par cadence d'échantillonnage.** Si
   rejouer le même signal physique à 5 s, 10 s et 60 s peut donner deux verdicts différents, le
   critère mesure la fréquence de lecture et non le phénomène. Ce test de propriété doit exister
   pour tout détecteur de ce type ; il interdit la classe de bug, là où un cas nominal n'interdit
   qu'une instance.
2. **Un seuil de détection doit être comparé au plancher de bruit de la grandeur mesurée**, et le
   rapport doit être écrit dans le code. Au-dessus du bruit, les deux classes à séparer produisent
   la même observation : aucun réglage ne peut plus les distinguer, et « élargir le seuil » dégrade
   simultanément les faux positifs *et* les vrais positifs.
3. **Ne pas arrondir dans un driver ni dans un handler.** L'arrondi appartient à l'affichage. Ici
   `round(val, 2)` appliqué deux fois détruisait le bruit d'acquisition qui est précisément la
   preuve qu'un capteur est vivant.
4. Un anti-rebond qui exige N évènements **consécutifs** et se réinitialise au premier évènement
   contraire est un **cliquet**, pas un anti-rebond : compter N évènements réels, sans reset.
5. Quand un diagnostic produit beaucoup de faux positifs, chercher d'abord **ce qu'il mesure**
   avant de toucher à ses seuils. Retoucher les seuils est la rustine qui masque la question.
