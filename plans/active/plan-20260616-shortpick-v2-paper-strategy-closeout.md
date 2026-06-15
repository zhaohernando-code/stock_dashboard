---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-paper-strategy-closeout"
title: "Shortpick V2 Paper Strategy Closeout"
status: "done"
created_at: "2026-06-16"
source_request: "Close the user-reported 试验田v2 paper-tracking and historical-replay regressions: restore prior high-performing strategy evidence, align paper tracking with v1 structure, add sell/return visibility, support frozen plus control strategies, and verify through real served routes."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-shortpick-v2-paper-strategy-closeout"
owner: "user"
review_rounds: 3
---

# Plan: Shortpick V2 Paper Strategy Closeout

## Compaction-Resistant Summary

Goal: repair `试验田v2` so historical replay restores H10 quiet champion evidence and paper tracking matches v1-style usable paper tracking.
Hard scope: no delayed buy, no fixed90 promotion, no new broad strategy search, no true-forward performance claim for replay-tagged rows.
Key dependencies: `DECISIONS.md`, H10 archived docs/artifact, v2 read model, v1 paper-tracking UI helpers, runtime publish path.
Major risks: confusing historical replay with true-forward paper tracking, losing fixed85/fixed80 again to old artifacts, overfitting UI to raw keys.
Approval state: MiMo plan review passed without blocking/major findings; prior user standing approval authorizes execution without approval blocking.

## Goal

Close the user-reported `试验田v2` regression end to end: recover the prior high-performing strategy inventory, make `历史回放` show the meaningful fixed-H10 statistical results instead of only old weak rows, and make `纸面追踪` follow the `试验田v1` paper-tracking structure with buy, sell/exit, return, charts, filters, frozen strategy, and controls.

## Problem / Rationale

The current served v2 page technically exposes fixed85/fixed80 as paper-governance metadata, but the user-facing paper tab does not behave like v1 paper tracking: it lacks cumulative return and ranking charts, lacks table filters, lacks exit/return fields, and repeats long row notes. The historical replay tab reads older 2026-06-12 strategy-search artifacts, so it shows weak rejected strategies while omitting the H10 quiet champion results that were later fixed in durable decisions and archives.

