# Plan — Résorption de la dette technique et simplification

**Date d'analyse** : 2026-08-26 · **Branche d'analyse** : `audit-phase2-thermique` (base `ad39de2`)
**Périmètre** : `RPi Version/` — l'intégralité de l'arbre Python (8 286 lignes, 45 fichiers), les
gabarits web, la configuration, les scripts de déploiement et la documentation.
**Référence amont** : `AUDIT-2026-08-25.md` (sûreté électrique / robustesse) — le présent plan ne le
remplace pas, il traite ce que l'audit ne couvrait pas : la **structure**, la **duplication** et le
**code mort**.

---

## 0. Constat de départ

Le noyau de sûreté issu des phases 0 à 2 est sain et ne doit pas être touché :
`components/climate_policy.py` (fonction pure), `utils/supervisor.py`, `utils/watchdog.py`,
`utils/atomic_io.py`, `utils/state_store.py`, `model/Component.energized()`.

La dette est ailleurs, et elle est nettement clivée :

> **Tout ce qui a été rouvert par les trois phases d'audit est de bonne qualité.
> Tout ce qui vient du portage ESP32 et n'a jamais été rouvert est de la dette brute.**

Ce clivage rend le nettoyage facile à cibler. Chiffres :

| Mesure | Valeur |
|---|---|
| Python total | 8 286 lignes / 45 fichiers |
| Python mort ou quasi mort identifié | ~1 400 lignes (**17 %**) |
| Réduction estimée après plan complet | **~1 900 lignes Python (≈ 23 %)** + ~1 000 lignes de markdown |
| Markdown total (docs/ + racine + tasks/) | ~4 065 lignes pour 8 286 lignes de code |
| Défauts fonctionnels réels trouvés | 3 sérieux + 6 mineurs |

**Aucune garantie de sûreté n'est retirée par ce plan.** Les lots 2, 3 et 6 en *ajoutent*.

### Cause racine unique du plus gros chantier

Ce dépôt n'a pas *un* schéma de configuration, il en a **cinq** (§ Lot 5). C'est ce qui a laissé
`initial_setup_tool.py` diverger jusqu'à produire un `param.json` qui ne valide plus — donc un boot
mort. Tout le reste du plan est du ramassage ; celui-là est structurel.

---

## 1. Ordonnancement recommandé

Les lots sont ordonnés par **risque retiré par ligne touchée**, pas par difficulté.

| Ordre | Lot | Titre | Effort | Gain |
|---|---|---|---|---|
| 1 | **Lot 1** | Rotation des secrets, `param.json` hors de git | faible | fuite d'identifiants fermée |
| 2 | **Lot 2** | Durées nulles en mode séquentiel (défaut 🔴) | très faible | supprime un battement de relais 230 V atteignable depuis l'IHM |
| 3 | **Lot 4** | Suppression d'`initial_setup_tool.py` | très faible | −963 lignes (−11,6 % du tree) |
| 4 | **Lot 3** | Suppression du code mort | faible | −250 lignes, referme un retour possible de C5 |
| 5 | **Lot 6** | Champs de configuration fantômes | faible | supprime deux faux réglages dangereux |
| 6 | **Lot 7** | Correctifs ponctuels (blocage event loop, dwell, deepcopy) | faible | correctness |
| 7 | **Lot 5** | Schéma de configuration unique | moyen | −80 lignes, supprime deux pièges documentés |
| 8 | **Lot 8** | Découpage de `server.py` | moyen | 654 → ~250 lignes |
| 9 | **Lot 9** | `DailyTimer` / `CyclicTimer` en schedules gelés | moyen | −150 lignes |
| 10 | **Lot 10** | Chemin de journalisation unique, `GPIO.setmode` centralisé, `in_window()` | moyen | −80 lignes, modules importables hors Pi |
| 11 | **Lot 11** | Retrait daté de la surface web historique | faible (à planifier) | −120 lignes |
| 12 | **Lot 12** | Ménage documentaire | faible | −1 000 lignes de markdown |
| — | **Lot 13** | *(optionnel, décision utilisateur)* tests de `climate_policy` | faible | verrouille les invariants de l'audit |

**Première session conseillée** : lots 1 → 2 → 4 → 3. Faisable d'un bloc, retire le maximum de risque.

### Règles transverses de mise en œuvre

- **Un lot = une branche = un commit** (ou une série cohérente). Ne jamais mélanger deux lots :
  la vérification se fait sans suite de tests, elle repose sur la relecture d'un diff étroit.
- **Jamais `sed -i` sous `/mnt/c/...`** (WSL/drvfs tronque le fichier à 0 octet). Utiliser Write/Edit.
  Récupération en cas de corruption : `git checkout HEAD -- <fichier>`.
- **Ne pas exécuter les tests/builds** : ce tree n'a ni suite de tests ni linter, et la règle projet
  réserve l'exécution à l'utilisateur. La vérification se fait par relecture et par description des
  transitions GPIO attendues (voir la section « Vérification » de chaque lot).
- **`CLAUDE.md` et `AGENTS.md` doivent rester identiques** après toute édition
  (`diff -u CLAUDE.md AGENTS.md` vide) — jusqu'à ce que le **Lot 12** supprime la contrainte.
- **Mettre à jour `CHANGELOG.md`** à chaque lot livré.

---

## 2. Lots

---

### Lot 1 — 🔴 Rotation des secrets et sortie de `param.json` du suivi git

**Priorité absolue, indépendante de tout le reste.**

#### Problème

`param/param.json` est **suivi par git** (`git ls-files param/` le confirme) et contient en clair :

- `Network_Settings.wifi_ssid` et `Network_Settings.wifi_password` (PSK Wi-Fi) ;
- `Network_Settings.influx_db_user` et `influx_db_password`.

Il est présent dans les **50 commits** de l'historique. Tout partage du dépôt (clone, push sur un
remote, archive) diffuse les identifiants. Retirer le fichier de l'index **ne suffit pas** :
l'historique reste.

#### Actions

1. **Faire tourner les secrets d'abord** (sans quoi le reste est cosmétique) :
   - changer le PSK Wi-Fi du réseau de la serre, ou basculer le Pi sur un SSID dédié ;
   - changer le mot de passe de l'utilisateur InfluxDB.
2. Créer `param/param.example.json` : copie de `param.json` avec **toutes** les valeurs des champs
   sensibles vidées (`""`), le reste en valeurs de référence documentées.
3. `git rm --cached param/param.json`
4. Ajouter à `.gitignore` :
   ```
   param/param.json
   param/runtime_state.json
   ```
   (`param/.csrf_token` y est déjà ; `param/sensor_stats.json` : voir note ci-dessous.)
5. Adapter `scripts/deploy.sh` : le fichier n'étant plus versionné, le déploiement ne doit ni
   l'écraser ni échouer s'il est absent côté cible. Vérifier le comportement actuel avant d'y toucher.
6. Documenter dans `docs/operations/install-raspberry-pi.md` la première mise en service :
   `cp param/param.example.json param/param.json` puis édition via `/conf`.
7. Mettre à jour `SECURITY.md` et la mention correspondante dans `CLAUDE.md`/`AGENTS.md`
   (section « Known rough edges »).

#### Décision à prendre

