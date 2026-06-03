#!/usr/bin/env bash

ashare_resolve_path() {
  python3 - "$1" <<'PY'
from pathlib import Path
import sys

print(Path(sys.argv[1]).expanduser().resolve())
PY
}

ashare_reject_source_artifact_root() {
  local repo_root="$1"
  local artifact_root="$2"

  if [[ "${ASHARE_ALLOW_REPO_ARTIFACT_WRITES:-0}" == "1" ]]; then
    return 0
  fi

  local resolved_root
  local legacy_artifacts
  local legacy_data_artifacts
  resolved_root="$(ashare_resolve_path "$artifact_root")"
  legacy_artifacts="$(ashare_resolve_path "$repo_root/artifacts")"
  legacy_data_artifacts="$(ashare_resolve_path "$repo_root/data/artifacts")"

  case "$resolved_root/" in
    "$legacy_artifacts/"*|"$legacy_data_artifacts/"*)
      {
        printf 'Refusing to use generated artifact root inside source checkout: %s\n' "$resolved_root"
        printf 'Use ASHARE_ARTIFACT_ROOT=%s/data/runtime-artifacts or another ignored runtime directory.\n' "$repo_root"
        printf 'Set ASHARE_ALLOW_REPO_ARTIFACT_WRITES=1 only for an intentional fixture refresh.\n'
      } >&2
      return 1
      ;;
  esac
}

ashare_resolve_local_artifact_root() {
  local repo_root="$1"
  local default_root="${2:-$repo_root/data/runtime-artifacts}"
  export ASHARE_ARTIFACT_ROOT="${ASHARE_ARTIFACT_ROOT:-$default_root}"
  ashare_reject_source_artifact_root "$repo_root" "$ASHARE_ARTIFACT_ROOT"
}