The fix must preserve the governance boundary: historical replay is research evidence, replay-tagged rows are not true-forward paper performance, fixed90 remains diagnostic only, and delayed buy remains forbidden.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Preserve and use the full prior strategy inventory from conversation/archive before changing display. | W-001,W-002 | covered | in-scope | Investigation record plus backend/API readout listing fixed85/fixed80, diagnostic fixed90, rank ablation, parameter evidence, and old rejected controls. |
| SRC-002 | `纸面追踪` display structure must match `试验田v1`: latest simulated trade, strategy explanation, line chart, bar chart, and table. | W-003,W-005 | covered | in-scope | Browser/API verification showing latest card, strategy cards, cumulative return chart, ranking/bar chart, and table on canonical v2 paper tab. |
| SRC-003 | Paper table must have filter controls like v1. | W-003,W-005 | covered | in-scope | Frontend test/static check and browser verification showing search, strategy/group, action/entry, exit/return status filters. |
| SRC-004 | Table “说明” must be concise and readable, not long repeated text or raw field-shaped data. | W-002,W-003,W-005 | covered | in-scope | Served page check confirms no raw config/key-shaped strings and notes are concise Chinese. |
| SRC-005 | Paper tracking must show sell/exit situations and a place to view returns, not only buy situations. | W-002,W-003,W-005 | covered | in-scope | Backend rows include exit day/status/return fields; UI table and charts display exit/return values. |
| SRC-006 | Paper tracking must include multiple meaningful strategies; best performer is frozen strategy and other good candidates are controls. | W-001,W-002,W-003,W-005 | covered | in-scope | Served API/UI identifies fixed85 as frozen benchmark, fixed80 as capital-shadow control, fixed90/70k/75k only when clearly labeled diagnostic if included. |
| SRC-007 | Historical replay must not regress to old weak numbers; it must show the high-performing H10 evidence previously found. | W-001,W-002,W-005 | covered | in-scope | `/shortpick-lab-v2/historical-replay?sample_limit=0` shows fixed85 total about +271%, fixed80 about +257%, rank2 ablation context, and old weak rows as rejected/legacy only. |
| SRC-008 | `历史回放` should remain statistics-only and not show concrete decision/detail rows. | W-002,W-003,W-005 | covered | in-scope | Frontend and served checks confirm no decision sample/detail table in historical replay. |
| SRC-009 | `纸面追踪` details should be limited to signal date `2026-05-08` onward and tagged `回放` when backfilled. | W-002,W-003,W-005 | covered | in-scope | Served API coverage starts at `2026-05-08`, rows have `回放` tag, true-forward and replay counts remain separate. |
| SRC-010 | No delayed buy; use fallback or skip only. | W-002,W-005 | covered | in-scope | Backend contract/tests reject delayed actions and UI contains no delayed-buy wording. |
| SRC-011 | Any strategy not beating market and annualized below 30% is not qualified. | W-001,W-002,W-005 | covered | in-scope | Strategy roster marks old weak rows rejected/legacy and qualified rows meet market/annualized gates. |
| SRC-012 | Live-facing changes must publish to runtime and verify real served route/API before closeout. | W-005 | covered | in-scope | Publish command runs with refresh skipped; served API and browser route verified after final merge. |
| SRC-013 | Closeout must identify why the previous process missed the regression. | W-001,W-004 | covered | in-scope | Investigation record plus verifier/test updates documenting missed source-roster and v1-parity gates. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | User opens `/projects/ashare-dashboard/?view=shortpick-v2&shortpickV2Tab=paper-tracking`. | Published runtime browser verification plus served API check. | FastAPI static mount and React bundle | none | matches_product_path | Browser text/screenshot evidence shows v1-like paper sections, charts, filters, exit/return, and strategy roster. |
| PF-002 | Frontend calls `/shortpick-lab-v2/paper-tracking`. | TestClient tests plus served runtime API summary after publish. | FastAPI v2 read model | controlled fixtures only for edge cases; served check uses runtime artifact/data resolution | controlled_simulation | Tests prove shape/edge cases; served API proves runtime rows, start date, tags, and exit/return fields. |
| PF-003 | Frontend calls `/shortpick-lab-v2/historical-replay?sample_limit=0`. | TestClient tests plus served runtime API summary after publish. | FastAPI v2 read model | none for served check | matches_product_path | API shows H10 fixed85/fixed80 and statistics-only payload; no detailed sample rows returned. |
| PF-004 | Strategy evidence source is resolved at runtime without manual user context. | Backend tests and served source-artifact references. | v2 read model artifact resolver | none | matches_product_path | Runtime payload references the chosen durable H10 source and does not fall back to old weak artifact as primary history. |
| PF-005 | Verification gate used during closeout. | New/updated verifier script run after publish. | project closeout scripts | script orchestrates tests/publish/browser checks as an auxiliary guard; closure still depends on PF-001/PF-003/PF-004 served API/browser production-path evidence | controlled_simulation | Script checks semantic roster, headline returns, v1 parity markers, filters, and exit/return visibility. |

## Scope

### In Scope

- Create or update a durable strategy inventory/read-model source for the H10 quiet champion evidence, prioritizing read-model resolution from the archived H10 governance source when generated H10 `output/` artifacts are absent.
- Restore `历史回放` statistics to include fixed85/fixed80 and relevant diagnostics/ablations, while keeping row details out of the UI.
- Extend v2 paper display rows with exit/return fields for replay-tagged rows from `2026-05-08` onward.
- Rework v2 paper UI to align with v1 paper tracking: latest trade, strategy explanation, cumulative return chart, strategy/exit effect chart, filters, and concise table.
- Add backend/frontend tests and runtime verifier checks that fail if fixed85/fixed80 disappear or v1 paper-tracking affordances regress.
- Publish to runtime, verify real served API/browser route, commit, push, merge to `main`, push `origin/main`, archive plan/run records, and clean temporary state.

