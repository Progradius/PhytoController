# Repository agent instructions

This file provides guidance to coding agents working with code in this repository.

## Instruction-file synchronization

`CLAUDE.md` and `AGENTS.md` are exact mirrors and must always remain synchronized. Any change to either
file must be applied identically to the other file in the same change. Before completing an edit, verify
that `diff -u CLAUDE.md AGENTS.md` produces no output. Do not update, rename, move, or delete only one of
these files.

## Scope

This directory (`RPi Version/`) is the Raspberry Pi / CPython 3.9+ port of PhytoController (greenhouse
controller: timers, motor speed, heater, sensors, InfluxDB export, embedded web UI).
The sibling `ESP32 Version/` is the original MicroPython implementation — same domain model, different
runtime (`machine.Pin`, `uasyncio`, Nextion display). Changes here are **not** meant to be mirrored there
unless asked; the two trees have diverged.

## Commands

```bash
sudo python3 main.py                 # run (root needed: GPIO, nmcli Wi-Fi, timedatectl, /dev/watchdog)
PHYTO_RUN_MODE=service python3 main.py   # run under systemd — see "Run modes" below
python3 initial_setup_tool.py        # interactive TUI to generate/edit param.json (writes to CWD, see gotchas)
pip install -r requirements.txt
pip install -r requirements-dev.txt  # dépendances runtime + validation hors matériel
python3 -m pytest                    # suite reproductible sans GPIO réel
npm ci && npm run test:ui           # tests responsive en lecture seule ; PHYTO_UI_BASE_URL surcharge la cible
docker build -t phyto . && docker run --privileged -p 8123:8123 \
  -v "$(pwd)/param/param.json:/app/param/param.json:rw" phyto
```

Web UI: `http://<pi>:8123` — `/` action-oriented dashboard with 5 s live refresh, `/history` for
the detailed 24/48/72 h charts, `/conf` section-based config form,
`/console` (SSE log stream), `/app` (per-device PWA page: connection, install, offline copies,
notifications, active worker version), `/api/v1/state` (versioned JSON), `/health/live`,
`/health/ready` and the legacy `/status`. `/monitor` redirects to the dashboard;
reset/reboot/poweroff remain **POST-only**.

The repository has a small `pytest` suite under `tests/`; run it for every Python change. It uses a
recording fake for GPIO and temporary configuration files, and must remain runnable without root,
external network or Raspberry Pi hardware (HTTP tests use loopback only). It does **not** qualify electrical behaviour: changes involving real
pins, relays or loads also require the supervised procedure in `docs/development/hardware-validation.md`.
There is still no linter configured; do not invent one as part of an unrelated change.

## Architecture

Boot sequence lives entirely in `main.py` (module-level, not in a `main()`): **take the instance lock** →
load config → force GPIO to safe states → Wi-Fi → NTP → build components/timers/sensors → hand everything
to `PuppetMaster`.

- `utils/single_instance.py` — **exactly one controller process at a time**. The lock is an abstract Unix
  socket (`\0phyto-controller`), taken before any GPIO access and before the signal/`atexit` handlers are
  registered, so a surplus instance exits without touching a pin. It waits up to 15 s (an old process may
  still be dying during a `systemctl restart`), then `sys.exit(1)` — a **non-zero** code on purpose, so
  systemd and `scripts/deploy.sh`'s health check see a failure instead of a silent "exited". Two live
  instances fight over the same pins: each forces the generics HIGH (cutting what the other held ON) and
  resets the motor. Nothing in `/dev/gpiomem` prevents that, hence the lock.
- `param/config.py` — `AppConfig` (Pydantic v2, still using v1-style `@validator`): the *schema*, not the
  owner. JSON keys are PascalCase aliases (`DailyTimer1_Settings`, `GPIO_Settings`, …); Python field names
  are snake_case. `load(path)` is a stateless read+validate primitive and `to_json()` a stateless
  serializer that re-emits booleans as the legacy `"enabled"`/`"disabled"` strings — **any new boolean
  field needs the same treatment in `to_json()`**. `AppConfig` no longer writes itself: giving the model a
  `save()` made it a second writer of `param.json`, hence two possible truths.
  GPIO pins are bounded to BCM 0–27; **uniqueness is deliberately not validated** — 27 and 22 each carry
  two roles in the production config, so a uniqueness validator would be a dead boot. Pin collisions
  belong to Phase 1's `PinRegistry`, together with the pin migration that goes with them.
- `param/config_store.py` — **`ConfigStore`, sole owner and sole writer of `param.json`** (Phase 3).
  `shared_config()` is the process singleton; `main.py` takes `.current` at boot and hands that **one**
  `AppConfig` instance to everyone. It is never replaced, only mutated in place (`replace_from`), so every
  reference distributed at boot (motor, sensors, `SystemStatus`, server, timers) stays current with
  nothing to subscribe to.
  * `refresh()` — the control-path method: compares `(mtime_ns, size)`, does **no I/O at all** while the
    file is unchanged, and **never raises**. A failed reread keeps the current config *and* records the
    stamp anyway, so a broken file is not reparsed on every tick of every loop.
  * `save(candidate)` / `commit()` — full `model_validate` of the whole model, previous content copied to
    `param.json.bak`, then `utils/atomic_io.write_text_atomic()` (tmp + `fsync` + `os.replace`, existing
    file mode preserved). **Never** go back to `write_text()`: a control loop can reread the file at any
    instant, and a power cut mid-write would leave a truncated `param.json`, i.e. a dead boot.
    `SensorStats._dump()` and `utils/state_store.py` use the same helper. A rejected `commit()` restores
    the shared instance from disk rather than leaving an invalid config in memory.
  * At boot an unusable `param.json` falls back to `param.json.bak` and **restores** it. There is nothing
    safe to synthesize beyond that: without `GPIO_Settings` no pin is known, so no output can be put in a
    safe state — refusing to start is the only honest answer, and `main.py` has touched no pin yet.
  * `param/param.json` is a **machine-local, gitignored file**. Only the inert
    `param/param.example.json` schema is versioned. `scripts/deploy.sh` rejects any target commit that
    tracks the live configuration, and an exclusive `flock` prevents concurrent deployments. Never
    reintroduce `param.json` into Git or a checkout/stash path: even a temporary replacement is observed
    immediately by the running control loops.
