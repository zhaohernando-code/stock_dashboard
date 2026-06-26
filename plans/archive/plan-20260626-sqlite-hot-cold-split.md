---
schema_version: 1
plan_id: "plan-20260626-sqlite-hot-cold-split"
title: "SQLite Hot/Cold Split"
status: "archived"
created_at: "2026-06-26"
source_request: "Implement the approved SQLite hot/cold split and refresh load-reduction plan."
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 3
---

# Plan: SQLite Hot/Cold Split

## Compaction-Resistant Summary
Goal: Reduce live dashboard timeouts by splitting hot runtime data from cold market/research history while keeping SQLite v1.
Scope: Add multi-DB config, migration/verification tooling, operations degrade/cache behavior, and runtime validation.
Out of scope: PostgreSQL migration and deleting source DB rows during first rollout.
Dependencies: ledger `ledger-20260626-sqlite-hot-cold-split` revision 5, isolated worktree, cross-review.
Major risks: broken data routing, hidden GET writes, live runtime publish failure, incomplete migration validation.
Approval state: implementation completed, published to runtime, and verified with served local API smoke checks.

## Goal
Implement a reversible v1 SQLite hot/cold split that keeps live dashboard paths fast while preserving historical market and research data.

## Problem / Rationale
Readonly diagnosis found the runtime DB is about 2.7G, with `market_bars` plus indexes consuming roughly 2.49G and mostly `1d` history. Live operations endpoints time out because heavy reads/rebuilds share one SQLite file with refresh writes. The first fix should reduce hot-path DB pressure without a PostgreSQL migration.

## Source Requirement Coverage
| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Keep SQLite v1 and split hot/cold DBs. | W-001, W-003 | covered | - | Config tests and temp DB migration tests. |
| SRC-002 | New market-history DB for large `1d market_bars`. | W-002, W-003 | covered | - | Migration verification report. |
| SRC-003 | New research archive DB for shortpick/research history. | W-002, W-003 | covered | - | Migration verification report. |
| SRC-004 | GET routes must not synchronously write projection fallback. | W-004 | covered | - | Static/API tests. |
| SRC-005 | Operations pages must degrade instead of heavy sync rebuild on cache/projection miss. | W-004 | covered | - | Endpoint tests and smoke timings. |
| SRC-006 | Cross-review must pass before implementation. | W-000 | covered | - | External review findings with no unresolved blocking issues. |
| SRC-007 | Runtime publish and real API verification are required. | W-006 | covered | - | Publish command and real curl checks. |

## Production Path Fidelity
| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | FastAPI runtime reads hot DB and serves dashboard routes. | Published runtime API smoke checks. | FastAPI app/runtime publish | none | matches_product_path | `/health`, `/dashboard/shell`, `/dashboard/operations*` curl timings. |
| PF-002 | Scheduled refresh writes forward outputs and projections. | CLI tests plus runtime scheduled-refresh status smoke. | scheduled refresh CLI | controlled temp DB for tests | controlled_simulation | Unit test evidence plus runtime status endpoint. |
| PF-003 | Migration creates cold DBs from existing SQLite source. | Temp source/target DB migration test and readonly runtime verification command. | migration script | controlled temp DB for automated test; real runtime verification is readonly | controlled_simulation | Row counts, time ranges, indexes verified. |

## Scope
### In Scope
- Add hot, market-history, and research-archive database URL configuration.
- Add repeatable migration and verification commands.
- Add repository/loader boundaries for hot vs cold reads; cold DBs are denormalized archive/query stores with no cross-database foreign keys.
- Prevent normal GET fallback writes in operations routes.
- Add degraded operations responses for cache/projection misses.
- Publish and verify runtime path.

### Out of Scope
- PostgreSQL migration.
- First-pass deletion/vacuum of source DB rows.
- Reworking the full quantitative strategy logic.

