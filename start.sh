#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${ROOT_DIR}/.run"
VENV_DIR="${ROOT_DIR}/.venv"
PID_FILE="${RUN_DIR}/backend.pid"
PORT_FILE="${RUN_DIR}/backend.port"
HOST_FILE="${RUN_DIR}/backend.host"
LOG_FILE="${RUN_DIR}/backend.log"
REQ_FILE="${ROOT_DIR}/requirements.txt"
REQ_HASH_FILE="${RUN_DIR}/requirements.sha256"

BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
DEFAULT_PORT="${BACKEND_PORT:-${PORT:-8000}}"
PORT_SEARCH_LIMIT="${PORT_SEARCH_LIMIT:-100}"
APP_ENV="${APP_ENV:-${ENVIRONMENT:-production}}"
APP_DEBUG="${APP_DEBUG:-${DEBUG:-0}}"
BACKEND_WORKERS="${BACKEND_WORKERS:-1}"
UVICORN_LOG_LEVEL="${UVICORN_LOG_LEVEL:-info}"
UVICORN_PROXY_HEADERS="${UVICORN_PROXY_HEADERS:-1}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-*}"
AUTO_INSTALL_MISSING_MODULES="${AUTO_INSTALL_MISSING_MODULES:-0}"

mkdir -p "${RUN_DIR}"

usage() {
  cat <<'EOF'
Usage:
  ./start.sh [start|run|stop|restart|status|logs]

Commands:
  start    Start backend in background (default)
  run      Run backend in foreground
  stop     Stop running backend
  restart  Restart backend (stop then start)
  status   Show backend status
  logs     Tail backend logs

Env vars:
  BACKEND_HOST       Default 0.0.0.0 (allow external access)
  BACKEND_PORT/PORT  Preferred port (auto-fallback if occupied)
  ENVIRONMENT        Default production
  DEBUG              Default 0
  BACKEND_WORKERS    Default 1 (recommended; app includes in-process scheduler)
  UVICORN_LOG_LEVEL  Default info
  UVICORN_PROXY_HEADERS 1 to trust reverse-proxy headers, default 1
  FORWARDED_ALLOW_IPS Default * (effective when UVICORN_PROXY_HEADERS=1)
  AUTO_INSTALL_MISSING_MODULES Default 0 (set 1 for dev convenience)
  PORT_SEARCH_LIMIT  Number of ports to try, default 100
  FORCE_INSTALL=1    Force reinstall requirements
EOF
}

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return 0
  fi
  echo "Error: python3/python not found." >&2
  exit 1
}

BASE_PYTHON="$(pick_python)"

ensure_venv() {
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    echo "Creating virtualenv at ${VENV_DIR}..."
    "${BASE_PYTHON}" -m venv "${VENV_DIR}"
  fi

  VENV_PYTHON="${VENV_DIR}/bin/python"
  "${VENV_PYTHON}" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "${VENV_PYTHON}" -m pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
}

requirements_hash() {
  "${BASE_PYTHON}" - <<'PY' "${REQ_FILE}"
import hashlib
import pathlib
import sys

req = pathlib.Path(sys.argv[1])
if not req.exists():
    print("")
else:
    print(hashlib.sha256(req.read_bytes()).hexdigest())
PY
}

ensure_deps() {
  ensure_venv
  local current_hash=""
  local saved_hash=""

  current_hash="$(requirements_hash)"
  if [[ -f "${REQ_HASH_FILE}" ]]; then
    saved_hash="$(cat "${REQ_HASH_FILE}")"
  fi

  if [[ "${FORCE_INSTALL:-0}" == "1" || "${current_hash}" != "${saved_hash}" ]]; then
    if [[ -f "${REQ_FILE}" ]]; then
      echo "Installing dependencies from requirements.txt..."
      "${VENV_PYTHON}" -m pip install -r "${REQ_FILE}"
      echo "${current_hash}" > "${REQ_HASH_FILE}"
    else
      echo "Warning: requirements.txt not found, skipping dependency install."
    fi
  fi
}

export_runtime_env() {
  export ENVIRONMENT="${APP_ENV}"
  export DEBUG="${APP_DEBUG}"
}

