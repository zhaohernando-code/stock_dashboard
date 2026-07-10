#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$HOME/codex/runtime/projects/ashare-dashboard}"
BACKEND_URL="${ASHARE_LOCAL_BACKEND_URL:-http://127.0.0.1:8000/health}"
FRONTEND_URL="${ASHARE_LOCAL_FRONTEND_URL:-http://127.0.0.1:5174/}"
LOCAL_API_BASE_URL="${ASHARE_LOCAL_API_BASE_URL:-http://127.0.0.1:8000/}"
CANONICAL_BASE_URL="${ASHARE_CANONICAL_BASE_URL:-https://hernando-zhao.cn/projects/ashare-dashboard/}"
BACKEND_ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
FRONTEND_ENV_FILE="${ASHARE_LOCAL_FRONTEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.frontend.env}"
RSYNC_BIN="${RSYNC_BIN:-rsync}"
MAX_WAIT_SECONDS="${ASHARE_PUBLISH_MAX_WAIT_SECONDS:-180}"
REFRESH_MODE="${ASHARE_PUBLISH_REFRESH_MODE:-sync}"
REFRESH_TIMEOUT_SECONDS="${ASHARE_PUBLISH_REFRESH_TIMEOUT_SECONDS:-900}"
BACKUP_MODE="${ASHARE_PUBLISH_BACKUP_MODE:-skip}"
VERIFY_MODE="${ASHARE_PUBLISH_VERIFY_MODE:-canonical}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RELEASE_OPERATIONS_SAMPLE_SYMBOL="${ASHARE_RELEASE_OPERATIONS_SAMPLE_SYMBOL:-${ASHARE_OPERATIONS_PREWARM_SAMPLE_SYMBOL:-600519.SH}}"
RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS="${ASHARE_RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS:-90}"
FRONTEND_DIR="$REPO_ROOT/frontend"

