#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${ROOT_DIR}/output/playwright/admin-console"
SEED_JSON="${OUTPUT_DIR}/seed.json"
PLAYWRIGHT_LOG="${OUTPUT_DIR}/playwright.log"
BACKEND_LOG="${OUTPUT_DIR}/backend.log"
PW_STEP_TIMEOUT_SECONDS="${PW_STEP_TIMEOUT_SECONDS:-90}"

mkdir -p "${OUTPUT_DIR}"
: > "${PLAYWRIGHT_LOG}"

if ! command -v npx >/dev/null 2>&1; then
  echo "Error: npx is required but not found on PATH."
  echo "Please install Node.js/npm first."
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq is required but not found on PATH."
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Error: curl is required but not found on PATH."
  exit 1
fi

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
PWCLI="${CODEX_HOME}/skills/playwright/scripts/playwright_cli.sh"
if [[ ! -x "${PWCLI}" ]]; then
  echo "Error: Playwright wrapper not found: ${PWCLI}"
  exit 1
fi

if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Error: python3 not found."
  exit 1
fi

find_free_port() {
  "${PYTHON_BIN}" - <<'PY'
import socket
for p in range(18100, 18200):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", p))
    except OSError:
        sock.close()
        continue
    sock.close()
    print(p)
    raise SystemExit(0)
raise SystemExit(1)
PY
}

BACKEND_PID=""
PW_SESSION="ar$((RANDOM % 9000 + 1000))"

cleanup() {
  set +e
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1
    wait "${BACKEND_PID}" >/dev/null 2>&1
  fi
  (
    cd "${OUTPUT_DIR}" && \
      "${PWCLI}" --session "${PW_SESSION}" close-all >/dev/null 2>&1
  )
  if ! "${PYTHON_BIN}" "${ROOT_DIR}/test/admin_console_seed.py" cleanup --input "${SEED_JSON}" >> "${PLAYWRIGHT_LOG}" 2>&1; then
    echo "Warning: cleanup failed, check ${PLAYWRIGHT_LOG}" >&2
  fi
}
trap cleanup EXIT

run_pw() {
  local rc=0
  local output=""
  output="$(
    "${PYTHON_BIN}" - "${PW_STEP_TIMEOUT_SECONDS}" "${OUTPUT_DIR}" "${PWCLI}" "${PW_SESSION}" "$@" <<'PY'
import os
import subprocess
import sys

timeout_seconds = float(sys.argv[1])
workdir = sys.argv[2]
pwcli = sys.argv[3]
session = sys.argv[4]
args = sys.argv[5:]
cmd = [pwcli, "--session", session, *args]

try:
    completed = subprocess.run(
        cmd,
        cwd=workdir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    sys.stdout.write((completed.stdout or "") + (completed.stderr or ""))
    raise SystemExit(completed.returncode)
except subprocess.TimeoutExpired as exc:
    stdout = exc.stdout or ""
    stderr = exc.stderr or ""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", "replace")
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    sys.stdout.write(stdout + stderr)
    sys.stdout.write(
        f"[timeout] Playwright command exceeded {int(timeout_seconds)}s: {' '.join(cmd)}\n"
    )
    raise SystemExit(124)
PY
  )" 2>&1 || rc=$?

  if [[ "${rc}" -ne 0 ]] && printf '%s\n' "${output}" | grep -q "is not open"; then
    local warmup_output=""
    local retry_output=""
    local retry_rc=0

    warmup_output="$(
      cd "${OUTPUT_DIR}" && "${PWCLI}" --session "${PW_SESSION}" open about:blank
    )" 2>&1 || true

    retry_output="$(
      cd "${OUTPUT_DIR}" && "${PWCLI}" --session "${PW_SESSION}" "$@"
    )" 2>&1 || retry_rc=$?

    output="${output}

[auto-recover] browser session was not open, ran: open about:blank
${warmup_output}

[auto-recover] retry output
${retry_output}"
    rc="${retry_rc}"
  fi

  {
    echo "===== PWCLI $* ====="
    echo "${output}"
    echo
  } >> "${PLAYWRIGHT_LOG}"

  if [[ "${rc}" -ne 0 ]]; then
    echo "Playwright command failed: $*" >&2
    echo "${output}" >&2
    return "${rc}"
  fi

  if printf '%s\n' "${output}" | grep -q '^### Error'; then
    echo "Playwright runtime error: $*" >&2
    echo "${output}" >&2
    return 1
  fi

  return 0
}

run_pw_code() {
  local code="$1"
  run_pw run-code "${code}"
}

PORT="$(find_free_port)"
BASE_URL="http://127.0.0.1:${PORT}"

echo "Seeding deterministic admin regression data..."
"${PYTHON_BIN}" "${ROOT_DIR}/test/admin_console_seed.py" seed --output "${SEED_JSON}" >/dev/null

