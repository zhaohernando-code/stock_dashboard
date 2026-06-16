---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-paper-nav-drawdown-fix"
title: "Shortpick V2 Paper NAV Drawdown Fix"
status: "done"
created_at: "2026-06-16"
source_request: "Fix the 试验田v2 paper tracking calculation problem where paper validation drawdown exceeds 20% because the UI compounds single-trade returns instead of account NAV."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-fix-v2-paper-nav-drawdown"
owner: "user"
review_rounds: 3
---

# Plan: Shortpick V2 Paper NAV Drawdown Fix

## Compaction-Resistant Summary

Goal: fix `试验田v2` paper tracking so charts use account NAV/drawdown, not single-trade return compounding.
Hard scope: no strategy-search changes, no H10 parameter changes, no data refresh, no true-forward claim for replay rows.
Key dependency: runtime paper API, `shortpick_v2_read_model.py`, `ShortpickLabV2View.tsx`, served browser verification.
Major risk: producing another chart that looks account-like but still bypasses account cash/position accounting.
Approval state: user explicitly requested `problem-closeout-loop` repair; MiMo plan review/rereview had no unresolved blockers or majors, so execution is in progress.

## Goal

Close the reported paper-tracking calculation defect end to end. The fixed page must show paper-account return and drawdown from the 20 万 account path per strategy, and must not compound row-level stock returns as if each trade were a full-account return.

## Problem / Rationale

Historical replay reports fixed85/fixed80 maximum drawdown around `-11.90%`, while paper tracking appeared to exceed 20%. Investigation shows the paper tab currently uses `return_text` from each completed trade and applies `cumulative *= 1 + returnValue`. That is a single-trade compounding chart, not an account NAV curve. With the current 2026-05-08 replay window, this produces about `-25.41%`; account-basis realized P/L is about `-8.44%`, and daily marked account drawdown is about `-17.65%`.

The repair must make the chart semantics match the account strategy: 20 万 initial cash, actual whole-lot position costs, overlapping holdings, and strategy-specific cash/position paths.

Original user instruction preserved: `修复纸面追踪的计算问题`.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Preserve the raw user defect report and investigation evidence. | W-001 | covered | in-scope | Investigation doc records raw report, expected/actual behavior, reproduction numbers, direct cause, and missed gates. |
| SRC-002 | Fix paper tracking calculation so drawdown is not inflated by full-trade compounding. | W-002,W-003 | covered | in-scope | Backend/account curve and frontend chart no longer use `cumulative *= 1 + row.returnValue` from row-level `return_text`. |
| SRC-003 | Use an account-level basis comparable to historical replay drawdown. | W-002,W-004 | covered | in-scope | API exposes per-strategy account NAV/drawdown from 20 万 initial cash and actual positions; tests assert drawdown differs from wrong full-trade compounding and stays out of the known wrong `-25%` range. |
| SRC-004 | Keep fixed80/fixed85 strategy semantics unchanged. | W-002,W-004 | covered | in-scope | H10 selected config IDs and historical replay values remain unchanged in focused tests/API checks. |
| SRC-005 | Validate the real paper tracking user path after publish. | W-004 | covered | in-scope | Served runtime API/browser verification shows account NAV chart labels and payload fields on `试验田v2 -> 纸面追踪`. |
| SRC-006 | Close the process gap that allowed the defect to escape. | W-001,W-004 | covered | in-scope | Verifier/test asserts chart source is account NAV, not raw trade-return compounding. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | User opens `试验田v2 -> 纸面追踪` and reads the paper return/drawdown charts. | Published runtime browser verification plus API payload checks. | React `ShortpickLabV2View` and FastAPI paper read model | none | matches_product_path | Browser text confirms account NAV chart labels; API confirms account curves and drawdown fields. |
| PF-002 | Frontend calls `/shortpick-lab-v2/paper-tracking`. | Focused TestClient/read-model tests plus served runtime API. | `shortpick_v2_read_model.py` | controlled fixture for regression math and direct runtime DB/API read, paired with served runtime check | controlled_simulation | Fixture proves wrong compounding is blocked with numeric bounds; served API proves runtime data path emits account curves. |
| PF-003 | Existing runtime verifier checks paper tab. | Update and run `scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh`. | Closeout verifier | none | matches_product_path | Verifier fails if account curves disappear or the old chart wording/algorithm returns. |

