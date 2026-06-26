#!/usr/bin/env bash

ashare_source_backend_env() {
  local env_file="${1:?env file is required}"
  local names=(
    ASHARE_DATABASE_URL
    ASHARE_HOT_DATABASE_URL
    ASHARE_MARKET_HISTORY_DATABASE_URL
    ASHARE_RESEARCH_ARCHIVE_DATABASE_URL
    ASHARE_RUNTIME_DB_PATH
    ASHARE_RUNTIME_ROOT
    ASHARE_LOCAL_VENV_PATH
    ASHARE_ARTIFACT_ROOT
  )
  local preserved_names=()
  local preserved_values=()
  local name
  for name in "${names[@]}"; do
    if [[ ${!name+x} ]]; then
      preserved_names+=("$name")
      preserved_values+=("${!name}")
    fi
  done

  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi

  local index
  for index in "${!preserved_names[@]}"; do
    export "${preserved_names[$index]}=${preserved_values[$index]}"
  done
}
