#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

BACKEND_PID=""

cleanup() {
  local exit_code=$?
  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  wait || true
  exit "${exit_code}"
}

trap cleanup INT TERM EXIT

cd "${ROOT_DIR}"
python -m uvicorn app.main:app --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

echo "Server: http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "Press Ctrl+C to stop service."

wait "${BACKEND_PID}"
