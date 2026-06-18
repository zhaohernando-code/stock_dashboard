---
schema_version: 1
plan_id: "plan-20260618-shortpick-v2-paper-ledger-refresh"
title: "Shortpick v2 paper ledger refresh"
status: "executing"
created_at: "2026-06-18"
source_request: "实现试验田v2在每日刷新时自动刷新真实前向纸面记录。"
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 1
---

# Plan: Shortpick v2 paper ledger refresh

## Compaction-Resistant Summary

Goal: make daily refresh produce and refresh v2 true-forward paper ledger rows, not only prewarm the read model.
Scope: use existing v2 paper ledger JSON schema and H10 governed configs; no new strategy search or historical result mutation.
Production path: `scripts/run-scheduled-refresh.sh` postmarket shortpick cycle writes ledger, then prewarms `/shortpick-lab-v2/paper-tracking`.
Validation: focused unit/static tests, runtime verify script, publish to runtime, served API proves `record_count > 0`.
Risk: accidental historical backfill or v1 ledger fallback; mitigate through schema, start-date, source-gap policy, and no delayed-buy tests.
Approval: user requested standard-flow implementation and previously approved non-blocking execution; plan is approved for execution after MiMo review found no blocker.

## Goal

Add the missing v2 paper ledger writer and scheduled-refresh integration so `试验田v2` paper tracking has durable true-forward rows after daily refresh, while preserving the existing historical replay and research-only labels.

## Problem / Rationale

`试验田v2` currently has a read model and display replay projection, but `/shortpick-lab-v2/paper-tracking/summary` reports `record_count: 0`, `paper_tracking_status: not_started_no_true_forward_rows`, and a missing `output/shortpick-v2-paper-tracking-ledger.json`. The daily refresh script only prewarms the v2 paper cache; it does not write the ledger artifact consumed by the v2 paper tracking read model.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Daily refresh should automatically refresh v2 forward paper tracking, not merely cache the display projection. | W-001, W-002, W-003 | covered | - | `run-scheduled-refresh.sh` invokes a v2 ledger refresh script; served v2 paper API reports ledger source `ready/active` and nonzero true-forward records. |
| SRC-002 | v2 paper tracking must remain true-forward; historical replay rows must not be counted as paper tracking收益. | W-001, W-003 | covered | - | Ledger schema validation passes; tests prove rows are written as `evidence_basis=true_forward_tracking` and no delayed/historical backfill action is introduced. |
| SRC-003 | Existing H10 governed candidate configs remain the active v2 observation set. | W-001 | covered | - | Writer uses existing H10 paper governance/read-model config ids and does not introduce new strategy-search outputs. |
| SRC-004 | Daily refresh must continue to tolerate source gaps and must not break v1 refresh, v2 cache prewarm, or runtime availability. | W-002, W-003 | covered | - | Static scheduled-refresh tests pass; publish verification passes; runtime health and scheduled-refresh status are OK. |
| SRC-005 | Standard flow requires plan/run records, task branch push, merge, base push, publish for live-facing changes, and cleanup. | W-004 | covered | - | Archived run document, merged PR, origin/main sync, runtime publish evidence, clean worktree/worktree cleanup. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | LaunchAgent calls `scripts/run-scheduled-refresh.sh`; postmarket `shortpick_lab` cycle writes v2 paper ledger and prewarms v2 paper read model. | Static script test plus direct execution of the new v2 refresh script and runtime verify script after publish. | scheduled refresh script | none | matches_product_path | Runtime artifact exists; `scripts/verify-shortpick-v2-paper-ledger-runtime.sh` exits 0 and served summary reads the produced ledger. |
| PF-002 | Browser/API users open `试验田v2` paper tracking; backend uses `build_shortpick_v2_paper_tracking_read_model` and ledger artifact. | Served API requests through `scripts/verify-shortpick-v2-paper-ledger-runtime.sh`. | FastAPI read model | none | matches_product_path | Served payload has true-forward `record_count > 0`, no missing ledger source, and Chinese readout remains available. |
| PF-003 | Unit tests construct temporary DB/artifacts to prove writer behavior without touching runtime. | Focused pytest using temp dirs and fixture market series. | test harness | controlled temp DB and artifacts; production owner still covered by PF-001/PF-002 | controlled_simulation | Test passes and production path evidence also collected. |

## Scope

### In Scope

- Add a v2 paper ledger artifact writer that emits `shortpick_v2_paper_tracking_ledger` JSON matching the existing schema.
- Use existing H10 v2 paper configs and current market data to produce signal-day records from `2026-05-08` onward.
- Preserve source gaps as ledger records instead of silently skipping coverage.
- Add a script/CLI entrypoint that can be called by daily refresh.
- Connect the v2 ledger refresh before v2 paper cache prewarm in `run-scheduled-refresh.sh`.
- Add targeted tests and runtime served verification.

### Out of Scope

- No new stock-picking strategy search.
- No mutation of historical replay artifacts or prior historical performance claims.
- No automatic real-money order placement or investment advice.
- No change to v1 paper-tracking strategy generation, except preserving existing daily refresh behavior.

## Assumptions and Dependencies