- `utils/runtime_paths.py` — **the single resolution of where runtime-written files live**, and the
  reason a checkout can no longer destroy the live configuration. On 08/09/2026 a hand-run
  `git checkout master` overwrote `param/param.json`: the deployed branch did not track the file, the
  target revision still did, and Git therefore materialised the commit's version **on top of the live
  config** — 26 h without lighting or cycle. Gitignoring is not protection; every commit before `5cddf2f`
  still tracks that file. `data_dir()` returns `PHYTO_DATA_DIR` when set and non-empty, otherwise the
  repository's `param/` — the historical default, so development, tests and Docker are unchanged. Eight
  anchors go through `data_file(...)`: `param.json` (and its `.bak`), `runtime_state.json`,
  `sensor_stats.json`, `equipment_metadata.json`, `.csrf_token`, `operator_history.sqlite3`,
  `cultures.sqlite3` and — derived from that database's path — the `culture_media/` directory. The
  resolution is memoised: a late environment change must not create a second truth mid-process, and
  `data_dir()`/`data_file()` are **pure** because they run at import time. `main.py` calls
  `ensure_data_dir()` at boot, before the instance lock and before any file access; when
  `PHYTO_DATA_DIR` is set but unusable it **exits loudly**, no pin having been touched. **Never add a
  silent fallback to `param/` there** — the process would quietly resume writing inside the Git working
  tree, which is the very incident this module removes. `scripts/deploy.sh` reads the variable from the
  systemd unit (`systemctl show`), never from its own environment: a shell-level `${PHYTO_DATA_DIR:-…}`
  would fall back to `param/` after migration and back up a directory the service no longer uses.
  Procedure and proof: `docs/operations/migration-donnees-vivantes.md`.
- `controllers/PuppetMaster.py` — the only orchestrator. It no longer creates tasks itself: it *registers*
  one supervised job per concern with `utils/supervisor.TaskSupervisor` — eleven jobs: 2 daily timers,
  2 cyclic timers, the `climate_control` thermal arbiter and the shared `sensor_snapshot` (the only ones
  with `gates_watchdog=True`), then `influx_push`, `culture_service`, `http_server`, `time_monitor` and
  `operator_service`, all auxiliary. It starts the watchdog loop, calls
  `sd_notify(READY=1)`, then awaits the supervisor. Its asyncio exception handler logs and keeps the loop
  alive on purpose — a crashing task must never take the greenhouse down.
- `utils/supervisor.py` — **the reason a dead control loop can no longer go unnoticed.** Every job runs
  inside `while True: try/except` with capped exponential back-off; its **safe state is re-applied before
  each restart** (`safe_state=` — output OFF, motor OFF); it publishes a heartbeat, and a job that is
  alive but silent past `max_silence` is cancelled and restarted by a watcher. Register with a *factory*
  (`lambda: coro(...)`), never a coroutine — a coroutine is consumable once, so it could not be relaunched.
  Business loops call `beat()` each iteration and `await supervisor.sleep(...)` instead of
  `asyncio.sleep(...)` so a long *intended* wait (up to 10 days for a cyclic timer) is not mistaken for a
  block. The job is carried by a `contextvars` variable, so no business signature has to thread it through.
  `snapshot()` / `is_healthy()` feed the state/health APIs and gate the watchdog. `request_reload()`
  cancels and restarts a control job when configuration changes and **deliberately skips the safe state**:
  the job was healthy, and re-applying OFF on every save would blink the relay. The safe state is for
  faults, stalls and abnormal returns only — what must be released on cancellation is already released by
  the job's own `finally` (`energized()`). Do not "restore symmetry" here.
- `utils/watchdog.py` — the watchdog is **conditional**: it only pets (systemd `WATCHDOG=1` if
  `NOTIFY_SOCKET`/`WATCHDOG_USEC` are set, otherwise `/dev/watchdog`) while `supervisor.is_healthy()`.
  A blind pet is worse than none: it certifies a process whose regulation may be dead. The `/dev/watchdog`
  fd is opened once and kept at module level — the magic close (`V`) *must* go to that same fd, which is
  why the old reopen-then-write failed with `EBUSY` and left the watchdog armed. Petting runs in the event
  loop, not a thread, so a blocked loop stops petting. The pet period is capped at
  `MAX_PET_PERIOD_SECONDS` (30 s) and **not** systemd's `WatchdogSec/2` convention: that convention
  assumes unconditional petting, so with a *conditional* pet a single unlucky health check would push the
  gap between two pets right to the timeout. Petting far more often than required means a fault has to
  persist for the whole `WatchdogSec` to reboot — the supervisor gets to recover first, systemd is the
  last resort. Keep `WatchdogSec` (unit drop-in, 600 s) **larger** than
  `PuppetMaster.MAX_SILENCE_SECONDS` (300 s) for the same reason.
- `components/*_handler.py` — the long-running coroutines. `timer_cyclic`, `climate_control` and (through
  `DailyTimer.refresh_from_config()`) `timer_daily` call `shared_config().refresh()` each iteration, which
  is how web-UI config edits and hand edits of `param.json` take effect without a restart. **Never go back
  to `AppConfig.load()` in a control loop**: that is a disk read plus a full validation on every tick, and
  it forces each caller to re-invent its own `try/except` fallback — there were three different variants
  of it before the store. The fallback now lives in one place. Because the store mutates the shared
  instance in place, objects holding a config reference (motor, heater, server, `SystemStatus`) see those
  edits with no refresh of their own.
  `timer_cyclic` guards a zero-length sequential cycle (`on + off == 0`) by sleeping instead of chaining
  two `sleep(0)` — a busy loop at full CPU. That guard is in the loop and not in a validator on purpose:
  refusing the config would be a dead boot, and `Cyclic2_Settings` already carries `0/0` harmlessly.
