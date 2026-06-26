# Run: DB Path Regression Guards

- Run ID: `2026-06-26-db-path-regression-guards`
- Branch: `codex/db-path-regression-guards`
- Base branch: `main`

## Goal
Prevent future runtime or maintenance scripts from silently writing to the legacy `ashare_dashboard.db` after the SQLite hot/cold split.

## Source
- User asked for strict checking and modification after read-only audit found live runtime coverage was correct, but some no-env maintenance defaults still pointed at the old DB path.

## Implementation Summary
- Changed Python default DB URL from `data/ashare_dashboard.db` to `data/ashare_hot.db`.
- Updated live/runtime scripts so no-env fallbacks target `ashare_hot.db`:
  - `start-local-backend.sh`
  - `run-scheduled-refresh.sh`
  - `prewarm-shortpick-v2-paper-cache.sh`
  - `refresh-shortpick-v1-control-combined-ledger.sh`
  - `refresh-shortpick-v2-paper-ledger.sh`
  - `run-shortpick-v2-h10-paper-governance.sh`
  - `verify-shortpick-10d-runtime-refresh.sh`
  - `migrate_005_add_market_cap_columns.py`
  - `backfill_shortpick_prefreeze_20260508_paper_tracking.py`
- Added `scripts/ashare-backend-env.sh` so scripts can source the shared backend env file while preserving caller-provided DB/runtime overrides.
- Added static regression tests for:
  - default DB URL is hot;
  - live defaults do not point to `ashare_dashboard.db`;
  - runtime scripts retain hot DB fallbacks;
  - backend env sourcing preserves explicit DB overrides;
  - shell syntax remains valid.
- Extended `check-artifact-git-governance.py` so pre-push governance checks also reject the old scheduled/backend DB fallback.
- Updated README/PROCESS wording from legacy live DB to hot DB semantics.

## Review Results
- MiMo code review: `NO_BLOCKING_CODE_REVIEW`.
- Medium finding fixed: `run-shortpick-v2-h10-paper-governance.sh` now checks missing sqlite DB files before launching long CLI work.
- Minor findings fixed or covered:
  - migration default path aligned to relative `data/ashare_hot.db`;
  - static regex now also catches `Path.home()...ashare_dashboard.db`;
  - explicit negative assertion added for `DEFAULT_DB_URL`.

## Gate Results
- H10 guard smoke: explicit `ASHARE_DATABASE_URL=sqlite:////tmp/ashare_missing_hot_guard_check.db` fails early with `Runtime database not found`.
- Targeted static tests: `25 passed`.
- `scripts/check-artifact-git-governance.py`: pass.
- Full pytest: `978 passed, 173 deselected, 6 subtests passed in 36.47s`.
- Policy audit: pass; no direct config reads, formula side effects, missing config lineage, or new unclassified items.

## Remaining Allowed Legacy References
- `ashare_dashboard.db` remains in backup-retention patterns, migration/cutover test fixtures, publish quiescence compatibility checks for old running processes, and documentation that identifies the original DB as a retained archive/rollback source.

## Runtime/Release Notes
- Runtime publish and post-publish API smoke are required before final closeout because startup scripts changed.
- Rollback is the previous `main` commit plus runtime republish; runtime data files are not modified by this code change.
