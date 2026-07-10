#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RELEASE_ROOT="$RUNTIME_ROOT/output/releases"
KEEP_RELEASES="${ASHARE_RUNTIME_RELEASE_KEEP_RECENT:-10}"
DRY_RUN="${ASHARE_RUNTIME_OUTPUT_PRUNE_DRY_RUN:-0}"

if ! [[ "$KEEP_RELEASES" =~ ^[0-9]+$ ]]; then
  echo "ASHARE_RUNTIME_RELEASE_KEEP_RECENT must be a non-negative integer." >&2
  exit 2
fi

remove_path() {
  local path="$1"
  if [[ ! -e "$path" ]]; then
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "Would remove reconstructible runtime path: $path"
  else
    echo "Removing reconstructible runtime path: $path"
    rm -rf "$path"
  fi
}

if [[ -d "$RELEASE_ROOT" ]]; then
  release_dirs=()
  while IFS= read -r path; do
    release_dirs+=("$path")
  done < <(
    find "$RELEASE_ROOT" -mindepth 1 -maxdepth 1 -type d -print0 \
      | xargs -0 stat -f '%m	%N' 2>/dev/null \
      | sort -rn \
      | cut -f2-
  )
  for ((index = KEEP_RELEASES; index < ${#release_dirs[@]}; index++)); do
    remove_path "${release_dirs[$index]}"
  done

  local_manifests=()
  while IFS= read -r path; do
    local_manifests+=("$path")
  done < <(
    find "$RELEASE_ROOT" -mindepth 1 -maxdepth 1 -type f -name 'local-*.json' -print0 \
      | xargs -0 stat -f '%m	%N' 2>/dev/null \
      | sort -rn \
      | cut -f2-
  )
  for ((index = KEEP_RELEASES; index < ${#local_manifests[@]}; index++)); do
    remove_path "${local_manifests[$index]}"
  done
fi

remove_path "$RUNTIME_ROOT/frontend/node_modules"
remove_path "$RUNTIME_ROOT/output/chrome-acceptance-profile"
remove_path "$RUNTIME_ROOT/output/playwright"
