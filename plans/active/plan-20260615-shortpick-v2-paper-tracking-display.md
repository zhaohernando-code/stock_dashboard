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
Hard scope: paper details are limited to the 2026-05-08-to-current window; `历史回放` shows aggregate statistics only; no new strategy search, delayed buy, fixed90 promotion, or true-forward claim for replay rows.
Key dependencies: existing H10 fixed85/fixed80 governance, v2 read model, v1 paper-tracking UI structure, runtime publish path.
Major risks: confusing historical/replay rows with real paper performance, leaking raw field names/config IDs into the UI, accidental full-history runtime reads, and validating only fixtures instead of the served route.
Approval state: MiMo/Codex findings through W-003 are dispositioned; W-003 is executing under the user's explicit continuation request.

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
| SRC-011 | `纸面追踪` should only display detailed results from signal date `2026-05-08` through the current available date, and the backend display path should not read the full historical daily market table to produce that bounded display. | W-003 | covered | in-scope | Backend uses a bounded market-bar window for the paper display replay projection; tests fail if the full daily-series loader is used; runtime verifier confirms coverage starts at `2026-05-08` and the API returns promptly after publish. |
| SRC-012 | `历史回放` should not display concrete decision/detail rows; it should show statistical/summary readouts only. | W-003 | covered | in-scope | Frontend removes decision-sample/detail table rendering from the historical replay tab; static and served-page checks prove `决策样本`/sample detail tables are absent while aggregate statistics remain visible. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | User opens the real served dashboard at `/projects/ashare-dashboard/?view=shortpick-v2&shortpickV2Tab=paper-tracking`. | Runtime publish plus browser/API smoke against the served route after `origin/main` has been updated. | FastAPI static mount, frontend bundle, and LaunchAgent runtime | none | matches_product_path | Served page renders `最新模拟交易`, `策略说明`, chart/table text, and visible `回放`; it does not show raw field-shaped strings in the paper tab; published runtime source/bundle correspond to the final `origin/main` commit. |
| PF-002 | `/shortpick-lab-v2/paper-tracking` returns the data consumed by the v2 paper tab. | TestClient/read-model tests plus served API verification. | FastAPI v2 read model | fixture artifacts/temporary DB are allowed only for edge-case unit coverage; the W-003 served API check must use the published runtime code and runtime artifact/data resolution path | controlled_simulation | Unit tests prove display-field shape and edge cases; served API evidence separately records whether real runtime data produced replay rows or a readable source-gap state, with true-forward/replay counts separated. |
| PF-003 | Backend projection builds catch-up rows from existing local data/artifacts without refreshing market data, calling models, or writing paper-ledger rows. | Focused backend tests and runtime verification script that runs read-only checks. | Shortpick V2 read model/projection builder | fixture data may be generated only for deterministic edge cases; runtime verification must not rely on those fixtures and must not create ledger rows | controlled_simulation | Tests verify no ledger mutation is required, replay evidence labels are explicit, and the runtime check proves the real published path returns replay rows or a readable gap state without raw errors. |
| PF-004 | Frontend converts backend fields into readable Chinese rather than exposing internal field names. | Static tests and built bundle/browser inspection. | `ShortpickLabV2View` | none | matches_product_path | Visible text uses Chinese labels for status, evidence, actions, strategy, and row tags; raw status/config identifiers and snake_case/key-shaped strings are absent from user-facing paper-tab strings. |
| PF-005 | Closeout follows project policy for live-facing changes. | Pre-push hook plus explicit runtime verification after merge/main push. | Git hooks, publish script, runtime services | none | matches_product_path | Default pytest, policy audit, task branch push, merge to main, origin/main push, plan archive, run archive, final-main runtime publish, and final-main runtime verification are recorded. |
| PF-006 | User opens `试验田v2 -> 历史回放` and expects a statistics-only summary, not a detailed replay table. | Static frontend test plus served browser text check after publish. | `ShortpickLabV2View` | none | matches_product_path | The historical replay tab renders aggregate cards/config summary only; visible page text excludes `决策样本`, per-sample detail columns, and raw sample/detail identifiers. |

## Scope

### In Scope

