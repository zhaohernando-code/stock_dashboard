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

within_market_hours() {
  [[ "$NOW_HHMM" > "09:34" && "$NOW_HHMM" < "11:31" ]] || [[ "$NOW_HHMM" > "13:04" && "$NOW_HHMM" < "15:01" ]]
}

if [[ "$NOW_DOW" -gt 5 ]]; then
  if [[ "$NOW_HHMM" == "09:30" ]]; then
    run_phase5_daily_refresh --analysis-only
  fi
  exit 0
fi

case "$NOW_HHMM" in
  "08:10"|"16:20"|"19:20"|"21:15")
    run_phase5_daily_refresh --analysis-only
    ;;
  *)
    if within_market_hours; then
      run_runtime_refresh --ops-only
    fi
    ;;
esac
