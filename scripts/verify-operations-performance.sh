#!/usr/bin/env bash

set -euo pipefail

API_BASE_URL="${ASHARE_LOCAL_API_BASE_URL:-http://127.0.0.1:8000}"
FRONTEND_URL="${ASHARE_LOCAL_FRONTEND_URL:-http://127.0.0.1:5174/}"
SAMPLE_SYMBOL="${ASHARE_RELEASE_OPERATIONS_SAMPLE_SYMBOL:-${ASHARE_OPERATIONS_PREWARM_SAMPLE_SYMBOL:-600519.SH}}"
MAX_API_SECONDS="${ASHARE_OPERATIONS_PERF_MAX_API_SECONDS:-5}"
MAX_PAGE_SECONDS="${ASHARE_OPERATIONS_PERF_MAX_PAGE_SECONDS:-2}"
CURL_TIMEOUT_SECONDS="${ASHARE_OPERATIONS_PERF_CURL_TIMEOUT_SECONDS:-30}"
CURL_BIN="${CURL_BIN:-curl}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUNTIME_ROOT=""
EXPECTED_COMMIT=""
SELF_TEST=0

usage() {
  cat <<'EOF'
Usage: scripts/verify-operations-performance.sh [options]

Options:
  --self-test                 Run deterministic parser/budget/commit checks without network calls.
  --api-base-url URL          Local API base URL. Default: http://127.0.0.1:8000
  --frontend-url URL          Served frontend URL. Default: http://127.0.0.1:5174/
  --sample-symbol SYMBOL      Operations sample symbol. Default: 600519.SH
  --max-api-seconds VALUE     Budget for each operations API endpoint. Default: 5
  --max-page-seconds VALUE    Budget for the frontend page shell. Default: 2
  --runtime-root PATH         Runtime root whose latest-successful.commit should be checked.
  --expected-commit SHA       Expected runtime commit; requires --runtime-root.
  --curl-timeout-seconds N    Curl max-time for each probe. Default: 30
  -h, --help                  Show this help.
EOF
}

fail() {
  echo "[perf] ERROR: $*" >&2
  return 1
}

normalize_base_url() {
  local value="$1"
  while [[ "$value" == */ ]]; do
    value="${value%/}"
  done
  printf '%s' "$value"
}

within_budget() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import sys

observed = float(sys.argv[1])
budget = float(sys.argv[2])
raise SystemExit(0 if observed <= budget else 1)
PY
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
    return 1
  fi
}

check_runtime_commit() {
  local runtime_root="$1"
  local expected_commit="$2"
  if [[ -z "$runtime_root" && -z "$expected_commit" ]]; then
    return 0
  fi
  if [[ -z "$runtime_root" || -z "$expected_commit" ]]; then
    fail "--runtime-root and --expected-commit must be supplied together"
    return 1
  fi

  local commit_file="$runtime_root/output/releases/latest-successful.commit"
  if [[ ! -f "$commit_file" ]]; then
    fail "Runtime commit file missing: $commit_file"
    return 1
  fi

  local actual_commit
  local expected_normalized
  actual_commit="$(tr -d '[:space:]' < "$commit_file")"
  expected_normalized="$(printf '%s' "$expected_commit" | tr -d '[:space:]')"
  if [[ "$actual_commit" != "$expected_normalized" ]]; then
    fail "Runtime commit mismatch: expected=$expected_normalized actual=$actual_commit"
    return 1
  fi
  echo "[perf] runtime commit ok: $actual_commit"
}

api_url() {
  local endpoint="$1"
  printf '%s%s' "$(normalize_base_url "$API_BASE_URL")" "$endpoint"
}