**Réécrire l'historique (`git filter-repo`) ou non ?** Si le dépôt n'a jamais quitté la machine et
n'a pas de remote public, la rotation des secrets suffit et la réécriture d'historique est un risque
inutile. Si le dépôt a été poussé quelque part, la réécriture est nécessaire **en plus** de la
rotation. **À trancher par l'utilisateur avant d'exécuter ce lot.**

#### Note sur `param/sensor_stats.json`

Il est également suivi et ne contient pas de secret, mais il est réécrit à chaque lecture de capteur :
il pollue tous les diffs. Le sortir aussi du suivi est cohérent (le fichier se recrée seul,
`SensorStats.__init__` gère l'absence). À faire dans le même lot.

#### Vérification

- `git ls-files param/` ne retourne plus que `config.py` (et `param.example.json`).
- `git log --oneline -- param/param.json` documente la date d'arrêt du suivi.
- Le Pi de production démarre toujours : son `param.json` local est intact, il n'est simplement plus
  poussé/tiré.

---

### Lot 2 — 🔴 Cyclique séquentiel à durées nulles : boucle serrée invisible du superviseur

#### Problème

**Fichiers** : `components/cyclic_timer_handler.py` (branche `elif mode == "séquentiel"`),
`param/config.py` → `CyclicSettings.on_time_day / off_time_day / on_time_night / off_time_night`
(tous `Field(0, ge=0)`).

Le `param.json` déployé a `Cyclic2_Settings` avec les **quatre durées à 0**. Ce timer est
actuellement en mode `journalier` et désactivé, donc dormant. **Un clic sur « séquentiel » dans
`/conf` suffit à l'armer** : la validation Pydantic accepte (`ge=0`), et la boucle devient :

```
beat()
AppConfig.load()                    ← lecture + parse disque
box("[S][Jour] #2 ON  @ …")         ← ligne INFO (fichier + flux SSE)
_save_phase(store, …, "on", 0)
with comp.energized():              ← GPIO LOW  (relais fermé)
    await hb_sleep(0)               ← retour immédiat
                                    ← GPIO HIGH (relais ouvert) + vérification
box("[S][Jour] #2 OFF @ …")         ← ligne INFO
_save_phase(store, …, "off", 0)
await hb_sleep(0)                   ← retour immédiat
→ itération suivante
```

Conséquences :

1. Le relais 230 V commute **à la vitesse du CPU** — usure mécanique immédiate, et pour une
   électrovanne ou un contacteur, un régime destructeur.
2. `param.json` est relu et re-validé à chaque itération.
3. `box()` journalise **deux lignes INFO par itération** : le fichier `logs/phyto.log` et le flux SSE
   `/console` saturent en quelques secondes.
4. **Le plus grave** : `beat()` est appelé en tête de boucle. Le superviseur voit la tâche
   parfaitement saine, `is_healthy()` reste vrai, et le watchdog continue d'être caressé.
   C'est exactement le mode de panne silencieuse que la Phase 1 devait rendre impossible —
   contourné par le haut, via une configuration valide au sens du schéma.

`store.save()` étant throttlé, la carte SD n'est pas en cause ; le journal, si.

#### Correctif — **deux niveaux, les deux nécessaires**

**Niveau 1 — validation du schéma** (`param/config.py`, `CyclicSettings`) :

```python
@model_validator(mode="after")
def _validate_sequential_durations(self):
    if self.mode == "séquentiel":
        zeros = [
            name for name in (
                "on_time_day", "off_time_day", "on_time_night", "off_time_night",
            )
            if getattr(self, name) <= 0
        ]
        if zeros:
            raise ValueError(
                "mode séquentiel : les durées ON/OFF doivent être strictement "
                f"positives ({', '.join(zeros)})"
            )
    return self
```

⚠️ **Attention au piège identifié en Phase 2** : un validateur bloquant sur une configuration
**déjà déployée** provoque un boot mort. Ici le risque est nul — le `param.json` de production a
`Cyclic2` en `journalier`, donc le validateur ne s'applique pas et le fichier continue de charger.
**Vérifier ce point sur le `param.json` réel du Pi avant de livrer** (`Cyclic1` et `Cyclic2` :
si `mode == "séquentiel"`, les quatre durées doivent déjà être > 0). `Cyclic1` est en séquentiel avec
9999/600/3600/600 → conforme.

Le validateur remonte proprement dans `/conf` via `_format_validation_errors` : l'utilisateur reçoit
un 422 avec le message, la configuration active reste inchangée. C'est le comportement voulu.

**Niveau 2 — plancher défensif dans le handler** (`components/cyclic_timer_handler.py`) :

Un `param.json` édité à la main contourne l'IHM. Le handler ne doit jamais entrer en boucle serrée,
quelle que soit l'entrée :

```python
MIN_PHASE_SECONDS = 1.0
...
on_d  = max(MIN_PHASE_SECONDS, on_d)
off_d = max(MIN_PHASE_SECONDS, off_d)
```

avec un `StateLogger` (`utils/log_dedup`) pour signaler **une fois** que la durée configurée a dû
être relevée — jamais à chaque tour.

#### Traitement du mode inconnu (même fichier, même lot)

Fin de `timer_cyclic` : un `mode` non reconnu fait `return`. Le superviseur interprète ça comme
« terminaison sans exception », applique l'état sûr et relance, avec un back-off qui monte à 300 s —
**indéfiniment**. Une faute de frappe dans le mode produit un cycle de relance perpétuel.

Correctif : forcer la sortie OFF, journaliser une fois (StateLogger), puis
`await hb_sleep(60)` et `continue` — la boucle reprendra dès que la configuration sera corrigée via
`/conf`, sans passer par le superviseur.

#### Vérification

- Relire le diff : la boucle séquentielle ne peut plus produire deux `hb_sleep` de durée nulle.
- Transitions GPIO attendues, `Cyclic2` passé en séquentiel avec durées nulles depuis `/conf` :
  **aucune** — le POST est refusé en 422, la sortie reste dans son état antérieur.
- Avec un `param.json` bricolé à durées nulles : une commutation par seconde au maximum, et **une
  seule** ligne WARNING signalant le relèvement.
- Confirmer que `AppConfig.load()` réussit toujours sur le `param.json` de production (lot bloquant
  sinon).

---

### Lot 3 — Suppression du code mort

Tous les éléments ci-dessous ont été vérifiés par recherche exhaustive sur `*.py` et `*.html` :
**zéro appelant**.

| Fichier | Élément | Remarque |
|---|---|---|
| `components/component_handler.py` | **fichier entier** (`toggle_state`) | en-tête pointant encore vers `controller/components/toggle_state.py` |
| `model/CyclicTimer.py` | 9 setters, `_set_and_save`, 9 getters triviaux, `refresh_from_config` | ~110 lignes — voir alerte ci-dessous |
| `model/DailyTimer.py` | `set_start_time`, `set_stop_time`, `get_component_state` | même alerte |
| `controllers/SystemStatus.py` | `get_cyclic_period`, `get_cyclic_duration` | |
| `function.py` | `convert_time_to_seconds`, `convert_minute_to_seconds`, `check_disk_usage` | `convert_time_to_minutes` est utilisé par `DailyTimer` : **le garder** |
| `utils/pretty_console.py` | `set_log_level`, `set_console_log_level`, `get_log_level` | tout passe par `apply_log_settings` |

#### ⚠️ Ce n'est pas du code mort inoffensif

`CyclicTimer._set_and_save()` et `DailyTimer.set_start_time()`/`set_stop_time()` appellent
`self._config.save()`. C'est un **second chemin d'écriture de `param.json`**, parallèle au serveur
web, **sans construction ni validation d'une configuration candidate** — exactement le défaut **C5**
que la Phase 1 a corrigé côté web (`/conf` valide un `AppConfig` complet *avant* la sauvegarde
atomique).

Il suffit qu'un futur développement appelle ces setters « qui existent déjà » pour rouvrir C5.
Leur suppression est donc un **correctif de sûreté**, pas du ménage.

#### Ordre d'exécution

1. `git rm components/component_handler.py` — vérifier au préalable qu'aucun `__init__.py` ni import
   dynamique n'y fait référence.
2. Supprimer les setters/getters de `CyclicTimer` et `DailyTimer`. **Conserver** :
   `CyclicTimer.__init__`, `_config_block`, `_load_from_config_block`, `get_mode` et les getters
   effectivement appelés par `cyclic_timer_handler` ; `DailyTimer.__init__`,
   `refresh_from_config` (appelée par `dailytimer_handler`), `toggle_state_daily`.
   → Vérifier appelant par appelant avec `grep -rn` avant chaque suppression.
3. Supprimer les deux méthodes de `SystemStatus`, les trois helpers de `function.py`, les trois de
   `pretty_console.py`.
4. Retirer les imports devenus inutiles dans chaque fichier touché.

#### Vérification

- Pour chaque symbole supprimé, `grep -rn "<symbole>" --include=*.py --include=*.html .` ne renvoie
  plus rien.
- `python3 -m compileall` sur l'arbre (compilation seule, pas d'exécution) : aucun `ImportError`
  résiduel. *Note : à faire côté utilisateur si la règle projet l'exige.*

