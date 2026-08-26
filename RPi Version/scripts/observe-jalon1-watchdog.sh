#!/usr/bin/env bash
# Observation bornée du jalon 1 avec watchdog systemd armé.
#
# Le script est strictement en lecture côté contrôleur : il interroge systemd
# et les API HTTP locales, puis écrit ses preuves sous ~/phyto-observations.
# Il ne redémarre aucun service et ne touche à aucun GPIO.

set -uo pipefail

SERVICE_NAME="${PHYTO_OBSERVATION_SERVICE:-phyto.service}"
API_BASE="${PHYTO_OBSERVATION_API_BASE:-http://127.0.0.1:8123}"
DURATION_SECONDS="${PHYTO_OBSERVATION_SECONDS:-172800}"
INTERVAL_SECONDS="${PHYTO_OBSERVATION_INTERVAL_SECONDS:-60}"
OUTPUT_ROOT="${PHYTO_OBSERVATION_DIR:-${HOME}/phyto-observations}"

die() { printf 'ERREUR : %s\n' "$*" >&2; exit 2; }
info() { printf '%s\n' "$*"; }

[[ "$DURATION_SECONDS" =~ ^[1-9][0-9]*$ ]] \
    || die "PHYTO_OBSERVATION_SECONDS doit être un entier strictement positif"
[[ "$INTERVAL_SECONDS" =~ ^[1-9][0-9]*$ ]] \
    || die "PHYTO_OBSERVATION_INTERVAL_SECONDS doit être un entier strictement positif"
command -v curl >/dev/null 2>&1 || die "curl est requis"
command -v python3 >/dev/null 2>&1 || die "python3 est requis"
command -v systemctl >/dev/null 2>&1 || die "systemctl est requis"

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
START_EPOCH="$(date +%s)"
END_EPOCH=$((START_EPOCH + DURATION_SECONDS))
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="$OUTPUT_ROOT/jalon1-watchdog-arme-$RUN_STAMP"
SAMPLES_FILE="$RUN_DIR/samples.jsonl"
SUMMARY_FILE="$RUN_DIR/summary.json"
METADATA_FILE="$RUN_DIR/metadata.txt"
LATEST_FILE="$OUTPUT_ROOT/latest-jalon1-watchdog-arme.txt"
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
BASE_COMMIT="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
BASE_COMMIT_LABEL="$(git -C "$APP_DIR" log -1 --oneline 2>/dev/null || true)"

[[ -n "$BASE_BOOT_ID" ]] || die "identifiant de boot illisible"
[[ "$BASE_PID" =~ ^[1-9][0-9]*$ ]] || die "MainPID initial invalide : ${BASE_PID:-vide}"
[[ "$BASE_NRESTARTS" =~ ^[0-9]+$ ]] || die "NRestarts initial invalide : ${BASE_NRESTARTS:-vide}"
[[ "$BASE_WATCHDOG_USEC" =~ ^[1-9][0-9]*(us|ms|min|s|h)?$ ]] \
    || die "watchdog non armé ou valeur illisible : ${BASE_WATCHDOG_USEC:-vide}"

cat > "$METADATA_FILE" <<EOF
protocole=jalon1-observation-watchdog-arme
debut_utc=$(date -u --date="@$START_EPOCH" +%Y-%m-%dT%H:%M:%SZ)
duree_secondes=$DURATION_SECONDS
intervalle_secondes=$INTERVAL_SECONDS
service=$SERVICE_NAME
api=$API_BASE
commit=$BASE_COMMIT
commit_label=$BASE_COMMIT_LABEL
boot_id=$BASE_BOOT_ID
main_pid=$BASE_PID
nrestarts=$BASE_NRESTARTS
watchdog_usec=$BASE_WATCHDOG_USEC
deviation=watchdog systemd volontairement armé pendant l'observation
EOF

info "Observation du jalon 1 démarrée"
info "Durée      : $DURATION_SECONDS s"
info "Intervalle : $INTERVAL_SECONDS s"
info "Watchdog   : $BASE_WATCHDOG_USEC (armé)"
info "Commit     : $BASE_COMMIT_LABEL"
info "Preuves    : $RUN_DIR"

sample_count=0
failure_count=0
warning_count=0

