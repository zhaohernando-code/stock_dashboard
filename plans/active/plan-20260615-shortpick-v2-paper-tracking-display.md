---
schema_version: 1
plan_id: "plan-20260615-shortpick-v2-paper-tracking-display"
title: "Shortpick V2 Paper Tracking Display"
status: "executing"
created_at: "2026-06-15"
source_request: "Implement the user's requested 试验田v2 paper-tracking display: match v1 structure, add 2026-05-08-to-now replay-tagged rows, and remove unreadable field-shaped/raw config text, using reviewed-plan-generator and plan-run-loop."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display"
owner: "user"
review_rounds: 3
---

# Plan: Shortpick V2 Paper Tracking Display

## Compaction-Resistant Summary

Goal: make `试验田v2 -> 纸面追踪` look and read like v1 paper tracking, while clearly labeling catch-up rows with `signal_date >= 2026-05-08` as `回放`.
Hard scope: no new strategy search, no delayed buy, no fixed90 promotion, no true-forward claim for replay rows, no extra v2 modules.
Key dependencies: existing H10 fixed85/fixed80 governance, v2 read model, v1 paper-tracking UI structure, runtime publish path.
Major risks: confusing historical/replay rows with real paper performance, leaking raw field names/config IDs into the UI, and validating only fixtures instead of the served route.
Approval state: MiMo round 1 passed after minor clarifications. Codex round 1 findings are accepted and resolved. The plan is executing W-001 under the user's explicit implementation request.

## Goal

Replace the current `试验田v2` paper-tracking presentation with a user-readable paper-tracking experience aligned with `试验田v1`: latest simulated trade, strategy explanation, charts, and a record table. The page must include available rows from signal date `2026-05-08` through the current available data, but those rows must be visibly tagged as `回放` and must not be counted or described as true-forward paper-tracking performance.

## Problem / Rationale