- `components/climate_policy.py` + `components/climate_control.py` — the **thermal arbiter**. Heater and
  ventilation regulate the same temperature, so they are one supervised job, not two. All the logic lives
  in the **pure** `decide(settings, inputs, memory)` of `climate_policy` (no GPIO, no disk, no implicit
  clock — time enters through `ClimateInputs`, state through a frozen `ClimateMemory`); `climate_control`
  only reads T/RH once, resynchronises on the **real** output states, applies, verifies the write and
  persists the winter budgets. Never put a regulation rule in the coroutine: a rule outside the pure
  function cannot be replayed or reviewed. Invariants that must survive any refactor:
  * **dead zone by construction** — `vent_threshold = max(target_temp_max, target_temp_min +
    hysteresis_offset + vent_deadband)`, so no temperature can have heater and extractor on at once. A
    *blocking* validator was deliberately rejected: a refused config is a dead boot. The raised threshold
    is logged (deduplicated on its value — it is an adjustment, **not** a failure, so no `StateLogger`)
    and published in `/api/v1/state`. **Exception**: with the heater disabled the threshold stays at
    `target_temp_max` — there are no two organs to separate, and raising it would only let the
    greenhouse run a degree hotter for nothing;
  * temperature outside `]-20 ; 60[` counts as a missed read; `MAX_CONSECUTIVE_SENSOR_FAILURES` missed
    reads force the heater OFF with a persistent alarm (`get_climate_alarm()`, aliased as the historical
    `get_heater_alarm()`) and the motor to `sensor_fallback_speed` — the named `REPLI_CAPTEUR` policy;
  * an uninterrupted ON cannot exceed `MAX_CONTINUOUS_ON_MINUTES`, followed by
    `FORCED_OFF_COOLDOWN_MINUTES` of forced rest. All durations use `time.monotonic()`, never
    `datetime.now()` — an NTP jump must not extend a heating window;
  * winter renewal and dehumidification draw from **two distinct bounded hourly budgets**, counted in
    really elapsed minutes; below `absolute_floor_temp` nothing ventilates at all. Humidity can no longer
    short-circuit the quota;
  * ventilation steps have a state hysteresis (distinct release threshold) and a `min_dwell_seconds` hold;
    `clamp_speed` never turns a 0 into `min_speed` — a stop order stays a stop.
- `utils/state_store.py` — `param/runtime_state.json` (atomic, throttled to one write per minute), the
  regulation state that must **not** restart from zero: winter budgets, and the cyclic timers' sequential
  phase. A missing, unreadable or expired record is ignored — a resume can only shorten a cycle, never
  invent one. `save(..., strict=True)` **re-raises** the `OSError` and writes immediately; the swallowing
  default stays the one for budgets, which must never be able to kill regulation.
- `utils/overrides.py` — operator **force-OFF** overrides. An override is a **policy input, never a GPIO
  access**: nothing in this module can switch anything on, it only ever cuts. Targets are the
  `EQUIPMENT_IDS` whitelist — never a pin number or a free-form name. Two clocks, expiry at the **first**
  of the two: `expires_epoch` is the only displayable deadline and the only one that survives a reboot,
  `deadline_mono` is never persisted so an NTP jump can shorten an override but never extend it. Caps are
  deliberately asymmetric — 4 h for `heater` and `motor`, 24 h elsewhere — because the **motor force-OFF
  is absolute**: it outranks `REPLI_CAPTEUR` *and* `SECURITE_HAUTE` (operator ruling, 28/08/2026), so the
  only remaining protection against a cooking greenhouse is how short the cut is, plus the
  `motor_lockout_overheat` alarm raised by the policy. `create()` persists with `strict=True` before
  returning (an accepted-but-unwritten override would vanish at the next reboot with nobody having lifted
  it, hence HTTP 500); `cancel()` applies in memory first and only then persists — never restore a cut the
  operator just lifted. The operator's free-text reason is **never interpolated into a log line**: it
  would travel into the `/console` SSE stream and its download. On boot an override resumed before the
  clock is trustworthy has its deadline re-based on the cap and is flagged "à confirmer".
- `model/` — thin GPIO/state wrappers: `Component` (one relay pin), `Motor` (4 pins = 4 speeds),
  `DailyTimer`/`CyclicTimer` (schedule logic), `SensorStats` (min/max, persisted to
  `param/sensor_stats.json`).
- `controllers/SensorController.py` — owns the sensor hardware and a single-thread executor so blocking
  reads never freeze asyncio and never run concurrently. It instantiates only the handlers enabled in
  `Sensor_State`, maintains the shared timestamped snapshot consumed by HTTP and InfluxDB, and exposes
  fresh cached reads to the motor/heater loops. `controllers/sensor_catalog.py` is the canonical mapping
  for keys, activation flags, UI labels/units and InfluxDB measurements.
- `controllers/sensor_quality.py` — pure calibration/quality policy. The catalog also owns hard plausible
  bounds, freshness and freeze defaults; `Sensor_Quality` only narrows/overrides them. Snapshots separate
  `raw_value`, offset-adjusted `observed_value` and trusted `value`, with statuses `normal`, `degraded`,
  `absent`, `inconsistent`. Quality starts in `observe`; switching to `enforce` requires the literal UI
  confirmation `ARMER`, and an already-confirmed BME280T inconsistency must enter `REPLI_CAPTEUR`
  immediately. Never restore DS18B20 discovery-order addressing: calibration is bound to stable 1-Wire
  IDs. Freeze/counter state is persisted, but monotonic timestamps are deliberately not restored.
  **Freeze detection is an anchored dead band, never a per-sample delta.** `freeze_epsilon` is compared
  against `freeze_anchor_value` — the value at the last *real* change — so the verdict is invariant under
  the read cadence. Comparing against the previous sample measures a *slope*: at 10 s the same healthy
  BME280 was declared frozen while at 60 s it was not, and a genuine 0.32 °C drift spread over 1 h 51
  counted as frozen (production, 30/08/2026). An `epsilon` **above the sensor's noise floor** makes the
  diagnostic blind — a calm night and a dead I²C register become the same observation, and no threshold
  can separate two identical observations — hence `freeze_epsilon = 0.0` (strict identity, i.e. liveness
  of the acquisition chain) for BME280 and DS18B20. Re-arming counts three *real* variations, not three
  *consecutive* ones: resetting the counter on a calm sample turns the debounce into a ratchet that never
  releases. Freeze answers "is acquisition alive?", never "is the value right?" — that one belongs to
  `redundancy_groups` and calibration.
