#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

VENV_PATH="${ASHARE_LOCAL_VENV_PATH:-$REPO_ROOT/.venv-mac}"
PYTHON_BIN="$VENV_PATH/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python virtualenv at $VENV_PATH" >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$REPO_ROOT/data/ashare_dashboard.db}"

TIMEZONE="${ASHARE_REFRESH_TIMEZONE:-Asia/Shanghai}"
NOW_HHMM="${ASHARE_SCHEDULED_REFRESH_AT:-$(TZ="$TIMEZONE" date '+%H:%M')}"
NOW_DOW="$(TZ="$TIMEZONE" date '+%u')"
TODAY_STR="$(TZ="$TIMEZONE" date '+%Y-%m-%d')"
POSTMARKET_REFRESH_AT="${ASHARE_POSTMARKET_DAILY_REFRESH_AT:-16:20}"
REFRESH_STATE_DIR="${ASHARE_SCHEDULED_REFRESH_STATE_DIR:-$HOME/.cache/codex/ashare-dashboard-refresh}"
RUN_LOCK_DIR="$REFRESH_STATE_DIR/run.lock"
DAILY_REFRESH_TIMEOUT_SECONDS="${ASHARE_DAILY_REFRESH_TIMEOUT_SECONDS:-7200}"
SHORTPICK_TIMEOUT_SECONDS="${ASHARE_SHORTPICK_TIMEOUT_SECONDS:-7200}"
NETWORK_CHECK_ENABLED="${ASHARE_REFRESH_NETWORK_CHECK:-1}"
NETWORK_PROBES="${ASHARE_REFRESH_NETWORK_PROBES:-https://www.baidu.com/ https://push2.eastmoney.com/}"

run_runtime_refresh() {
  "$PYTHON_BIN" -m ashare_evidence.cli refresh-runtime-data \
    --database-url "$ASHARE_DATABASE_URL" \
    --skip-simulation \
    "$@"
}

run_phase5_daily_refresh() {
  "$PYTHON_BIN" -m ashare_evidence.cli phase5-daily-refresh \
    --database-url "$ASHARE_DATABASE_URL" \
    --skip-simulation \
    "$@"
}

run_shortpick_lab() {
  "$PYTHON_BIN" -m ashare_evidence.cli shortpick-lab-run \
    --database-url "$ASHARE_DATABASE_URL" \
    --rounds-per-model "${ASHARE_SHORTPICK_ROUNDS_PER_MODEL:-5}"
}

time_ge() {
  [[ "$1" == "$2" || "$1" > "$2" ]]
}

time_lt() {
  [[ "$1" < "$2" ]]
}

date_add_days() {
  local base_date="$1"
  local delta_days="$2"
  "$PYTHON_BIN" - "$base_date" "$delta_days" <<'PY'
from datetime import date, timedelta
import sys

base = date.fromisoformat(sys.argv[1])
delta = int(sys.argv[2])
print((base + timedelta(days=delta)).isoformat())
PY
}

network_available() {
  if [[ "$NETWORK_CHECK_ENABLED" == "0" ]]; then
    return 0
  fi
  local probe
  for probe in $NETWORK_PROBES; do
    if curl -fsSL --connect-timeout 5 --max-time 10 "$probe" >/dev/null 2>&1; then
      return 0
    fi
  done
  echo "Network unavailable; deferring scheduled daily refresh." >&2
  return 1
}

acquire_run_lock() {
  mkdir -p "$REFRESH_STATE_DIR"
  if mkdir "$RUN_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$RUN_LOCK_DIR/pid"
    return 0
  fi

  local existing_pid=""
  if [[ -f "$RUN_LOCK_DIR/pid" ]]; then
    existing_pid="$(cat "$RUN_LOCK_DIR/pid" 2>/dev/null || true)"
  fi
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Another scheduled refresh is already running (pid=$existing_pid); skipping this tick." >&2
    return 1
  fi

  rm -rf "$RUN_LOCK_DIR"
  if mkdir "$RUN_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$RUN_LOCK_DIR/pid"
    return 0
  fi
  echo "Unable to acquire scheduled refresh lock at $RUN_LOCK_DIR; skipping this tick." >&2
  return 1
}