The current v2 paper-tracking page exposes contract/config/read-model fields and empty or backtest-like artifacts. That is not useful to read, and it violates the user's expectation that paper tracking should look like the already validated v1 surface. At the same time, the H10 governance work intentionally prevented historical replay from being silently treated as real forward paper tracking. This change must therefore improve the user-facing page and add a replay-tagged catch-up view without weakening the governance boundary.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use `reviewed-plan-generator` and `plan-run-loop` for this implementation. | W-001,W-002,W-003 | covered | in-scope | Schema-v1 plan validation, MiMo plan/run reviews, archived run record, branch push, merge to main, base push, and plan archive evidence. |
| SRC-002 | Current v2 paper tracking must stop presenting historical backtest/config data as the main paper-tracking display. | W-001,W-002,W-003 | covered | in-scope | Read model separates replay-tagged rows from true-forward status; frontend avoids raw config/backtest-field presentation in the paper tab; served API/UI check confirms the page copy. |
| SRC-003 | Display structure must match v1 paper tracking: latest simulated trade, strategy explanation, charts, and table. | W-001,W-002,W-003 | covered | in-scope | V2 paper tab contains sections named `最新模拟交易`, `策略说明`, chart content, and record table content with tests/static checks and served browser evidence. |
| SRC-004 | Add data from signal date `2026-05-08` through current available data, labeled with `回放`. | W-001,W-002,W-003 | covered | in-scope | Backend projection exposes `coverage_start`, `coverage_end`, `latest_source_signal_date`, row/gap counts, and either one replay row or a readable gap for every available source signal date in the inclusive `>= 2026-05-08` window; frontend displays visible `回放` tags; served API/browser verification checks the same inclusive window. |
| SRC-005 | Ban field-shaped/raw unreadable UI content; all configuration and explanations must be Chinese and readable. | W-001,W-002,W-003 | covered | in-scope | Helper mapping converts status/action/config/evidence labels to Chinese; static and served-page checks reject raw labels such as `contract_ready`, `research_observation`, `true_forward_tracking`, `config_id`, `decision_action`, `v2 Paper Ledger Rows`, and visible snake_case/key-shaped strings in the paper tab. |
| SRC-006 | Preserve H10 governance: replay rows are not true-forward paper performance, fixed90 stays diagnostic-only, and delayed buy remains forbidden. | W-001,W-002,W-003 | covered | in-scope | Read-model tests prove replay rows use replay evidence labels, true-forward counts remain separate, fixed90 is not a candidate row, and no delayed-entry wording/action is introduced. |
| SRC-007 | Keep `试验田v2` limited to `纸面追踪` and `历史回放`; do not add parameter search or extra modules. | W-002,W-003 | covered | in-scope | Frontend static checks continue to find only the two v2 tabs and no parameter-search controls. |
| SRC-008 | Because this is live-facing, publish to runtime and verify the real served route/API before closeout. | W-003 | covered | in-scope | Runtime verification script runs relevant gates, publishes with refresh skipped, checks served `/shortpick-lab-v2/paper-tracking`, and verifies the browser route under `/projects/ashare-dashboard/`. |
| SRC-009 | Keep `/shortpick-lab-v2/paper-tracking` response compatible for existing consumers while adding display fields. | W-001,W-002,W-003 | covered | in-scope | Tests assert existing top-level fields and summary fields remain present, new display fields are additive/optional, summary endpoint still omits heavy rows where intended, and frontend types match backend schema. |
| SRC-010 | Schema/deployment-risk work requires Codex escalation evidence in addition to MiMo. | W-001,W-002,W-003 | covered | in-scope | Codex plan review plus W-001/W-003 run/code escalation reviews are recorded with no unresolved blocking or major findings before merge. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | User opens the real served dashboard at `/projects/ashare-dashboard/?view=shortpick-v2&shortpickV2Tab=paper-tracking`. | Runtime publish plus browser/API smoke against the served route after `origin/main` has been updated. | FastAPI static mount, frontend bundle, and LaunchAgent runtime | none | matches_product_path | Served page renders `最新模拟交易`, `策略说明`, chart/table text, and visible `回放`; it does not show raw field-shaped strings in the paper tab; published runtime source/bundle correspond to the final `origin/main` commit. |
| PF-002 | `/shortpick-lab-v2/paper-tracking` returns the data consumed by the v2 paper tab. | TestClient/read-model tests plus served API verification. | FastAPI v2 read model | fixture artifacts/temporary DB are allowed only for edge-case unit coverage; the W-003 served API check must use the published runtime code and runtime artifact/data resolution path | controlled_simulation | Unit tests prove display-field shape and edge cases; served API evidence separately records whether real runtime data produced replay rows or a readable source-gap state, with true-forward/replay counts separated. |
| PF-003 | Backend projection builds catch-up rows from existing local data/artifacts without refreshing market data, calling models, or writing paper-ledger rows. | Focused backend tests and runtime verification script that runs read-only checks. | Shortpick V2 read model/projection builder | fixture data may be generated only for deterministic edge cases; runtime verification must not rely on those fixtures and must not create ledger rows | controlled_simulation | Tests verify no ledger mutation is required, replay evidence labels are explicit, and the runtime check proves the real published path returns replay rows or a readable gap state without raw errors. |
| PF-004 | Frontend converts backend fields into readable Chinese rather than exposing internal field names. | Static tests and built bundle/browser inspection. | `ShortpickLabV2View` | none | matches_product_path | Visible text uses Chinese labels for status, evidence, actions, strategy, and row tags; raw status/config identifiers and snake_case/key-shaped strings are absent from user-facing paper-tab strings. |
| PF-005 | Closeout follows project policy for live-facing changes. | Pre-push hook plus explicit runtime verification after merge/main push. | Git hooks, publish script, runtime services | none | matches_product_path | Default pytest, policy audit, task branch push, merge to main, origin/main push, plan archive, run archive, final-main runtime publish, and final-main runtime verification are recorded. |

## Scope

### In Scope

