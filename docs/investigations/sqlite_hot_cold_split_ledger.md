# Requirement Alignment Ledger: SQLite Hot/Cold Split

## Metadata
- Ledger ID: `ledger-20260626-sqlite-hot-cold-split`
- Revision: `5`
- Created At: `2026-06-26`
- Updated At: `2026-06-26`
- Project / Workspace / System: `stock_dashboard`
- Current Stage: `archived_for_merge`
- Decision Owner: `user`
- Decision Owner Rule: `thread requester`
- Authoritative Location: `docs/investigations/sqlite_hot_cold_split_ledger.md`
- Secondary References: `plans/archive/plan-20260626-sqlite-hot-cold-split.md`
- Freshness Signal: `Revision and updated date must match downstream plan/run references.`
- Stale / Archive Rule: `Archive after implementation closeout or superseding plan.`
- Last Synced Message / Source Cursor: `MiMo implementation review passed, minor findings fixed, gates passed, plan archived for merge`
- Related Artifacts: `runtime DB inspection, proposed plan in chat`

## Raw Input Log
| Entry ID | Time | Source Type | Source | Immutable Raw Snapshot / Exact Reference | Access Status | Content Hash / Version | Captured By | Notes |
|----------|------|-------------|--------|------------------------------------------|---------------|------------------------|-------------|-------|
| RAW-001 | 2026-06-26 | chat | user | Asked whether timeout cause was DB lock/resource contention and whether SQLite should be split because 2.7G likely contains historical backtest data while daily analysis is forward-looking. | available | chat | Codex | Investigation found `market_bars` dominates DB size. |
| RAW-002 | 2026-06-26 | chat | user | Requested a plan that must be cross-reviewed before implementation. | available | chat | Codex | Produced chat plan. |
| RAW-003 | 2026-06-26 | chat | user | Requested implementation of the SQLite 热冷拆分与刷新降载计划. | available | chat | Codex | Current implementation source. |

## Normalized Understanding
- Goal: Reduce live dashboard timeouts by separating hot runtime data from cold market-history/research data while keeping SQLite v1.
- Background: Runtime DB is about 2.7G; readonly inspection found `market_bars` table plus indexes dominate the file, mostly `1d` history.
- Detailed Needs: Preserve live-facing behavior, add multi-DB configuration, prevent GET fallback writes, provide repeatable migration/verification, publish to runtime and verify real API paths.
- Non-Goals: Do not switch to PostgreSQL in this iteration; do not delete source DB data in the first migration.

## Confirmed In Scope
| ID | Item | Priority | Source Entry IDs | Confirmation Evidence |
|----|------|----------|------------------|-----------------------|
| SCOPE-001 | SQLite hot/cold physical split v1. | P0 | RAW-001, RAW-003 | User approved implementation plan. |
| SCOPE-002 | Cross-review before implementation. | P0 | RAW-002, RAW-003 | Plan states review gate is mandatory. |
| SCOPE-003 | Runtime/API degradation and cache behavior for operations pages. | P0 | RAW-001, RAW-003 | Timeout investigation showed operations endpoints are slow. |
| SCOPE-004 | Repeatable migration scripts and validation. | P0 | RAW-003 | Plan requires repeatable migration and verification. |

## Confirmed Out Of Scope
| ID | Item | Source Entry IDs | Confirmation Evidence |
|----|------|------------------|-----------------------|
| OOS-001 | PostgreSQL migration. | RAW-003 | User-provided plan says v1 keeps SQLite. |
| OOS-002 | Deleting original DB data during first rollout. | RAW-003 | User-provided plan says source DB is retained as archive. |

## Deferred / Later
| ID | Item | Priority | Source Entry IDs | Reason / Trigger |
|----|------|----------|------------------|------------------|
| DEF-001 | Vacuum/physical deletion of cold rows from source DB. | P1 | RAW-003 | Deferred until switched runtime has passed validation. |
| DEF-002 | PostgreSQL or DuckDB adoption. | P2 | RAW-001, RAW-003 | Consider only after SQLite split evidence. |

## Acceptance Criteria
| ID | Criterion | Source Entry IDs | Verification Method | Acceptance Critical |
|----|-----------|------------------|---------------------|---------------------|
| AC-001 | Hot DB can be configured separately from market-history and research archive DBs. | RAW-003 | Unit tests and config inspection. | yes |
| AC-002 | Migration can be rerun without duplicate cold rows or corrupting target DBs. | RAW-003 | Temp-DB migration tests. | yes |
| AC-003 | GET operations endpoints do not write projections in normal fallback path. | RAW-003 | Static/unit tests. | yes |
| AC-004 | Operations endpoints return degraded payloads instead of synchronous 8-10s heavy rebuilds when cache/projection is absent. | RAW-003 | API/unit tests. | yes |
| AC-005 | Runtime publish and real API smoke checks prove live path works. | RAW-003 | publish script plus curl checks. | yes |

## Dependencies
| ID | Item | Depends On | Blocks | Type | Notes |
|----|------|------------|--------|------|-------|
| DEP-001 | Isolated task worktree. | - | implementation | workflow | Required by workspace guard. |
| DEP-002 | External review. | - | implementation | review | Must complete before code changes beyond governance artifacts. |
| DEP-003 | Runtime data access. | DEP-001 | validation | runtime | Required for live smoke after publish. |