- `sensor_handlers/` wrap the vendored drivers in `lib/sensors/`. A failed read returns `None` rather than
  raising — every consumer must handle `None`. **Drivers and handlers must not round**: full precision has
  to reach the quality policy, whose freeze test lives on the acquisition noise. Rounding belongs to
  presentation, which uses the catalog's `decimals` (`mesure` Jinja filter, `toFixed` in the JS).
- `network/web/server.py` — aiohttp server with explicit routes and exact static-asset allow-list. It
  enforces a 64 KiB body limit, a persisted CSRF token (see below), same-origin POSTs, private/LAN `Host` validation,
  security headers and no-store on dynamic responses. `/conf/{section}` builds and validates a complete
  candidate `AppConfig` before the atomic save; blank secret fields mean “unchanged”, and GPIO is read-only.
  Errors ≥400 render `templates/error.html` for a browser and stay plain text for anything else —
  redirects are `HTTPException`s too and must never go through that path. That page offers at most
  three links, and `_error_response()` decides: « Revenir à la page précédente » only when the
  `Referer` is **same-origin and validated** (same scheme, same host, host itself in the LAN
  allow-list, no credentials) and re-emitted **path-only**, never `//…`; « Réessayer » only for a
  GET whose status is 500/502/503/504 — never after a POST, and never on a 4xx, which retrying
  cannot fix; the dashboard, always. Never derive a link from a raw request header here.
  `/app` is a plain read page (no CSRF, no secret), served like the other read pages. The CSRF token comes from
  `utils/csrf.py` and is **persisted** in `param/.csrf_token` (0600, gitignored) so a `systemctl restart`
  does not 403 every page left open; a fresh token per process was pure friction, not extra safety.
- `network/web/pages.py` — Jinja2 with autoescape; asset URLs carry a content hash so a redeployed
  CSS/JS file is not served from cache. Every page must stay inline-script/style free: the CSP has
  no `unsafe-inline`. Two display filters share **one** rounding rule: `nombre` returns a
  `Markup('<span class="num">…</span>')` — the tabular-figures class is posed by the filter itself,
  value and unit still escaped — and `nombre_texte` the exact same formatting **bare**, for the
  three contexts that render no markup (`<option>`, an attribute, `title=`). Both delegate to the
  pure `model/nombre.nombre_texte` — the **single** server-side French rounding rule, also used by
  the presentation sentences computed in models (`chart_summary`, assistance hints); never write a
  `:.2f` for display again. `mesure` stays the dashboard-side rounding, kept identical to the JS
  `toFixed`. Browser side, `formatNombre` (`culture_analysis.js`, `history.js`) is the aligned
  replica; `culture_cycles.js` and `culture_solutions.js` delegate to it and only keep the same
  `toLocaleString` options as a fallback so their charts still draw without the explorer asset.
  Stored values, numeric API fields and CSV exports stay unrounded.
- `network/web/templates/macros/ui.html` — the eight shared presentation macros
  (`compact_header`, `empty_state`, `alarm_summary`, `equipment_row`, `journal_entry`,
  `field_group`, `chart_detail`, `network_state`). **Presentation only**: no business rule, no
  implicit command. An action is a `{href, label}` pair rendered as a GET **link**; anything that
  POSTs belongs in the `caller` block the macro yields to. Optional keys are read through
  `is defined` guards so a caller may omit them. A page reuses these instead of re-inventing a
  header, an empty state or a journal line; changing a signature is a repo-wide change.
