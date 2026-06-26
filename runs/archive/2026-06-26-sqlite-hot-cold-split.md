# Run: SQLite Hot/Cold Split

- Run ID: `2026-06-26-sqlite-hot-cold-split`
- Plan path: `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260626-sqlite-hot-cold-split/plans/archive/plan-20260626-sqlite-hot-cold-split.md`
- Work item IDs: `W-000` through `W-006`
- Branch: `codex/sqlite-hot-cold-split`
- Base branch: `main`

## Goal
Implement and land the approved SQLite hot/cold split foundation and operations API load-shedding behavior.

## Non-goals
- No PostgreSQL migration.
- No deletion/vacuum of the original 2.7G runtime DB in this run.
- No automatic live cutover to a newly slimmed hot DB file in this run.

## Plan Evidence
- User requested implementation of the reviewed SQLite hot/cold split plan.
- Database review blocking issue about cross-DB FK/JOIN was resolved by denormalized cold archive tables.
- Runtime review blocking issue about operations GET projection writes was resolved by cache/projection/degraded-only GET behavior.

## Implementation Summary
- Added hot/history/research DB URL helpers plus read-only engine/session support with `PRAGMA query_only=ON`.
- Added `sqlite-hot-cold-split` CLI and denormalized cold schemas:
  - `market_bar_history` for broad `1d` bars.
  - `research_archive_rows` for shortpick/research source rows.
- Added `MarketHistoryRepository` as the explicit read-only cold market-history adapter.
- Changed operations endpoints so cache/projection misses return explicit degraded payloads instead of synchronous heavy rebuilds or projection writes.
- Updated tests for no-write/no-rebuild operations behavior and split migration idempotence/read-only/FK boundaries.
- After implementation review, fixed minor findings:
  - Closed read-only repository SQLite connections in `finally`.
  - Switched migration copies from `fetchall()` to `fetchmany()` batches.

## Review Results
- MiMo database review: no unresolved blocking findings after table placement/no-cross-DB-FK revision.
- MiMo runtime/API review: blocking GET projection write finding accepted and fixed.
- MiMo implementation review: `NO_BLOCKING_CODE_REVIEW`; two minor findings fixed before merge.

## Gate Results
- `python3 -m pytest -q`: `973 passed, 173 deselected, 6 subtests passed`.
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`: pass.
- Plan validator: pass after schema status/order correction.

## Runtime Evidence
- Published runtime commit: `46e3900f85e91673687cbd29ea8e36f307d02b95`.
- Publish command: `ASHARE_PUBLISH_MAX_WAIT_SECONDS=600 ASHARE_PUBLISH_VERIFY_MODE=local ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`.
- Release manifest: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/local-20260626T110855Z-46e3900.json`.
- Served API smoke after publish:
  - `/health`: 200, 0.017s.
  - `/dashboard/shell`: 200, 0.408s.
  - `/dashboard/scheduled-refresh-status`: 200, 0.040s.
  - `/dashboard/operations`: 200, degraded cache miss, 0.009s.
  - `/dashboard/operations/summary`: 200, projection response, 0.022s.
  - `/dashboard/operations/details?section=portfolios`: 200, degraded cache miss, 0.012s.
  - `/dashboard/operations/details?section=replay`: 200, degraded cache miss, 0.012s.

## Risk And Rollback Notes
- The original runtime DB remains intact; this run does not delete source rows.
- Rollback remains a code/config rollback to the previous main commit; no destructive migration was run.
- The cold migration command is explicit maintenance tooling and should be run with source/target backups before any real physical split cutover.

## Archive And Merge Result
- Plan moved from `plans/active/` to `plans/archive/`.
- Merge/push result to be recorded by git history and final closeout.