## Conflicts / Tensions
| ID | Conflict | Source Entry IDs | Impact | Status | Resolution |
|----|----------|------------------|--------|--------|------------|
| CON-001 | Full physical split is broad; safe rollout requires a reversible v1. | RAW-003 | Migration and runtime risk. | resolved | Implement additive split and config fallback first; do not delete source data. |

## Open Questions
| ID | Question | Why It Matters | Options | Status | Created At Round | Escalation Rule |
|----|----------|----------------|---------|--------|------------------|-----------------|
| Q-001 | None acceptance-critical. | - | - | closed | 1 | - |

## Decisions
| ID | Decision | Chosen Option | Decided By | Evidence | Revisit Trigger |
|----|----------|---------------|------------|----------|-----------------|
| D-001 | Storage technology for v1. | SQLite multi-DB split. | user | User-provided plan. | If split does not meet endpoint targets. |
| D-002 | Original DB treatment. | Keep as source/archive; no first-pass deletion. | user | User-provided plan. | After runtime validation and backup. |

## Constraints And Risks
| ID | Type | Constraint / Risk | Source Entry IDs | Handling |
|----|------|-------------------|------------------|----------|
| R-001 | runtime | Live-facing changes must be published and verified against runtime. | RAW-003 | Include publish and real API smoke gates. |
| R-002 | data | Cold DB split can break historical calculations if repository routing is incomplete. | RAW-003 | Add fallback, tests, and review. |
| R-003 | performance | Large `market_bars` reads can still time out if live endpoints scan cold DB. | RAW-001 | Operations endpoints must prefer projections/degraded responses. |
| R-004 | data | SQLite cannot enforce foreign keys across separate DB files. | RAW-003 | Cold DBs use denormalized archive/query tables without cross-DB FK constraints. |
| R-005 | rollback | Switching to hot DB can create new writes that are not present in the source DB rollback target. | RAW-003 | Back up hot DB before switch; rollback preserves hot DB as merge source. |
| R-006 | runtime | Operations GET routes currently write projections and can 500 on cold cache miss. | RAW-003 | W-004 removes GET writes and returns degraded payloads. |

## Source Coverage Map
| Source ID | Source Requirement | Status | Superseded By | Priority | Acceptance Critical | Coverage Target | Coverage Status | Evidence Required |
|-----------|--------------------|--------|---------------|----------|---------------------|-----------------|-----------------|-------------------|
| SRC-001 | Keep SQLite v1 and split hot/cold DBs. | active | - | P0 | yes | W-001, W-003 | implemented | Config tests and migration tests passed. |
| SRC-002 | New market-history DB for large `1d market_bars`. | active | - | P0 | yes | W-002, W-003 | implemented | Migration verification test passed. |
| SRC-003 | Research archive DB for shortpick/research history. | active | - | P1 | yes | W-002, W-003 | implemented | Migration verification test passed. |
| SRC-004 | GET routes must not synchronously write projection fallback. | active | - | P0 | yes | W-004 | implemented | API tests passed. |
| SRC-005 | Operations pages must avoid heavy sync rebuild and degrade. | active | - | P0 | yes | W-004 | implemented | Endpoint tests passed. |
| SRC-006 | Cross-review before implementation. | active | - | P0 | yes | W-000 | completed | MiMo review log recorded in plan. |
| SRC-007 | Runtime publish and real served API verification. | active | - | P0 | yes | W-006 | completed | Publish succeeded; `/health`, `/dashboard/shell`, `/dashboard/operations*` served API smoke passed. |
| SRC-008 | Cold DBs must avoid cross-DB FK/JOIN assumptions. | active | - | P0 | yes | W-002, W-003 | implemented | Cold schema FK check and repository test passed. |

## Revision Baselines
| Revision | Confirmed By | Confirmed At | Summary | Downstream Artifacts |
|----------|--------------|--------------|---------|----------------------|
| 1 | user request | 2026-06-26 | Implement the approved SQLite hot/cold split plan with cross-review. | plans/active/plan-20260626-sqlite-hot-cold-split.md |
| 2 | MiMo review resolution | 2026-06-26 | Added explicit table placement, no-cross-DB-FK decision, and rollback backup constraint. | plans/active/plan-20260626-sqlite-hot-cold-split.md |
| 3 | implementation | 2026-06-26 | Added cold URL/read-only helpers, migration CLI, market-history repository, and operations degraded/cache-only behavior. | source and tests |
| 4 | runtime validation | 2026-06-26 | Published to local runtime and verified served API response times/degraded behavior. | runtime |
| 5 | merge closeout | 2026-06-26 | Fixed MiMo minor findings, archived plan, and prepared main merge. | runs/archive/2026-06-26-sqlite-hot-cold-split.md |

## Change Log
| Time | Revision | Change | Reason | Updated By |
|------|----------|--------|--------|------------|
| 2026-06-26 | 1 | Created ledger. | Implementation requested. | Codex |
| 2026-06-26 | 2 | Resolved database review blocking finding. | SQLite cross-DB FK is not viable. | Codex |
| 2026-06-26 | 3 | Recorded implementation and test evidence. | Runtime publish requires a clean committed worktree. | Codex |
| 2026-06-26 | 4 | Recorded runtime publish and served API smoke evidence. | Closeout evidence. | Codex |
| 2026-06-26 | 5 | Recorded implementation review and archive-for-merge evidence. | Completion requested. | Codex |