- `network/web/static/service-worker.js` + `network/web/static/js/pwa.js` — PWA locale **à
  fraîcheur dominante**. Le service worker ne met jamais en cache `/api/`, `/health/`, `/status`,
  le SSE ni une méthode mutante ; il conserve seulement les assets hachés et les dernières pages de
  lecture. Les snapshots IndexedDB ne sont lus qu'après un échec réseau, gardent la bannière
  « HORS LIGNE — données datant de… — lecture seule » et ne déclenchent jamais de notification.
  Aucune commande n'est mise en attente ou rejouée. HTTPS `:443` est un second point d'écoute
  optionnel ; tout échec TLS laisse HTTP `:8123` et le contrôle actifs. Les notifications sont
  locales, opt-in, limitées aux alarmes de contrôle/critiques et sans garantie PWA fermée ; le
  texte affiché à une permission refusée vient de la fonction **pure** `notificationDenialHelp`
  (agent utilisateur en entrée, aucun accès au DOM ni à l'horloge), jamais d'une chaîne de
  ternaires enfouie dans un rendu.
  Le worker **n'active plus une version de lui-même** : plus de `skipWaiting()` spontané, une
  version installée attend le message `{type:"activer"}` que seul le bouton « Mettre à jour » de
  la bannière de `base.html` envoie (`{type:"version"}` sert seulement à afficher la version
  active). Sur `controllerchange`, la page ne recharge **que** si `window.PhytoForms.isDirty()`
  est faux ; sinon elle annonce « La mise à jour s'appliquera à la prochaine ouverture ». Les
  anciens caches ne sont purgés qu'à l'activation, **après** `clients.claim()` : une page ouverte,
  y compris hors ligne, continue de vivre sur les caches de sa propre version. Budgets d'attente
  explicites (`fetchWithBudget`) : 8 s pour une navigation de page, 15 s pour le précache et le
  préchauffage de `/`, `/history`, `/alarms`, `/app`. Le précache est **parallèle** et reste
  atomique (`Promise.all` rejette au premier échec, donc pas de version incomplète). Le repli sur
  une copie datée n'a lieu que sur un **échec de transport** : une réponse HTTP du contrôleur est
  toujours servie telle quelle, et un **5xx n'est ni mis en cache ni remplacé par une copie**.
  Côté `pwa.js`, deux attributs de gabarit pilotent le verrou hors ligne : `data-offline-local`
  exempte les seuls outils de **lecture locale** (recherche dans les lignes déjà chargées,
  explorateur de graphique, sélection de série, onglets de vue) — jamais un envoi, jamais un
  `[type=submit]` ; `data-offline-filter` déclare un **filtre serveur**, qui reçoit alors la note
  « Filtre indisponible hors ligne : seules les données conservées sont affichées », posée à côté
  du formulaire et non dedans. À défaut de l'attribut, le discriminant est « formulaire GET sans
  `data-form-key` », la clé que pose le socle du carnet sur les formulaires qu'il intercepte.
  L'inventaire des copies conservées est un **fragment partagé**, `templates/offline_index.html`
  (section `#copies`, `[data-culture-offline-index]`, `[data-offline-latest]`), inclus par `/app`,
  `/offline`, `/cultures/cycles` et `/cultures/journal` : une page qui veut l'afficher l'inclut,
  elle ne le recopie pas. `/app` (`templates/pwa.html`) est la page de cet appareil — connexion,
  installation, notifications, version active du worker, copies — et ne porte **pas** de second
  bouton « Mettre à jour » : la bannière de `base.html` en est l'unique propriétaire.
- `network/web/influx_handler.py` — InfluxDB **v1** line protocol over async aiohttp with a bounded timeout.
  It consumes the shared sensor snapshot and never performs or duplicates a hardware read.
- `controllers/OperatorService.py` + `utils/alarm_manager.py` + `utils/operator_history.py` — couche
  opérateur **auxiliaire** (jalon 2). Elle relit les snapshots existants et les GPIO, détecte les
  alarmes idempotentes, puis confie tous les accès SQLite à un unique thread dédié. La base locale
  conserve 72 h d'échantillons d'une minute et 30 jours d'occurrences résolues ; une panne ou une
  corruption de cet historique alarme mais ne dégrade jamais `control_healthy()` ni le watchdog.
  `/alarms`, `/history`, `/api/v1/alarms` et `/api/v1/history?hours=24|48|72` exposent ce diagnostic. Ne faites
  aucune lecture matérielle supplémentaire pour l'historique et ne déplacez jamais SQLite dans une
  boucle de contrôle ou dans l'event loop. Les annotations de `/actions/history/notes` sont des événements
  auxiliaires sans effet sur la régulation ; leur texte ne doit jamais être recopié dans les logs.

## Carnet de cultures (schéma 4)

`model/culture*.py` porte les règles **pures** ; `utils/culture_store.py` reste le seul écrivain de
`param/cultures.sqlite3`, dans un unique thread auxiliaire borné, et n'est plus qu'un assemblage de
mixins par domaine : `culture_solution_store`, `culture_cycle_store`, `culture_media_store`,
`culture_checklist_store` (vérifications), `culture_targets_store` (plages cibles pH/EC),
`culture_light_store` (repères d'éclairage), `culture_equipment_store` (affectations datées) et
`culture_journal_store` (journal transversal et observations d'espace). Un domaine = un mixin + son
modèle pur + sa vue ; ne pas rapatrier de règle métier dans `culture_store.py`.
`network/web/cultures.py` monte les pages `/cultures`, `/cultures/solutions`, `/cultures/cycles`,
`/cultures/targets`, `/cultures/light`, `/cultures/equipment`, `/cultures/journal` et leurs API
`/api/v1/cultures/…`. Chaque page du carnet inclut le fragment partagé
`templates/culture_navigation.html` en lui passant `culture_section` (`''`, `solutions`, `cycles`,
`targets`, `light`, `equipment`, `journal`) : c'est lui qui rend les sept rubriques, `aria-current`,
le contexte conservé (`detail`, `selected`, `culture_subjects`, `filters.target`) et le lien
« Vue globale », qui reste toujours dans la rubrique courante — et, pour la rubrique
« Solutions et relevés », la **vue courante** : la navigation du carnet conserve `view` au même
titre que `detail` et `selected`, sans quoi quitter puis revenir sur la rubrique repartait au
défaut et perdait l'onglet choisi. Une nouvelle page ne réinvente pas sa navigation.
`/cultures/solutions` et `/cultures/cycles` servent toutes leurs vues sur la **même** route, par
`?view=` (`SOLUTION_VIEWS = saisir|releves|analyser` dans `network/web/cultures.py`,
`CYCLE_VIEWS = faire|comparer` dans `network/web/culture_cycles.py`) : aucune route nouvelle,
tous les panneaux rendus, ceux qui ne sont pas la vue courante marqués `hidden`. Ces « onglets »
sont des **liens** qui rechargent la page : `aria-current="page"` et rien d'autre — jamais
`role="tablist"`/`role="tab"`/`aria-selected` sur un `<a href>`, qui promettraient un panneau
échangé sur place et une navigation aux flèches. Une valeur inconnue retombe sur le défaut plutôt
que de refuser la page, et rien n'est persisté : `view` n'est qu'un choix d'affichage.
Un lien du journal vers une fiche ou vers un relevé porte `retour=` — l'adresse de la vue courante
du journal, filtres **normalisés** et `offset` compris, construite par `JournalViews.return_url()`
(`network/web/culture_journal.py`) et non dans un gabarit, où l'auto-échappement produisait des
`&amp;` dans le paramètre. `CultureViews.page` ne l'accepte que s'il désigne une adresse **locale
du carnet** (préfixe `/cultures`, ni `//` initial ni `\`) : sans schéma ni hôte possibles, la
fiche ne peut pas offrir un lien sortant choisi par l'appelant. Un `retour` refusé est ignoré,
jamais une erreur — le lien de retour existe toujours, simplement non contextualisé.
La cascade des plages cibles est rendue par la seule opération de magasin **en lecture seule**
`target_resolution` (`utils/culture_targets_store.py`), qui lit les associations d'alimentation
réellement déclarées à la date consultée (`_feeding_at`, dans `utils/culture_solution_store.py`,
domaine propriétaire des tables) puis appelle la règle **pure** `resolve_targets` sans la
dupliquer ; la vue `network/web/culture_targets.py` n'y ajoute que le libellé court de la source
(« cible directe », « sujet alimenté », « réservoir »). Ne jamais rejouer cette cascade dans un
gabarit ni en JavaScript. Tout y est **déclaratif** : jamais un accès GPIO, une modification de
`param.json`, un override, un changement du watchdog ni une nouvelle acquisition capteur, et jamais
de SQLite dans l'event loop (`CultureStore.call(...)`). Une erreur, une corruption ou un schéma
inconnu conserve la base et rend le carnet indisponible **sans** dégrader `control_healthy()` ni le
watchdog (`gates_watchdog=False`). Le carnet garde origines multi-mères, révisions et clés
d'idempotence (`request_id` + empreinte) sans purge de 72 h ; les mutations revalident tout le
parcours et l'occupation exclusive de l'espace 2 avant commit ; les absences ne deviennent jamais
des zéros.

Schémas : 2 = solutions structurées (périodes, recettes versionnées, préparation figée, arrosages
multi-mères à volume total unique, alimentation coupée à la récolte) ; 3 = photos dans
`param/culture_media/`, rappels versionnés, vérifications et agrégats horaires durables
(`CultureService`, snapshots existants uniquement) ; **4 = livré en une seule fois avant les lots
D à H**, son DDL figé dans `utils/culture_schema_v4.py` — ne plus le retoucher, un besoin nouveau
est un schéma 5. Chaque version traversée écrit sa sauvegarde exclusive `.before-vN.sqlite3` et
refuse d'écraser une sauvegarde existante. La migration 4 met `PRAGMA foreign_keys=OFF` **hors**
transaction — indispensable pour recréer une table enfant, sans effet à l'intérieur d'une
transaction —, exécute le DDL dans un `BEGIN IMMEDIATE`, contrôle `PRAGMA foreign_key_check`
**dans** la transaction, puis rétablit les clés dans un `finally` ; toute erreur laisse la base
intacte en version 3 avec sa sauvegarde, qui bloque volontairement une seconde tentative.

Invariants ajoutés par les lots D à H, à préserver :

- le **conflit de vérification** est dérivé à la lecture (rejeu de `project()` comparé au contexte
  enregistré à la saisie), jamais stocké : une copie serait une seconde vérité à resynchroniser
  après chaque correction rétrospective ;
- les **plages cibles** se résolvent mesure par mesure, dans l'ordre strict cible directe → sujet
  alimenté → réservoir, **sans fusion** entre sources et **sans rétroactivité** ; `stage` reste
  informatif, pour qu'une correction de stade ne change pas l'applicabilité d'une plage passée ;
- la résolution d'un **contexte d'équipement** suit affectation datée → `equipment_context` copié à
  la saisie → inconnu, et ne retombe **jamais** sur le catalogue courant : un nom d'aujourd'hui
  n'est pas une association d'hier ;
- le **journal** est la vue SQL `culture_journal`, une ligne par opération (cibles jointes à la
  demande, un arrosage partagé compte pour 1) ; elle est exclue de l'export, ses trois sources y
  figurant déjà ;
- une **observation d'espace** vise l'espace explicitement : aucune fausse plante n'est créée pour
  porter la note, et la trace n'entre pas dans l'historique opérateur purgé à 72 h ;
- une **photo** a un propriétaire exclusif (`owner_kind`, deux paires de clés étrangères et des
  `CHECK`) : jamais à la fois un événement et une observation d'espace ;
- la **synthèse climatique** est agrégée en SQL sur des seaux alignés UTC
  (`bucket = hour - hour % pas`, invariants au changement d'heure), avec des moyennes pondérées
  `SUM(total) / SUM(valid_count)` — jamais une moyenne de moyennes horaires ; une période sans
  agrégat est une lacune, pas un zéro ;
- le sélecteur d'**interventions** reste une fenêtre bornée de 200, enrichie des interventions déjà
  liées aux relevés affichés, avec recherche paginée : ne jamais charger tout le carnet dans un
  `select` ;
- le **backfill** n'accepte que des étapes strictement antérieures au début du stade courant.

Conventions d'interface des lots UI 1 et 2 (aucune route ni persistance nouvelle) :
`static/js/culture_forms.js` est le **socle unique** des formulaires du carnet — `register`
(identifiants stables, rejouable après un clonage d'origines), `submitJson` / `submitBinary`
(CSRF, garde hors ligne, clé d'idempotence conservée tant que la saisie ne change pas) et
`showError` (résumé en tête + message au champ) ; un formulaire nouveau l'adopte au lieu de refaire
sa gestion d'erreur. La clé d'idempotence est mémorisée **par destination** (`requestKey(form,
channel, signature)`), pas seulement par formulaire : un même formulaire porte deux actes
successifs et distincts — l'observation, puis sa photo — et une mémoire unique laissait le second
effacer la clé du premier, donc créer une seconde note si la première réponse s'était perdue.
La passe « photos » y ajoute deux conventions : `register` pose lui-même
l'**aperçu local** (`data-culture-photo-preview`, `URL.createObjectURL` révoquée au changement, au
`reset` et au `pagehide` hors cache arrière/avant) sur tout champ fichier d'images — aucune page ne
le réécrit, et l'aperçu n'émet rien. `attachPhotoChoices` pose de son côté les deux boutons
« Prendre une photo » / « Choisir une image existante » (`.culture-photo-choices`, après le
`<label>`) : c'est **le seul** endroit où `capture="environment"` est posé, et il est retiré par
l'autre bouton — aucun gabarit ne doit réintroduire l'attribut, qui interdisait la photothèque, et
`accept="image/*"` reste le repli sans JavaScript. Les deux boutons visent le même champ, donc la
même mutation et la même clé d'idempotence : « Reprendre la photo » ne peut pas faire de doublon.
Tout y est indexé par **contrôle**, jamais par formulaire :
deux champs photo d'un même formulaire partageraient sinon une URL d'objet et une zone. Et
`submitBinary` passe par `sendUpload` (`XMLHttpRequest`, pour la seule progression d'envoi), qui
rend **exactement** les quatre formes de retour du contrat — hors ligne, occupé, réponse HTTP,
réseau/délai — que `send` produit aussi, celui-ci y ajoutant seulement le message d'une exception
inattendue ; il partage ses gardes via `withGuards`, et **crée la barre à l'intérieur** de
celles-ci, sans quoi un envoi refusé en fabriquerait une seconde. Son
`Content-Type: application/octet-stream` explicite est vital (sans lui, XHR déduit `image/png` et
le serveur répond 415), et `img-src` autorise `blob:` pour cet aperçu seul. La `<progress>` vit
dans l'`<output role="status">` — région **atomique** — où elle n'est ajoutée qu'une fois, son
avancement ne passant que par `value`/`aria-valuetext` ; le pourcentage visible est posé hors de la
région, sans quoi chaque pour cent serait réannoncé. Aucune reprise, aucune file, aucun rejeu
d'envoi. Un refus se rattache au contrôle par son attribut `name`, jamais par un `id`
deviné : `CultureError(message, field, index)`, `index` étant le rang 0-based dans un groupe
répété ; le serveur n'émet **qu'une erreur par requête** (le socle JS, lui, en affiche N), et un
503 n'en nomme aucune. Les règles d'action sont **pures** dans `model/culture.py` —
`allowed_actions`, `stage_options`, `first_stage`, `creation_stages`, `fiche_actions` : aucune
condition d'action en Jinja ou en JS, et le test d'équivalence `tests/test_culture_actions.py`
s'adapte au nouveau balisage, il ne se supprime pas. Le bloc `agenda` est calculé dans `_overview`
**sans projection neuve**, borné (`TODAY_JOURNAL`, `upcoming_count` au lieu d'une liste), et
réutilise `overview["today"]`, l'unique date du carnet. Le retour après enregistrement passe par
les ancres `event-{id}` / `reminder-{id}` en `tabindex="-1"` (et `data-cycle-return="agenda"` pour
un rappel actionné depuis l'accueil) : l'élément focalisé **est** la confirmation, pas un
`aria-live` de plus.

Lot UI 3 : `model/culture_assistance.py` porte les suggestions et le rapprochement de
relevés ; `culture_assistance_store` expose des aides éphémères (4 maximum, validité de
30 s) et la prévalidation. Les aides sont redemandées à l'ouverture et au retour sur la
page, jamais plus d'une fois par 30 s — **aucun sondage périodique** —, et une fiche dont
la version est inchangée reçoit `{"unchanged": true}` sans qu'aucune projection ne soit
refaite. La prévalidation n'est **pas** sur le chemin nominal d'enregistrement : elle ne
part que sur « Vérifier avant d'enregistrer » et au premier envoi d'un relevé de solution,
une fois par empreinte de saisie ; un échec autre qu'un refus n'empêche pas d'enregistrer.
Celle-ci réutilise les mutations culture/solution dans une transaction
**annulée même au succès**, sans clé ni version persistée ; la mutation finale revalide
normalement. Une ressemblance (fenêtre de 200 relevés, 3 liens maximum) n'est jamais une
interdiction métier ; le rejeu d'une clé déjà acceptée contourne cette aide, pas la
vérification de son empreinte. Aucune suggestion n'est conservée hors ligne, aucune
mesure n'est préremplie et aucune vérification n'est cochée automatiquement.

Lot UI 4 : `network/web/static/js/culture_analysis.js` est l'**unique** explorateur de
graphique du carnet ; son contrat avec les scripts hôtes est
`chart(svg, rows, label, columns) → refresh(positions)`, où `rows[i] = {text, cells}` et
`positions[i] = {x, y}` **dans le repère du `viewBox`**, calculé par l'hôte : l'explorateur
ne mesure jamais le DOM point par point. Une figure nouvelle adopte ce contrat au lieu de
refaire son curseur. `model/culture_text.search_key` (NFD, marques retirées, casse pliée,
sans locale) est la **seule** définition de l'équivalence de recherche côté serveur ; sa
réplique JavaScript dans `culture_analysis.js` doit rester alignée, sans quoi le filtre du
navigateur masquerait un choix que le serveur a retenu.

Ne pas copier naïvement un SQLite vivant en WAL : l'export utilise l'API de sauvegarde ; le ZIP
réunit base, médias et manifeste SHA-256, et `scripts/restore-cultures.py [--bundle]` ne publie
jamais que vers une copie isolée nouvelle. Les photos sont réencodées sans métadonnées et bornées
en taille, dimensions, nombre et espace disque. La PWA garde au plus 20 pages du carnet et 40 photos
consultées, datées, relues après **échec réseau** seulement ; aucun rappel ne déclenche de
notification système et aucune mutation n'est mise en attente ou rejouée.
Une **seconde** base IndexedDB, `phyto-culture-drafts`, conserve les **brouillons** des formulaires
du carnet explicitement inscrits — `data-culture-draft` sur le formulaire, `data-draft-field` sur
chaque champ, et `[data-culture-draft-banner="<clé>"]` dans le gabarit pour poser la bannière
**hors** du `<details>` qui replie le formulaire, sans quoi un brouillon en attente resterait
invisible. Le périmètre est fermé et vérifié à l'inscription : texte, dates et sélections
seulement, jamais une mesure (`ph`, `ec`, `volume`, `temperature`), une confirmation, un secret
(`data-secret`, `password`, `token`, `csrf`…), une photo, ni rien hors `/cultures`. C'est du texte
d'opérateur **en clair sur l'appareil** : expiration 24 h, purge une fois par page à l'ouverture de
la base, plafond de 50 brouillons (le plus ancien évincé). La restauration est **explicite** —
bouton « Restaurer le brouillon », après revalidation de la cible, de la version de la fiche, de
l'expiration et de chaque valeur (option toujours présente et non désactivée, `checkValidity`) — et
elle **régénère la clé d'idempotence** au lieu de rejouer l'ancienne. Aucune soumission automatique,
aucune file, aucun rejeu : l'invariant « aucune mutation n'est mise en attente ou rejouée » reste
entier — un brouillon est une saisie **non envoyée**, pas une commande différée. La fixture Playwright du
carnet démarre **un serveur par test** : l'espace 2 est exclusif et une occupation ouverte n'a pas
de fin, donc deux specs ne peuvent pas partager une base. Les tests navigateur mutateurs sont
désactivés sur toute cible `PHYTO_UI_BASE_URL` externe ; leur base locale est temporaire.
Guide et contrat : `docs/operations/cultures.md`, `docs/reference/cultures-api.md`.

## GPIO conventions — read before touching any pin code

Two opposite polarities coexist and mixing them can close relays on high voltage:

- **`Component` (lights, cyclic outputs, heater) is active-LOW**: `set_state(1)` → `GPIO.LOW`. Safe/OFF
  state is HIGH, which is why boot and `cleanup_gpio()` drive these pins HIGH. Any ON → wait → OFF
  sequence **must** go through `Component.energized()` (a context manager whose `finally` cuts the output
  on exception, on task cancellation and on normal exit, then verifies the pin actually went back and
  raises a CRITICAL alarm if not). Writing `set_state(1)` / `await` / `set_state(0)` by hand leaves the
  relay stuck ON the day the wait is interrupted — that is a flooded greenhouse.
- **`Motor` (4 speed relays) is active-HIGH**: safe/OFF state is all four pins LOW, and exactly one pin
  goes HIGH for speeds 1–4. Motor pins are deliberately excluded from `GENERIC_SAFE_PINS` in `main.py`.

`main.py` installs SIGINT/SIGTERM/SIGHUP handlers plus `atexit` hooks so both polarities are restored to
their safe state on any exit path. Preserve that guarantee in any change to shutdown or pin setup.
`cleanup_gpio()` is idempotent (three call paths converge on one run).

**Never call `GPIO.cleanup()`.** It puts every pin back to *input* with its default pull, which for both
polarities is the **command** level: GPIO 18/22/23/27 fall to the pull-down (`LOW` = active for
active-LOW `Component`s, heater included) and the motor pins rise to the pull-up. The safe state must be
**terminal**: pins stay driven outputs until power is cut. Verified live — after `systemctl stop phyto`,
all nine pins still read `op` with generics `hi` and motor `lo`. Releasing the pins only becomes
acceptable if external resistors guarantee the safe state (pull-up on active-LOW inputs, pull-down on
motor inputs) — a **hardware** dependency, not a software option.

⚠️ The fixed `gpio=N=op,dh` block that lived in the old root file `notes` (deleted on 11/09/2026) was
**wrong and dangerous**: `dh` is the safe level of the active-LOW outputs but the *command* level of the
active-HIGH motor, so it closed a speed relay at power-on. Never reintroduce such a hand-written list.
Under Bookworm the boot partition is `/boot/firmware/config.txt` and `/boot/config.txt` is ignored, so
nothing protects the power-on window today. Generating those lines from the validated pin registry
(`op,dh` for active-LOW, `op,dl` for the motor) is Phase 1 of the audit (roadmap, lot 3).

## Run modes

`PHYTO_RUN_MODE=service` (systemd) is still read by `main.py`, but the server no longer forks anything:
`/console` streams the **current** process's logs through `utils/log_stream.ConsoleStream`, a logging
handler plugged onto the `phyto` logger (deque of the last 1000 lines + SSE queues). The page uses a
plain native renderer (xterm.js was dropped in `bfc0978`); `network/web/static/` holds local CSS, JS,
font and favicon assets, so the page works without Internet. The hardware watchdog now lives in `utils/watchdog.py` and
is **enabled by default**, with `PHYTO_HW_WATCHDOG=0` as the explicit opt-out.

## Known rough edges (don't mistake these for your own breakage)

- `initial_setup_tool.py` is a straight carry-over from the ESP32 version: it reads/writes `param.json`
  relative to the current directory, not `param/param.json`. Run it from `param/` or copy the result.
- `param/param.json` holds Wi-Fi and InfluxDB credentials in clear text and is deliberately **ignored by
  Git**. Never force-add it or paste its values into logs, issues or commits. The historically versioned
  credentials must still be considered compromised until rotated.
- **On the Pi, never run `git checkout <branch>` or `git pull`** — always `scripts/deploy.sh`, which
  leaves HEAD detached on the target. A branch checkout is what destroyed the live configuration on
  08/09/2026. Since `utils/runtime_paths.py` the data itself is out of reach, but the Pi must stay the
  read-only checkout the whole deployment script assumes.
- The HTTP server has **no authentication** — a deliberate choice, 8123 is LAN-only. Destructive actions
  are dedicated POST routes protected by CSRF/origin checks and an explicit browser confirmation. Never
  move one behind GET: a prefetch or an `<img src>` on any LAN page could fire it. Hostnames outside the
  local/private allow-list require `PHYTO_ALLOWED_HOSTS`.

## Style

Code, comments, log messages and console output are in French (see `utils/pretty_console.py` helpers:
`debug`, `info`, `action`, `success`, `warning`, `error`, `critical`, `clock`, `title`, `box`). Match
that. Never use bare `print` — `pretty_console` is the single logging façade (console **and**
`logs/phyto.log`).

## Logging

- `utils/pretty_console.py` is the only entry point. Level mapping: `debug`/`action`/`clock` → DEBUG
  (running noise), `info`/`success` → INFO (events), `warning` → WARNING, `error`/`exception` → ERROR.
  One filter gates console *and* file.
- Every call takes an optional `name=` (`name="motor"` → logger `phyto.motor`, printed as `[phyto.motor]`
  in the file). Use it instead of manual `[MOTOR]` prefixes.
- Level and retention come from `Log_Settings` in `param/param.json` (`level`, `retention_days`),
  overridable by `PHYTO_LOG_LEVEL`; both are applied at boot in `main.py` and re-applied on POST `/conf`.
- File rotation: `TimedRotatingFileHandler` at midnight, archives gzipped, `retention_days` kept.
- **Log transitions, not states.** `Component.set_state()`/`Motor._set_pin()` only log a real change;
  periodic loops log their ticks at DEBUG and the event (ON/OFF, speed change) at INFO.
- Repeated failures (Influx push, sensor reads, `param.json` load, stats dump) go through
  `utils/log_dedup.StateLogger`: one ERROR/WARNING on entering failure, one INFO on recovery.
- InfluxDB credentials never appear in a log line: they travel in aiohttp request parameters, and error
  messages only carry `host:port/db` plus the exception class.
