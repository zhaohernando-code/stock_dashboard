#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_ROOT="${ASHARE_RUNTIME_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
DATA_DIR="${ASHARE_RUNTIME_DATA_DIR:-$RUNTIME_ROOT/data}"
ARCHIVE_ROOT="${ASHARE_DB_BACKUP_ARCHIVE_ROOT:-$HOME/Library/Logs/codex-archive/ashare-dashboard-db-backups}"
KEEP_RECENT="${ASHARE_DB_BACKUP_KEEP_RECENT:-2}"
MIN_AGE_DAYS="${ASHARE_DB_BACKUP_MIN_AGE_DAYS:-1}"
ARCHIVE_RETENTION_DAYS="${ASHARE_DB_BACKUP_ARCHIVE_RETENTION_DAYS:-30}"
DRY_RUN="${ASHARE_DB_BACKUP_PRUNE_DRY_RUN:-0}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "Runtime data directory not found: $DATA_DIR" >&2
  exit 0
fi

if ! [[ "$KEEP_RECENT" =~ ^[0-9]+$ && "$MIN_AGE_DAYS" =~ ^[0-9]+$ && "$ARCHIVE_RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  echo "Retention settings must be non-negative integers." >&2
  exit 2
fi

mkdir -p "$ARCHIVE_ROOT"

now_epoch="$(date '+%s')"
min_age_seconds=$((MIN_AGE_DAYS * 86400))

file_mtime_epoch() {
  local path="$1"
  stat -f '%m' "$path"
}

file_is_open() {
  local path="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof "$path" >/dev/null 2>&1
  else
    return 1
  fi
}

archive_backup() {
  local path="$1"
  local rel="${path#$DATA_DIR/}"
  local stamp
  stamp="$(date -r "$path" '+%Y%m%dT%H%M%S')"
  local archive_name="${rel//\//__}.${stamp}.gz"
  local archive_path="$ARCHIVE_ROOT/$archive_name"

  if [[ -e "$archive_path" ]]; then
    echo "Archive already exists, removing source: $path -> $archive_path"
    if [[ "$DRY_RUN" != "1" ]]; then
      rm -f "$path"
    fi
    return 0
  fi

  echo "Archiving runtime DB backup: $path -> $archive_path"
  if [[ "$DRY_RUN" != "1" ]]; then
    gzip -c "$path" > "$archive_path"
    touch -r "$path" "$archive_path"
    rm -f "$path"
  fi
}

candidates=()
while IFS= read -r path; do
  candidates+=("$path")
done < <(
  find "$DATA_DIR" "$DATA_DIR/backups" -maxdepth 1 -type f \
    \( -name 'ashare_dashboard.before-*.db' -o -name 'ashare_dashboard.db.bak-*' \) \
    -print 2>/dev/null | sort -u
)

if (( ${#candidates[@]} == 0 )); then
  echo "No runtime DB backup files found."
else
  newest_first=()
  while IFS= read -r path; do
    newest_first+=("$path")
  done < <(
    for path in "${candidates[@]}"; do
      printf '%s\t%s\n' "$(file_mtime_epoch "$path")" "$path"
    done | sort -rn | cut -f2-
  )

  index=0
  for path in "${newest_first[@]}"; do
    index=$((index + 1))
    if (( index <= KEEP_RECENT )); then
      echo "Keeping recent runtime DB backup: $path"
      continue
    fi

    mtime="$(file_mtime_epoch "$path")"
    age_seconds=$((now_epoch - mtime))
    if (( age_seconds < min_age_seconds )); then
      echo "Keeping young runtime DB backup: $path"
      continue
    fi

    if file_is_open "$path"; then
      echo "Skipping open runtime DB backup: $path" >&2
      continue
    fi

    archive_backup "$path"
  done
fi

if (( ARCHIVE_RETENTION_DAYS > 0 )); then
  find "$ARCHIVE_ROOT" -type f -name '*.gz' -mtime +"$ARCHIVE_RETENTION_DAYS" -print -delete
fi
