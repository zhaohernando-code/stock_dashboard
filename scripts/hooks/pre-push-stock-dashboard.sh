#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

common_git_dir="$(git rev-parse --git-common-dir)"
if [[ "$common_git_dir" != /* ]]; then
  common_git_dir="$repo_root/$common_git_dir"
fi
common_project_root="$(dirname "$common_git_dir")"

if [ "$(basename "$repo_root")" != "stock_dashboard" ] && [ "$(basename "$common_project_root")" != "stock_dashboard" ]; then
  exit 0
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "pre-push blocked: stock_dashboard working tree is dirty." >&2
  echo "Commit or stash local changes before pushing so main/upstream containment is auditable." >&2
  exit 1
fi

while read -r local_ref local_sha remote_ref remote_sha; do
  [ -n "${local_ref:-}" ] || continue
  if [ "$remote_ref" = "refs/heads/main" ]; then
    main_sha="$(git rev-parse main)"
    if [ "$local_sha" != "$main_sha" ]; then
      echo "pre-push blocked: pushes to origin/main must use the local main tip." >&2
      echo "local_ref=$local_ref local_sha=$local_sha main=$main_sha" >&2
      exit 1
    fi
  fi
done

# Git exports repository-local environment variables to hooks. Clear them before
# running tests so nested temporary git repositories are evaluated on their own.
unset $(git rev-parse --local-env-vars)

echo "pre-push: checking agent and hook constraints"
bash scripts/check-agent-constraints.sh

echo "pre-push: running stock_dashboard fast regression"
python3 -m pytest -q

echo "pre-push: running policy governance audit"
PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit \
  --fail-on-new-unclassified \
  --fail-on-direct-config-read \
  --fail-on-formula-side-effects \
  --fail-on-missing-config-lineage
