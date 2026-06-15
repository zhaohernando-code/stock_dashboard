# Run: 2026-06-15-W-001-h10-quiet-benchmark-robustness

## Run ID

2026-06-15-W-001-h10-quiet-benchmark-robustness

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-robust-strategy-search-42e199/plans/active/plan-20260615-h10-quiet-benchmark-robustness.md

## Hop ID

W-001

## Work item ID

W-001

## Goal

Make h10 robustness analyze the fixed85/fixed80 quiet champion benchmark configs directly as first-class targets, with 90k retained only as a diagnostic row.

## Non-goals

- Do not add execution decomposition; that is W-002.
- Do not run real runtime artifacts; that is W-003.
- Do not promote paper tracking or weaken turnover/return/drawdown gates.
- Do not reopen broad strategy families or delayed buy.

## Plan evidence

W-001 task: "Make h10 robustness benchmark-focused so fixed85/fixed80 are primary analyzed configs, with 90k allowed only as a diagnostic row."

Acceptance Type: `test_pass`

Acceptance Spec: `cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q`

## Source coverage evidence

| Source ID | Source Requirement | W-001 Coverage |
|-----------|--------------------|----------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop for subsequent development. | This run uses plan-run-loop lock/state/run records plus MiMo run-plan and code review. |
| SRC-002 | Prioritize fixed85/fixed80专项稳健性 instead of new strategy search. | W-001 changes robustness config selection so fixed85/fixed80 benchmarks are analyzed directly. |
| SRC-003 | Evaluate annual/period stability and top-winner removal before paper tracking. | W-001 keeps existing period reset and trade-contribution stress paths applied to the benchmark configs. |
| SRC-004 | Keep 90k as diagnostic boundary research, not a promoted candidate. | W-001 may include a 90k row only with a diagnostic role, not selected/paper-tracking language. |

SRC-005 and SRC-006 are outside W-001 scope; they are covered by W-002 and W-005 respectively.

## Files expected to change

- `src/ashare_evidence/shortpick_v2_h10_robustness.py`
- `tests/test_shortpick_v2_h10_robustness.py`
- `tests/test_shortpick_v2_rule_selection.py` only if selection-role expectations need a focused assertion.
- `plans/active/plan-20260615-h10-quiet-benchmark-robustness.md`
- This run document, later moved to `runs/archive/`.

## Implementation steps

1. Extend `_analysis_configs` to include `benchmark_configs` before selected/holdout/baseline rows so fixed85/fixed80 are primary analyzed configs.
2. Preserve stable roles: benchmark configs should remain benchmark-focused; 90k, if added in this hop, must be diagnostic-only and not a selected config.
3. Adjust risk-flag targeting so benchmark-focused configs receive the same robustness checks that matter for the fixed85/fixed80 decision, primarily by changing the role/config filter inside `_risk_flags()`.
4. Add focused tests proving fixed85/fixed80 benchmark rows are analyzed directly, period/stress outputs apply to them, and 90k is not promoted.

## Acceptance criteria

- `analyzed_configs` includes fixed85 and fixed80 benchmark config IDs as direct rows.
- fixed85/fixed80 rows retain a benchmark role or explicitly benchmark-focused role.
- Any 90k inclusion is diagnostic-only.
- Period reset and top-winner stress outputs include the benchmark configs.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q

## Planned Evidence

- MiMo run-plan review: pending.
- Code change summary: pending.
- MiMo code-risk review: pending.
- Gate: `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q`.

## Actual Evidence

- Syntax smoke: `python3 -m compileall -q src/ashare_evidence/shortpick_v2_h10_robustness.py tests/test_shortpick_v2_h10_robustness.py` exited 0.
- W-001 acceptance gate: `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q` exited 0 with 14 passed in 0.72s.

## Risk and rollback notes

Primary risk is accidentally making selected 70/75k rows look like the decision target again, or treating 90k as promoted despite turnover concerns. Rollback is limited to the robustness config-selection and tests from this run.

## Gate plan

Run the W-001 acceptance command after MiMo code review or after fixing any review blockers:

`python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q`

## MiMo plan-review result

Passed. MiMo reported no blocking or major issues. Accepted two minor documentation clarifications: note that SRC-005/SRC-006 are out of W-001 scope, and clarify that risk flag targeting primarily means the role/config filter inside `_risk_flags()`.

## Codex escalation plan-review result

Not required.

## Implementation summary

- `_analysis_configs` now reads `benchmark_configs` before selected, holdout, and baseline configs.
- Added a controlled `diagnostic_boundary` row for the exact 90k h10 quiet champion config when that replay row exists.
- Risk flags now target fixed85/fixed80 benchmark rows when benchmark rows are present; legacy selection-only artifacts still fall back to `phase5_contract_candidate` targets.
- Added focused tests for benchmark-first analysis order, 90k diagnostic role, period/stress coverage, and benchmark-focused risk targeting.

## MiMo code-review result

Passed. First review reported no blocking or major issues and two minors. Accepted M-2 by adding an explicit assertion that the 90k diagnostic row appears in yearly period reset results. M-1 was closed by recording the pytest gate result. A second narrow MiMo review after the legacy compatibility fix also reported no blocking or major issues.

## Codex escalation code-review result

Not required.

## Gate results

Passed. `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q` exited 0 with 14 passed in 0.72s.

## Plan update summary

Plan set to `executing`; W-001 moved from `in_progress` to `done` with MiMo review and pytest evidence.

## Plan archive result

Not applicable for W-001.

## Archive and merge result

Run record ready to archive under `runs/archive/2026-06-15-W-001-h10-quiet-benchmark-robustness.md`; merge deferred until full plan completion.
