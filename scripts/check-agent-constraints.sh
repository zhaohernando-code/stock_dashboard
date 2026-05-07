#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

require_text() {
  local file="$1"
  local needle="$2"
  if ! grep -Fq -- "$needle" "$file"; then
    echo "agent-constraints blocked: $file missing required text: $needle" >&2
    exit 1
  fi
}

forbid_text() {
  local file="$1"
  local needle="$2"
  if grep -Fq -- "$needle" "$file"; then
    echo "agent-constraints blocked: $file contains forbidden stale text: $needle" >&2
    exit 1
  fi
}

require_executable() {
  local file="$1"
  if [ ! -x "$file" ]; then
    echo "agent-constraints blocked: $file must be executable" >&2
    exit 1
  fi
}

require_text CLAUDE.md "bash scripts/install-git-hooks.sh"
require_text CLAUDE.md "python3 -m pytest -q"
require_text CLAUDE.md "policy-audit"
require_text CLAUDE.md "--fail-on-new-unclassified"
require_text CLAUDE.md "bash scripts/test-runtime-integration.sh"
require_text CLAUDE.md "scripts/hooks/pre-push-stock-dashboard.sh"
require_text CLAUDE.md "origin/main"
require_text CLAUDE.md "policy_config_loader"
require_text CLAUDE.md "publish-local-runtime.sh"
forbid_text CLAUDE.md "PYTHONPATH=src python3 -m pytest tests/ -v"

require_text PROJECT_RULES.md "scripts/install-git-hooks.sh"
require_text PROJECT_RULES.md "policy-audit"
require_text PROJECT_RULES.md "默认 \`pytest\` 只允许承担开发快回归职责"

require_text pyproject.toml "not slow_integration and not runtime_integration"
require_text .github/workflows/ci.yml "bash scripts/check-agent-constraints.sh"
require_text .github/workflows/ci.yml "python3 -m pytest -q"
require_text .github/workflows/ci.yml "policy-audit"
forbid_text .github/workflows/ci.yml "pytest tests/ -v"

require_text scripts/hooks/pre-push-stock-dashboard.sh "bash scripts/check-agent-constraints.sh"
require_text scripts/hooks/pre-push-stock-dashboard.sh "python3 -m pytest -q"
require_text scripts/hooks/pre-push-stock-dashboard.sh "policy-audit"
require_text scripts/install-git-hooks.sh "../../.githooks"
require_text scripts/install-git-hooks.sh "pre-push"

require_executable scripts/check-agent-constraints.sh
require_executable scripts/test-runtime-integration.sh
require_executable scripts/hooks/pre-push-stock-dashboard.sh
require_executable scripts/install-git-hooks.sh

echo "agent-constraints: pass"
