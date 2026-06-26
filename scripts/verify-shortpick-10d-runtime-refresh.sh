#!/usr/bin/env bash

set -euo pipefail

RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$HOME/codex/runtime/projects/ashare-dashboard}"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$SCRIPT_ROOT/scripts/ashare-backend-env.sh"

# shellcheck source=scripts/ashare-backend-env.sh
source "$BACKEND_ENV_HELPER"
ashare_source_backend_env "$ENV_FILE"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$RUNTIME_ROOT}"

if [[ -n "${ASHARE_RUNTIME_DB_PATH:-}" ]]; then
  DB_PATH="$ASHARE_RUNTIME_DB_PATH"
elif [[ "${ASHARE_DATABASE_URL:-}" == sqlite:///* ]]; then
  DB_PATH="${ASHARE_DATABASE_URL#sqlite:///}"
else
  DB_PATH="$RUNTIME_ROOT/data/ashare_hot.db"
fi
PYTHON_BIN="${ASHARE_RUNTIME_PYTHON_BIN:-$RUNTIME_ROOT/.venv-mac/bin/python}"
VERIFY_DATE="${ASHARE_VERIFY_SHORTPICK_SIGNAL_DATE:-2026-05-26}"
VERIFY_HORIZON="${ASHARE_VERIFY_SHORTPICK_HORIZON:-10}"
VALIDATE_DAYS="${ASHARE_VERIFY_SHORTPICK_VALIDATE_DAYS:-60}"
VALIDATE_LIMIT="${ASHARE_VERIFY_SHORTPICK_VALIDATE_LIMIT:-20}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

if [[ ! -f "$DB_PATH" ]]; then
  echo "Runtime database not found: $DB_PATH" >&2
  exit 1
fi

export PYTHONPATH="$RUNTIME_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export ASHARE_VERIFY_DB_PATH="$DB_PATH"
export ASHARE_VERIFY_DATE="$VERIFY_DATE"
export ASHARE_VERIFY_HORIZON="$VERIFY_HORIZON"

echo "[verify] Runtime root: $RUNTIME_ROOT"
echo "[verify] Runtime database: $DB_PATH"
echo "[verify] Before refresh target snapshot status:"
"$PYTHON_BIN" - <<'PY'
import json
import os
import sqlite3

db_path = os.environ["ASHARE_VERIFY_DB_PATH"]
target_date = os.environ["ASHARE_VERIFY_DATE"]
horizon = int(os.environ["ASHARE_VERIFY_HORIZON"])
target_roles = [
    "frozen_paper_primary",
    "llm_paper_control_primary",
    "market_factor_control_low_turnover_uptrend_next_open_entry",
    "market_factor_control_random_pool",
]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    select
      r.id as run_id,
      r.run_date as run_date,
      c.id as candidate_id,
      c.symbol as symbol,
      json_extract(c.candidate_payload, '$.tracking_role') as tracking_role,
      v.horizon_days as horizon_days,
      v.status as status,
      v.entry_at as entry_at,
      v.exit_at as exit_at,
      json_extract(v.validation_payload, '$.available_forward_bars') as available_forward_bars,
      json_extract(v.validation_payload, '$.required_forward_bars') as required_forward_bars
    from shortpick_experiment_runs r
    join shortpick_candidates c on c.run_id = r.id
    left join shortpick_validation_snapshots v
      on v.candidate_id = c.id and v.horizon_days = ?
    where r.run_date = ?
      and json_extract(c.candidate_payload, '$.tracking_role') in ({placeholders})
    order by tracking_role, c.id
    """.format(placeholders=",".join("?" for _ in target_roles)),
    [horizon, target_date, *target_roles],
).fetchall()
print(json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2))
PY

echo "[verify] Running shortpick recent validation refresh with existing market data only."
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-lab-validate-recent \
  --database-url "sqlite:///$DB_PATH" \
  --days "$VALIDATE_DAYS" \
  --limit "$VALIDATE_LIMIT" \
  --horizon "$VERIFY_HORIZON" \
  --existing-market-data-only

echo "[verify] After refresh target snapshot assertion:"
"$PYTHON_BIN" - <<'PY'
import json
import os
import sqlite3
import sys

db_path = os.environ["ASHARE_VERIFY_DB_PATH"]
target_date = os.environ["ASHARE_VERIFY_DATE"]
horizon = int(os.environ["ASHARE_VERIFY_HORIZON"])
target_roles = [
    "frozen_paper_primary",
    "llm_paper_control_primary",
    "market_factor_control_low_turnover_uptrend_next_open_entry",
    "market_factor_control_random_pool",
]

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    select
      r.id as run_id,
      r.run_date as run_date,
      c.id as candidate_id,
      c.symbol as symbol,
      json_extract(c.candidate_payload, '$.tracking_role') as tracking_role,
      v.horizon_days as horizon_days,
      v.status as status,
      v.entry_at as entry_at,
      v.exit_at as exit_at,
      v.stock_return as stock_return,
      v.excess_return as excess_return
    from shortpick_experiment_runs r
    join shortpick_candidates c on c.run_id = r.id
    left join shortpick_validation_snapshots v
      on v.candidate_id = c.id and v.horizon_days = ?
    where r.run_date = ?
      and json_extract(c.candidate_payload, '$.tracking_role') in ({placeholders})
    order by tracking_role, c.id
    """.format(placeholders=",".join("?" for _ in target_roles)),
    [horizon, target_date, *target_roles],
).fetchall()
payload = [dict(row) for row in rows]
completed_roles = {str(row["tracking_role"]) for row in payload if row["status"] == "completed"}
missing_roles = sorted(set(target_roles) - completed_roles)
if missing_roles:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    print(
        f"Missing completed {horizon}d snapshots for {target_date}: {', '.join(missing_roles)}",
        file=sys.stderr,
    )
    sys.exit(1)
print(json.dumps(payload, ensure_ascii=False, indent=2))
print(f"[verify] PASS: {target_date} has completed {horizon}d snapshots for all target paper-tracking roles.")
PY