- Add or extend a v2 paper-tracking projection that supplies readable display data for latest simulated trade, strategy explanation, chart inputs, and table rows.
- Add replay-tagged catch-up rows from signal date `2026-05-08` through the latest available source date, while preserving true-forward/replay separation.
- Update the v2 paper-tracking frontend to follow the v1 section structure and remove raw field-shaped visible content.
- Add tests for backend projection, frontend static/readability checks, and served runtime verification.
- Publish the committed live-facing changes and verify the real served route/API before merging closeout.

### Out of Scope

- No new strategy search, parameter tuning, or benchmark replacement.
- No true-forward paper-ledger writer implementation.
- No historical replay rows promoted as real paper-tracking performance.
- No fixed90 promotion or turnover-gate weakening.
- No delayed buy, retry buy, or later discretionary entry.
- No new `试验田v2` modules beyond `纸面追踪` and `历史回放`.

## Assumptions and Dependencies

- H10 fixed85 and fixed80 remain the only current v2 observation candidates; fixed90 remains diagnostic-only.
- `2026-05-08` is the required v2/v1-aligned paper-tracking start anchor.
- The catch-up rows may be computed or projected from existing committed/runtime data, but they must carry a visible `回放` tag and replay evidence wording.
- If no source rows exist for part of the 2026-05-08-to-current window, the API/UI must show a readable gap state rather than moving the start date or inventing buys.
- Runtime publish uses `ASHARE_PUBLISH_REFRESH_MODE=skip` unless a later explicit requirement says otherwise.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Build the v2 paper-tracking display projection, including replay-tagged catch-up rows, inclusive window coverage metadata, additive API fields, and readable summaries while preserving H10 governance boundaries. | Backend read model/schema/tests for latest trade, strategy explanation, chart/table data, replay tags, true-forward separation, inclusive coverage, and API compatibility | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py | Passed 22 tests on 2026-06-15T13:05Z; also passed replay/strategy-search compatibility tests with 48 tests. MiMo code review had no blocker/major and two accepted minor cleanups were applied. Codex escalation code review had no blocker/major. |
| W-002 | done | 2 | W-001 | Rework the `试验田v2` paper tab to use the v1-style display structure and Chinese-readable labels, with no raw field-shaped visible content. | `frontend/src/components/ShortpickLabV2View.tsx`, types/helpers/static tests; no CSS change was needed. | test_pass | cmd:python3 -m pytest -q tests/test_frontend_shortpick_static.py && cd frontend && npm run build | Passed 6 static tests and frontend build on 2026-06-15T13:24Z. MiMo code review had no blocker; rowKey, fallback-column, and replay visible-text guard recommendations were accepted and applied. |
| W-003 | pending | 3 | W-001,W-002 | Create the live-facing closeout verifier, then perform archive, task-branch push, main merge/push, final-main publish, and final served verification. The verifier must assert `coverage_start == 2026-05-08`, inclusive row-or-gap coverage through the latest available source date, separated replay/true-forward counts, and no snake_case/key-shaped visible strings on the served paper tab. | New runtime verification script, served API/browser evidence from final `origin/main`, archived run doc, archived plan, task branch push, main merge/push | command_exit_0 | cmd:bash scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh | |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- `试验田v2 -> 纸面追踪` opens with v1-like sections: `最新模拟交易`, `策略说明`, chart content, and a table.
- Rows from `2026-05-08` through the latest available source date appear when data is available and carry visible `回放` tags.
- Coverage evidence includes `coverage_start = 2026-05-08`, `coverage_end`, `latest_source_signal_date`, replay row count, gap count, and proof that every available source signal date in the inclusive window produced either a replay display row or a readable gap.
- Replay-tagged rows are not described as true-forward paper performance and do not increase true-forward paper-ledger counts.
- The paper tab does not expose raw field-shaped strings or config identifiers as the primary visible language.
- All strategy/config/status/action explanations visible to the user are Chinese-readable.
- `/shortpick-lab-v2/paper-tracking` remains backward compatible: existing top-level fields stay present, new display fields are additive/optional, and summary/full endpoints keep their intended row-payload behavior.
- H10 fixed85/fixed80 remain the governed candidates; fixed90 remains diagnostic-only.
- V2 remains limited to `纸面追踪` and `历史回放`.
- The task branch is pushed, merged to `main`, `origin/main` is pushed, the plan and run docs are archived, and temporary run state is cleaned.
- Runtime is published and the real served API/page are verified after the committed changes.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md`
- MiMo plan review reports no unresolved blocking findings.
- Codex escalation plan review reports no unresolved blocking or major findings.
- MiMo run-plan/code reviews report no unresolved blocking findings for each run.
- Codex escalation run/code review is required for W-001 and W-003 and must report no unresolved blocking or major findings.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`
- `python3 -m pytest -q tests/test_frontend_shortpick_static.py`
- `cd frontend && npm run build`
- If parameters/formulas are touched, run the policy audit command from `AGENTS.md`; otherwise record why it is not required before push.
- `bash scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh` after `origin/main` points at the final merged commit.
- Project pre-push hook on task branch and main push.