- Existing H10 paper governance artifact remains the source of selected v2 configs.
- Existing v2 read model and schema are authoritative for the ledger contract.
- Runtime has enough market data after `2026-05-08` to generate rows; if not, source-gap records are acceptable.
- User has already approved non-blocking execution of standard-flow work in this thread.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | completed | 1 | - | Implement v2 paper ledger writer, CLI/script entrypoint, and writer/read-model tests using the existing schema and governed H10 configs. Tests must assert records are on or after `2026-05-08`. | `src/ashare_evidence/shortpick_v2_paper_ledger.py`, CLI/script, tests | test_pass | cmd:python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py -k 'paper_tracking' | passed: 15 passed, 16 deselected |
| W-002 | completed | 2 | W-001 | Wire v2 paper ledger refresh into the postmarket scheduled refresh before v2 paper cache prewarm, with shell syntax/static coverage. | `scripts/run-scheduled-refresh.sh` integration and static tests | test_pass | cmd:bash -n scripts/run-scheduled-refresh.sh scripts/refresh-shortpick-v2-paper-ledger.sh scripts/verify-shortpick-v2-paper-ledger-runtime.sh && python3 -m pytest -q tests/test_scheduled_refresh_static.py tests/test_publish_script_static.py | passed: 25 passed |
| W-003 | in_progress | 3 | W-002 | Verify runtime behavior through publish and served API using a scriptable production-path gate. | Published runtime and API evidence | command_exit_0 | cmd:scripts/verify-shortpick-v2-paper-ledger-runtime.sh | local writer smoke passed against runtime DB: record_count=4 |
| W-004 | pending | 4 | W-003 | Close out standard flow with archived run record, plan archive, push, merge, origin/main sync, and cleanup. | Archived run + merged PR + clean local state | manual | manual:run record archived, PR merged, origin/main clean, temporary worktree removed |  |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- Daily refresh has a real v2 paper ledger refresh step, not only cache prewarm.
- The v2 ledger artifact validates against `shortpick_v2_paper_tracking_ledger.schema.json`.
- The served v2 paper tracking API reads the ledger and reports true-forward records.
- Historical replay rows remain tagged as replay and are not counted as true-forward paper rows.
- Runtime publish verification passes after the live-facing change.

### Validation Gates

- `python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py -k 'paper_tracking'`
- `bash -n scripts/run-scheduled-refresh.sh scripts/refresh-shortpick-v2-paper-ledger.sh scripts/verify-shortpick-v2-paper-ledger-runtime.sh && python3 -m pytest -q tests/test_scheduled_refresh_static.py tests/test_publish_script_static.py`
- `npm run check --prefix frontend`
- `scripts/verify-shortpick-v2-paper-ledger-runtime.sh`
- Project pre-push fast regression and policy audit.
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- Served API checks for `/health`, `/shortpick-lab-v2/paper-tracking/summary`, and `/shortpick-lab-v2/paper-tracking`.

## Risks and Mitigations

- Risk: writer accidentally treats display replay rows as true-forward results. Mitigation: writer produces schema records directly and tests `evidence_basis=true_forward_tracking`, while replay display remains separate.
- Risk: source gaps hide missing data. Mitigation: create `source_gap`/`not_observed` records and summary counts.
- Risk: daily refresh duration increases. Mitigation: reuse existing replay-window loader and keep timeout bounded behind a separate environment variable.
- Risk: generated artifact makes runtime API slower. Mitigation: prewarm after writer and verify served API response time.
- Risk: plan/run overhead becomes stale. Mitigation: archive run record and move plan to archive in the same PR.

## Open Questions

- None blocking. If runtime has no eligible signal days, the implementation should still write a schema-valid ledger with source-gap/empty summary rather than fail the entire daily refresh.

## Revision History

| Timestamp | Actor | Change |
|-----------|-------|--------|
| 2026-06-18 | Codex | Drafted standard-flow plan for v2 paper ledger daily refresh. |
| 2026-06-18 | Codex | Accepted MiMo plan review findings: script runtime verification, clarified W-001 sequencing, added start-date and shell syntax gates. |
| 2026-06-18 | Codex | Started full-plan execution; W-001 moved from pending to in_progress. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-003 runtime verification should be scriptable instead of only manual. | minor | accepted | Added `scripts/verify-shortpick-v2-paper-ledger-runtime.sh` as W-003 command gate and PF evidence. | W-003, PF-001, PF-002 |
| 1 | MiMo | W-001 should make writer/test sequencing explicit for plan-run-loop execution. | major | accepted | W-001 now explicitly includes writer, CLI/script, tests, and start-date assertion before running pytest. | W-001 |
| 1 | MiMo | W-002 lacks an intermediate shell/dry-run style gate. | minor | accepted | W-002 now includes `bash -n` for run and verification scripts plus static tests. | W-002, W-003 |
| 1 | MiMo | Frontend check is broad for this backend/script change. | note | rejected | Retained because live-facing runtime publish includes frontend bundle health and project CI now has a cheap `check` script. | Validation Gates |

## User Review Notes

- User requested: `按照标准流程进行实现`.
- Prior standing instruction in this thread: do not request approval and do not block on approval. This plan treats the current implementation request as execution authorization after external plan review has no blocking finding.
