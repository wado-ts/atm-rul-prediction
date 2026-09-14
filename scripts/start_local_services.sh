#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
SEQUENCE_DIR="$APP_DIR/external_services/sequence-building-service"
INFERENCE_DIR="$APP_DIR/external_services/inference-service"
LOG_DIR="${LOCAL_SERVICE_LOG_DIR:-$SCRIPT_DIR/logs}"
STARTUP_TIMEOUT_SECONDS="${LOCAL_SERVICE_STARTUP_TIMEOUT_SECONDS:-120}"
POLL_INTERVAL_SECONDS="${LOCAL_SERVICE_POLL_INTERVAL_SECONDS:-2}"

mkdir -p "$LOG_DIR"

find_python() {
    local service_dir="$1"
    local windows_python="$service_dir/.venv/Scripts/python.exe"
    local unix_python="$service_dir/.venv/bin/python"

    if [[ -x "$windows_python" ]]; then
        printf '%s\n' "$windows_python"
    elif [[ -x "$unix_python" ]]; then
        printf '%s\n' "$unix_python"
    elif command -v python >/dev/null 2>&1; then
        command -v python
    elif command -v python3 >/dev/null 2>&1; then
        command -v python3
    else
        echo "Python was not found for $service_dir. Create its .venv or install Python 3.11+." >&2
        exit 1
    fi
}

SEQUENCE_PYTHON_BIN="$(find_python "$SEQUENCE_DIR")"
INFERENCE_PYTHON_BIN="$(find_python "$INFERENCE_DIR")"
APP_PYTHON_BIN="$(find_python "$APP_DIR")"

if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for service readiness checks." >&2
    exit 1
fi

for required_dir in "$SEQUENCE_DIR" "$INFERENCE_DIR" "$APP_DIR"; do
    if [[ ! -d "$required_dir" ]]; then
        echo "Required service directory not found: $required_dir" >&2
        exit 1
    fi
done

PIDS=()

cleanup() {
    local exit_code=$?
    trap - EXIT INT TERM

    for pid in "${PIDS[@]:-}"; do
        [[ -n "$pid" ]] || continue
        if command -v taskkill >/dev/null 2>&1; then
            taskkill //PID "$pid" //T //F >/dev/null 2>&1 || true
        else
            kill "$pid" >/dev/null 2>&1 || true
        fi
    done

    exit "$exit_code"
}
trap cleanup EXIT INT TERM

start_service() {
    local name="$1"
    local directory="$2"
    local port="$3"
    local python_bin="$4"
    shift 4

    echo "Starting $name on port $port..."
    (
        cd "$directory"
        exec "$python_bin" -m uvicorn "$@"
    ) >"$LOG_DIR/$name.log" 2>&1 &

    local pid=$!
    PIDS+=("$pid")
    echo "$name PID: $pid (log: $LOG_DIR/$name.log)"
}

wait_for_endpoint() {
    local name="$1"
    local url="$2"
    local pid="$3"
    local deadline=$((SECONDS + STARTUP_TIMEOUT_SECONDS))

    while (( SECONDS < deadline )); do
        if curl --silent --show-error --fail --max-time 5 "$url" >/dev/null 2>&1; then
            echo "$name is ready: $url"
            return 0
        fi

        sleep "$POLL_INTERVAL_SECONDS"
    done

    echo "Timed out waiting for $name at $url. See $LOG_DIR/$name.log" >&2
    return 1
}

start_service "sequence-builder" "$SEQUENCE_DIR" 9001 "$SEQUENCE_PYTHON_BIN" \
    app.main:app --host 127.0.0.1 --port 9001
wait_for_endpoint "sequence-builder" "http://127.0.0.1:9001/healthz" "${PIDS[0]}"

start_service "inference" "$INFERENCE_DIR" 9002 "$INFERENCE_PYTHON_BIN" \
    app.main:app --host 127.0.0.1 --port 9002
wait_for_endpoint "inference" "http://127.0.0.1:9002/readyz" "${PIDS[1]}"

start_service "atm-rul-app" "$APP_DIR" 8000 "$APP_PYTHON_BIN" \
    app.main:app --host 127.0.0.1 --port 8000
wait_for_endpoint "atm-rul-app" "http://127.0.0.1:8000/healthz" "${PIDS[2]}"

echo
echo "All services are running. Dashboard: http://127.0.0.1:8000"
echo "Press Ctrl+C to stop all services."

wait "${PIDS[2]}"