measure_url() {
  local label="$1"
  local url="$2"
  local budget_seconds="$3"
  local body_file
  local duration
  body_file="$(mktemp)"
  if ! duration="$("$CURL_BIN" --noproxy "*" -fsS -o "$body_file" -w '%{time_total}' \
    --max-time "$CURL_TIMEOUT_SECONDS" "$url")"; then
    rm -f "$body_file"
    fail "$label request failed: $url"
    return 1
  fi
  rm -f "$body_file"

  if within_budget "$duration" "$budget_seconds"; then
    echo "[perf] $label ${duration}s <= ${budget_seconds}s $url"
    return 0
  fi
  echo "[perf] $label ${duration}s > ${budget_seconds}s $url" >&2
  return 1
}

run_self_test() {
  require_command "$PYTHON_BIN"

  if ! within_budget 1.25 2; then
    fail "self-test expected 1.25 <= 2"
    return 1
  fi
  if within_budget 2.25 2; then
    fail "self-test expected 2.25 > 2"
    return 1
  fi

  local temp_root
  temp_root="$(mktemp -d)"
  mkdir -p "$temp_root/output/releases"
  printf '%s\n' "abc123" > "$temp_root/output/releases/latest-successful.commit"
  check_runtime_commit "$temp_root" "abc123" >/dev/null
  if check_runtime_commit "$temp_root" "def456" >/dev/null 2>&1; then
    rm -rf "$temp_root"
    fail "self-test expected commit mismatch to fail"
    return 1
  fi
  rm -rf "$temp_root"

  temp_root="$(mktemp -d)"
  if check_runtime_commit "$temp_root" "abc123" >/dev/null 2>&1; then
    rm -rf "$temp_root"
    fail "self-test expected missing commit file to fail"
    return 1
  fi
  rm -rf "$temp_root"

  if [[ "$(normalize_base_url "http://127.0.0.1:8000///")" != "http://127.0.0.1:8000" ]]; then
    fail "self-test URL normalization failed"
    return 1
  fi

  echo "[perf:self-test] ok"
}

while (($#)); do
  case "$1" in
    --self-test)
      SELF_TEST=1
      shift
      ;;
    --api-base-url)
      API_BASE_URL="${2:?missing value for --api-base-url}"
      shift 2
      ;;
    --frontend-url)
      FRONTEND_URL="${2:?missing value for --frontend-url}"
      shift 2
      ;;
    --sample-symbol)
      SAMPLE_SYMBOL="${2:?missing value for --sample-symbol}"
      shift 2
      ;;
    --max-api-seconds)
      MAX_API_SECONDS="${2:?missing value for --max-api-seconds}"
      shift 2
      ;;
    --max-page-seconds)
      MAX_PAGE_SECONDS="${2:?missing value for --max-page-seconds}"
      shift 2
      ;;
    --runtime-root)
      RUNTIME_ROOT="${2:?missing value for --runtime-root}"
      shift 2
      ;;
    --expected-commit)
      EXPECTED_COMMIT="${2:?missing value for --expected-commit}"
      shift 2
      ;;
    --curl-timeout-seconds)
      CURL_TIMEOUT_SECONDS="${2:?missing value for --curl-timeout-seconds}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ "$SELF_TEST" == "1" ]]; then
  run_self_test
  exit 0
fi

require_command "$CURL_BIN"
require_command "$PYTHON_BIN"
check_runtime_commit "$RUNTIME_ROOT" "$EXPECTED_COMMIT"

status=0
measure_url \
  "operations-portfolios" \
  "$(api_url "/dashboard/operations/details?section=portfolios&sample_symbol=$SAMPLE_SYMBOL")" \
  "$MAX_API_SECONDS" || status=1
measure_url \
  "operations-replay" \
  "$(api_url "/dashboard/operations/details?section=replay&sample_symbol=$SAMPLE_SYMBOL")" \
  "$MAX_API_SECONDS" || status=1
measure_url "frontend-page" "$FRONTEND_URL" "$MAX_PAGE_SECONDS" || status=1

if [[ "$status" == "0" ]]; then
  echo "[perf] ok"
fi
exit "$status"