while (( $(date +%s) < END_EPOCH )) && (( STOP_REQUESTED == 0 )); do
    SAMPLE_EPOCH="$(date +%s)"
    SAMPLE_UTC="$(date -u --date="@$SAMPLE_EPOCH" +%Y-%m-%dT%H:%M:%SZ)"

    READY_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/ready.json" \
        -w '%{http_code}' "$API_BASE/health/ready" 2>/dev/null || true)"
    API_CODE="$(curl -sS --max-time 5 -o "$TMP_DIR/state.json" \
        -w '%{http_code}' "$API_BASE/api/v1/state" 2>/dev/null || true)"

    CURRENT_ACTIVE="$(system_value ActiveState)"
    CURRENT_SUBSTATE="$(system_value SubState)"
    CURRENT_PID="$(system_value MainPID)"
    CURRENT_NRESTARTS="$(system_value NRestarts)"
    CURRENT_WATCHDOG_USEC="$(system_value WatchdogUSec)"
    CURRENT_BOOT_ID="$(tr -d '\r\n' < /proc/sys/kernel/random/boot_id 2>/dev/null || true)"

    export SAMPLE_EPOCH SAMPLE_UTC READY_CODE API_CODE
    export CURRENT_ACTIVE CURRENT_SUBSTATE CURRENT_PID CURRENT_NRESTARTS
    export CURRENT_WATCHDOG_USEC CURRENT_BOOT_ID
    export BASE_PID BASE_NRESTARTS BASE_WATCHDOG_USEC BASE_BOOT_ID BASE_COMMIT
    export READY_JSON_PATH="$TMP_DIR/ready.json"
    export STATE_JSON_PATH="$TMP_DIR/state.json"

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


failures = []
warnings = []
ready = load_json(os.environ["READY_JSON_PATH"])
state = load_json(os.environ["STATE_JSON_PATH"])

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
actuators = {}
sensors = []
healthy = None
control_healthy = None
time_state = None
if os.environ.get("API_CODE") != "200" or not isinstance(state, dict):
    failures.append("api_state_indisponible")
else:
    health = state.get("health") or {}
    healthy = health.get("healthy")
    control_healthy = health.get("control_healthy")
    tasks = health.get("tasks") or {}
    actuators = state.get("actuators") or {}
    sensors = state.get("sensors") or []
    time_state = (state.get("time") or {}).get("state")

    if healthy is not True:
        failures.append("sante_globale_fausse")
    if control_healthy is not True:
        failures.append("sante_controle_fausse")

    gated = {name: task for name, task in tasks.items() if task.get("gates_watchdog")}
    if not gated:
        failures.append("ensemble_watchdog_vide")
    for name, task in tasks.items():
        if task.get("alive") is not True or task.get("healthy") is not True:
            failures.append(f"tache_malsaine:{name}")
        if int(task.get("restarts") or 0) != 0:
            failures.append(f"tache_redemarree:{name}")
        if int(task.get("stalls") or 0) != 0:
            failures.append(f"tache_bloquee:{name}")
        if task.get("last_error"):
            failures.append(f"tache_derniere_erreur:{name}")

    for name, actuator in actuators.items():
        if actuator.get("stale") is True:
            failures.append(f"actionneur_perime:{name}")
        tracking = actuator.get("tracking")
        if tracking not in {"ok", "known_hardware_fault"}:
            failures.append(f"suivi_actionneur:{name}:{tracking}")

    for sensor in sensors:
        if sensor.get("status") != "ok":
            warnings.append(f"capteur:{sensor.get('key')}:{sensor.get('status')}")
    if time_state not in {"synchronized", "plausible"}:
        warnings.append(f"heure:{time_state}")

record = {
    "ts": os.environ.get("SAMPLE_UTC"),
    "epoch": int(os.environ.get("SAMPLE_EPOCH", "0")),
    "commit": os.environ.get("BASE_COMMIT"),
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
            "stalls": task.get("stalls"),
            "last_error": task.get("last_error"),
        }
        for name, task in tasks.items()
    },
    "actuators": {
        name: {
            "requested": actuator.get("requested"),
            "actual": actuator.get("actual"),
            "stale": actuator.get("stale"),
            "tracking": actuator.get("tracking"),
            "age_seconds": actuator.get("age_seconds"),
        }
        for name, actuator in actuators.items()
    },
    "sensor_statuses": {
        sensor.get("key"): sensor.get("status") for sensor in sensors
    },
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
        0) info "$SAMPLE_UTC OK santé contrôle et tâches" ;;
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
export START_EPOCH FINISH_EPOCH END_EPOCH DURATION_SECONDS INTERVAL_SECONDS
export STOP_REQUESTED sample_count failure_count warning_count
export SUMMARY_FILE SAMPLES_FILE METADATA_FILE RUN_DIR BASE_COMMIT BASE_COMMIT_LABEL
python3 - <<'PY'
import json
import os
import tempfile


interrupted = os.environ.get("STOP_REQUESTED") == "1"
failures = int(os.environ.get("failure_count", "0"))
warnings = int(os.environ.get("warning_count", "0"))
summary = {
    "protocol": "jalon1-observation-watchdog-arme",
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
    "samples": int(os.environ.get("sample_count", "0")),
    "failed_samples": failures,
    "warning_samples": warnings,
    "deviation": "watchdog systemd volontairement armé pendant l'observation",
    "artifacts": {
        "samples": os.environ.get("SAMPLES_FILE"),
        "metadata": os.environ.get("METADATA_FILE"),
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