show_runtime_summary() {
  echo "Runtime config: ENVIRONMENT=${APP_ENV} DEBUG=${APP_DEBUG} HOST=${BACKEND_HOST} WORKERS=${BACKEND_WORKERS}"
  if [[ "${BACKEND_WORKERS}" != "1" ]]; then
    echo "Warning: BACKEND_WORKERS=${BACKEND_WORKERS}. The app has an in-process scheduler; keep 1 worker unless scheduler is externalized."
  fi
  if [[ "${APP_ENV}" == "production" && "${SECRET_KEY:-development-secret-key}" == "development-secret-key" ]]; then
    echo "Warning: SECRET_KEY is using the default development value. Set a strong SECRET_KEY in production."
  fi
}

build_uvicorn_cmd() {
  local host="$1"
  local port="$2"

  UVICORN_CMD=(
    "${VENV_PYTHON}" -m uvicorn app.main:app
    --host "${host}"
    --port "${port}"
    --workers "${BACKEND_WORKERS}"
    --log-level "${UVICORN_LOG_LEVEL}"
  )

  if [[ "${UVICORN_PROXY_HEADERS}" == "1" ]]; then
    UVICORN_CMD+=(--proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS}")
  fi
}

pid_is_backend() {
  local pid="$1"
  local cmdline

  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    return 1
  fi

  cmdline="$(ps -p "${pid}" -o command= 2>/dev/null || true)"
  if [[ "${cmdline}" == *"uvicorn"* && "${cmdline}" == *"app.main:app"* ]]; then
    return 0
  fi

  return 1
}

is_running() {
  if [[ ! -f "${PID_FILE}" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  if pid_is_backend "${pid}"; then
    return 0
  fi
  rm -f "${PID_FILE}" "${PORT_FILE}" "${HOST_FILE}"
  return 1
}

get_missing_module() {
  if [[ ! -f "${LOG_FILE}" ]]; then
    return 1
  fi
  local line module
  line="$(grep -E "ModuleNotFoundError: No module named '.*'" "${LOG_FILE}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 1
  fi
  module="${line##*No module named \'}"
  module="${module%\'}"
  if [[ -z "${module}" ]]; then
    return 1
  fi
  echo "${module}"
}

try_install_missing_module() {
  if [[ "${AUTO_INSTALL_MISSING_MODULES}" != "1" ]]; then
    return 1
  fi
  local module pkg
  module="$(get_missing_module || true)"
  if [[ -z "${module}" ]]; then
    return 1
  fi
  pkg="${module//_/-}"
  echo "Attempting to install missing module '${module}' (package '${pkg}')..."
  "${VENV_PYTHON}" -m pip install "${pkg}" || return 1
  return 0
}

show_start_failure_hint() {
  if [[ ! -f "${LOG_FILE}" ]]; then
    return 0
  fi
  local module pkg
  module="$(get_missing_module || true)"
  if [[ -n "${module}" ]]; then
    pkg="${module//_/-}"
    echo "Hint: missing Python module '${module}'."
    echo "Add it to requirements.txt and run: FORCE_INSTALL=1 ./start.sh start"
    echo "Quick test: ${VENV_PYTHON} -m pip install ${pkg}"
  fi
}

find_free_port() {
  local host="$1"
  local start_port="$2"
  local tries="$3"
  "${BASE_PYTHON}" - <<'PY' "${host}" "${start_port}" "${tries}"
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
tries = int(sys.argv[3])

for p in range(port, port + tries):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, p))
    except OSError:
        s.close()
        continue
    s.close()
    print(p)
    raise SystemExit(0)

raise SystemExit(1)
PY
}