release_run_lock() {
  if [[ -f "$RUN_LOCK_DIR/pid" ]] && [[ "$(cat "$RUN_LOCK_DIR/pid" 2>/dev/null || true)" == "$$" ]]; then
    rm -rf "$RUN_LOCK_DIR"
  fi
}

write_run_context() {
  local target_date="$1"
  local slot_name="$2"
  mkdir -p "$RUN_LOCK_DIR"
  {
    printf 'pid=%s\n' "$$"
    printf 'target_date=%s\n' "$target_date"
    printf 'slot=%s\n' "$slot_name"
    printf 'started_at=%s\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
  } > "$RUN_LOCK_DIR/context"
}

run_with_timeout() {
  local timeout_seconds="$1"
  shift
  "$@" &
  local child_pid=$!
  local deadline=$((SECONDS + timeout_seconds))
  while kill -0 "$child_pid" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      echo "Command timed out after ${timeout_seconds}s: $*" >&2
      kill "$child_pid" 2>/dev/null || true
      sleep 5
      kill -9 "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
      return 124
    fi
    sleep 2
  done
  wait "$child_pid"
}

slot_state_file() {
  local target_date="$1"
  local slot_name="$2"
  printf '%s/daily-%s-%s.ok\n' "$REFRESH_STATE_DIR" "$target_date" "$slot_name"
}

slot_completed() {
  local target_date="$1"
  local slot_name="$2"
  [[ -f "$(slot_state_file "$target_date" "$slot_name")" ]]
}

mark_slot_completed() {
  local target_date="$1"
  local slot_name="$2"
  mkdir -p "$REFRESH_STATE_DIR"
  {
    printf 'target_date=%s\n' "$target_date"
    printf 'slot=%s\n' "$slot_name"
    printf 'completed_at=%s\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
  } > "$(slot_state_file "$target_date" "$slot_name")"
  rm -f "$(slot_state_file "$target_date" "$slot_name" | sed 's/\.ok$/.failed/')" \
    "$(slot_state_file "$target_date" "$slot_name" | sed 's/\.ok$/.deferred/')"
}

mark_slot_deferred() {
  local target_date="$1"
  local slot_name="$2"
  local reason="$3"
  mkdir -p "$REFRESH_STATE_DIR"
  {
    printf 'target_date=%s\n' "$target_date"
    printf 'slot=%s\n' "$slot_name"
    printf 'deferred_at=%s\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
    printf 'reason=%s\n' "$reason"
  } > "$(slot_state_file "$target_date" "$slot_name" | sed 's/\.ok$/.deferred/')"
}

mark_slot_failed() {
  local target_date="$1"
  local slot_name="$2"
  local exit_code="$3"
  local started_at="$4"
  mkdir -p "$REFRESH_STATE_DIR"
  {
    printf 'target_date=%s\n' "$target_date"
    printf 'slot=%s\n' "$slot_name"
    printf 'started_at=%s\n' "$started_at"
    printf 'failed_at=%s\n' "$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
    printf 'exit_code=%s\n' "$exit_code"
    printf 'reason=%s\n' "daily refresh 执行失败，将等待下一次 5 分钟轮询重试。"
  } > "$(slot_state_file "$target_date" "$slot_name" | sed 's/\.ok$/.failed/')"
}

run_daily_refresh_slot() {
  local target_date="$1"
  local slot_name="$2"
  if slot_completed "$target_date" "$slot_name"; then
    return 0
  fi
  if ! network_available; then
    mark_slot_deferred "$target_date" "$slot_name" "当前未联网，daily refresh 等待联网后补跑。"
    return 0
  fi
  if ! acquire_run_lock; then
    return 0
  fi
  local started_at
  started_at="$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
  write_run_context "$target_date" "$slot_name"
  trap release_run_lock EXIT
  echo "Running ${slot_name} daily refresh for ${target_date} at ${NOW_HHMM}."
  if run_with_timeout "$DAILY_REFRESH_TIMEOUT_SECONDS" run_phase5_daily_refresh --analysis-only; then
    mark_slot_completed "$target_date" "$slot_name"
    release_run_lock
    trap - EXIT
    return 0
  fi
  local exit_code=$?
  mark_slot_failed "$target_date" "$slot_name" "$exit_code" "$started_at"
  release_run_lock
  trap - EXIT
  return 1
}

