#!/usr/bin/env bash
set -euo pipefail

workspace_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -x "$workspace_root/.venv/bin/python" ]]; then
    python_exe="$workspace_root/.venv/bin/python"
elif [[ -x "$workspace_root/python_ai/.venv/bin/python" ]]; then
    python_exe="$workspace_root/python_ai/.venv/bin/python"
else
    python_exe="$(command -v python3 || command -v python || true)"
fi

if [[ -z "$python_exe" ]]; then
    echo "Python executable not found. Install Python 3 or create a virtual environment." >&2
    exit 1
fi

if ! command -v go >/dev/null 2>&1; then
    echo "Go executable not found. Install Go and ensure it is on PATH." >&2
    exit 1
fi

stop_stale_port_processes() {
    local port="$1"

    if command -v fuser >/dev/null 2>&1; then
        fuser -k -TERM "${port}/tcp" >/dev/null 2>&1 || true
    elif command -v lsof >/dev/null 2>&1; then
        lsof -ti "tcp:${port}" | xargs -r kill -TERM 2>/dev/null || true
    else
        echo "Warning: neither fuser nor lsof is installed; cannot clear port ${port}." >&2
    fi
}

stop_stale_port_processes 5000
stop_stale_port_processes 8080

echo "Starting Python service on port 5000..."
cd "$workspace_root"
"$python_exe" -m uvicorn python_ai.app.main:app --host 127.0.0.1 --port 5000 &
python_pid=$!

cleanup() {
    if kill -0 "$python_pid" 2>/dev/null; then
        kill "$python_pid" 2>/dev/null || true
        wait "$python_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

sleep 2

echo "Starting Go server on port 8080..."
go run ./cmd/scraper-server