### Out of Scope

- New broad strategy search or parameter exploration.
- Promotion of fixed90 to active paper/frozen strategy.
- Delayed buy, next-day retry, or discretionary entry.
- Real order execution or production trading automation.
- Claiming replay-tagged rows as true-forward paper performance.

## Assumptions and Dependencies

- The archived H10 governance JSON and markdown docs are accepted durable evidence when generated `output/shortpick-v2-h10-*` JSON files are absent from the current checkout.
- fixed85 is the current frozen benchmark line; fixed80 is the capital-shadow/control line.
- fixed90 can be shown only as diagnostic boundary evidence, not as a paper-tracking active strategy.
- H10 / 10 trading days remains fixed for this repair.
- The runtime local DB has enough market bars after `2026-05-08` to continue producing bounded replay-tagged rows; if not, the UI must show a data gap rather than invent results.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Complete and commit the problem investigation plus strategy inventory source decision. | Investigation doc and chosen durable H10 source contract. | file_contains | path:docs/investigations/SHORTPICK_LAB_V2_PAPER_TRACKING_REGRESSION_2026-06-16.md \| pattern:quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1 | `rg` found the fixed85 benchmark ID in the investigation doc at lines 48 and 70; the doc preserves raw user problem, strategy inventory, direct cause, process gaps, and remediation map. |
| W-002 | done | 2 | W-001 | Repair backend read models so historical replay exposes the H10 strategy statistics and paper tracking projects strategy roster, exit, and return fields without weakening governance; prefer the archived H10 governance artifact as the durable summary source when H10 `output/` artifacts are missing. | Backend read-model/schema/tests for history and paper display. | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py | Passed `30 passed in 4.64s`; default source read-model sample now returns fixed85 `+271.2294%`, fixed80 `+257.2453%`, diagnostic fixed90, and `evidence_basis=h10_governance_summary_only` when old replay artifacts are absent. MiMo code rereview reported no blocking/major findings. |
| W-003 | done | 3 | W-002 | Rework v2 paper-tracking frontend to match v1 paper-tracking structure with charts, filters, concise table notes, multi-strategy roster, and exit/return visibility. | React component/types/styles/tests or static checks. | command_exit_0 | cmd:cd frontend && npm run build | Passed `cd frontend && npm run build`; focused v2 backend/contract tests also passed `30 passed in 5.10s`. Frontend now includes strategy roster, cumulative paper return chart, strategy exit-effect bar chart, search/strategy/action/exit filters, and exit/return table visibility. MiMo sharded review passed after accepting and fixing the `phase6_forward_observation_candidate` label/color mapping finding. |
| W-004 | done | 4 | W-002,W-003 | Add a closeout verifier that checks strategy roster completeness, H10 headline values, v1 paper UI parity markers, filters, no raw keys, no delayed-buy wording, and statistics-only historical replay. | Runtime verification script and focused tests. | command_exit_0 | cmd:bash scripts/verify-shortpick-v2-paper-strategy-closeout-runtime.sh | Passed `bash scripts/verify-shortpick-v2-paper-strategy-closeout-runtime.sh`: focused tests `30 passed in 4.95s`, H10 historical replay inventory verification passed, v2 paper frontend marker verification passed, and frontend build passed with only the existing Vite large chunk warning. Plan validation also passed after W-004 and final MiMo evidence updates. |
| W-005 | done | 5 | W-004 | Run final reviewed closeout: MiMo review, required gates, publish, served API/browser verification, commit, branch push, merge to main, push origin/main, archive plan/run records, and clean temporary state. | Archived run record, archived/done plan, pushed merge, published runtime verification. | manual | manual:final closeout evidence shows merged `main`, pushed `origin/main`, runtime served route verified, and temporary run state cleaned | Final MiMo closeout review found no blocking/major issues. Default pytest passed `924 passed, 173 deselected, 6 subtests passed in 32.59s`; policy audit passed; publish passed with deploy verification `19 passed, 0 failed`; local runtime served API/browser verification passed with `available=27`, `replay=54`, `gaps=0`, `true_forward=0`. Canonical unauthenticated route returned auth 302/401, so browser verification used the authenticated-equivalent local runtime served route. Merge/push evidence is reported in final closeout. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- `历史回放` shows fixed85 and fixed80 H10 quiet champion statistics, including the headline values around `+271%` and `+257%`, and no longer presents old weak rows as the main outcome.
- `纸面追踪` visibly follows v1 paper-tracking structure: latest simulated trade, strategy explanation, cumulative return chart, strategy/exit effect chart, filters, and table.
- Paper table rows include buy/action data plus exit/sell state and return fields where the holding window is available.
- fixed85 is the frozen benchmark strategy; fixed80 is visible as control/capital-shadow; diagnostics remain diagnostic.
- `2026-05-08` onward replay-tagged rows remain clearly marked `回放` and separate from true-forward counts.
- No user-visible raw config/key-shaped fields, no delayed-buy wording, and no false true-forward performance claim.
- Investigation/root-cause record remains committed and references the process gap that allowed the regression.
- Runtime publish and served route/API verification complete after the final merge.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-paper-strategy-closeout.md`
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`
- `cd frontend && npm run build`
- `bash scripts/verify-shortpick-v2-paper-strategy-closeout-runtime.sh`
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- Served API checks for `/shortpick-lab-v2/paper-tracking` and `/shortpick-lab-v2/historical-replay?sample_limit=0`
- Browser verification for `/projects/ashare-dashboard/?view=shortpick-v2&shortpickV2Tab=paper-tracking` and `shortpickV2Tab=historical-replay`

