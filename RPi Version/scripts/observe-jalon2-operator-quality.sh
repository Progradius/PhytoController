#!/usr/bin/env bash
# Observation bornée du jalon 2 : expérience opérateur et qualité capteurs.
#
# Le script est strictement en lecture côté contrôleur : il interroge systemd
# et les API HTTP locales, puis écrit ses preuves sous ~/phyto-observations.
# Il ne modifie ni configuration, ni GPIO, ni service. La qualité capteurs doit
# rester en mode « observe » pendant toute la fenêtre.

set -uo pipefail

SERVICE_NAME="${PHYTO_OBSERVATION_SERVICE:-phyto.service}"
API_BASE="${PHYTO_OBSERVATION_API_BASE:-http://127.0.0.1:8123}"
DURATION_SECONDS="${PHYTO_OBSERVATION_SECONDS:-172800}"
INTERVAL_SECONDS="${PHYTO_OBSERVATION_INTERVAL_SECONDS:-60}"
PROBE_INTERVAL_SECONDS="${PHYTO_OBSERVATION_PROBE_INTERVAL_SECONDS:-600}"
OUTPUT_ROOT="${PHYTO_OBSERVATION_DIR:-${HOME}/phyto-observations}"

die() { printf 'ERREUR : %s\n' "$*" >&2; exit 2; }
info() { printf '%s\n' "$*"; }

[[ "$DURATION_SECONDS" =~ ^[1-9][0-9]*$ ]] \
    || die "PHYTO_OBSERVATION_SECONDS doit être un entier strictement positif"