## Scope

### In Scope

- Add backend account NAV/drawdown projection for v2 paper display, reusing the existing `/shortpick-lab-v2/paper-tracking` response rather than adding a new endpoint.
- Update frontend paper charts to consume account curves and display per-strategy account return/drawdown.
- Add regression tests for the known defect.
- Update runtime verifier to check account NAV payload and visible account chart wording.
- Publish, served-route verify, merge to main, push `origin/main`, and clean task worktree.

### Out of Scope

- Changing H10 selection rules, fixed80/fixed85 amounts, holding period, or buy/sell logic.
- Running a new broad historical backtest.
- Treating replay-tagged rows as true-forward paper evidence.
- Implementing broker-grade tax/fee accounting beyond the current paper display/replay cost basis.

## Assumptions and Dependencies

- Verified before planning: the runtime DB has `market_bars` 1d closes for the current completed paper symbols, and paper display rows already carry strategy ID, signal/entry/exit dates, quantity, cash before/after, and return fields.
- For comparability, the first repair should prefer daily marked account NAV over realized-only P/L when daily closes are available.
- True-forward ledger rows may have fewer mark-to-market fields; if a complete marked path cannot be produced, the UI must show available account curve data without inventing missing values.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Record investigation and direct defect. | Investigation document. | file_contains | path:docs/investigations/SHORTPICK_LAB_V2_PAPER_NAV_DRAWDOWN_DEFECT_2026-06-16.md \| pattern:cumulative *= 1 + row.returnValue | Investigation doc records the raw problem, reproduction, root cause, downstream scan, and remediation map. |
| W-002 | done | 2 | W-001 | Add backend account NAV/drawdown projection for paper display. Reuse `/shortpick-lab-v2/paper-tracking`, add `paper_display.account_curves`, source daily closes from existing replay `series_by_symbol`, use 20 万 initial cash, actual row cost from `cash_before - cash_after`, whole-lot quantity, entry/exit dates, and mark open positions to daily close. | Read-model fields and tests. | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py | Implemented in `shortpick_v2_read_model.py`; focused pytest passed for replay display, completed-trade account NAV, open-position drawdown, and windowed loader tests. |
| W-003 | done | 3 | W-002 | Update frontend charts/types to use backend account curves instead of row-return compounding; table filters must not recompute account NAV from partial rows, except strategy selection may narrow visible curves. | React/types/styles changes. | command_exit_0 | cmd:npm --prefix frontend run build | `npm run build` passed in `frontend`; charts now render account NAV and max drawdown from `account_curves`. |
| W-004 | done | 4 | W-002,W-003 | Run closeout verification, external review, publish, served browser/API verification, merge, push, and cleanup. | Updated verifier, published runtime, merged main. | manual | manual:checklist: API has `paper_display.account_curves`; visible page says account/NAV basis; served API runtime drawdown does not match old full-trade-compounding drawdown; `git log` and runtime commit stamp equal final commit; `main` and `origin/main` pushed | MiMo review found no blocker/major after open-position test was added. DeepSeek rereview confirmed true-forward account-curve P1 closed. Publish succeeded with deploy verification 19/19. Runtime verifier passed against `http://127.0.0.1:5173/?view=shortpick-v2&shortpickV2Tab=paper-tracking`: API `available=27`, `replay=54`, `true_forward=0`, `account_curves=2`; visible page shows account NAV wording and historical replay tab. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The paper tracking line chart uses backend account NAV curve data, not row-level `return_text` compounding.
- The visible chart copy says account/NAV basis clearly enough that single-trade return and account return are not confused.
- Backend paper API includes per-strategy account curve points with account return and drawdown values.
- Runtime/current-window API drawdown must not reproduce the known wrong full-trade-compounding result. The verifier computes the old table-return compounding drawdown and fails if the account curve still matches that old basis.
- A regression test catches the known case where full-trade compounding reaches about `-25%` while account P/L is much smaller.
- Historical replay selected configs and headline H10 values remain unchanged.
- Runtime served paper tab and historical tab still pass verification after publish.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-paper-nav-drawdown-fix.md`
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`
- `npm --prefix frontend run build`
- `bash scripts/verify-shortpick-v2-paper-strategy-closeout-runtime.sh`
- `bash scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh` against local runtime after publish
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`

## Risks and Mitigations

- Risk: backend NAV reconstruction diverges from historical replay engine accounting.
  Mitigation: label it as paper display account NAV, add tests for directionally correct account basis, and keep row-level returns visible separately.
- Risk: frontend table filters could distort a full account curve.
  Mitigation: chart strategy selector may filter by strategy, but generic table filters must not recompute account NAV from partial rows.
- Risk: true-forward rows do not have enough market data for daily mark-to-market.
  Mitigation: support curves only when enough data exists and show clear empty state.

## Open Questions

- None blocking. Daily marked account NAV is selected as the first repair because it is the closest paper-display counterpart to historical max drawdown.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-16 | Initial plan for v2 paper NAV/drawdown calculation repair. | Codex |
| 1 | 2026-06-16 | Accepted MiMo plan review findings: clarified backend fields/data source, explained fixed80/fixed85 short-window equality, and added numeric correctness gates/checklist. | Codex |
| 2 | 2026-06-16 | MiMo rereview confirmed all prior major findings closed; plan moved to executing under the user's explicit repair request. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-002 lacked concrete backend field/source description and should verify daily close availability. | major | accepted | W-002 now states it reuses `/shortpick-lab-v2/paper-tracking`, adds `paper_display.account_curves`, and sources daily closes from existing replay `series_by_symbol`; assumptions now record runtime DB availability was verified. | W-002,PF-002 |
| 1 | MiMo | Investigation showed identical fixed80/fixed85 paper numbers without explanation. | major | accepted | Investigation now explains that current short-window completed rows buy the same whole-lot quantities after board-lot rounding; this does not imply general equivalence. | W-001 |
| 1 | MiMo | Gates lacked numeric correctness assertions to prevent the `-25%` wrong-compounding result. | major | accepted | Source coverage, acceptance criteria, and W-004 checklist now require numeric bounds and rejection of the known wrong full-trade compounding range. | W-002,W-004 |
| 1 | MiMo | W-004 manual closeout checklist was too broad. | minor | accepted | W-004 acceptance spec now lists API field, visible wording, numeric bound, final commit, runtime stamp, and push checks. | W-004 |
| 1 | MiMo | Preserve the original Chinese user instruction in plan. | minor | accepted | Problem section now quotes `修复纸面追踪的计算问题`. | all |
| 1 | MiMo | Clarify verifier script ownership. | minor | accepted | W-004 explicitly owns updating verifier checks; existing closeout and display verifiers remain in validation gates. | W-004 |
| 1 | MiMo | Rereview found prior major findings closed; W-002 Evidence is empty while pending. | minor | rejected | Pending work-item evidence should remain empty until execution produces real output; W-002 acceptance spec already names the required test evidence. | W-002 |
| 2 | MiMo | Account NAV tests lacked an open-position drawdown case. | major | accepted | Added `test_shortpick_v2_paper_account_curve_marks_open_position_drawdown` covering mark-to-market floating loss before exit. | W-002 |
| 2 | MiMo | Runtime verifier used a brittle fixed `-20%` threshold. | minor | accepted | Verifier now computes the old full-trade-compounding drawdown and checks that account curves do not match it. | W-004 |
| 3 | DeepSeek | `account_curves` only included replay rows; future true-forward ledger rows could be omitted. | major | accepted | Added `_paper_display_account_curves_from_session` and recompute `replay_rows + true_forward_rows` when true-forward rows exist. DeepSeek rereview confirmed the P1 is closed. | W-002,W-004 |

## User Review Notes

- User explicitly requested `problem-closeout-loop` and to repair the paper tracking calculation problem.