## Risks and Mitigations

- Risk: historical H10 replay JSON files are missing from current `output/`.
  Mitigation: explicitly choose a durable source contract using the archived governance JSON and markdown evidence, or regenerate/copy validated artifacts as part of W-002; tests must prove runtime resolution.
- Risk: UI could imply replay rows are true-forward paper returns.
  Mitigation: keep `回放` tags, true-forward/replay count split, and research-only copy; tests check wording.
- Risk: fixed90 headline value may tempt promotion.
  Mitigation: keep fixed90 diagnostic-only in data model, labels, tests, and verifier.
- Risk: v1 UI reuse may create type mismatch or overly large data payload.
  Mitigation: reuse interaction concepts, not necessarily raw v1 types; keep paper details bounded to `2026-05-08` onward.
- Risk: closeout verifier may only check text again.
  Mitigation: verifier must assert strategy IDs, numeric headline bands, exit/return fields, filter controls, and absence of detail rows in history.

## Open Questions

- W-002 should prefer the archived H10 governance artifact as the durable runtime source for H10 summary readouts when generated H10 JSON artifacts are absent; regenerating/copying `output/` artifacts is allowed only if it improves runtime traceability without making old weak artifacts primary again.
- W-002 should decide whether 70k/75k appear in the UI as secondary diagnostics or remain in documentation only; fixed85/fixed80 must appear regardless.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-16 | Initial remediation plan for v2 paper-tracking and historical-replay regression. | Codex |
| 1 | 2026-06-16 | Accepted MiMo minors: clarified H10 source preference and verifier-vs-production-path relationship; marked plan approved under prior user standing approval. | Codex |
| 2 | 2026-06-16 | Started plan-run-loop execution in worktree `codex/shortpick-v2-paper-strategy-closeout`; W-001/W-002 selected as first implementation hop. | Codex |
| 3 | 2026-06-16 | Completed W-001/W-002 backend repair: investigation recorded, historical replay H10 governance overlay/fallback added, paper display exit/return fields projected, tests and MiMo rereview passed. | Codex |
| 4 | 2026-06-16 | Completed W-003 frontend repair: v2 paper tracking now has multi-strategy roster, v1-like return charts, filters, exit/return columns, and Chinese-readable labels; frontend build and focused tests passed. | Codex |
| 5 | 2026-06-16 | Completed W-004 auxiliary closeout verifier for H10 strategy restoration and v2 paper UI parity markers; verifier passed. | Codex |
| 6 | 2026-06-16 | Ran final MiMo closeout review; no blocking/major findings. Accepted the legacy-reference verifier tightening and recorded that replay-tag served validation remains W-005. | Codex |
| 7 | 2026-06-16 | Completed W-005 gates, publish, and served runtime verification; canonical route requires login for unauthenticated automation, local runtime served browser/API verification passed. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Old artifact repair mechanism should be made less ambiguous before implementation. | minor | accepted | W-002 and scope now state the preferred durable source: archived H10 governance evidence when generated H10 output artifacts are missing. | W-002,PF-004 |
| 1 | MiMo | PF-005 verifier is controlled simulation and should be clearly auxiliary to served API/browser checks. | minor | accepted | PF-005 now states closeout depends on PF-001/PF-003/PF-004 production-path evidence. | PF-001,PF-003,PF-004,PF-005,W-005 |
| 1 | MiMo | No blocking or major findings; source coverage, governance boundaries, and false-positive controls are sufficient. | note | accepted | Confirms the plan is ready for execution after the accepted minor clarifications. | all |
| 2 | MiMo | Backend/read-model W-001/W-002 repair restores H10 fixed85/fixed80 and marks old strategy-search rows as legacy reference only. | note | accepted | Rereview reported no blocking or major findings after H10-only fallback and legacy-source separation fixes. | W-001,W-002 |
| 3 | MiMo | `phase6_forward_observation_candidate` lacked frontend role/color mapping. | major | accepted | Added Chinese label `前向观察候选` and green role color; reran frontend build and focused v2 tests successfully. | W-003 |
| 3 | MiMo | `reasonLabel` could pass through technical strings for old strategy-search/H10 cases. | minor | accepted | Replaced broad substring pass-through with exact known-value Chinese mappings and generic fallback for unknown reasons. | W-003 |
| 3 | MiMo | A 股 red/green value color convention may need confirmation in internationalized contexts. | minor | rejected | This product is an A 股 dashboard and existing project convention uses red for positive and green for negative; no change required. | W-003 |
| 3 | MiMo | Final closeout review found no blocking or major issues in W-004 verifier or plan evidence chain. | note | accepted | Proceeding to W-005 final gates, publish, served verification, merge, and archive. | W-004,W-005 |
| 3 | MiMo | Verifier allowed old baseline/rejected rows with `gate_status=None`, slightly wider than the legacy-reference-only plan language. | minor | accepted | Tightened W-004 verifier to require `gate_status == "legacy_reference"` for old baseline/rejected rows when present; verifier reran successfully. | W-004 |
| 3 | MiMo | Plan validation gate evidence was not explicitly recorded in W-001-W-004 evidence. | minor | accepted | Recorded plan validation pass in W-004 evidence and reran `validate_plan.py`. | W-004 |
| 3 | MiMo | Replay tag presence is delegated to W-005 served API verification rather than W-004 source verifier. | minor | deferred | W-004 is an auxiliary source/worktree verifier; PF-001/PF-003/PF-004 served route checks in W-005 remain the production-path acceptance. | W-005 |

## User Review Notes

- User previously requested the next runtime process not be blocked on approvals and explicitly approved all following run steps. This plan has no source reductions; approval is used only to start execution after successful review.