---

### Lot 4 — Suppression d'`initial_setup_tool.py`

#### Problème

963 lignes, **11,6 % du Python du dépôt**, carry-over direct de la version ESP32 :

- rédigé **en anglais** dans un projet dont la convention impose le français (code, commentaires,
  logs, console) ;
- **53 `print()` nus**, alors que `CLAUDE.md` pose `utils/pretty_console` comme façade unique et
  interdit explicitement `print` ;
- lit et écrit `param.json` **relativement au répertoire courant**, pas `param/param.json`
  (rough edge déjà documentée) ;
- **aucune validation Pydantic** : il écrit du JSON brut ;
- **schéma périmé** : recherche vérifiée, il ne connaît **aucun** de
  `Heater_Settings`, `Log_Settings`, `hysteresis_offset`, `vent_deadband`, `vent_step`,
  `vent_release`, `absolute_floor_temp`, `min_dwell_seconds`, `sensor_fallback_speed`,
  `winter_humidity_minutes_per_hour`.

**Conséquence** : l'outil ne peut aujourd'hui produire qu'un `param.json` que `AppConfig.load()`
**rejette** — c'est-à-dire un boot mort. Il est plus dangereux que l'absence d'outil.

#### Actions

1. `git rm initial_setup_tool.py`.
2. Retirer la ligne correspondante de la section « Commands » de `CLAUDE.md` **et** `AGENTS.md`.
3. Retirer la rough edge associée (« `initial_setup_tool.py` est un straight carry-over… ») dans les
   deux fichiers.
4. Chercher les autres mentions : `grep -rn "initial_setup_tool" --include=*.md --include=*.sh .`
   (README, docs/operations/install-raspberry-pi.md, scripts/deploy.sh).

#### Remplacement (facultatif, ~40 lignes)

Si un générateur de `param.json` de référence reste utile, il s'écrit au-dessus d'`AppConfig` :

```python
# scripts/make_param.py
"""Génère un param/param.json de référence, validé par le schéma."""
from param.config import AppConfig
import json, pathlib

DEFAULTS = json.loads((pathlib.Path(__file__).parent.parent
                       / "param" / "param.example.json").read_text(encoding="utf-8"))
AppConfig.model_validate(DEFAULTS).save()   # validation + écriture atomique
```

Il hérite gratuitement de la validation, de l'écriture atomique et de la sérialisation
`"enabled"`/`"disabled"`. L'édition courante reste du ressort de `/conf`, qui la couvre entièrement.

**Ce lot dépend du Lot 1** (`param.example.json` doit exister) si le remplacement est retenu.

#### Vérification

- `grep -rn "initial_setup_tool" .` (hors `.git`) ne renvoie rien.
- `diff -u CLAUDE.md AGENTS.md` vide.

---

### Lot 5 — 🔴 Schéma de configuration unique (chantier structurel)

#### Problème

La configuration est décrite **cinq fois** :

| Endroit | Rôle | Poids |
|---|---|---|
| `param/config.py` | le schéma — **source de vérité** | 300 lignes |
| `network/web/server.py` → `SECTION_FIELDS`, `RELOAD_JOBS`, `SENSITIVE_FIELDS` | re-description manuelle des sections et des champs | ~90 lignes |
| `network/web/templates/conf.html` | libellés, unités, bornes, textes d'aide | 186 lignes |
| `initial_setup_tool.py` | sa propre idée du schéma | 963 lignes *(supprimé au Lot 4)* |
| `docs/reference/configuration.md` | la documentation | ~200 lignes |

Ajouter un champ demande **quatre à cinq éditions coordonnées**, sans filet automatique.
La preuve empirique que ce contrat ne tient pas, c'est le Lot 4 : l'outil de setup a divergé
jusqu'à produire un fichier invalide, sans que rien ne le signale.

Le patron correct **existe déjà dans ce dépôt** et fonctionne bien :
`controllers/sensor_catalog.py` est une table unique dont `SensorController`, `influx_handler`,
`server.py` et `conf.html` sont tous des **consommateurs**. Il faut l'étendre à la configuration.

#### Sous-lot 5.a — Type `EnabledFlag` (gain immédiat, faible risque)

**Problème précis** dans `param/config.py` :

- `@validator("enabled", pre=True)` — la **même** fonction `_parse_enabled` copiée **4 fois**
  (`DailyTimerSettings`, `CyclicSettings`, `HeaterSettings`, + variante `SensorState._parse_sensor`) ;
- `AppConfig.save()` re-sérialise `"enabled"`/`"disabled"` à la main dans **5 blocs copiés-collés**
  (heater, daily 1, daily 2, cyclic 1, cyclic 2) plus le dict des capteurs.

C'est le piège documenté dans `CLAUDE.md` : « any new boolean field needs the same treatment there ».
Une contrainte tenue à la main est une contrainte qui cédera.

**Correctif** — un type annoté unique :

```python
from typing import Annotated
from pydantic import BeforeValidator, PlainSerializer

_TRUEISH = {"enabled", "true", "1", "yes", "on"}

def _parse_enabled(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUEISH

EnabledFlag = Annotated[
    bool,
    BeforeValidator(_parse_enabled),
    PlainSerializer(lambda v: "enabled" if v else "disabled", return_type=str),
]
```

Puis `enabled: EnabledFlag = True` dans les quatre modèles, et
`bme280_state: EnabledFlag` (etc.) dans `SensorState`.

