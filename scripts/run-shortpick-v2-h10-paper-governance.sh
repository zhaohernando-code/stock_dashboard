#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$HOME/codex/runtime/projects/ashare-dashboard}"

ENV_FILE="${ASHARE_LOCAL_BACKEND_ENV_FILE:-$HOME/.config/codex/ashare-dashboard.backend.env}"
BACKEND_ENV_HELPER="$REPO_ROOT/scripts/ashare-backend-env.sh"

# shellcheck source=scripts/ashare-backend-env.sh
source "$BACKEND_ENV_HELPER"
ashare_source_backend_env "$ENV_FILE"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$RUNTIME_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_DB_PATH="${ASHARE_RUNTIME_DB_PATH:-$RUNTIME_ROOT/data/ashare_hot.db}"
DATABASE_URL="${ASHARE_DATABASE_URL:-sqlite:///$RUNTIME_DB_PATH}"
OUTPUT_DIR="${ASHARE_H10_PAPER_GOVERNANCE_OUTPUT_DIR:-output}"
DOC_MARKER="${ASHARE_H10_PAPER_GOVERNANCE_DOC_MARKER:-H10 paper governance; future true-forward only; fixed90 diagnostic only}"
DOC_PATH="${ASHARE_H10_PAPER_GOVERNANCE_DOC_PATH:-docs/archive/SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md}"

REPLAY_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-quiet-champion-replay-artifact.json"
SELECTION_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-quiet-champion-selection-artifact.json"
PARAMETER_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-parameter-significance-artifact.json"
RANK_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-rank-ablation-artifact.json"
ROBUSTNESS_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json"
EXECUTION_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-quiet-execution-decomposition-artifact.json"
PAPER_GOVERNANCE_ARTIFACT="$OUTPUT_DIR/shortpick-v2-h10-paper-governance-artifact.json"
PUBLISHED_ARTIFACT="${ASHARE_H10_PAPER_GOVERNANCE_PUBLISHED_ARTIFACT:-docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json}"

step() {
  printf '[h10-paper-governance] %s\n' "$*"
}

if [[ "$DATABASE_URL" == sqlite:///* ]]; then
  DB_PATH="${DATABASE_URL#sqlite:///}"
  if [[ ! -f "$DB_PATH" ]]; then
    echo "Runtime database not found: $DB_PATH" >&2
    exit 1
  fi
fi

mkdir -p "$OUTPUT_DIR" "$(dirname "$PUBLISHED_ARTIFACT")"
export PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

step "Generating h10 quiet champion replay artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-strategy-search \
  --database-url "$DATABASE_URL" \
  --candidate-batch h10_quiet_champion \
  --horizon-days 10 \
  --initial-cash 200000 \
  --output "$REPLAY_ARTIFACT"

step "Generating h10 quiet champion selection artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-rule-selection \
  --replay-artifact "$REPLAY_ARTIFACT" \
  --threshold-profile h10_quiet_champion \
  --output "$SELECTION_ARTIFACT"

step "Generating h10 parameter-significance artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-parameter-significance \
  --database-url "$DATABASE_URL" \
  --horizon-days 10 \
  --initial-cash 200000 \
  --output "$PARAMETER_ARTIFACT"

step "Generating h10 rank-ablation artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-rank-ablation \
  --database-url "$DATABASE_URL" \
  --horizon-days 10 \
  --initial-cash 200000 \
  --output "$RANK_ARTIFACT"

step "Generating h10 benchmark robustness artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-robustness \
  --database-url "$DATABASE_URL" \
  --replay-artifact "$REPLAY_ARTIFACT" \
  --selection-artifact "$SELECTION_ARTIFACT" \
  --horizon-days 10 \
  --initial-cash 200000 \
  --output "$ROBUSTNESS_ARTIFACT"

step "Generating h10 execution decomposition artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-execution-decomposition \
  --database-url "$DATABASE_URL" \
  --replay-artifact "$REPLAY_ARTIFACT" \
  --selection-artifact "$SELECTION_ARTIFACT" \
  --horizon-days 10 \
  --initial-cash 200000 \
  --output "$EXECUTION_ARTIFACT"

step "Validating h10 robustness/execution source artifacts"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-artifact-validate \
  --robustness-artifact "$ROBUSTNESS_ARTIFACT" \
  --execution-artifact "$EXECUTION_ARTIFACT"

step "Building h10 paper-governance artifact"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-paper-governance \
  --rank-ablation-artifact "$RANK_ARTIFACT" \
  --parameter-significance-artifact "$PARAMETER_ARTIFACT" \
  --robustness-artifact "$ROBUSTNESS_ARTIFACT" \
  --execution-artifact "$EXECUTION_ARTIFACT" \
  --output "$PAPER_GOVERNANCE_ARTIFACT" \
  --published-artifact "$PUBLISHED_ARTIFACT"

step "Validating h10 paper-governance artifacts"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-paper-governance-validate \
  --artifact "$PAPER_GOVERNANCE_ARTIFACT"
"$PYTHON_BIN" -m ashare_evidence.cli shortpick-v2-h10-paper-governance-validate \
  --artifact "$PUBLISHED_ARTIFACT"

step "Verifying durable doc marker"
"$PYTHON_BIN" - "$DOC_PATH" "$DOC_MARKER" <<'PY'
from pathlib import Path
import sys

doc_path = Path(sys.argv[1])
marker = sys.argv[2]
body = doc_path.read_text(encoding="utf-8")
if marker not in body:
    raise SystemExit(f"Missing durable doc marker in {doc_path}: {marker}")
PY

step "Done"
