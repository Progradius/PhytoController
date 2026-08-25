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
docker build -t phyto . && docker run --privileged -p 8123:8123 phyto
```

Web UI: `http://<pi>:8123` — `/` dashboard with 5 s live refresh, `/conf` section-based config form,
`/console` (SSE log stream), `/api/v1/state` (versioned JSON), `/health/live`, `/health/ready` and the
legacy `/status`. `/monitor` redirects to the dashboard; reset/reboot/poweroff remain **POST-only**.

There is **no test suite and no linter configured** in this tree. Do not invent one; verify changes by
reading the code and, when hardware is involved, by describing the expected GPIO transitions.

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
- `param/config.py` — `AppConfig` (Pydantic v2, still using v1-style `@validator`). Single source of truth,
  loaded from and saved to `param/param.json`. JSON keys are PascalCase aliases (`DailyTimer1_Settings`,
  `GPIO_Settings`, …); Python field names are snake_case. `save()` re-serializes booleans back to the
  legacy `"enabled"`/`"disabled"` strings — any new boolean field needs the same treatment there. It
  writes through `utils/atomic_io.write_text_atomic()` (tmp + `fsync` + `os.replace`, existing file mode
  preserved) — **never** go back to `write_text()`: a control loop can re-read the file at any instant,
  and a power cut mid-write would leave a truncated `param.json`, i.e. a dead boot. `SensorStats._dump()`
  uses the same helper.
- `controllers/PuppetMaster.py` — the only orchestrator. It no longer creates tasks itself: it *registers*
  one supervised job per concern (2 daily timers, 2 cyclic timers, motor `temp_control`, `heat_control`,
  shared sensor snapshot, Influx push, HTTP server) with `utils/supervisor.TaskSupervisor`, starts the watchdog loop, calls
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
- `components/*_handler.py` — the long-running coroutines. Note that `timer_cyclic` and `timer_daily`
  **re-read `AppConfig.load()` from disk on every iteration**, which is how web-UI config edits take
  effect without a restart. Objects holding a config reference (motor, heater, server) do not see those
  edits unless explicitly refreshed. Every one of those reloads is wrapped in `try/except` with a
  **fallback to the last valid config** (`timer_cyclic`, `temp_control`, `timer_daily`): an unreadable
  `param.json` must never kill a control task, because nothing would ever drive that output again.
- `components/heater_control.py` — beyond the hysteresis, three safety guards that must survive any
  refactor: temperature outside `]-20 ; 60[` counts as a missed read; `MAX_CONSECUTIVE_SENSOR_FAILURES`
  missed reads force the heater OFF with a persistent alarm (`get_heater_alarm()`); an uninterrupted ON
  cannot exceed `MAX_CONTINUOUS_ON_MINUTES`, followed by `FORCED_OFF_COOLDOWN_MINUTES` of forced rest.
  All durations use `time.monotonic()`, never `datetime.now()` — an NTP jump must not extend a heating
  window.
- `model/` — thin GPIO/state wrappers: `Component` (one relay pin), `Motor` (4 pins = 4 speeds),
  `DailyTimer`/`CyclicTimer` (schedule logic), `SensorStats` (min/max, persisted to
  `param/sensor_stats.json`).
- `controllers/SensorController.py` — owns the sensor hardware and a single-thread executor so blocking
  reads never freeze asyncio and never run concurrently. It instantiates only the handlers enabled in
  `Sensor_State`, maintains the shared timestamped snapshot consumed by HTTP and InfluxDB, and exposes
  fresh cached reads to the motor/heater loops. `controllers/sensor_catalog.py` is the canonical mapping
  for keys, activation flags, UI labels/units and InfluxDB measurements.
- `sensor_handlers/` wrap the vendored drivers in `lib/sensors/`. A failed read returns `None` rather than
  raising — every consumer must handle `None`.
- `network/web/server.py` — aiohttp server with explicit routes and exact static-asset allow-list. It
  enforces a 64 KiB body limit, per-process CSRF token, same-origin POSTs, private/LAN `Host` validation,
  security headers and no-store on dynamic responses. `/conf/{section}` builds and validates a complete
  candidate `AppConfig` before the atomic save; blank secret fields mean “unchanged”, and GPIO is read-only.
  Errors ≥400 render `templates/error.html` for a browser and stay plain text for anything else —
  redirects are `HTTPException`s too and must never go through that path. The CSRF token comes from
  `utils/csrf.py` and is **persisted** in `param/.csrf_token` (0600, gitignored) so a `systemctl restart`
  does not 403 every page left open; a fresh token per process was pure friction, not extra safety.
- `network/web/pages.py` — Jinja2 with autoescape; asset URLs carry a content hash so a redeployed
  CSS/JS file is not served from cache. Every page must stay inline-script/style free: the CSP has
  no `unsafe-inline`.
- `network/web/influx_handler.py` — InfluxDB **v1** line protocol over async aiohttp with a bounded timeout.
  It consumes the shared sensor snapshot and never performs or duplicates a hardware read.

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

⚠️ The `gpio=N=op,dh` block in `notes` is **wrong and dangerous** — see the header added there. Under
Bookworm the boot partition is `/boot/firmware/config.txt` and `/boot/config.txt` is ignored, so nothing
protects the power-on window today. Generating those lines from `param.json` is Phase 1 of the audit.

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
- `param/param.json` holds Wi-Fi and InfluxDB credentials in clear text and **is tracked in git**. Never
  paste its values into logs, issues, or commits.
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