**Point d'attention** : `PlainSerializer` s'applique à `model_dump()`. Or `model_dump(by_alias=True)`
est utilisé à **deux endroits aux besoins opposés** :

- `AppConfig.save()` → veut la forme legacy `"enabled"`/`"disabled"` ✅ ;
- `server._configuration_post()` → construit un `payload` qu'il **re-valide** ensuite
  (`model_validate(payload)`), et compare `payload[top][nested]` à des booléens via
  `isinstance(current, bool)` dans `_apply_section_to_payload`.

Le second cassera si la sérialisation renvoie des chaînes. **Deux solutions**, à trancher à
l'implémentation :

1. Utiliser `mode="json"` / `mode="python"` pour distinguer les deux usages
   (`PlainSerializer(..., when_used="json")` → `save()` utilise `model_dump(mode="json")`,
   `server.py` garde `model_dump()` en mode python, qui reste booléen). **Solution recommandée.**
2. Adapter `_apply_section_to_payload` pour reconnaître les deux formes.

Après ce sous-lot : **~45 lignes en moins** dans `config.py`, et le piège disparaît structurellement.

#### Sous-lot 5.b — Source de configuration unique et cachée

**Problème** : quatre tâches relisent et re-valident `param.json` toutes les 30-60 s
(`timer_daily` ×2 via `DailyTimer.refresh_from_config`, `timer_cyclic` ×2, `climate_control`),
chacune avec **son propre** `try/except` + repli sur la dernière configuration valide, copié-collé
trois fois. Plus les rechargements ponctuels de `network_handler.do_connect()` et
`is_host_connected()`.

**Correctif** — `utils/config_source.py` :

```python
"""Source unique de configuration : cache par mtime, repli intégré.

Quatre tâches de régulation relisaient param.json indépendamment, chacune avec
sa propre copie du try/except + repli. Le repli est la partie critique (une
lecture impossible ne doit jamais tuer une boucle de contrôle) : il n'a aucune
raison d'exister en trois exemplaires.
"""

class ConfigSource:
    def current(self) -> AppConfig:
        """Configuration à jour, ou la dernière valide si le fichier est illisible.

        Le mtime évite de re-parser un fichier inchangé à chaque tick, sans
        jamais retarder la prise en compte d'une sauvegarde /conf (os.replace
        met le mtime à jour).
        """
```

Contrats à respecter impérativement :

- **Ne jamais lever** : un `param.json` illisible retourne la dernière configuration valide.
  C'est la garantie qui empêche une boucle de contrôle de mourir (audit C7).
- **Ne jamais retarder** une modification IHM : `write_text_atomic` fait un `os.replace`, le mtime
  change, le cache est invalidé au tick suivant. Le comportement « prise en compte à chaud sans
  redémarrage » est préservé à l'identique.
- Journalisation déduplquée : le `StateLogger` `_load_state` déjà présent dans `config.py` reste le
  seul émetteur.

Puis remplacer dans `timer_cyclic`, `climate_control` et `DailyTimer.refresh_from_config` les blocs
`try: AppConfig.load() except: repli` par un appel à `config_source.current()`.

Gain : **−3 blocs try/except dupliqués**, et 4 parses redondants par minute supprimés.

#### Sous-lot 5.c — Métadonnées de présentation dans le schéma

Porter libellé, unité, texte d'aide, bornes affichées et « nécessite un redémarrage » dans
`json_schema_extra` de chaque champ Pydantic. Exemple :

```python
vent_deadband: float = Field(
    1.0, alias="vent_deadband", ge=0, le=20,
    json_schema_extra={
        "section": "temperature",
        "label": "Zone morte chauffage/ventilation",
        "unit": "°C",
        "help": "Écart minimal entre l'extinction du chauffage et le démarrage "
                "de la ventilation. C'est lui qui interdit de chauffer et "
                "d'extraire en même temps.",
    },
)
```

Puis :

- `SECTION_FIELDS` devient **dérivé** : construit au démarrage par parcours de
  `AppConfig.model_fields` → sous-modèles → `json_schema_extra["section"]`.
- `SENSITIVE_FIELDS` devient un marqueur `json_schema_extra={"sensitive": True}`.
- `conf.html` : une macro Jinja unique qui boucle sur les champs d'une section, au lieu de 186 lignes
  de formulaires écrits à la main. Les macros `switch()`, `number()`, `save_button()` existent déjà —
  c'est un aiguillage sur le type du champ.
- `docs/reference/configuration.md` : peut être généré, ou au minimum vérifié par un script de
  cohérence.

⚠️ **Ce sous-lot est le plus lourd et le seul à risque visuel** (l'IHM change de mécanique de rendu).
Il est **facultatif à court terme** : 5.a et 5.b apportent l'essentiel du gain pour une fraction du
coût. Le faire seulement si l'ajout de champs de configuration reste une opération fréquente.

#### Vérification

- 5.a : sauvegarder chaque section depuis `/conf` et confirmer que `param.json` contient toujours
  `"enabled"`/`"disabled"` (et non `true`/`false`) — c'est la compatibilité legacy à ne pas casser.
- 5.b : couper les droits de lecture sur `param.json` pendant que le contrôleur tourne ; aucune tâche
  ne doit mourir, un seul WARNING dédupliqué doit apparaître, la régulation doit continuer sur la
  dernière configuration valide. Restaurer les droits → un seul INFO de rétablissement.
- 5.b : sauvegarder une section depuis `/conf` et confirmer la prise en compte au tick suivant
  (≤ 60 s) sans redémarrage.

---

### Lot 6 — Champs de configuration fantômes exposés à l'exploitant

#### Problème

Ce n'est pas de la dette cosmétique : ce sont des **réglages affichés dans `/conf` que plus personne
ne lit**. Quelqu'un qui règle `target_temp: 25` croit régler le déclenchement de la ventilation.
Rien ne se passe, et rien ne le dit.

| Champ | Statut |
|---|---|
| `Motor_Settings.target_temp` | **requis** dans le modèle, **0 lecture** dans tout le code. L'arbitre lit `Temperature_Settings.target_temp_*` ; `settings_from_config()` ne le référence pas |
| `Motor_Settings.hysteresis` | idem — l'arbitre utilise `Temperature_Settings.hysteresis_offset` |
| `GPIO_Settings.i2c_sda` | **0 lecture** — le bus est `smbus2.SMBus(1)` en dur |
| `GPIO_Settings.i2c_scl` | **0 lecture** — idem |
| `GPIO_Settings.ds18_pin` | **0 lecture** — les DS18B20 passent par sysfs (`/sys/bus/w1/devices/28-*`) |

Ces cinq champs sont des reliquats du portage ESP32, où ils avaient un sens (`machine.I2C(sda=…,
scl=…)`, `onewire` logiciel).

#### Actions

1. Retirer les cinq champs de `param/config.py` (`MotorSettings`, `GPIOSettings`).
2. **Migration silencieuse à la lecture** — un `param.json` déployé les contient encore. `ValidatedModel`
   hérite de `BaseModel` dont le défaut `extra="ignore"` accepte déjà les clés inconnues :
   **vérifier ce point** (`model_config = ConfigDict(validate_assignment=True, populate_by_name=True)`
   n'impose pas `extra="forbid"`, donc c'est bon). Les clés survivront simplement jusqu'à la première
   sauvegarde `/conf`, qui réécrira le fichier sans elles.
3. Retirer `i2c_sda`, `i2c_scl`, `ds18_pin` du tableau GPIO en lecture seule de `conf.html`
   (`gpio_fields` dans `network/web/pages.py` boucle sur `config.gpio.model_fields` → la suppression
   du modèle suffit, mais le vérifier).
4. Retirer `target_temp`/`hysteresis` de `SECTION_FIELDS["motor"]` s'ils y figurent (vérifier :
   ils n'y sont **pas** aujourd'hui, ce qui confirme qu'ils sont fantômes jusque dans l'IHM).