[[ "$INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]] \
    || die "PHYTO_OBSERVATION_INTERVAL_SECONDS doit être un entier strictement positif"
[[ "$PROBE_INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]] \
    || die "PHYTO_OBSERVATION_PROBE_INTERVAL_SECONDS doit être un entier strictement positif"
command -v curl >/dev/null 2>&1 || die "curl est requis"
command -v python3 >/dev/null 2>&1 || die "python3 est requis"
command -v systemctl >/dev/null 2>&1 || die "systemctl est requis"

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
START_EPOCH="$(date +%s)"
END_EPOCH=$((START_EPOCH + DURATION_SECONDS))
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$OUTPUT_ROOT/jalon2-operateur-qualite-$RUN_STAMP"
SAMPLES_FILE="$RUN_DIR/samples.jsonl"
SUMMARY_FILE="$RUN_DIR/summary.json"
METADATA_FILE="$RUN_DIR/metadata.txt"
FINAL_STATE_FILE="$RUN_DIR/final-state.json"
FINAL_ALARMS_FILE="$RUN_DIR/final-alarms.json"
FINAL_HISTORY_FILE="$RUN_DIR/final-history.json"
LATEST_FILE="$OUTPUT_ROOT/latest-jalon2-operateur-qualite.txt"
TMP_DIR="$(mktemp -d)"

mkdir -p "$RUN_DIR"
chmod 700 "$OUTPUT_ROOT" "$RUN_DIR" 2>/dev/null || true
: > "$SAMPLES_FILE"
printf '%s\n' "$RUN_DIR" > "$LATEST_FILE"

cleanup() { rm -rf "$TMP_DIR"; }
STOP_REQUESTED=0
request_stop() { STOP_REQUESTED=1; }
trap cleanup EXIT
trap request_stop INT TERM

system_value() {
    systemctl show "$SERVICE_NAME" --value -p "$1" 2>/dev/null || true
}

BASE_BOOT_ID="$(tr -d '\r\n' < /proc/sys/kernel/random/boot_id 2>/dev/null || true)"
BASE_PID="$(system_value MainPID)"
BASE_NRESTARTS="$(system_value NRestarts)"
BASE_WATCHDOG_USEC="$(system_value WatchdogUSec)"
BASE_COMMIT="${PHYTO_OBSERVATION_EXPECTED_COMMIT:-$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)}"
BASE_COMMIT_LABEL="$(git -C "$APP_DIR" log -1 --oneline 2>/dev/null || true)"

[[ -n "$BASE_BOOT_ID" ]] || die "identifiant de boot illisible"
[[ "$BASE_PID" =~ ^[1-9][0-9]*$ ]] || die "MainPID initial invalide : ${BASE_PID:-vide}"
[[ "$BASE_NRESTARTS" =~ ^[0-9]+$ ]] || die "NRestarts initial invalide : ${BASE_NRESTARTS:-vide}"
[[ "$BASE_WATCHDOG_USEC" =~ ^[1-9][0-9]*(us|ms|min|s|h)?$ ]] \
    || die "watchdog non armé ou valeur illisible : ${BASE_WATCHDOG_USEC:-vide}"
[[ "$BASE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] || die "commit attendu invalide : ${BASE_COMMIT:-vide}"

cat > "$METADATA_FILE" <<EOF
protocole=jalon2-observation-operateur-qualite
debut_utc=$(date -u --date="@$START_EPOCH" +%Y-%m-%dT%H:%M:%SZ)
duree_secondes=$DURATION_SECONDS
intervalle_secondes=$INTERVAL_SECONDS
intervalle_sondes_auxiliaires_secondes=$PROBE_INTERVAL_SECONDS
service=$SERVICE_NAME
api=$API_BASE
commit=$BASE_COMMIT
commit_label=$BASE_COMMIT_LABEL
boot_id=$BASE_BOOT_ID
main_pid=$BASE_PID
nrestarts=$BASE_NRESTARTS
watchdog_usec=$BASE_WATCHDOG_USEC
mode_qualite_requis=observe
EOF

info "Observation du jalon 2 démarrée"
info "Durée      : $DURATION_SECONDS s"
info "Intervalle : $INTERVAL_SECONDS s"
info "Sondes aux.: $PROBE_INTERVAL_SECONDS s"
info "Watchdog   : $BASE_WATCHDOG_USEC (armé)"
info "Commit     : $BASE_COMMIT_LABEL"
info "Preuves    : $RUN_DIR"

sample_count=0
failure_count=0
warning_count=0
last_probe_epoch=0

while (( $(date +%s) < END_EPOCH )) && (( STOP_REQUESTED == 0 )); do
    SAMPLE_EPOCH="$(date +%s)"
    SAMPLE_UTC="$(date -u --date="@$SAMPLE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"

    READY_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/ready.json" \
        -w '%{http_code}' "$API_BASE/health/ready" 2>/dev/null || true)"
    API_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/state.json" \
        -w '%{http_code}' "$API_BASE/api/v1/state" 2>/dev/null || true)"
    ALARMS_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/alarms.json" \
        -w '%{http_code}' "$API_BASE/api/v1/alarms/active" 2>/dev/null || true)"

    PROBE_DUE=0
    HISTORY_CODE=""
    MANIFEST_CODE=""
    WORKER_CODE=""
    OFFLINE_CODE=""
    INFLUX_PROBE_JSON=""
    if (( last_probe_epoch == 0 || SAMPLE_EPOCH - last_probe_epoch >= PROBE_INTERVAL_SECONDS )); then
        PROBE_DUE=1
        last_probe_epoch="$SAMPLE_EPOCH"
        HISTORY_CODE="$(curl -sS --max-time 10 -o "$TMP_DIR/history.json" \
            -w '%{http_code}' "$API_BASE/api/v1/history?hours=24" 2>/dev/null || true)"
        MANIFEST_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/manifest.json" \
            -w '%{http_code}' "$API_BASE/app.webmanifest" 2>/dev/null || true)"
        WORKER_CODE="$(curl -sS --max-time 5 -o /dev/null \
            -w '%{http_code}' "$API_BASE/service-worker.js" 2>/dev/null || true)"
        OFFLINE_CODE="$(curl -sS --max-time 5 -o /dev/null \
            -w '%{http_code}' "$API_BASE/offline" 2>/dev/null || true)"
        INFLUX_PROBE_JSON="$(PHYTO_OBSERVATION_APP_DIR="$APP_DIR" python3 - <<'PY'
import json
import os
import urllib.parse
import urllib.request


def result(payload):
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


try:
    config_path = os.path.join(
        os.environ["PHYTO_OBSERVATION_APP_DIR"], "param", "param.json"
    )
    with open(config_path, "r", encoding="utf-8") as source:
        network = json.load(source)["Network_Settings"]
    if str(network.get("host_machine_state", "offline")).lower() != "online":
        result({"enabled": False, "ok": True, "sensors": {}})
        raise SystemExit(0)
    query = (
        'SELECT last("status") AS "status" FROM "sensor_quality" '
        'WHERE time > now() - 5m GROUP BY "sensor"'
    )
    body = urllib.parse.urlencode({
        "db": network["influx_db_name"],
        "u": network["influx_db_user"],
        "p": network["influx_db_password"],
        "q": query,
    }).encode("utf-8")
    endpoint = (
        f'http://{network["host_machine_address"]}:'
        f'{network["influx_db_port"]}/query'
    )
    request = urllib.request.Request(endpoint, data=body, method="POST")
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.load(response)
    query_result = (payload.get("results") or [{}])[0]
    if query_result.get("error"):
        result({"enabled": True, "ok": False, "error": "query_error", "sensors": {}})
        raise SystemExit(0)
    sensors = {}
    for series in query_result.get("series") or []:
        key = (series.get("tags") or {}).get("sensor")
        values = series.get("values") or []
        if key and values and len(values[-1]) >= 2:
            sensors[key] = {"time": values[-1][0], "status": values[-1][1]}
    result({"enabled": True, "ok": True, "sensors": sensors})
except SystemExit:
    raise
except Exception as exc:
    result({
        "enabled": True,
        "ok": False,
        "error": exc.__class__.__name__,
        "sensors": {},
    })
PY
)"
    fi

    CURRENT_ACTIVE="$(system_value ActiveState)"
    CURRENT_SUBSTATE="$(system_value SubState)"
    CURRENT_PID="$(system_value MainPID)"
    CURRENT_NRESTARTS="$(system_value NRestarts)"
    CURRENT_WATCHDOG_USEC="$(system_value WatchdogUSec)"
    CURRENT_BOOT_ID="$(tr -d '\r\n' < /proc/sys/kernel/random/boot_id 2>/dev/null || true)"

    export SAMPLE_EPOCH SAMPLE_UTC READY_CODE API_CODE ALARMS_CODE
    export PROBE_DUE HISTORY_CODE MANIFEST_CODE WORKER_CODE OFFLINE_CODE INFLUX_PROBE_JSON
    export CURRENT_ACTIVE CURRENT_SUBSTATE CURRENT_PID CURRENT_NRESTARTS
    export CURRENT_WATCHDOG_USEC CURRENT_BOOT_ID
    export BASE_PID BASE_NRESTARTS BASE_WATCHDOG_USEC BASE_BOOT_ID BASE_COMMIT START_EPOCH
    export READY_JSON_PATH="$TMP_DIR/ready.json"
    export STATE_JSON_PATH="$TMP_DIR/state.json"
    export ALARMS_JSON_PATH="$TMP_DIR/alarms.json"
    export HISTORY_JSON_PATH="$TMP_DIR/history.json"
    export MANIFEST_JSON_PATH="$TMP_DIR/manifest.json"

    SAMPLE_LINE="$(python3 - <<'PY'
import json
import os
import sys


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            return json.load(source)
    except Exception:
        return None


def load_json_text(payload):
    try:
        return json.loads(payload)
    except Exception:
        return None


def integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


failures = []
warnings = []
ready = load_json(os.environ["READY_JSON_PATH"])
state = load_json(os.environ["STATE_JSON_PATH"])
active_alarms = load_json(os.environ["ALARMS_JSON_PATH"])
probe_due = os.environ.get("PROBE_DUE") == "1"
history_probe = load_json(os.environ["HISTORY_JSON_PATH"]) if probe_due else None
manifest = load_json(os.environ["MANIFEST_JSON_PATH"]) if probe_due else None
influx_probe = load_json_text(os.environ.get("INFLUX_PROBE_JSON", "")) if probe_due else None
sample_epoch = integer(os.environ.get("SAMPLE_EPOCH"))
start_epoch = integer(os.environ.get("START_EPOCH"))

if os.environ.get("CURRENT_ACTIVE") != "active":
    failures.append("service_non_actif")
if os.environ.get("CURRENT_SUBSTATE") != "running":
    failures.append("service_non_running")
if os.environ.get("CURRENT_PID") != os.environ.get("BASE_PID"):
    failures.append("main_pid_modifie")
if os.environ.get("CURRENT_NRESTARTS") != os.environ.get("BASE_NRESTARTS"):
    failures.append("nrestarts_modifie")
if os.environ.get("CURRENT_BOOT_ID") != os.environ.get("BASE_BOOT_ID"):
    failures.append("boot_id_modifie")
if os.environ.get("CURRENT_WATCHDOG_USEC") != os.environ.get("BASE_WATCHDOG_USEC"):
    failures.append("watchdog_modifie_ou_desarme")

if os.environ.get("READY_CODE") != "200" or not isinstance(ready, dict):
    failures.append("readiness_indisponible")
elif ready.get("ready") is not True:
    failures.append("readiness_fausse")

tasks = {}
domains = {}
actuators = {}
sensors = []
healthy = None
control_healthy = None
time_state = None
schema_version = None
deployed_version = None
alarm_summary = {}
history_state = {}
network_state = {}
https_state = {}

if os.environ.get("API_CODE") != "200" or not isinstance(state, dict):
    failures.append("api_state_indisponible")
else:
    schema_version = state.get("schema_version")
    deployed_version = state.get("version")
    health = state.get("health") or {}
    healthy = health.get("healthy")
    control_healthy = health.get("control_healthy")
    tasks = health.get("tasks") or {}
    domains = health.get("domains") or {}
    actuators = state.get("actuators") or {}
    sensors = state.get("sensors") or []
    time_state = (state.get("time") or {}).get("state")
    alarm_summary = state.get("alarms") or {}
    history_state = state.get("history") or {}
    network_state = state.get("network") or {}
    https_state = ((state.get("web") or {}).get("https") or {})

    if schema_version != 2:
        failures.append(f"schema_api_inattendu:{schema_version}")
    if deployed_version != os.environ.get("BASE_COMMIT"):
        failures.append("commit_processus_inattendu")
    if healthy is not True:
        failures.append("sante_globale_fausse")
    if control_healthy is not True:
        failures.append("sante_controle_fausse")

    required_tasks = {
        "daily_timer_1", "daily_timer_2", "cyclic_timer_1", "cyclic_timer_2",
        "climate_control", "sensor_snapshot", "influx_push", "http_server",
        "time_monitor", "operator_service",
    }
    for name in sorted(required_tasks - set(tasks)):
        failures.append(f"tache_absente:{name}")
    gated = {name: task for name, task in tasks.items() if task.get("gates_watchdog")}
    if not gated:
        failures.append("ensemble_watchdog_vide")
    for name, task in tasks.items():
        if task.get("alive") is not True or task.get("healthy") is not True:
            failures.append(f"tache_malsaine:{name}")
        if integer(task.get("restarts")) != 0:
            failures.append(f"tache_redemarree:{name}")
        if integer(task.get("stalls")) != 0:
            failures.append(f"tache_bloquee:{name}")
        if task.get("last_error"):
            failures.append(f"tache_derniere_erreur:{name}")
    for domain in ("timers", "climate", "sensors", "operations"):
        if domain not in domains:
            failures.append(f"domaine_absent:{domain}")
        elif domains[domain].get("healthy") is not True:
            failures.append(f"domaine_malsain:{domain}")

    required_actuators = {"daily_1", "daily_2", "cyclic_1", "cyclic_2", "heater", "motor"}
    for name in sorted(required_actuators - set(actuators)):
        failures.append(f"actionneur_absent:{name}")
    for name, actuator in actuators.items():
        if actuator.get("stale") is True:
            failures.append(f"actionneur_perime:{name}")
        tracking = actuator.get("tracking")
        if tracking not in {"ok", "known_hardware_fault"}:
            failures.append(f"suivi_actionneur:{name}:{tracking}")

    required_sensor_fields = {
        "key", "status", "acquisition_status", "reason_codes", "raw_value",
        "observed_value", "value", "control_usable", "would_block_control",
        "control_disposition", "enforcement_mode", "unchanged_for_s",
        "freshness_threshold_s", "plausible_range", "freeze_epsilon",
        "freeze_after_seconds", "freeze_min_samples", "calibration", "failures",
        "redundancy",
    }
    if not sensors:
        failures.append("aucun_capteur_actif")
    for sensor in sensors:
        key = sensor.get("key") or "inconnu"
        for field in sorted(required_sensor_fields - set(sensor)):
            failures.append(f"contrat_capteur_incomplet:{key}:{field}")
        mode = sensor.get("enforcement_mode")
        if mode != "observe":
            failures.append(f"mode_qualite_non_observe:{key}:{mode}")
        status = sensor.get("status")
        if status not in {"normal", "degraded", "absent", "inconsistent"}:
            failures.append(f"statut_capteur_invalide:{key}:{status}")
        elif status != "normal":
            warnings.append(f"capteur:{key}:{status}")
        if sensor.get("would_block_control") is True:
            warnings.append(f"capteur_bloquerait_controle:{key}")
        if (sensor.get("calibration") or {}).get("overdue") is True:
            warnings.append(f"calibration_expiree:{key}")

    if time_state not in {"synchronized", "plausible"}:
        warnings.append(f"heure:{time_state}")

    if integer(alarm_summary.get("critical_count")) > 0:
        failures.append("alarme_critique_active")
    if integer(alarm_summary.get("control_count")) > 0:
        warnings.append("alarme_controle_active")
    if integer(alarm_summary.get("auxiliary_count")) > 0:
        warnings.append("alarme_auxiliaire_active")

    if history_state.get("available") is not True:
        warnings.append("historique_indisponible")
    if history_state.get("last_error_class"):
        warnings.append(f"historique_erreur:{history_state.get('last_error_class')}")
    last_sample_ts = history_state.get("last_sample_ts")
    if isinstance(last_sample_ts, (int, float)):
        if sample_epoch - float(last_sample_ts) > 180:
            warnings.append("historique_echantillon_perime")
    elif sample_epoch - start_epoch > 180:
        warnings.append("historique_sans_echantillon")

    network_status = network_state.get("status")
    if network_status != "online":
        warnings.append(f"reseau:{network_status}")
    if https_state.get("configured") is True and https_state.get("ready") is not True:
        warnings.append("https_configure_non_pret")

if os.environ.get("ALARMS_CODE") != "200" or not isinstance(active_alarms, dict):
    warnings.append("api_alarmes_indisponible")
else:
    active_summary = active_alarms.get("summary") or {}
    if active_alarms.get("schema_version") != 1:
        warnings.append("schema_alarmes_inattendu")
    if integer(active_summary.get("critical_count")) > 0:
        failures.append("api_alarme_critique_active")

history_metrics = None
pwa_probe = None
influx_metrics = None
if probe_due:
    if os.environ.get("HISTORY_CODE") != "200" or not isinstance(history_probe, dict):
        warnings.append("api_historique_indisponible")
    else:
        buckets = history_probe.get("buckets")
        bucket_seconds = history_probe.get("bucket_seconds")
        if history_probe.get("hours") != 24 or not isinstance(buckets, list):
            warnings.append("contrat_historique_inattendu")
            buckets = []
        starts = [
            float(item["bucket_start_ts"])
            for item in buckets
            if isinstance(item, dict) and isinstance(item.get("bucket_start_ts"), (int, float))
        ]
        gaps = [right - left for left, right in zip(starts, starts[1:])]
        max_gap = max(gaps, default=0.0)
        latest_age = sample_epoch - starts[-1] if starts else None
        history_metrics = {
            "bucket_seconds": bucket_seconds,
            "buckets": len(buckets),
            "max_gap_seconds": round(max_gap, 1),
            "latest_bucket_age_seconds": round(latest_age, 1) if latest_age is not None else None,
            "series": len(history_probe.get("series") or []),
            "events": len(history_probe.get("events") or []),
        }
        if sample_epoch - start_epoch > 300 and not starts:
            warnings.append("historique_sans_bucket")
        if isinstance(bucket_seconds, (int, float)) and max_gap > float(bucket_seconds) * 2.5:
            warnings.append("historique_trou_agrege")
        if latest_age is not None and latest_age > 300:
            warnings.append("historique_bucket_perime")

    pwa_probe = {
        "manifest_code": os.environ.get("MANIFEST_CODE"),
        "worker_code": os.environ.get("WORKER_CODE"),
        "offline_code": os.environ.get("OFFLINE_CODE"),
        "manifest_valid": isinstance(manifest, dict) and bool(manifest.get("start_url")),
    }
    if os.environ.get("MANIFEST_CODE") != "200" or not pwa_probe["manifest_valid"]:
        warnings.append("pwa_manifeste_indisponible")
    if os.environ.get("WORKER_CODE") != "200":
        warnings.append("pwa_worker_indisponible")
    if os.environ.get("OFFLINE_CODE") != "200":
        warnings.append("pwa_repli_indisponible")

    if not isinstance(influx_probe, dict):
        warnings.append("sonde_influx_qualite_invalide")
    else:
        influx_metrics = influx_probe
        if influx_probe.get("enabled") is True:
            if influx_probe.get("ok") is not True:
                warnings.append("influx_qualite_indisponible")
            else:
                influx_sensors = set((influx_probe.get("sensors") or {}).keys())
                active_sensor_keys = {
                    sensor.get("key") for sensor in sensors if sensor.get("key")
                }
                if sample_epoch - start_epoch > 180:
                    for key in sorted(active_sensor_keys - influx_sensors):
                        warnings.append(f"influx_qualite_capteur_absent:{key}")

record = {
    "ts": os.environ.get("SAMPLE_UTC"),
    "epoch": sample_epoch,
    "commit": deployed_version,
    "schema_version": schema_version,
    "service": {
        "active": os.environ.get("CURRENT_ACTIVE"),
        "substate": os.environ.get("CURRENT_SUBSTATE"),
        "main_pid": os.environ.get("CURRENT_PID"),
        "nrestarts": os.environ.get("CURRENT_NRESTARTS"),
        "watchdog_usec": os.environ.get("CURRENT_WATCHDOG_USEC"),
        "boot_id": os.environ.get("CURRENT_BOOT_ID"),
    },
    "http": {
        "ready_code": os.environ.get("READY_CODE"),
        "api_code": os.environ.get("API_CODE"),
        "alarms_code": os.environ.get("ALARMS_CODE"),
    },
    "healthy": healthy,
    "control_healthy": control_healthy,
    "time_state": time_state,
    "tasks": {
        name: {
            "domain": task.get("domain"),
            "gates_watchdog": task.get("gates_watchdog"),
            "alive": task.get("alive"),
            "healthy": task.get("healthy"),
            "silence_s": task.get("silence_s"),
            "restarts": task.get("restarts"),
            "reloads": task.get("reloads"),
            "stalls": task.get("stalls"),
            "last_error": task.get("last_error"),
        }
        for name, task in tasks.items()
    },
    "actuators": {
        name: {
            "requested": actuator.get("requested"),
            "actual": actuator.get("actual"),
            "actual_status": actuator.get("actual_status"),
            "stale": actuator.get("stale"),
            "tracking": actuator.get("tracking"),
            "age_seconds": actuator.get("age_seconds"),
        }
        for name, actuator in actuators.items()
    },
    "sensors": {
        sensor.get("key"): {
            "status": sensor.get("status"),
            "acquisition_status": sensor.get("acquisition_status"),
            "reason_codes": sensor.get("reason_codes"),
            "control_usable": sensor.get("control_usable"),
            "would_block_control": sensor.get("would_block_control"),
            "control_disposition": sensor.get("control_disposition"),
            "enforcement_mode": sensor.get("enforcement_mode"),
            "unchanged_for_s": sensor.get("unchanged_for_s"),
            "failures": sensor.get("failures"),
        }
        for sensor in sensors
    },
    "alarms": alarm_summary,
    "history": history_state,
    "network": network_state,
    "https": https_state,
    "history_probe": history_metrics,
    "pwa_probe": pwa_probe,
    "influx_quality_probe": influx_metrics,
    "failures": sorted(set(failures)),
    "warnings": sorted(set(warnings)),
}
sys.stdout.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
if failures:
    raise SystemExit(2)
if warnings:
    raise SystemExit(3)
PY
)"
    sample_status=$?

    if [[ -z "$SAMPLE_LINE" ]]; then
        SAMPLE_LINE="{\"ts\":\"$SAMPLE_UTC\",\"failures\":[\"validation_interne_impossible\"]}"
        sample_status=2
    fi
    printf '%s\n' "$SAMPLE_LINE" >> "$SAMPLES_FILE"
    ((sample_count += 1))

    case "$sample_status" in
        0) info "$SAMPLE_UTC OK contrôle, opérateur et qualité en observation" ;;
        3) ((warning_count += 1)); info "$SAMPLE_UTC AVERTISSEMENT — voir samples.jsonl" ;;
        *) ((failure_count += 1)); info "$SAMPLE_UTC ÉCHEC — voir samples.jsonl" ;;
    esac

    now_epoch="$(date +%s)"
    remaining=$((END_EPOCH - now_epoch))
    (( remaining > 0 )) || break
    sleep_for="$INTERVAL_SECONDS"
    (( sleep_for <= remaining )) || sleep_for="$remaining"
    sleep "$sleep_for" || true
done

FINISH_EPOCH="$(date +%s)"
[[ -s "$TMP_DIR/state.json" ]] && cp "$TMP_DIR/state.json" "$FINAL_STATE_FILE"
[[ -s "$TMP_DIR/alarms.json" ]] && cp "$TMP_DIR/alarms.json" "$FINAL_ALARMS_FILE"
[[ -s "$TMP_DIR/history.json" ]] && cp "$TMP_DIR/history.json" "$FINAL_HISTORY_FILE"
chmod 600 "$FINAL_STATE_FILE" "$FINAL_ALARMS_FILE" "$FINAL_HISTORY_FILE" 2>/dev/null || true

export START_EPOCH FINISH_EPOCH END_EPOCH DURATION_SECONDS INTERVAL_SECONDS PROBE_INTERVAL_SECONDS
export STOP_REQUESTED sample_count failure_count warning_count
export SUMMARY_FILE SAMPLES_FILE METADATA_FILE RUN_DIR BASE_COMMIT BASE_COMMIT_LABEL
export FINAL_STATE_FILE FINAL_ALARMS_FILE FINAL_HISTORY_FILE
python3 - <<'PY'
import collections
import json
import os
import tempfile


records = []
try:
    with open(os.environ["SAMPLES_FILE"], "r", encoding="utf-8") as source:
        records = [json.loads(line) for line in source if line.strip()]
except Exception:
    pass

interrupted = os.environ.get("STOP_REQUESTED") == "1"
failures = int(os.environ.get("failure_count", "0"))
warnings = int(os.environ.get("warning_count", "0"))
failure_types = collections.Counter(
    item for record in records for item in record.get("failures", [])
)
warning_types = collections.Counter(
    item for record in records for item in record.get("warnings", [])
)
gaps = [
    right.get("epoch", 0) - left.get("epoch", 0)
    for left, right in zip(records, records[1:])
]
sensor_statuses = {}
for key in sorted({key for record in records for key in record.get("sensors", {})}):
    sensor_statuses[key] = dict(collections.Counter(
        record.get("sensors", {}).get(key, {}).get("status")
        for record in records if key in record.get("sensors", {})
    ))
history_probes = [record["history_probe"] for record in records if record.get("history_probe")]
influx_probes = [
    record["influx_quality_probe"]
    for record in records if record.get("influx_quality_probe")
]

summary = {
    "protocol": "jalon2-observation-operateur-qualite",
    "status": (
        "interrupted" if interrupted
        else "failed" if failures
        else "accepted_with_warnings" if warnings
        else "accepted"
    ),
    "commit": os.environ.get("BASE_COMMIT"),
    "commit_label": os.environ.get("BASE_COMMIT_LABEL"),
    "start_epoch": int(os.environ.get("START_EPOCH", "0")),
    "finish_epoch": int(os.environ.get("FINISH_EPOCH", "0")),
    "requested_duration_seconds": int(os.environ.get("DURATION_SECONDS", "0")),
    "actual_duration_seconds": (
        int(os.environ.get("FINISH_EPOCH", "0"))
        - int(os.environ.get("START_EPOCH", "0"))
    ),
    "interval_seconds": int(os.environ.get("INTERVAL_SECONDS", "0")),
    "probe_interval_seconds": int(os.environ.get("PROBE_INTERVAL_SECONDS", "0")),
    "samples": int(os.environ.get("sample_count", "0")),
    "failed_samples": failures,
    "warning_samples": warnings,
    "failure_types": dict(sorted(failure_types.items())),
    "warning_types": dict(sorted(warning_types.items())),
    "max_sample_gap_seconds": max(gaps, default=0),
    "sensor_statuses": sensor_statuses,
    "history_probes": len(history_probes),
    "final_history": history_probes[-1] if history_probes else None,
    "influx_quality_probes": len(influx_probes),
    "final_influx_quality": influx_probes[-1] if influx_probes else None,
    "manual_qualifications_remaining": [
        "PWA Chrome Android, coupure/reconnexion et notifications",
        "calibration par instrument de référence",
        "armement Sensor_Quality enforce",
        "repli matériel et régulation thermique automatique",
    ],
    "artifacts": {
        "samples": os.environ.get("SAMPLES_FILE"),
        "metadata": os.environ.get("METADATA_FILE"),
        "final_state": os.environ.get("FINAL_STATE_FILE"),
        "final_alarms": os.environ.get("FINAL_ALARMS_FILE"),
        "final_history": os.environ.get("FINAL_HISTORY_FILE"),
    },
}
target = os.environ["SUMMARY_FILE"]
directory = os.path.dirname(target)
fd, temporary = tempfile.mkstemp(prefix=".summary.", suffix=".tmp", dir=directory)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(summary, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
PY

info "Observation terminée : $SUMMARY_FILE"
if (( STOP_REQUESTED == 1 )); then
    info "Résultat : interrompu"
    exit 130
fi
if (( failure_count > 0 )); then
    info "Résultat : ÉCHEC ($failure_count échantillon(s) en défaut)"
    exit 1
fi
if (( warning_count > 0 )); then
    info "Résultat : À EXAMINER ($warning_count avertissement(s))"
    exit 3
else
    info "Résultat : accepté sans anomalie"
fi