## Assumptions and Dependencies
- Ledger revision: `ledger-20260626-sqlite-hot-cold-split` revision 2.
- Implementation must happen in isolated branch `codex/sqlite-hot-cold-split`.
- Source DB remains available and untouched except readonly verification.
- Runtime publish target is `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard`.
- Cold DB schemas must not contain foreign keys to hot DB tables; they store logical identifiers such as `symbol`, `bar_key`, `run_id`, and source primary-key values.
- Before runtime cutover, create a hot DB backup. Rollback means switching configuration back to the original source DB and preserving the split hot DB as a merge source.

## Table Placement Contract
| Table / Data Family | Target DB | Physical Shape | Write Owner | Read Owner | Notes |
|---------------------|-----------|----------------|-------------|------------|-------|
| `account_spaces`, `watchlist_entries`, `watchlist_follows`, `provider_credentials`, `model_api_keys`, `app_settings`, `policy_config_versions` | hot | Original ORM tables | FastAPI/settings/refresh | FastAPI | Live configuration and credentials remain hot only. |
| `stocks`, `sectors`, `sector_memberships`, model/prompt registry tables | hot | Original ORM tables | analysis refresh | FastAPI/analysis | Required for live relationships and forward analysis. |
| Current `recommendations`, `recommendation_evidence`, `feature_snapshots`, `model_runs`, `model_results`, `news_items`, `news_entity_links`, `ingestion_runs` | hot | Original ORM tables | analysis refresh | FastAPI/operations | Keep full live ORM compatibility in v1. |
| Hot `market_bars` | hot | Original ORM table | forward/intraday refresh | FastAPI/operations | Keep `5min`, active-watchlist recent `1d`, and benchmark recent windows needed by live routes. |
| Cold historical market bars | market_history | New denormalized `market_bar_history` table with `symbol`, `timeframe`, `observed_at`, OHLCV, source row id, payload, lineage; no FK | migration/history refresh | explicit repository only | Stores broad/full `1d` history. No cross-DB join; application merges by `symbol`. |
| `shortpick_*`, old validation snapshots, historical experiment rows | research_archive | Archive copies plus archive metadata; no FK enforcement | migration/archive refresh | explicit archive tooling/projections | Live UI reads only hot projections or degraded summaries in v1. |
| `frontend_projections`, paper portfolio/order/fill tables, simulation sessions/events | hot | Original ORM tables | projection refresh/API | FastAPI | Live UI state remains hot. |

## Work Items
| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-000 | done | 1 | - | Run database and runtime/API cross-review before implementation. | Review log with no unresolved blocking findings. | manual | manual:external review complete | MiMo DB review passed; MiMo runtime review blocking item closed by W-004. |
| W-001 | done | 2 | W-000 | Add multi-DB runtime config and read-only cold session helpers. | Hot/history/research DB URL loaders, `query_only` or URI read-only cold behavior, and tests. | test_pass | cmd:python3 -m pytest -q tests/test_sqlite_hot_cold_split.py tests/test_frontend_projections.py -q | passed |
| W-002 | done | 3 | W-001 | Add split classification and migration verification tooling. | Repeatable CLI/script for denormalized cold DB migration and validation. | test_pass | cmd:python3 -m pytest -q tests/test_sqlite_hot_cold_split.py -q | passed |
| W-003 | done | 4 | W-002 | Add explicit cold repository boundary for market-history reads. | Repository boundary that avoids cross-DB FK/JOIN assumptions and tests. | test_pass | cmd:python3 -m pytest -q tests/test_sqlite_hot_cold_split.py -q | passed; repository is explicit cold read adapter. |
| W-004 | done | 5 | W-001 | Remove normal GET projection writes and add degraded operations responses. | Operations routes return cached/projection/degraded responses without sync rebuild writes. | test_pass | cmd:python3 -m pytest -q tests/test_frontend_projections.py -q | passed |
| W-005 | done | 6 | W-001,W-004 | Enable safe operations cache/projection prewarm defaults. | Prewarm skips while scheduled refresh lock is active; cache miss degrades instead of blocking. | test_pass | cmd:python3 -m pytest -q tests/test_frontend_projections.py -q | passed |
| W-006 | done | 7 | W-002,W-003,W-004,W-005 | Run gates, publish runtime, and verify real API path. | Validation evidence and closeout. | command_exit_0 | cmd:python3 -m pytest -q | pytest and policy audit passed; publish succeeded with `ASHARE_PUBLISH_VERIFY_MODE=local`; served API smoke passed. |