5. Mettre à jour `docs/reference/configuration.md` et `docs/hardware/gpio-matrix.md`.
6. Mettre à jour `param/param.example.json` (Lot 1).

#### Vérification

- Démarrer avec le `param.json` de production **inchangé** (contenant encore les cinq clés) :
  `AppConfig.load()` doit réussir. C'est le point bloquant de ce lot.
- Sauvegarder une section depuis `/conf` : le `param.json` réécrit ne contient plus les cinq clés.
- `grep -rn "target_temp\b\|i2c_sda\|i2c_scl\|ds18_pin" --include=*.py --include=*.html .` ne renvoie
  plus rien (attention : `target_temp_min_day` etc. doivent survivre — utiliser `\b`).

---

### Lot 7 — Correctifs ponctuels

Six correctifs indépendants, regroupés pour une seule relecture.

#### 7.1 🟠 `time.sleep(0.05)` bloquant dans l'event loop

**Fichier** : `components/MotorHandler.py` (import `from time import sleep`, appel dans
`set_motor_speed`).

`set_motor_speed()` est appelé depuis la coroutine `climate_control`. Chaque changement de vitesse
**gèle l'event loop entier pendant 50 ms** : serveur HTTP, flux SSE `/console`, boucle de caresse du
watchdog, les quatre timers. C'est le seul `sleep` bloquant restant dans du code asynchrone, et il
est dans le chemin GPIO.

