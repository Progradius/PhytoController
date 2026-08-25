# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

Web UI: `http://<pi>:8123` — `/` state, `/conf` config form, `/monitor` live values, `/console` (SSE log
stream), `/status` (JSON).

There is **no test suite and no linter configured** in this tree. Do not invent one; verify changes by
reading the code and, when hardware is involved, by describing the expected GPIO transitions.

## Architecture

Boot sequence lives entirely in `main.py` (module-level, not in a `main()`): load config → force GPIO to
safe states → Wi-Fi → NTP → build components/timers/sensors → hand everything to `PuppetMaster`.

- `param/config.py` — `AppConfig` (Pydantic v2, still using v1-style `@validator`). Single source of truth,
  loaded from and saved to `param/param.json`. JSON keys are PascalCase aliases (`DailyTimer1_Settings`,
  `GPIO_Settings`, …); Python field names are snake_case. `save()` re-serializes booleans back to the
  legacy `"enabled"`/`"disabled"` strings — any new boolean field needs the same treatment there.
- `controllers/PuppetMaster.py` — the only orchestrator. Spawns one asyncio task per concern (2 daily
  timers, 2 cyclic timers, motor `temp_control`, `heat_control`, Influx push, HTTP server) then blocks
  forever. Its asyncio exception handler logs and keeps the loop alive on purpose — a crashing task must
  never take the greenhouse down.
- `components/*_handler.py` — the long-running coroutines. Note that `timer_cyclic` and `timer_daily`
  **re-read `AppConfig.load()` from disk on every iteration**, which is how web-UI config edits take
  effect without a restart. Objects holding a config reference (motor, heater, server) do not see those
  edits unless explicitly refreshed.
- `model/` — thin GPIO/state wrappers: `Component` (one relay pin), `Motor` (4 pins = 4 speeds),
  `DailyTimer`/`CyclicTimer` (schedule logic), `SensorStats` (min/max, persisted to
  `param/sensor_stats.json`).
- `controllers/SensorController.py` — opens `/dev/i2c-1` once, instantiates only the handlers enabled in
  `Sensor_State`, and exposes `get_sensor_value("BME280T")`-style string keys. `sensor_dict` groups those
  keys into InfluxDB *measurements* (`air`, `water`, `distance`, `lux`, `surface_temp`).
- `sensor_handlers/` wrap the vendored drivers in `lib/sensors/`. A failed read returns `None` rather than
  raising — every consumer must handle `None`.
- `network/web/server.py` — hand-rolled asyncio HTTP server (no framework): parses the request line by
  hand, routes with if/elif, renders `network/web/pages.py` templates. `_apply_conf_changes()` maps POSTed
  alias names (incl. dotted `DailyTimer1_Settings.enabled`) back onto the model, saves, then rebuilds the
  sensor stack and calls `influx_handler.reload_sensor_handler()`.
- `network/web/influx_handler.py` — InfluxDB **v1** line protocol over `requests` (blocking calls inside
  the event loop). Module-level globals initialized at import time via `reload_sensor_handler()`.

## GPIO conventions — read before touching any pin code

Two opposite polarities coexist and mixing them can close relays on high voltage:

- **`Component` (lights, cyclic outputs, heater) is active-LOW**: `set_state(1)` → `GPIO.LOW`. Safe/OFF
  state is HIGH, which is why boot and `cleanup_gpio()` drive these pins HIGH.
- **`Motor` (4 speed relays) is active-HIGH**: safe/OFF state is all four pins LOW, and exactly one pin
  goes HIGH for speeds 1–4. Motor pins are deliberately excluded from `GENERIC_SAFE_PINS` in `main.py`.

`main.py` installs SIGINT/SIGTERM/SIGHUP handlers plus `atexit` hooks so both polarities are restored to
their safe state on any exit path. Preserve that guarantee in any change to shutdown or pin setup.
`notes` documents the matching `/boot/config.txt` `gpio=N=op,dh` lines and the systemd watchdog setup.

## Run modes

`PHYTO_RUN_MODE=service` (systemd) is still read by `main.py`, but the server no longer forks anything:
`/console` streams the **current** process's logs through `utils/log_stream.ConsoleStream`, a logging
handler plugged onto the `phyto` logger (deque of the last 1000 lines + SSE queues). xterm.js is vendored
in `network/web/static/`, so the page works without Internet. `PHYTO_HW_WATCHDOG=0` (the default) skips
the `/dev/watchdog` thread.

## Known rough edges (don't mistake these for your own breakage)

- `SystemStatus.get_cyclic_period()` reads `config.cyclic1.period_minutes`, a field that no longer exists
  on `CyclicSettings` (it is `period_days` now) — it raises if called. `/status` works around it with
  `getattr`.
- `network/web/api_handler.py` (the `API` class) is dead code: nothing imports it. Routing is done inline
  in `server.py`.
- `initial_setup_tool.py` is a straight carry-over from the ESP32 version: it reads/writes `param.json`
  relative to the current directory, not `param/param.json`. Run it from `param/` or copy the result.
- `param/param.json` holds Wi-Fi and InfluxDB credentials in clear text and **is tracked in git**. Never
  paste its values into logs, issues, or commits.
- The `/monitor` route shells out to `sudo reboot` / `shutdown -h now` on a query parameter, and the HTTP
  server has no authentication — treat 8123 as LAN-only.

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
- InfluxDB credentials never appear in a log line: they travel in `requests.post(params=…)`, and error
  messages only carry `host:port/db` plus the exception class.