## Acceptance Criteria & Validation Gates
### Overall Acceptance Criteria
- Hot DB remains the live default DB for FastAPI writes.
- Cold DBs can be generated and verified without deleting source data and without cross-DB foreign keys.
- Cold DB connections are read-only by default for live code; maintenance scripts must opt into writable target URLs.
- Operations GET routes do not write projections in normal fallback paths.
- Operations endpoints do not hang on cache/projection miss; they return degraded payloads.
- Runtime publish and real served API smoke checks pass.

### Validation Gates
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` if formula/config-governed code changes.
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- Real API curl checks after publish.

## Risks and Mitigations
- Risk: Cold repository routing misses a live query. Mitigation: hot fallback plus focused tests.
- Risk: Migration script duplicates rows. Mitigation: unique keys and repeatability tests.
- Risk: Cross-DB joins/FKs are accidentally introduced. Mitigation: denormalized cold tables and tests that cold schema has no FK list entries.
- Risk: Rollback loses hot DB increments. Mitigation: create hot DB backup before runtime switch and document hot DB as merge source.
- Risk: Degraded operations payload hides useful errors. Mitigation: include explicit status/reason in payload.
- Risk: Runtime publish drifts from source. Mitigation: publish and verify real API before closeout.

## Open Questions
None acceptance-critical.

## Revision History
| Revision | Date | Change |
|----------|------|--------|
| 1 | 2026-06-26 | Initial executable plan from user-approved chat plan. |
| 2 | 2026-06-26 | Implemented cold DB config, migration/repository boundary, and operations degraded/cache-only behavior. |
| 3 | 2026-06-26 | Recorded successful runtime publish and served API smoke checks. |
| 4 | 2026-06-26 | Fixed implementation-review minor findings, reran gates, and archived plan for merge. |

## External Review Log
| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Missing explicit table-to-DB mapping. | major | resolved | Added `Table Placement Contract`. | W-001,W-002,W-003 |
| 1 | MiMo | Cold DB lacks readonly infrastructure. | major | accepted | W-001 now requires read-only cold connections. | W-001 |
| 1 | MiMo | Cross-DB SQLite FK/JOIN strategy missing. | blocking | resolved | Revised architecture: cold DBs are denormalized archive/query stores with no cross-DB FK; repositories merge by logical keys. | W-002,W-003 |
| 1 | MiMo | Rollback and hot DB backup unclear. | major | resolved | Added hot DB backup and rollback-as-config-switch/merge-source strategy. | W-002,W-006 |
| 2 | MiMo | `GET /dashboard/operations/summary` writes projection on miss. | blocking | accepted | This is the primary W-004 implementation target; remove write fallback and use degraded/cache response. | W-004,SRC-004 |
| 2 | MiMo | Cold operations cache first-build failures return 500 instead of degraded payload. | major | accepted | W-004 requires try/except degraded response for operations GET handlers. | W-004,W-005,SRC-005 |
| 2 | MiMo | Hot DB must retain ORM eager-load tables such as recommendations and portfolios. | major | resolved | `Table Placement Contract` keeps recommendations, paper portfolios, paper orders/fills, and simulation tables in hot DB. | W-001,W-002,W-003 |
| 3 | MiMo | Implementation code review found no blocking issues; noted cold repository connection cleanup and migration `fetchall()` memory risk. | minor | resolved | Added connection `finally: close()` and batch `fetchmany()` migration copies. | W-002,W-003 |
| 3 | MiMo | Tests prove operations GET no-write/no-rebuild and migration idempotence/read-only/FK boundary. | note | resolved | Gate evidence retained and full pytest/policy audit reran after minor fixes. | W-002,W-003,W-004,W-006 |

## User Review Notes
- User requested implementation of this plan after plan creation.