if [[ -f "$FRONTEND_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$FRONTEND_ENV_FILE"
  set +a
fi

if ! command -v "$RSYNC_BIN" >/dev/null 2>&1; then
  echo "Missing required command: $RSYNC_BIN" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "Missing required command: npm" >&2
  exit 1
fi

if ! command -v launchctl >/dev/null 2>&1; then
  echo "Missing required command: launchctl" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl" >&2
  exit 1
fi

if ! command -v lsof >/dev/null 2>&1; then
  echo "Missing required command: lsof" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Missing required command: $PYTHON_BIN" >&2
  exit 1
fi

ensure_frontend_dependencies() {
  if [[ ! -f "$FRONTEND_DIR/package-lock.json" ]]; then
    echo "Frontend package-lock.json missing: $FRONTEND_DIR/package-lock.json" >&2
    exit 1
  fi

  if [[ -x "$FRONTEND_DIR/node_modules/.bin/tsc" && -x "$FRONTEND_DIR/node_modules/.bin/vite" ]]; then
    return 0
  fi

  echo "[publish] Installing frontend dependencies with npm ci"
  npm --prefix "$FRONTEND_DIR" ci
}

LOCK_DIR="$HOME/.codex-system/locks"
PUBLISH_LOCK_DIR="$LOCK_DIR/publish.lock"
LOCK_MAX_AGE_SECONDS=300

acquire_publish_lock() {
  mkdir -p "$LOCK_DIR"
  if mkdir "$PUBLISH_LOCK_DIR" 2>/dev/null; then
    printf "pid=%s\nstarted=%s\noperation=publish\n" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$PUBLISH_LOCK_DIR/meta"
    return 0
  fi
  if [[ -d "$PUBLISH_LOCK_DIR" ]]; then
    local lock_age
    lock_age="$(($(date +%s) - $(stat -f %m "$PUBLISH_LOCK_DIR" 2>/dev/null || date +%s)))"
    if [[ "$lock_age" -lt "$LOCK_MAX_AGE_SECONDS" ]]; then
      echo "Refusing to publish: lock file exists (age=${lock_age}s)." >&2
      echo "Another publish may be in progress. Remove $PUBLISH_LOCK_DIR if this is stale." >&2
      exit 1
    fi
    echo "Stale lock directory (age=${lock_age}s) — overwriting." >&2
    rm -rf "$PUBLISH_LOCK_DIR"
    if mkdir "$PUBLISH_LOCK_DIR" 2>/dev/null; then
      printf "pid=%s\nstarted=%s\noperation=publish\n" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$PUBLISH_LOCK_DIR/meta"
      return 0
    fi
  fi
  echo "Refusing to publish: unable to acquire publish lock at $PUBLISH_LOCK_DIR." >&2
  exit 1
}

release_publish_lock() {
  rm -rf "$PUBLISH_LOCK_DIR"
}

DIRTY_STATUS="$(git -C "$REPO_ROOT" status --short --untracked-files=normal)"
if [[ -n "$DIRTY_STATUS" ]]; then
  echo "Refusing to publish from a dirty worktree. Commit or stash changes first." >&2
  echo "$DIRTY_STATUS" >&2
  exit 1
fi

acquire_publish_lock

# Pause scheduled refresh during publish to avoid concurrent DB writes
SCHEDULED_LABEL="com.codex.ashare-dashboard.scheduled-refresh"
SCHEDULED_PLIST="$HOME/Library/LaunchAgents/${SCHEDULED_LABEL}.plist"
SCHEDULED_REFRESH_PAUSED=0
SCHEDULED_REFRESH_STATE_DIR="${ASHARE_SCHEDULED_REFRESH_STATE_DIR:-$HOME/.cache/codex/ashare-dashboard-refresh}"
SCHEDULED_RUN_LOCK_DIR="$SCHEDULED_REFRESH_STATE_DIR/run.lock"
SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS="${ASHARE_PUBLISH_SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS:-180}"

ensure_scheduled_refresh_calendar() {
  if [[ ! -f "$SCHEDULED_PLIST" ]]; then
    return 0
  fi
  "$PYTHON_BIN" - "$SCHEDULED_PLIST" <<'PY'
from pathlib import Path
import plistlib
import sys

path = Path(sys.argv[1])
with path.open("rb") as handle:
    payload = plistlib.load(handle)
intervals = payload.get("StartCalendarInterval")
if isinstance(intervals, dict):
    intervals = [intervals]
elif not isinstance(intervals, list):
    intervals = []
required = [
    {"Hour": 13, "Minute": 55},
    {"Hour": 14, "Minute": 0},
    {"Hour": 14, "Minute": 5},
    {"Hour": 16, "Minute": 20},
]
seen = {
    (int(item.get("Hour")), int(item.get("Minute")))
    for item in intervals
    if isinstance(item, dict) and "Hour" in item and "Minute" in item
}
for item in required:
    key = (item["Hour"], item["Minute"])
    if key not in seen:
        intervals.append(item)
payload["StartCalendarInterval"] = sorted(
    intervals,
    key=lambda item: (int(item.get("Hour", 0)), int(item.get("Minute", 0))),
)
payload["StartInterval"] = 300
# RunAtLoad must stay false: launchctl bootstrap (below, and any reload during
# governance work) would otherwise fire a full ~50min phase5-daily-refresh on
# every publish/reload. The StartCalendarInterval/StartInterval ticks plus the
# .ok slot guard already trigger exactly one refresh per trading day.
payload["RunAtLoad"] = False
with path.open("wb") as handle:
    plistlib.dump(payload, handle)
PY
}

scheduled_refresh_lock_active() {
  if [[ ! -f "$SCHEDULED_RUN_LOCK_DIR/pid" ]]; then
    return 1
  fi
  local lock_pid
  lock_pid="$(cat "$SCHEDULED_RUN_LOCK_DIR/pid" 2>/dev/null || true)"
  [[ -n "$lock_pid" ]] && kill -0 "$lock_pid" 2>/dev/null
}

scheduled_refresh_process_active() {
  pgrep -f "$RUNTIME_ROOT/scripts/run-scheduled-refresh.sh" >/dev/null 2>&1 && return 0
  pgrep -f "ashare_evidence.cli phase5-daily-refresh .*${RUNTIME_ROOT}/data/ashare_dashboard.db" >/dev/null 2>&1 && return 0
  pgrep -f "ashare_evidence.cli refresh-runtime-data .*${RUNTIME_ROOT}/data/ashare_dashboard.db" >/dev/null 2>&1 && return 0
  return 1
}

wait_for_scheduled_refresh_quiescent() {
  local deadline=$((SECONDS + SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS))
  while (( SECONDS < deadline )); do
    if ! scheduled_refresh_lock_active && ! scheduled_refresh_process_active; then
      return 0
    fi
    sleep 2
  done
  echo "Scheduled refresh is still running after ${SCHEDULED_REFRESH_QUIESCE_TIMEOUT_SECONDS}s; refusing to publish while DB-heavy refresh is active." >&2
  return 1
}

resume_scheduled_refresh() {
  if [[ "$SCHEDULED_REFRESH_PAUSED" != "1" ]]; then
    return 0
  fi
  echo "[publish] Resuming scheduled-refresh"
  if [[ ! -f "$SCHEDULED_PLIST" ]]; then
    echo "Scheduled refresh plist missing: $SCHEDULED_PLIST" >&2
    return 1
  fi
  ensure_scheduled_refresh_calendar
  launchctl bootout "gui/$(id -u)" "$SCHEDULED_PLIST" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$SCHEDULED_PLIST"
  # Do NOT kickstart here. The agent is loaded with RunAtLoad=false; its
  # StartCalendarInterval/StartInterval ticks plus the .ok slot guard fire
  # exactly one phase5-daily-refresh per trading day. Force-starting on every
  # publish would launch a ~50min full refresh that holds the DB lock and times
  # out the dashboard (the original outage).
  SCHEDULED_REFRESH_PAUSED=0
}

cleanup_on_exit() {
  local status=$?
  if [[ "${SCHEDULED_REFRESH_PAUSED:-0}" == "1" ]]; then
    resume_scheduled_refresh || true
  fi
  release_publish_lock
  exit "$status"
}

trap cleanup_on_exit EXIT

echo "[publish] Pausing scheduled-refresh"
launchctl stop "$SCHEDULED_LABEL" 2>/dev/null || true
SCHEDULED_REFRESH_PAUSED=1
wait_for_scheduled_refresh_quiescent

COMMIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"

BACKUP_ROOT="$HOME/codex/runtime/projects/ashare-dashboard.backups"
BACKUP_DIR="$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT_SHA:0:7}"
MAX_BACKUPS=5

mkdir -p "$RUNTIME_ROOT"

echo "[publish] Release source commit: $COMMIT_SHA"

if [[ "$BACKUP_MODE" == "skip" ]]; then
  echo "[publish] Runtime backup skipped (ASHARE_PUBLISH_BACKUP_MODE=skip)"
elif [[ "$BACKUP_MODE" == "source" ]]; then
  echo "[publish] Backing up runtime source files to $BACKUP_DIR"
  mkdir -p "$BACKUP_DIR"
  if [ -d "$RUNTIME_ROOT/frontend/dist" ] || [ -d "$RUNTIME_ROOT/src" ]; then
    rsync -a \
      --exclude ".git" \
      --exclude "data" \
      --exclude "output" \
      --exclude ".venv" \
      --exclude ".venv-mac" \
      --exclude "venv" \
      --exclude "node_modules" \
      --exclude "frontend/node_modules" \
      "$RUNTIME_ROOT/" "$BACKUP_DIR/"
    echo "[publish] Backup saved: $BACKUP_DIR"
    echo "[publish] Rollback: rsync -a --delete --exclude data --exclude output $BACKUP_DIR/ $RUNTIME_ROOT/"
  else
    echo "[publish] Runtime empty — skipping backup (first publish?)"
  fi

  backup_count=$(ls -d "$BACKUP_ROOT"/*/ 2>/dev/null | wc -l | tr -d ' ')
  if [ "$backup_count" -gt "$MAX_BACKUPS" ]; then
    ls -dt "$BACKUP_ROOT"/*/ | tail -n +$((MAX_BACKUPS + 1)) | xargs rm -rf
    echo "[publish] Rotated backups, keeping last $MAX_BACKUPS"
  fi
else
  echo "Unsupported ASHARE_PUBLISH_BACKUP_MODE: $BACKUP_MODE" >&2
  echo "Use 'skip' for normal deploys or 'source' for a small source-only rollback snapshot." >&2
  exit 1
fi
echo "[publish] Building repo frontend"
ensure_frontend_dependencies
npm --prefix "$FRONTEND_DIR" run build

echo "[publish] Syncing repo to runtime"
rm -rf "$RUNTIME_ROOT/.git"
"$RSYNC_BIN" -a --delete \
  --exclude ".git" \
  --exclude "data" \
  --exclude "output" \
  --exclude ".venv" \
  --exclude ".venv-mac" \
  --exclude "venv" \
  --exclude "node_modules" \
  --exclude "frontend/node_modules" \
  "$REPO_ROOT/" "$RUNTIME_ROOT/"

echo "[publish] Restarting LaunchAgents"

stale_process_pids() {
  local process_pattern="$1"
  if [[ -z "$process_pattern" ]]; then
    return 0
  fi
  pgrep -f "$process_pattern" 2>/dev/null || true
}

wait_for_stale_processes_to_exit() {
  local process_pattern="$1"
  if [[ -z "$process_pattern" ]]; then
    return 0
  fi
  for _i in $(seq 1 50); do
    if [[ -z "$(stale_process_pids "$process_pattern")" ]]; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

kill_stale_runtime_processes() {
  local display_name="$1"
  local process_pattern="$2"
  local pids
  pids="$(stale_process_pids "$process_pattern")"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  echo "[publish] Terminating stale $display_name process(es): $(echo "$pids" | tr '\n' ' ')"
  echo "$pids" | xargs kill -TERM 2>/dev/null || true
  wait_for_stale_processes_to_exit "$process_pattern" && return 0

  pids="$(stale_process_pids "$process_pattern")"
  if [[ -n "$pids" ]]; then
    echo "[publish] Killing stale $display_name process(es): $(echo "$pids" | tr '\n' ' ')"
    echo "$pids" | xargs kill -KILL 2>/dev/null || true
  fi
}

restart_agent() {
  local plist_path="$1"
  local port="$2"
  local display_name="$3"
  local process_pattern="$4"

  echo "[publish] Restarting $display_name (port $port)"

  # Remove the job from the current GUI domain to prevent KeepAlive from
  # racing a replacement process onto the same port while we wait for release.
  launchctl bootout "gui/$(id -u)" "$plist_path" 2>/dev/null || true

  # Wait up to 5s for the old process to release the port.
  for _i in $(seq 1 50); do
    lsof -ti ":$port" >/dev/null 2>&1 || break
    sleep 0.1
  done

  # Hard-kill if something (e.g. a process launched outside launchd)
  # still holds the port.
  lsof -ti ":$port" | xargs kill -KILL 2>/dev/null || true
  # Also remove stale children that did not bind the port. A prior failed
  # LaunchAgent start can leave a uvicorn/node process alive but unreachable,
  # which makes the served route intermittently fail with ECONNREFUSED.
  kill_stale_runtime_processes "$display_name" "$process_pattern"
  sleep 0.2

  # Re-add the job to launchd. RunAtLoad will trigger the start.
  launchctl bootstrap "gui/$(id -u)" "$plist_path"
}

BACKEND_PLIST="$HOME/Library/LaunchAgents/com.codex.ashare-dashboard.backend.plist"
FRONTEND_PLIST="$HOME/Library/LaunchAgents/com.codex.ashare-dashboard.frontend.plist"

restart_agent "$BACKEND_PLIST" 8000 "backend" "uvicorn ashare_evidence.api:app .*--port 8000|start-local-backend.sh"
restart_agent "$FRONTEND_PLIST" 5174 "frontend" "serve-frontend-dist.mjs .*--port 5174|start-local-frontend.sh"

wait_for_health() {
  local url="$1"
  local deadline=$((SECONDS + MAX_WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $url" >&2
  return 1
}

echo "[publish] Waiting for backend health"
wait_for_health "$BACKEND_URL"

echo "[publish] Waiting for frontend health"
wait_for_health "$FRONTEND_URL"

repo_index_html="$REPO_ROOT/frontend/dist/index.html"
runtime_index_html="$RUNTIME_ROOT/frontend/dist/index.html"

if [[ ! -f "$repo_index_html" ]]; then
  echo "Repo build output missing: $repo_index_html" >&2
  exit 1
fi

if [[ ! -f "$runtime_index_html" ]]; then
  echo "Runtime build output missing: $runtime_index_html" >&2
  exit 1
fi

repo_assets="$(grep -Eo 'assets/index-[^\" ]+\.(js|css)' "$repo_index_html" | tr '\n' ' ' | sed 's/[[:space:]]*$//')"
served_assets="$(curl -fsS "$FRONTEND_URL" | grep -Eo 'assets/index-[^\" ]+\.(js|css)' | tr '\n' ' ' | sed 's/[[:space:]]*$//')"

if [[ -z "$repo_assets" ]]; then
  echo "Unable to read repo asset names from $repo_index_html" >&2
  exit 1
fi

if [[ "$repo_assets" != "$served_assets" ]]; then
  echo "Served frontend assets do not match repo build." >&2
  echo "repo:   $repo_assets" >&2
  echo "served: $served_assets" >&2
  exit 1
fi

mkdir -p "$RUNTIME_ROOT/output/releases"
if [[ "$VERIFY_MODE" == "canonical" ]]; then
  echo "[publish] Verifying repo/runtime/canonical parity"
  MANIFEST_PATH="$(
    cd "$REPO_ROOT"
    PYTHONPATH=src "$PYTHON_BIN" -m ashare_evidence.release_verifier \
      --repo-root "$REPO_ROOT" \
      --runtime-root "$RUNTIME_ROOT" \
      --local-frontend-url "$FRONTEND_URL" \
      --local-api-base-url "$LOCAL_API_BASE_URL" \
      --canonical-base-url "$CANONICAL_BASE_URL" \
      --expected-commit-sha "$COMMIT_SHA" \
      --release-output-root "$RUNTIME_ROOT/output/releases" \
      --operations-sample-symbol "$RELEASE_OPERATIONS_SAMPLE_SYMBOL" \
      --operations-warmup-timeout-seconds "$RELEASE_OPERATIONS_WARMUP_TIMEOUT_SECONDS" \
      --skip-latest-successful-update
  )"
elif [[ "$VERIFY_MODE" == "local" ]]; then
  echo "[publish] Canonical release verifier skipped (ASHARE_PUBLISH_VERIFY_MODE=local)"
  MANIFEST_PATH="$RUNTIME_ROOT/output/releases/local-$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT_SHA:0:7}.json"
  cat > "$MANIFEST_PATH" <<JSON
{
  "schema_version": 1,
  "verification_mode": "local",
  "commit_sha": "$COMMIT_SHA",
  "runtime_root": "$RUNTIME_ROOT",
  "local_frontend_url": "$FRONTEND_URL",
  "local_api_base_url": "$LOCAL_API_BASE_URL",
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
JSON
else
  echo "Unsupported ASHARE_PUBLISH_VERIFY_MODE: $VERIFY_MODE" >&2
  echo "Use 'canonical' for full release verification or 'local' for auto deploys." >&2
  exit 1
fi

echo "[publish] Triggering post-deploy data refresh"
if [[ -f "$BACKEND_ENV_FILE" ]]; then
  set -a
  source "$BACKEND_ENV_FILE"
  set +a
fi
export ASHARE_ARTIFACT_ROOT="${ASHARE_ARTIFACT_ROOT:-$RUNTIME_ROOT/data/artifacts}"
if [[ "$REFRESH_MODE" == "skip" ]]; then
  echo "[publish] Data refresh skipped by ASHARE_PUBLISH_REFRESH_MODE=skip"
elif [[ "$REFRESH_MODE" == "async" ]]; then
  PYTHONPATH="$RUNTIME_ROOT/src" "$PYTHON_BIN" -m ashare_evidence.cli refresh-runtime-data \
      --analysis-only --skip-simulation 2>&1 | sed 's/^/[publish:refresh] /' &
  REFRESH_PID=$!
  echo "[publish] Data refresh triggered (PID $REFRESH_PID)"
else
  REFRESH_LOG="$(mktemp)"
  PYTHONPATH="$RUNTIME_ROOT/src" "$PYTHON_BIN" -m ashare_evidence.cli refresh-runtime-data \
      --analysis-only --skip-simulation >"$REFRESH_LOG" 2>&1 &
  REFRESH_PID=$!
  REFRESH_DEADLINE=$((SECONDS + REFRESH_TIMEOUT_SECONDS))
  while kill -0 "$REFRESH_PID" 2>/dev/null; do
    if (( SECONDS >= REFRESH_DEADLINE )); then
      kill "$REFRESH_PID" 2>/dev/null || true
      wait "$REFRESH_PID" 2>/dev/null || true
      sed 's/^/[publish:refresh] /' "$REFRESH_LOG" || true
      rm -f "$REFRESH_LOG"
      echo "[publish] Data refresh timed out after ${REFRESH_TIMEOUT_SECONDS}s" >&2
      exit 1
    fi
    sleep 1
  done
  if ! wait "$REFRESH_PID"; then
    sed 's/^/[publish:refresh] /' "$REFRESH_LOG" || true
    rm -f "$REFRESH_LOG"
    echo "[publish] Data refresh failed" >&2
    exit 1
  fi
  sed 's/^/[publish:refresh] /' "$REFRESH_LOG" || true
  rm -f "$REFRESH_LOG"
  echo "[publish] Data refresh completed"
fi

echo "[publish] Runtime frontend matches repo build"
echo "[publish] Backend healthy at $BACKEND_URL"
echo "[publish] Frontend healthy at $FRONTEND_URL"
echo "[publish] Release parity manifest: $MANIFEST_PATH"

echo "[publish] Running deploy verification..."
if [[ "$VERIFY_MODE" == "local" ]]; then
    echo "[publish] Full deploy verification skipped by ASHARE_PUBLISH_VERIFY_MODE=local"
elif bash "$REPO_ROOT/scripts/verify-deploy.sh"; then
    echo "[publish] VERIFICATION PASSED"
else
    echo "[publish] VERIFICATION FAILED — check output above"
    exit 1
fi

cp "$MANIFEST_PATH" "$RUNTIME_ROOT/output/releases/latest-successful.json"
printf '%s\n' "$COMMIT_SHA" > "$RUNTIME_ROOT/output/releases/latest-successful.commit"