start_backend() {
  if is_running; then
    local pid port host
    pid="$(cat "${PID_FILE}")"
    port="$(cat "${PORT_FILE}" 2>/dev/null || echo "${DEFAULT_PORT}")"
    host="$(cat "${HOST_FILE}" 2>/dev/null || echo "${BACKEND_HOST}")"
    echo "Backend already running (PID ${pid}): http://${host}:${port}"
    return 0
  fi

  ensure_deps
  export_runtime_env
  show_runtime_summary

  local port
  if ! port="$(find_free_port "${BACKEND_HOST}" "${DEFAULT_PORT}" "${PORT_SEARCH_LIMIT}")"; then
    echo "Error: no free port found from ${DEFAULT_PORT} (+${PORT_SEARCH_LIMIT})." >&2
    exit 1
  fi

  if [[ "${port}" != "${DEFAULT_PORT}" ]]; then
    echo "Port ${DEFAULT_PORT} is occupied, using ${port}."
  fi

  local attempt pid i
  for attempt in 1 2; do
    (
      cd "${ROOT_DIR}"
      build_uvicorn_cmd "${BACKEND_HOST}" "${port}"
      nohup "${UVICORN_CMD[@]}" >> "${LOG_FILE}" 2>&1 &
      echo $! > "${PID_FILE}"
      echo "${port}" > "${PORT_FILE}"
      echo "${BACKEND_HOST}" > "${HOST_FILE}"
    )

    pid="$(cat "${PID_FILE}")"
    for i in {1..25}; do
      if ! kill -0 "${pid}" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done

    if is_running; then
      break
    fi

    if [[ "${attempt}" == "1" ]] && try_install_missing_module; then
      echo "Retrying backend start after auto-install..."
      continue
    fi

    echo "Error: backend failed to start. Check logs: ${LOG_FILE}" >&2
    show_start_failure_hint
    exit 1
  done

  echo "Backend started: http://${BACKEND_HOST}:${port}"
  echo "PID: $(cat "${PID_FILE}")"
  echo "Logs: ${LOG_FILE}"
}

run_foreground() {
  ensure_deps
  export_runtime_env
  show_runtime_summary

  local port
  if ! port="$(find_free_port "${BACKEND_HOST}" "${DEFAULT_PORT}" "${PORT_SEARCH_LIMIT}")"; then
    echo "Error: no free port found from ${DEFAULT_PORT} (+${PORT_SEARCH_LIMIT})." >&2
    exit 1
  fi
  if [[ "${port}" != "${DEFAULT_PORT}" ]]; then
    echo "Port ${DEFAULT_PORT} is occupied, using ${port}."
  fi
  echo "Running in foreground: http://${BACKEND_HOST}:${port}"
  cd "${ROOT_DIR}"
  build_uvicorn_cmd "${BACKEND_HOST}" "${port}"
  exec "${UVICORN_CMD[@]}"
}

stop_backend() {
  if ! is_running; then
    echo "Backend is not running."
    return 0
  fi

  local pid
  pid="$(cat "${PID_FILE}")"
  echo "Stopping backend PID ${pid}..."
  kill "${pid}" 2>/dev/null || true

  for _ in {1..20}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done

  if kill -0 "${pid}" 2>/dev/null; then
    echo "Force killing PID ${pid}..."
    kill -9 "${pid}" 2>/dev/null || true
  fi

  rm -f "${PID_FILE}" "${PORT_FILE}" "${HOST_FILE}"
  echo "Backend stopped."
}

status_backend() {
  if is_running; then
    local pid port host
    pid="$(cat "${PID_FILE}")"
    port="$(cat "${PORT_FILE}" 2>/dev/null || echo "${DEFAULT_PORT}")"
    host="$(cat "${HOST_FILE}" 2>/dev/null || echo "${BACKEND_HOST}")"
    echo "Backend is running."
    echo "PID: ${pid}"
    echo "URL: http://${host}:${port}"
    echo "Log: ${LOG_FILE}"
  else
    echo "Backend is not running."
  fi
}

logs_backend() {
  touch "${LOG_FILE}"
  tail -n 100 -f "${LOG_FILE}"
}

cmd="${1:-start}"
case "${cmd}" in
  start)
    start_backend
    ;;
  run)
    run_foreground
    ;;
  stop)
    stop_backend
    ;;
  restart)
    stop_backend
    start_backend
    ;;
  status)
    status_backend
    ;;
  logs)
    logs_backend
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: ${cmd}" >&2
    usage
    exit 1
    ;;
esac