PENDING_EMAIL="$(jq -r '.pending_user.email' "${SEED_JSON}")"
DIST_TASK_ID="$(jq -r '.distribution_task.id' "${SEED_JSON}")"
REVIEW_ASSIGNMENT_ID="$(jq -r '.review_assignment.id' "${SEED_JSON}")"
MANUAL_SUBMISSION_ID="$(jq -r '.manual_submission.id' "${SEED_JSON}")"

PENDING_EMAIL_JSON="$(printf '%s' "${PENDING_EMAIL}" | jq -Rs .)"

echo "Starting temporary backend for regression on ${BASE_URL}..."
(
  cd "${ROOT_DIR}"
  exec env METRICS_UPDATE_INTERVAL_SECONDS=0 \
    "${PYTHON_BIN}" -m uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"
) > "${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!

for _ in {1..40}; do
  if curl -fsS "${BASE_URL}/login" >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done

if ! curl -fsS "${BASE_URL}/login" >/dev/null 2>&1; then
  echo "Backend did not become ready. See ${BACKEND_LOG}" >&2
  exit 1
fi

echo "Running Playwright regression (admin login + 审核流 + 分配流)..."

run_pw_code "$(cat <<JS
async (page) => {
  await page.goto('${BASE_URL}/login', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.fill('#username', 'admin@example.com');
  await page.fill('#password', 'admin123');
  await Promise.all([
    page.waitForURL('**/admin/dashboard', { timeout: 15000 }),
    page.click('button[type="submit"]'),
  ]);
  await page.waitForSelector('#admin-user-chip', { timeout: 10000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  await page.goto('${BASE_URL}/admin/users', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForSelector('#user-review-body', { timeout: 10000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  const email = ${PENDING_EMAIL_JSON};
  const pendingRow = page.locator('#user-review-body tr', { hasText: email }).first();

  await pendingRow.waitFor({ state: 'visible', timeout: 15000 });
  await pendingRow.locator('button', { hasText: '进入审核' }).click();
  await pendingRow.waitFor({ state: 'detached', timeout: 15000 });

  await page.selectOption('#user-status-filter', 'under_review');
  await page.waitForTimeout(500);

  const reviewRow = page.locator('#user-review-body tr', { hasText: email }).first();
  await reviewRow.waitFor({ state: 'visible', timeout: 15000 });
  await reviewRow.locator('button', { hasText: '通过' }).click();
  await reviewRow.waitFor({ state: 'detached', timeout: 15000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  await page.goto('${BASE_URL}/admin/tasks', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForSelector('#distribute-task-id', { timeout: 10000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  const taskId = String(${DIST_TASK_ID});
  page.setDefaultTimeout(10000);

  const waitUntil = async (predicate, errorMessage, timeoutMs = 10000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (await predicate()) return;
      await page.waitForTimeout(200);
    }
    throw new Error(errorMessage);
  };

  await page.waitForSelector('#distribute-task-id', { timeout: 10000 });
  await waitUntil(
    () => page.evaluate((id) => {
      const select = document.querySelector('#distribute-task-id');
      if (!select) return false;
      return Array.from(select.querySelectorAll('option')).some((option) => option.value === id);
    }, taskId),
    'Published task options did not load expected task ID'
  );
  await page.selectOption('#distribute-task-id', taskId);
  await page.fill('#candidate-preview-limit', '1');

  await page.click('#view-eligible-btn');
  await waitUntil(
    () => page.evaluate(() => {
      const text = document.querySelector('#task-op-result')?.textContent || '';
      return text.includes('候选达人总数');
    }),
    'Eligible bloggers summary did not render'
  );
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  await page.goto('${BASE_URL}/admin/reviews', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForSelector('#assignment-review-body', { timeout: 10000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  const assignmentId = String(${REVIEW_ASSIGNMENT_ID});
  const queueRow = page.locator('#assignment-review-body tr', { hasText: assignmentId }).first();
  await queueRow.waitFor({ state: 'visible', timeout: 15000 });

  await queueRow.locator('button', { hasText: '进入审核' }).click();

  const inReviewRow = page
    .locator('#assignment-review-body tr', { hasText: assignmentId })
    .filter({ hasText: '审核中' })
    .first();
  await inReviewRow.waitFor({ state: 'visible', timeout: 15000 });

  await inReviewRow.locator('button', { hasText: '通过' }).click();
  await queueRow.waitFor({ state: 'detached', timeout: 15000 });
}
JS
)"

run_pw_code "$(cat <<JS
async (page) => {
  const submissionId = String(${MANUAL_SUBMISSION_ID});
  const manualRow = page.locator('#manual-review-body tr', { hasText: submissionId }).first();
  await manualRow.waitFor({ state: 'visible', timeout: 15000 });
  await manualRow.locator('button', { hasText: '通过' }).click();
  await manualRow.waitFor({ state: 'detached', timeout: 15000 });
}
JS
)"

echo
echo "Admin console regression completed successfully."
echo "Artifacts:"
echo "- Playwright log: ${PLAYWRIGHT_LOG}"
echo "- Backend log: ${BACKEND_LOG}"
echo "- Working dir: ${OUTPUT_DIR}"