- Add or extend a v2 paper-tracking projection that supplies readable display data for latest simulated trade, strategy explanation, chart inputs, and table rows.
- Add replay-tagged catch-up rows from signal date `2026-05-08` through the latest available source date, while preserving true-forward/replay separation and avoiding full-history market reads for this bounded display.
- Update the v2 paper-tracking frontend to follow the v1 section structure and remove raw field-shaped visible content.
- Keep the `历史回放` tab statistics-only by removing concrete decision/detail-row rendering from that tab.
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
| W-003 | in_progress | 3 | W-001,W-002 | Create the live-facing closeout verifier, fix release-blocking display/runtime defects found by the verifier, dry-run it before merge, then perform archive, task-branch push, main merge/push, final-main publish, and final served verification. The verifier must assert the runtime commit stamp equals the expected commit, `coverage_start == 2026-05-08`, inclusive row-or-gap coverage through the latest available source date using explicit coverage date arrays, separated replay/true-forward counts, no full-history market read for the paper display projection, no concrete historical replay detail table, and no snake_case/key-shaped visible strings on the served v2 tabs. | New runtime verification script, bounded paper-display market read, statistics-only historical replay tab, pre-merge dry-run evidence, served API/browser evidence from final `origin/main`, archived run doc, archived plan, task branch push, main merge/push | command_exit_0 | cmd:bash scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh | |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- `试验田v2 -> 纸面追踪` opens with v1-like sections: `最新模拟交易`, `策略说明`, chart content, and a table.
- Rows from `2026-05-08` through the latest available source date appear when data is available and carry visible `回放` tags.
- Backend paper display projection reads only a bounded window required for the `2026-05-08`-to-current display, not the full historical market table.
- `试验田v2 -> 历史回放` shows statistical/summary values only and does not render concrete decision-sample/detail rows.
- Coverage evidence includes `coverage_start = 2026-05-08`, `coverage_end`, `latest_source_signal_date`, replay row count, gap count, and proof that every available source signal date in the inclusive window produced either a replay display row or a readable gap.
- Replay-tagged rows are not described as true-forward paper performance and do not increase true-forward paper-ledger counts.
- The paper tab does not expose raw field-shaped strings or config identifiers as the primary visible language.
- All strategy/config/status/action explanations visible to the user are Chinese-readable.
- `/shortpick-lab-v2/paper-tracking` remains backward compatible: existing top-level fields stay present, new display fields are additive/optional, and summary/full endpoints keep their intended row-payload behavior.
- H10 fixed85/fixed80 remain the governed candidates; fixed90 remains diagnostic-only.
- V2 remains limited to `纸面追踪` and `历史回放`.
- The task branch is pushed, merged to `main`, `origin/main` is pushed, the plan and run docs are archived, and temporary run state is cleaned.
- Runtime is published and the real served API/page are verified after the committed changes.
- W-003 verifier has been dry-run before merging to `main`, then run again after final-main publish.
- Runtime commit stamp at `output/releases/latest-successful.commit` matches the expected final `origin/main` commit.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md`
- MiMo plan review reports no unresolved blocking findings.
- Codex escalation plan review reports no unresolved blocking or major findings.
- MiMo run-plan/code reviews report no unresolved blocking findings for each run.
- Codex escalation run/code review is required for W-001 and W-003 and must report no unresolved blocking or major findings.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`
- `python3 -m pytest -q tests/test_frontend_shortpick_static.py`
- `cd frontend && npm run build`
- A focused backend regression test proves the paper display projection does not call the full daily-series loader.
- A focused frontend static test proves the historical replay tab does not render decision-sample/detail rows.
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
- Risk: bounded paper-display replay accidentally uses offline backtest input loaders and blocks runtime on the large market database. Mitigation: use a bounded market-bar window and add a regression test that fails if the full daily-series loader is invoked.
- Risk: historical replay becomes a second detailed backtest screen. Mitigation: remove the decision-sample table from the tab and verify only summary/statistical readouts remain visible.

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
| 8 | 2026-06-15 | Started W-003 closeout verification run after W-002 checkpoint commit `39ca7d7`. | Codex |
| 9 | 2026-06-15 | Accepted W-003 MiMo run-plan findings: added pre-merge dry-run, runtime commit-stamp assertion, explicit coverage-array row-or-gap checks, and generic served-page snake_case checks. | Codex |
| 10 | 2026-06-15 | Accepted W-003 MiMo code-review findings: browser verification now covers both v2 tabs, true-forward table consistency is asserted when relevant, visible English technical fallback copy was removed, and snake_case scanning has an explicit allowlist escape hatch. | Codex |
| 11 | 2026-06-15 | Accepted W-003 Codex escalation review finding: verifier now directly checks historical replay API data load and requires data-dependent replay-tab page text, closing the empty-shell false-pass risk. | Codex |
| 12 | 2026-06-15 | Accepted user clarification: paper tracking details are bounded to the `2026-05-08`-to-current display window, backend display generation must avoid full historical market reads, and historical replay must become statistics-only with no concrete decision/detail rows. | Codex |
| 13 | 2026-06-15 | Accepted W-003 Codex implementation review findings: true-forward ledger records now reject dates before `2026-05-08`, verifier checks final table row dates, window-loader date filtering has direct test coverage, and historical replay keeps `sample_limit=1` API compatibility while the UI requests `sample_limit=0`. | Codex |
| 14 | 2026-06-15 | Completed W-003 fix review pass with MiMo: bounded paper-display reads, statistics-only historical replay, row-level verifier checks, and API compatibility tests have no unresolved blocking/major/material findings. | Codex |
| 15 | 2026-06-15 | Accepted W-003 runtime dry-run findings: verifier now follows statistics-only historical replay semantics, paper-display cold path requests only the single display H10 source, the read window is capped to 120 days before `2026-05-08` through latest market day, and cold runtime read-model timing is under the verifier timeout. | Codex |
| 16 | 2026-06-15 | Accepted FastAPI cold-path finding: v2 paper-tracking routes now use `response_model=None`, the read model explicitly returns `records: []` on summary/empty projections, and full-route TestClient coverage prevents payload filtering regressions. | Codex |
| 17 | 2026-06-15 | Clarified runtime verification strategy: the dedicated verifier prewarms the v2 paper API with a bounded 120-second cap, then enforces a 30-second served API fetch for the user-facing hot path. | Codex |
| 18 | 2026-06-15 | Stabilized browser verification after finding Playwright `run-code` did not enforce waits: the verifier now polls real `document.body.innerText`, waits for data-loaded paper/history terms, and clicks the exact history tab role element. | Codex |

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
| 3 | MiMo | W-003 should dry-run the verifier before merge because first running it after `main` publish would raise rollback cost if the verifier itself is broken. | major | accepted | W-003 now requires a pre-merge dry-run before main merge, followed by final-main publish and verification. | W-003 |
| 3 | MiMo | W-003 verifier should assert runtime commit/build stamp equals expected final commit, not only inspect data fields that could match stale code. | major | accepted | W-003 verifier now checks `output/releases/latest-successful.commit` against the expected commit. | W-003,PF-001,PF-005 |
| 3 | MiMo | Row-or-gap accounting and raw-text checks need concrete implementation details. | minor | accepted | W-003 verifier now checks `available_source_signal_dates`, `covered_signal_dates`, `gap_signal_dates`, `row_or_gap_*` booleans, replay/true-forward summary consistency, and a generic snake_case visible-text regex. | W-003,SRC-004,SRC-005 |
| 3 | MiMo | W-003 code review found the browser check only covered the paper tab and could miss historical-replay visible raw text. | major | accepted | The verifier now switches to `历史回放` and applies the same visible-text/raw-field checks there. | W-003,SRC-005,SRC-007 |
| 3 | MiMo | If true-forward count is positive, the verifier should ensure the display table has a visible `真实前向` row. | major | accepted | The API verifier now fails when `true_forward_record_count > 0` but no table row is tagged `真实前向`. | W-003,SRC-006 |
| 3 | MiMo | Generic snake_case visible-text checks may need a future controlled escape hatch. | major | accepted | The check remains strict by default and now supports `ASHARE_VERIFY_ALLOWED_VISIBLE_SNAKE_CASE` for explicit allowlisted exceptions. | W-003,SRC-005 |
| 3 | Codex | Historical replay browser checks could false-pass on static shell text if the historical replay API failed. | major | accepted | The verifier now curls `/shortpick-lab-v2/historical-replay?sample_limit=5`, asserts positive selected configs/baselines/decision samples and expected evidence basis, then requires data-dependent replay-tab text such as `历史账户回放筛选` and `已记录来源`. | W-003,SRC-007 |
| 3 | Codex | Final evidence should record actual URL if page URL is overridden and ensure expected commit equals the published runtime commit. | minor | accepted | The run doc will record the actual page URL and commit used by the pre-merge and final verifier runs. | W-003,PF-001 |
| 3 | MiMo | User clarification is adequately reflected: paper display is bounded to the 2026-05-08-to-current window, full-history market reads are release-blocking, and historical replay is statistics-only. | note | accepted | No blocking or major issue. Minor suggestion to list passive source rows in the run doc is non-blocking because W-003 already copies its direct source coverage and preserves the earlier W-001/W-002 evidence. | SRC-011,SRC-012,W-003,PF-006 |
| 3 | Codex | Existing true-forward ledger rows could still contain `signal_date < 2026-05-08`, leaking pre-anchor details into the paper table even after replay rows were bounded. | major | accepted | `_validate_paper_tracking_record` now requires ISO `signal_date` on or after `2026-05-08`; a regression test writes a `2026-05-07` ledger row and asserts the read model rejects it. | SRC-004,SRC-011,W-003 |
| 3 | Codex | Runtime verifier checked coverage arrays but not the final `paper_display.table.rows`, so a display-row leak before `2026-05-08` could pass. | major | accepted | The verifier now checks every final table row has a signal date and that it is not before `coverage_start`. | SRC-004,SRC-011,W-003 |
| 3 | Codex | The no-full-loader regression test did not directly prove the bounded replay-window SQL helper filters market bars by date. | minor | accepted | Added a direct helper test that seeds out-of-window market bars and asserts the loaded bar days are within the requested window. | SRC-011,W-003 |
| 3 | Codex | Moving the served historical replay path to `sample_limit=0` weakened explicit compatibility coverage for clients that still request detail samples. | minor | accepted | The read-model test now asserts `sample_limit=1` still returns one decision sample while `sample_limit=0` returns no samples and records a zero limit in summary. | SRC-009,SRC-012,W-003 |
| 3 | MiMo | Final W-003 fix review found no unresolved blocker, major, or material minor issue after the Codex findings were addressed. | note | accepted | MiMo confirmed the `2026-05-08` floor, statistics-only UI request, sample-limit compatibility, bounded-window loader test, and runtime row-date/detail-text verifier checks. | SRC-009,SRC-011,SRC-012,W-003,PF-006 |
| 3 | Runtime dry-run | The verifier still required positive historical replay `selected_configs`, but the real current statistics-only data has zero selected configs, one baseline config, and four rejected configs. | major | accepted | Verifier now allows zero selected configs, requires baseline/statistical config rows, checks summary counts, checks `decision_sample_limit == 0`, and rejects any non-empty `decision_samples`. | SRC-012,W-003,PF-006 |
| 3 | Runtime dry-run | The first cold paper-tracking API request completed but was too slow for a smoke verifier. | major | accepted | Paper display now loads only 120 days of lookback plus current bars and asks the H10 helper for only `quiet_breakout_rank2_poolhot10_mtw`; a cold runtime read-model check completed in about 8.2 seconds. | SRC-011,W-003,PF-002 |
| 3 | MiMo | One shard claimed paper-tracking detail rows violate the statistics-only requirement. | blocking | rejected | The finding applied the `历史回放` requirement to `纸面追踪`; the user explicitly requires paper tracking to show detailed results from `2026-05-08` onward with `回放` tags. | SRC-003,SRC-004,SRC-012 |
| 3 | MiMo | API cold-path replay construction remains heavier than a pure artifact read path. | major | accepted | The hot path is still dynamic because current artifacts stop at `2026-05-08`, but the implementation was reduced to a single display source and a 120-day read window; verifier now imposes a 30-second API timeout. | SRC-011,W-003,PF-002 |
| 3 | MiMo | Final sharded synthesis returned PASS after reviewing the performance/verifier fixes. | note | accepted | Second shard confirmed the statistics-only historical replay verifier and tests; synthesis returned PASS with no unresolved blocker or major issue. | W-003,PF-006 |
| 3 | Runtime cold-path test | Even after dynamic replay was reduced, the LaunchAgent-served paper API still took about 35.5 seconds cold, while the same read model took about 7-9 seconds in a direct process. | major | accepted | The paper-tracking routes now explicitly set `response_model=None`, avoiding FastAPI response-model validation on the deep display payload; a temporary FastAPI cold request against runtime DB/artifacts completed in about 6.7 seconds. | SRC-011,W-003,PF-002 |
| 3 | MiMo | Full `/shortpick-lab-v2/paper-tracking` needed API-level coverage after disabling response model validation. | minor | accepted | Added a TestClient full-route test that asserts `records` remains present, paper display rows are returned, rows are tagged `回放`, and coverage starts at `2026-05-08`. | SRC-009,SRC-011,W-003 |
| 3 | Runtime verifier | LaunchAgent cold requests can still compete with startup/browser traffic; the release verifier should validate the route after bounded prewarm, not fail the whole release on a one-time cold cache fill that completes. | minor | accepted | The verifier now prewarms `/shortpick-lab-v2/paper-tracking` with a 120-second cap, then performs the actual API validation with the normal 30-second cap so the served post-deploy user path is proven fast. | SRC-008,SRC-011,W-003,PF-001 |
| 3 | MiMo | Focused verifier review after the browser polling fix found no blocker or major issue; two minor notes about implicit `--raw eval` output format and commit-stamp proxy semantics have no current impact. | minor | accepted | The script's own Python substring checks tolerate the current `--raw eval` output, the local served verifier passed, and commit-stamp verification remains paired with API/browser checks and publish-script ownership. | W-003,PF-001,PF-002,PF-006 |

## User Review Notes

- User requested implementation, not just discussion, and explicitly required `reviewed-plan-generator` plus `plan-run-loop`.
- User previously approved not blocking on approval prompts during the run; this plan records that approval but still requires review and execution evidence before merge.