## Risks and Mitigations

- Risk: replay catch-up rows weaken the previous no-backfill governance boundary. Mitigation: model them as replay display rows with visible `回放` tag and separate counts/evidence, not true-forward ledger rows.
- Risk: frontend hides raw fields in one card but leaves config/status identifiers elsewhere. Mitigation: static tests reject known raw visible strings and browser verification checks the served paper tab.
- Risk: runtime route again serves stale or broken assets. Mitigation: publish after commit and verify the mounted served route, not only local build output.
- Risk: source data after `2026-05-08` is incomplete. Mitigation: show readable gap/empty state and keep the start anchor fixed.
- Risk: additive display fields accidentally break existing API consumers. Mitigation: keep existing response fields stable and add compatibility tests for full and summary endpoints.
- Risk: large frontend component edits regress v1. Mitigation: keep changes scoped to `ShortpickLabV2View` and v2 types/helpers, with existing v1 tests still run through project pre-push.

## Open Questions

- None for execution. If source data is missing for some dates, the implementation should show a readable gap state rather than blocking or inventing rows.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-15 | Initial draft for v2 paper-tracking display and replay-tag catch-up implementation. | Codex |
| 1 | 2026-06-15 | Accepted MiMo minor findings by separating fixture-only tests from required served runtime evidence and clarifying that W-003 creates the runtime verification script. | Codex |
| 2 | 2026-06-15 | Accepted Codex escalation findings: approved the reviewed plan for execution, added Codex escalation gates, tightened inclusive `2026-05-08` coverage evidence, added API compatibility acceptance, required final-main runtime publish/verification, and broadened raw-field visible-text checks. | Codex |
| 3 | 2026-06-15 | Accepted MiMo focused re-review minor by placing the exact W-003 runtime verifier assertions directly in the work item. | Codex |
| 4 | 2026-06-15 | Started plan-run-loop execution for W-001; plan status changed to executing and W-001 to in_progress. | Codex |
| 5 | 2026-06-15 | Completed W-001 backend display projection, additive schema/API support, replay-tagged coverage rows, summary-row omission behavior, cache/degrade guards, focused tests, MiMo code review, and Codex escalation review. | Codex |
| 6 | 2026-06-15 | Started W-002 frontend implementation run; W-002 status changed to in_progress after W-001 checkpoint commit. | Codex |
| 7 | 2026-06-15 | Completed W-002 frontend display implementation: paper tab now consumes `paper_display`, renders latest trade/strategy/charts/table, hides raw field-shaped content, adds replay/coverage summary cards, and passes static tests plus frontend build. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | PF-002/PF-003 could blur fixture validation with real runtime data validation. | minor | accepted | PF-002/PF-003 now explicitly limit fixtures to edge-case unit coverage and require W-003 served API evidence from the published runtime path. | PF-002,PF-003,W-003 |
| 1 | MiMo | W-003 references a runtime verification script but did not state whether it exists or is created by the plan. | minor | accepted | W-003 now explicitly creates the new verification script before running it. | W-003 |
| 1 | MiMo | The plan covers v1 structure, 2026-05-08 replay tag, field-shape ban, H10 governance boundary, and plan-run-loop execution. | note | accepted | No blocking or major change required. | SRC-003,SRC-004,SRC-005,SRC-006 |
| 1 | Codex | `status: draft` would stop schema-v1 plan-run-loop execution. | blocking | accepted | The plan is now `approved` after MiMo/Codex review, using the user's explicit implementation request as approval to execute this plan. | plan-lifecycle |
| 1 | Codex | Codex escalation was pending but not included in gates despite API/schema-facing and deployment-risk work. | blocking | accepted | Validation gates now require Codex escalation plan review and W-001/W-003 run/code escalation reviews. | SRC-010,W-001,W-003 |
| 1 | Codex | SRC-004 did not prove inclusive 2026-05-08-through-latest coverage, only at least one replay row. | major | accepted | SRC-004 and acceptance now require coverage metadata and row-or-gap evidence for every available source signal date in the inclusive window. | SRC-004,W-001,W-003 |
| 1 | Codex | API/schema compatibility lacked an independent acceptance criterion. | major | accepted | Added SRC-009 and acceptance requiring additive/optional display fields and stable existing full/summary endpoint fields. | SRC-009,W-001 |
| 1 | Codex | W-003 ordering could publish/verify a task-branch or intermediate commit instead of final `origin/main`. | major | accepted | W-003/PF-001/PF-005 now require final-main publish and served verification after `origin/main` is updated. | W-003,PF-001,PF-005 |
| 1 | Codex | `post-2026-05-08` in the summary could be read as excluding 2026-05-08. | minor | accepted | The compaction summary now says `signal_date >= 2026-05-08`. | SRC-004 |
| 1 | Codex | Raw-field ban relied too much on a denylist and could miss new snake_case/key-shaped leaks. | minor | accepted | SRC-005/PF-004 now require static and served visible-text checks for snake_case/key-shaped strings in addition to named raw examples. | SRC-005,PF-004 |
| 2 | MiMo | Focused re-review found no blocker or major issue; fixture/runtime boundary, final-main verification, inclusive row-or-gap coverage, and H10 replay/true-forward separation are resolved. | note | accepted | No plan change required for these items. | PF-002,PF-003,W-003,SRC-004,SRC-006 |
| 2 | MiMo | W-003 work item should state the runtime verifier's field-level assertions directly, not only through general acceptance criteria. | minor | accepted | W-003 now names the required served API/page checks: `coverage_start == 2026-05-08`, row-or-gap coverage, separated replay/true-forward counts, and no snake_case/key-shaped visible strings. | W-003 |
| 3 | MiMo | W-001 implementation has no blocker or major issue; summary/detail split, replay exception downgrade, row-or-gap accounting, sanitized table rows, and decision-sample limit are sound. | note | accepted | Two minor performance/cache cleanups were accepted and applied: summary skips unnecessary row construction and cache writes purge expired entries. | W-001 |
| 3 | Codex | W-001 escalation found no blocker or major issue; four named risks are closed in reviewed code. | note | accepted | No further backend scope change required before W-002. | W-001 |
| 3 | MiMo | W-002 implementation has no blocker; paper tab uses `paper_display` instead of raw `records`/`row_contract`, and known raw strings have no visible rendering path. | note | accepted | Confirms the main frontend direction satisfies the user-facing paper-tab requirement. | W-002 |
| 3 | MiMo | Table row keys and fallback columns could be safer, and replay tab lacked comparable visible-text guard coverage. | major | accepted | Raw-id row keys were replaced with generated display keys, fallback columns now include reason and selected-rank text, and the static test now checks replay visible JSX text for snake_case/raw field leakage. | W-002 |
| 3 | MiMo | Existing `records` and `row_contract` fields remain in the TypeScript response type for compatibility even though the paper tab no longer consumes them. | note | accepted | No change required for W-002 because SRC-009 requires additive compatibility; static tests explicitly prevent paper-tab reads from these fields. | W-002,SRC-009 |

## User Review Notes

- User requested implementation, not just discussion, and explicitly required `reviewed-plan-generator` plus `plan-run-loop`.
- User previously approved not blocking on approval prompts during the run; this plan records that approval but still requires review and execution evidence before merge.