La temporisation elle-même est **légitime** (délai de retombée des relais entre le « tout LOW » et
l'activation de la nouvelle vitesse) : il ne faut pas la supprimer, il faut la rendre non bloquante.

Correctif : rendre `set_motor_speed` `async` et utiliser `await asyncio.sleep(0.05)`.
Appelants à adapter :
- `components/climate_control.py` (branche `else: motor_handler.set_motor_speed(...)`) ;
- vérifier `all_off()` — il n'a pas de `sleep`, il reste synchrone et **doit le rester** :
  il est utilisé comme `safe_state` par le superviseur, qui appelle une fonction **synchrone**
  (`PuppetMaster._climate_off`, `_motor_off`). **Ne pas rendre `all_off` asynchrone.**

#### 7.2 `_sync_motor` ne recale pas `motor_speed_since`

**Fichier** : `components/climate_control.py`, fonction `_sync_motor`.

Quand l'état réel des broches diverge du cache, la fonction fait
`replace(memory, motor_speed=real)` mais laisse `motor_speed_since` à sa valeur antérieure.
Le temps de maintien (`_apply_dwell`) se calcule alors contre un instant qui ne correspond plus à la
vitesse effectivement en place : soit un changement est autorisé trop tôt, soit il est bloqué trop
longtemps.

Correctif : passer `now_mono` à `_sync_motor` et faire
`replace(memory, motor_speed=real, motor_speed_since=now_mono)` — une resynchronisation **est** un
changement de vitesse du point de vue du maintien.

#### 7.3 `deepcopy` répété dans le payload d'état

**Fichier** : `network/web/server.py`, `_state_payload`.

```python
for key in self.stats.KEYS:
    item = self.stats.get_all().get(key, {})   # ← deepcopy complet par itération
```

`SensorStats.get_all()` fait un `copy.deepcopy` sous verrou. Appelé **une fois par clé** (3 clés),
sur chaque requête, et le tableau de bord rafraîchit toutes les 5 s. Sortir l'appel de la boucle.

#### 7.4 « None » affiché avant le premier tick de l'arbitre

**Fichier** : `network/web/templates/main.html` (bloc `climate-thresholds`).

Le garde `{%- if state.climate.vent_threshold is not none -%}` ne couvre que `vent_threshold`, alors
que la ligne affiche aussi `heater_off_threshold`. Les deux sont `None` dans le `_snapshot` initial de
`climate_control`, avant le premier tick. Étendre le garde aux deux valeurs, ou n'afficher la ligne
que si `state.climate.state` n'est pas `None`.

Vérifier au passage le même risque sur `climate-budgets` (`renew_minutes_used` etc. valent `0.0` à
l'initialisation, donc pas de « None » — mais afficher `0/0 min` avant le premier tick est trompeur).

#### 7.5 Rechargements de configuration redondants au boot

**Fichier** : `network/network_handler.py`.

`do_connect()` et `is_host_connected()` font chacun un `AppConfig.load()` alors que `main.py` vient
de charger la configuration et pourrait la passer. Deux lectures disque inutiles et un risque de
divergence si le fichier change entre les deux.

Correctif : accepter un paramètre `config` optionnel (comme le fait déjà
`function.motor_all_pin_down_at_boot`), et le passer depuis `main.py`.

#### 7.6 `console_stream.install()` appelé à deux endroits

`main.py` et `Server.__init__`. La méthode est idempotente (`self._installed`), donc **bénin** —
mais c'est le signe que la responsabilité n'est pas placée. Le point d'installation naturel est
`main.py` (démarrage du processus) ; retirer l'appel de `Server.__init__`.

⚠️ Vérifier d'abord que `Server` n'est jamais instancié sans passer par `main.py`
(aujourd'hui : construit uniquement dans `PuppetMaster._register_jobs`, donc oui).

#### Vérification du lot

- 7.1 : décrire les transitions GPIO attendues sur un changement de vitesse 0 → 2 :
  `pin1..pin4 = LOW` (déjà), attente 50 ms **sans blocage de la boucle**, `pin2 = HIGH`.
  Confirmer que `/api/v1/state` répond pendant la transition.
- 7.1 : confirmer que `all_off()` est resté synchrone et que `PuppetMaster._climate_off` /
  `_motor_off` compilent sans `await`.
- 7.4 : charger `/` immédiatement après un redémarrage, avant le premier tick de l'arbitre (30 s) :
  aucun « None » ne doit apparaître.

---

### Lot 8 — Découpage de `network/web/server.py`

#### Problème

654 lignes, **cinq métiers dans une classe** :

1. routage et cycle de vie aiohttp ;
2. sécurité : trois middlewares (en-têtes/CSP, validation d'hôte, CSRF/origine) + `_error_response` ;
3. mapping formulaire → configuration : `SECTION_FIELDS`, `_validate_form_shape`,
   `_apply_section_to_payload`, `_format_validation_errors`, `_apply_runtime_changes` ;
4. construction du payload d'état : `_state_payload`, `_timer_payload`, `_logical_state` ;
5. actions système : reboot, poweroff, reset de statistiques, routes historiques.

#### Découpage proposé

| Nouveau module | Contenu |
|---|---|
| `network/web/security.py` | les trois middlewares, `_host_without_port`, `_build_allowed_names`, `HTTP_ERROR_TITLES`, `_error_response` |
| `network/web/config_forms.py` | `SECTION_FIELDS`, `SENSITIVE_FIELDS`, `RELOAD_JOBS`, `_validate_form_shape`, `_apply_section_to_payload`, `_format_validation_errors` |
| `network/web/state.py` | `_state_payload`, `_timer_payload`, `_logical_state`, `_utc_now` |
| `network/web/server.py` | routage, cycle de vie, handlers — **~250 lignes** |

**Contraintes de sûreté à ne pas casser** (elles viennent de la Phase 1, audit C11/C12/C13) :

- les middlewares doivent rester dans **cet ordre** :
  `_security_middleware` → `_host_middleware` → `_csrf_middleware` ;
- `_error_response` doit continuer à **laisser passer les 3xx** (les redirections sont des
  `HTTPException` : les transformer en page d'erreur casserait tous les `HTTPSeeOther`) ;
- les actions destructrices restent **POST-only** avec CSRF + contrôle d'origine ;
- les champs sensibles vides valent « inchangé », et le GPIO reste en lecture seule.

#### Sous-lot 8.b — Route statique unique

Six handlers quasi identiques (`_style`, `_dashboard_js`, `_config_js`, `_console_js`, `_font`,
`_favicon`) + six déclarations de routes = ~26 lignes.

```python
STATIC_ASSETS = {
    ("css", "style.css"): "text/css",
    ("js", "dashboard.js"): "application/javascript",
    ("js", "config.js"): "application/javascript",
    ("js", "console.js"): "application/javascript",
    ("fonts", "visitor1.ttf"): "font/ttf",
}

async def _static(self, request):
    key = (request.match_info["kind"], request.match_info["name"])
    content_type = STATIC_ASSETS.get(key)
    if content_type is None:
        raise web.HTTPNotFound()
    return await self._asset(f"{key[0]}/{key[1]}", content_type)
```

⚠️ **La garantie de sécurité doit être strictement conservée** : la liste blanche est **exacte**
(couples explicites, pas de motif), donc aucune traversée de chemin n'est possible — c'est le
correctif de C11 et il ne doit pas se relâcher en `Path(STATIC_DIR / user_input)`.
`/favicon.svg` reste une route dédiée (elle est à la racine, pas sous `static/`).

Gain : ~8 lignes au lieu de 26.

#### Vérification

- Parcourir toutes les routes déclarées avant/après : la liste doit être **identique** en méthode et
  en chemin (sauf les six routes statiques, remplacées par une).
- `GET /static/../param/param.json` → 404 (pas de traversée).
- `GET /static/css/inconnu.css` → 404.
- `POST /conf/temperature` sans jeton CSRF → 403 ; avec jeton mais `Origin` étranger → 403.
- `GET /monitor` → 303 vers `/#surveillance` **et non** une page d'erreur.
- `GET /` avec `Host: exemple.com` → 421.

---

### Lot 9 — `DailyTimer` / `CyclicTimer` : de classes actives à schedules gelés

**Dépend du Lot 3** (les setters doivent avoir disparu).

#### Problème

Après le Lot 3, il reste ~200 lignes pour deux classes qui ne sont plus que des **sacs de champs**,
et dont l'encapsulation est déjà rompue : `cyclic_timer_handler.py` fait

```python
cyclic_timer._config = cfg
cyclic_timer._load_from_config_block()
```

— il écrit **deux attributs privés** de la classe pour la recharger. La classe n'apporte plus rien
que le handler ne fasse lui-même.

#### Cible

```python
@dataclass(frozen=True)
class CyclicSchedule:
    timer_id: str
    mode: str
    period_days: int
    triggers_per_day: int
    first_trigger_hour: int
    action_duration: int
    on_time_day: int
    off_time_day: int
    on_time_night: int
    off_time_night: int

    @classmethod
    def from_config(cls, config, timer_id: str) -> "CyclicSchedule":
        block = config.cyclic1 if timer_id == "1" else config.cyclic2
        ...
```

Le handler garde le `Component` séparément (c'est le seul état mutable réel) et reconstruit un
`CyclicSchedule` gelé à chaque rechargement de configuration. Même traitement pour `DailyTimer` :
`DailySchedule.from_config(...)` + la logique de bascule déplacée dans le handler ou dans une
fonction pure.

#### Points d'attention

- `PuppetMaster` passe `self.cyclic_timer1.component` comme `safe_state` au superviseur, et
  `server.py` lit `getattr(self.cyclic_timer1, "component", None)` pour `/api/v1/state` **et**
  `self.config.cyclic1` pour `_timer_payload`. Ces accès doivent continuer de fonctionner :
  prévoir un petit conteneur `CyclicOutput(component, timer_id)` conservé par `main.py`, ou adapter
  les deux appelants.
- `DailyTimer.__init__` fait aujourd'hui une **synchronisation immédiate** de la sortie
  (`toggle_state_daily()` au chargement, ou `set_state(0)` si désactivé). Ce comportement au boot
  doit être conservé — c'est lui qui met la lampe dans le bon état avant le premier tick de 60 s.
- `dailytimer_handler` teste `hasattr(dailytimer, "refresh_from_config")` : ce test défensif devient
  inutile et doit disparaître avec la refonte.

Gain estimé : **~150 lignes**.

#### Vérification

- Décrire les transitions GPIO attendues au boot, `DailyTimer1` actif à l'instant du démarrage :
  `GPIO 5 → LOW` (relais fermé, éclairage ON) avant l'entrée dans la boucle, comme aujourd'hui.
- `/api/v1/state` : le bloc `timers` doit être **byte-identique** avant/après.
- Modifier un horaire via `/conf` : prise en compte au tick suivant (≤ 60 s), sans redémarrage.

---

### Lot 10 — Chemin de journalisation unique, GPIO centralisé, fenêtre horaire unique

#### 10.a — `pretty_console` : deux chemins d'émission parallèles

**Fichier** : `utils/pretty_console.py`, fonction `_print` (et `title`, `box`).

Chaque message part par **deux chemins indépendants** : un `print()` direct (ou `rich_console.print`)
pour la console, et un `log.log(level, msg)` pour le fichier.

Conséquences :

1. `/console` est branché sur le **logger** (`utils/log_stream.ConsoleStream` est un
   `logging.Handler`). Le terminal voit donc les pictogrammes et les couleurs, `/console` voit le
   format fichier. Deux vérités.
2. Les cadres `╔══╗` de `box()` et les barres `═══` de `title()` partent dans le `stdout` du service
   systemd, où personne ne les lit — et où ils encombrent `journalctl`.
3. Le filtre de niveau doit être vérifié **à la main** (`log.isEnabledFor(level)`) dans `_print`,
   `title` **et** `box`, parce que le `print` ne passe pas par le logger. Trois copies de la même
   garde.

**Correctif** : un `logging.StreamHandler` avec un formatter coloré, ajouté au logger `phyto` à côté
du `TimedRotatingFileHandler`. Les fonctions publiques (`debug`/`info`/`success`/… ) deviennent de
simples appels `log.log(...)` ; le décor devient l'affaire du formatter, qui sait s'il écrit sur un
tty (`sys.stdout.isatty()`).

Gains : **~60 lignes en moins**, un seul filtre de niveau, `/console` et le terminal enfin cohérents,
et le décor supprimé automatiquement hors tty.

⚠️ **Ne pas casser** : `apply_log_settings()` (niveau + rétention, appelé au boot et sur POST `/conf`),
la priorité `PHYTO_LOG_LEVEL` > `param.json` > INFO, le rotator gzip, et le fait que `box()` écrive
**une seule ligne** dans le fichier (`" | ".join(...)`) — le multi-ligne casse le parsing.

#### 10.b — Trois `GPIO.setmode()` au niveau module

`model/Component.py`, `model/Motor.py` et `function.py` appellent tous
`GPIO.setmode(GPIO.BCM)` + `GPIO.setwarnings(False)` **à l'import**, en plus de `main.py`.

Conséquence : **aucun module métier n'est importable hors Raspberry Pi**
(`import RPi.GPIO` échoue, et même disponible, l'import a des effets de bord matériels).
C'est ce qui rend ce projet non testable, bien plus que l'absence de suite de tests.

**Correctif** : `utils/gpio.py` avec une fonction idempotente

```python
_configured = False

def ensure_mode() -> None:
    """Configure le mode BCM une seule fois pour tout le processus."""
```

appelée depuis `Component.__init__` et `Motor.__init__` (pas à l'import), et une fois depuis
`main.py`. Les trois `GPIO.setmode` de niveau module disparaissent.

⚠️ **Ne pas toucher à la séquence de boot de `main.py`** : `motor_all_pin_down_at_boot(config)`
**avant** l'initialisation des génériques reste l'ordre correct, et `GENERIC_SAFE_PINS` /
`MOTOR_PINS` gardent leur séparation. **Ne jamais introduire `GPIO.cleanup()`** (audit C3).

#### 10.c — Trois copies de la fenêtre horaire jour/nuit

La formule « fenêtre qui peut enjamber minuit » est écrite **trois fois** :

- `components/climate_control.py` → `_is_day(cfg)` ;
- `components/cyclic_timer_handler.py` → `_is_day_from(cfg)` ;
- `model/DailyTimer.py` → `toggle_state_daily()` (inline).

Toutes trois calculent `(start <= now <= stop) if start <= stop else (now >= start or now <= stop)`.

**Correctif** : `utils/schedule.py`

```python
def in_window(start_hour: int, start_minute: int,
              stop_hour: int, stop_minute: int,
              now: datetime | None = None) -> bool:
    """Vrai si `now` tombe dans la fenêtre, y compris quand elle enjambe minuit."""
```

et `is_day(config, now=None)` qui l'applique au `daily_timer1` (l'éclairage définit le jour —
sémantique historique à conserver telle quelle).

#### Vérification

- 10.a : `journalctl -u phyto` ne contient plus de caractères de cadre ; `/console` et la sortie
  d'un lancement manuel affichent les mêmes lignes ; changer le niveau via `/conf` prend effet
  immédiatement sur les deux.
- 10.b : `python3 -c "import model.Component"` sur une machine sans `RPi.GPIO` échoue toujours sur
  l'import du module tiers, mais plus sur un effet de bord matériel — le vrai test est qu'aucun
  `setmode` ne s'exécute avant la première instanciation.
- 10.c : vérifier les trois cas limites de `in_window` : fenêtre normale (07:00→19:00), fenêtre
  enjambant minuit (19:00→07:00, cas du `param.json` déployé), fenêtre dégénérée (start == stop).

---

### Lot 11 — Retrait daté de la surface web historique

#### Problème

Cinq chemins de compatibilité doublent des routes propres :

| Route historique | Remplacée par |
|---|---|
| `GET /status` | `GET /api/v1/state` |
| `POST /monitor` + `_legacy_monitor_action` | `POST /actions/stats/reset`, `/actions/system/reboot`, `/actions/system/poweroff` |
| `GET /monitor` | redirection vers `/#surveillance` |
| `GET /index.html` | `GET /` |
| `GET /favicon.ico` | `GET /favicon.svg` |

Surtout : **`controllers/SystemStatus.py` (77 lignes) n'existe plus que pour `/status`**, et seules
**2 de ses 6 méthodes** y servent (`get_component_state`, `get_motor_speed` — les deux autres sont
supprimées au Lot 3). Retirer `/status` tue la classe entière, ainsi que le paramètre
`controller_status` traversant `main.py` → `PuppetMaster` → `Server`.

#### Actions

1. **Fixer une date de retrait** et l'annoncer. `docs/operations/web-baseline-2026-08-25.md` existe
   déjà : y ajouter une section « Surface historique — retrait prévu le AAAA-MM-JJ ».
2. Avant retrait : vérifier qu'aucun script d'exploitation ne consomme `/status`
   (`grep -rn "status" scripts/ deploy/ docs/operations/`) — le runbook et la doc de monitoring en
   parlent, il faut les migrer vers `/api/v1/state` et `/health/ready`.
3. Le jour du retrait : supprimer les cinq routes, `_legacy_status`, `_legacy_monitor_action`,
   `_favicon_redirect`, `controllers/SystemStatus.py`, et le paramètre `controller_status` de
   `PuppetMaster` et `Server`.
4. Adapter `docs/reference/http-interface.md` et `docs/reference/status-schema.md`.

Gain : **~120 lignes**.

**Note** : `get_climate_alarm` est déjà aliasé en `get_heater_alarm` pour la même raison
(compatibilité des scripts d'exploitation). Traiter les deux alias au même moment, ou décider
explicitement de conserver l'alias.

#### Vérification

- Après retrait : `GET /status` → 404 rendu en HTML pour un navigateur, en texte sinon.
- `/api/v1/state` et `/health/ready` couvrent l'intégralité de ce que `/status` exposait
  (comparer champ à champ **avant** de supprimer).

---

### Lot 12 — Ménage documentaire

~4 065 lignes de markdown pour 8 286 lignes de Python.

#### 12.a — `CLAUDE.md` / `AGENTS.md` : 215 lignes dupliquées à l'octet

`diff -q CLAUDE.md AGENTS.md` : **identiques**. Et une règle du projet demande de vérifier
`diff -u` après chaque édition. Une contrainte tenue à la main est une contrainte qui cédera.

Options, par ordre de préférence :

1. **Lien symbolique** : `git rm AGENTS.md && ln -s CLAUDE.md AGENTS.md && git add AGENTS.md`.
   Git suit les liens symboliques nativement. ⚠️ Sur un checkout Windows sans
   `core.symlinks=true`, le lien apparaît comme un fichier texte contenant le chemin — **à vérifier
   sur l'environnement réel avant d'adopter** (ce dépôt est monté sous `/mnt/c`).
2. **Hook `pre-commit`** de trois lignes qui recopie `CLAUDE.md` vers `AGENTS.md` et échoue si le
   diff n'est pas vide. Fonctionne partout, mais n'est pas versionné par défaut.
3. **Statu quo** assumé, avec la règle explicitement documentée (situation actuelle).

À trancher selon le résultat du test de symlink.

#### 12.b — Plans de chantiers terminés

`tasks/audit_phase0_todo.md` (6,3 K), `audit_phase1_todo.md` (8,4 K), `audit_phase2_todo.md` (10,4 K),
`todo.md` (14,1 K), `logging_refonte_plan.md` (13 K) = **834 lignes** de plans **achevés**, qui
redisent `AUDIT-2026-08-25.md` et le `CHANGELOG`.

→ Déplacer sous `docs/decisions/` s'ils ont une valeur d'archive (ils documentent des **raisonnements**
utiles : pourquoi la zone morte est calculée plutôt que validée, pourquoi le repli capteur est nommé),
sinon supprimer. Le présent plan (`tasks/plan_dette_technique.md`) suivra le même chemin une fois
exécuté.

#### 12.c — Le fichier `notes`

165 lignes, dont un bloc **dangereux** annoté `⛔ NE PAS RECOPIER LE BLOC CI-DESSOUS TEL QUEL ⛔`
(les lignes `gpio=N=op,dh`, fausses pour les broches moteur actives-HAUT, et de toute façon ignorées
sous Bookworm où le fichier de boot est `/boot/firmware/config.txt`).

**Un fichier qu'on doit accompagner d'un avertissement de ne pas le lire doit être supprimé, pas
commenté.** Le contenu encore utile (activation OneWire, paquets `network-manager`) appartient à
`docs/operations/install-raspberry-pi.md` ; la mise en garde sur les états sûrs au boot appartient à
`docs/hardware/gpio-matrix.md` et à `docs/risk-register.md` (finding C2, toujours ouvert).

#### Vérification

- `docs/index.md` mis à jour (il sert de table des matières).
- Aucun lien mort : `grep -rn "](.*\.md)" docs/ *.md` et vérifier chaque cible.

---

### Lot 13 — *(optionnel, décision utilisateur)* Tests de `climate_policy`

**⚠️ Ce lot contredit une règle explicite du projet** : `CLAUDE.md` indique
« There is **no test suite and no linter configured** in this tree. Do not invent one ».
Il n'est donc **pas** à exécuter sans accord explicite. Il est décrit ici parce que le rapport
valeur/coût y est inhabituel.

#### Argument

`components/climate_policy.py` est **pur** : pas de GPIO, pas de disque, pas d'horloge implicite
(le temps entre par `ClimateInputs`, l'état par `ClimateMemory` gelé). C'est :

- le module qui décide de commuter **230 V** ;
- 584 lignes, le plus gros du dépôt ;
- **testable sans aucun matériel**, sur n'importe quelle machine.

Aujourd'hui, tous ses invariants sont préservés par **relecture humaine**, comme le demande
`CLAUDE.md` (« Invariants that must survive any refactor »). Un fichier de test les verrouille.

#### Contenu proposé (~150 lignes, `pytest`, zéro dépendance matérielle)

| Scénario | Invariant vérifié | Audit |
|---|---|---|
| `temp_max` sous `temp_min + hyst + deadband` | `vent_threshold` relevé, `vent_threshold_raised` vrai, jamais chauffage+extraction simultanés | C9 |
| Balayage de température de −10 à 40 °C | il n'existe **aucune** température où `heater_on and motor_speed > 0` | C9 |
| Mode hiver, budget de renouvellement épuisé | passage à `winter_default_speed`, puis 0 si trop froid | C8 |
| Mode hiver, RH élevée, budget déshumidification épuisé | **pas** de court-circuit du quota de renouvellement | C8 |
| `temp < absolute_floor_temp` | `motor_speed == 0` quel que soit le budget | C8 |
| 5 lectures invalides consécutives (dont hors `]-20;60[`) | `REPLI_CAPTEUR`, chauffage OFF, alarme, `sensor_fallback_speed` | C10 |
| ON continu > 120 min | coupure + cooldown de 15 min, rallumage inhibé pendant | Phase 0 |
| Oscillation de 0,1 °C autour d'un seuil de palier | aucun changement de palier (hystérésis d'état) | E9 |
| Deux changements à moins de `min_dwell_seconds` | le second est retenu, sauf urgence (`immediate`) | E9 |
| `clamp_speed(settings, 0)` avec `min_speed = 2` | retourne **0** — un ordre d'arrêt reste un arrêt | M13 |
| Saut d'horloge arrière sur `now_epoch` | la fenêtre de budget est réarmée, pas gelée | M14 |

Emplacement : `tests/test_climate_policy.py`. Ajouter `pytest` en dépendance **de développement
uniquement** (fichier séparé `requirements-dev.txt`, jamais dans `requirements.txt` — le Pi n'a pas à
l'installer).

---

## 3. Récapitulatif chiffré

| Lot | Python retiré | Python ajouté | Net |
|---|---|---|---|
| 1 — Secrets | 0 | 0 | 0 (+ 1 fichier exemple) |
| 2 — Durées nulles | 0 | ~25 | **+25** (correctif de sûreté) |
| 3 — Code mort | ~250 | 0 | **−250** |
| 4 — `initial_setup_tool` | 963 | ~40 (optionnel) | **−923** |
| 5 — Schéma unique (5.a + 5.b) | ~110 | ~50 | **−60** |
| 6 — Champs fantômes | ~15 | ~5 | **−10** |
| 7 — Correctifs ponctuels | ~5 | ~15 | **+10** |
| 8 — Découpage `server.py` | 0 (déplacé) + 18 | 0 | **−18** |
| 9 — Schedules gelés | ~200 | ~50 | **−150** |
| 10 — Journalisation, GPIO, `in_window` | ~110 | ~50 | **−60** |
| 11 — Surface historique | ~120 | 0 | **−120** |
| **Total Python** | | | **≈ −1 550 à −1 900** (19 à 23 %) |
| 12 — Documentation | ~1 000 lignes md | 0 | **−1 000** |

---

## 4. Journal d'exécution

À tenir à jour au fur et à mesure. Un lot n'est coché que lorsque sa section « Vérification » est
intégralement satisfaite.

- [ ] **Lot 1** — Rotation des secrets, `param.json` hors de git — *décision préalable : réécriture d'historique ou non*
- [ ] **Lot 2** — Durées nulles en mode séquentiel — *vérifier d'abord que `AppConfig.load()` passe sur le `param.json` de production*
- [ ] **Lot 4** — Suppression d'`initial_setup_tool.py`
- [ ] **Lot 3** — Suppression du code mort
- [ ] **Lot 6** — Champs de configuration fantômes
- [ ] **Lot 7** — Correctifs ponctuels (7.1 à 7.6)
- [ ] **Lot 5.a** — Type `EnabledFlag`
- [ ] **Lot 5.b** — `utils/config_source.py`
- [ ] **Lot 5.c** — Métadonnées de présentation dans le schéma *(facultatif)*
- [ ] **Lot 8** — Découpage de `server.py` (+ route statique unique)
- [ ] **Lot 9** — Schedules gelés
- [ ] **Lot 10** — Journalisation, GPIO, `in_window`
- [ ] **Lot 11** — Retrait de la surface web historique — *date de retrait à fixer :*
- [ ] **Lot 12** — Ménage documentaire
- [ ] **Lot 13** — Tests de `climate_policy` *(nécessite un accord explicite : contredit une règle projet)*

---

## 5. Section revue *(à remplir en fin de chantier)*

> Conformément à la convention du projet : consigner ici ce qui a été fait, ce qui a été écarté et
> pourquoi, et toute correction reçue en cours de route (à reporter aussi dans `tasks/lessons.md`).