run_shortpick_lab_slot() {
  local target_date="$1"
  local slot_name="shortpick_lab"
  if [[ "${ASHARE_ENABLE_SHORTPICK_LAB:-0}" != "1" ]]; then
    return 0
  fi
  if slot_completed "$target_date" "$slot_name"; then
    return 0
  fi
  if ! network_available; then
    mark_slot_deferred "$target_date" "$slot_name" "当前未联网，短投试验田等待联网后补跑。"
    return 0
  fi
  if ! acquire_run_lock; then
    return 0
  fi
  local started_at
  started_at="$(TZ="$TIMEZONE" date '+%Y-%m-%dT%H:%M:%S%z')"
  write_run_context "$target_date" "$slot_name"
  trap release_run_lock EXIT
  echo "Running shortpick lab for ${target_date} at ${NOW_HHMM}."
  if run_with_timeout "$SHORTPICK_TIMEOUT_SECONDS" run_shortpick_lab; then
    mark_slot_completed "$target_date" "$slot_name"
    release_run_lock
    trap - EXIT
    return 0
  fi
  local exit_code=$?
  mark_slot_failed "$target_date" "$slot_name" "$exit_code" "$started_at"
  release_run_lock
  trap - EXIT
  return 1
}

within_market_hours() {
  [[ "$NOW_HHMM" > "09:30" && "$NOW_HHMM" < "11:31" ]] || [[ "$NOW_HHMM" > "13:00" && "$NOW_HHMM" < "15:01" ]]
}

CACHE_DIR="$HOME/.cache/codex"
TRADE_CALENDAR_CACHE="$CACHE_DIR/trade_calendar.json"

is_trading_day() {
  local date_to_check="${1:-$TODAY_STR}"
  mkdir -p "$CACHE_DIR"
  local cache_path="$CACHE_DIR/trade_calendar_${date_to_check}.json"
  TRADE_CALENDAR_CACHE="$cache_path" _TRADE_DATE_CHECK="$date_to_check" "$PYTHON_BIN" -c "
import json, os, sys
from datetime import date

cache_path = os.environ.get('TRADE_CALENDAR_CACHE', '')
target = os.environ.get('_TRADE_DATE_CHECK', '')

# Check daily cache
if os.path.exists(cache_path):
    try:
        cache = json.load(open(cache_path))
        if cache.get('date') == target:
            sys.exit(0 if cache.get('is_trading_day') else 1)
    except Exception:
        pass

# Query AKShare
try:
    import akshare as ak
    dates = ak.tool_trade_date_hist_sina()
    trade_dates = set(dates['trade_date'].tolist())
    is_td = date.fromisoformat(target) in trade_dates
    json.dump({'date': target, 'is_trading_day': is_td}, open(cache_path, 'w'))
    sys.exit(0 if is_td else 1)
except Exception as e:
    # If API fails (network issue, etc.), assume trading day to be safe
    print(f'Warning: trade calendar check failed: {e}', file=sys.stderr)
    sys.exit(0)
" 2>&1
}

previous_trading_date() {
  local offset candidate
  for offset in -1 -2 -3 -4 -5 -6 -7; do
    candidate="$(date_add_days "$TODAY_STR" "$offset")"
    if is_trading_day "$candidate"; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

run_due_daily_refreshes() {
  if [[ "$NOW_DOW" -le 5 ]] && time_ge "$NOW_HHMM" "$POSTMARKET_REFRESH_AT" && is_trading_day "$TODAY_STR"; then
    run_daily_refresh_slot "$TODAY_STR" "postmarket"
    run_shortpick_lab_slot "$TODAY_STR"
    return 0
  fi

  local previous_date=""
  if network_available && previous_date="$(previous_trading_date)"; then
    run_daily_refresh_slot "$previous_date" "postmarket"
    run_shortpick_lab_slot "$previous_date"
  fi

  return 0
}

if time_ge "$NOW_HHMM" "$POSTMARKET_REFRESH_AT" || [[ "$NOW_DOW" -gt 5 ]]; then
  run_due_daily_refreshes
elif is_trading_day "$TODAY_STR" && within_market_hours; then
  run_runtime_refresh --ops-only
else
  run_due_daily_refreshes
fi
