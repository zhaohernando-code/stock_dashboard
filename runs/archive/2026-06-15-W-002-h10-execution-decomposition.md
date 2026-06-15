# Run: 2026-06-15-W-002-h10-execution-decomposition

## Run ID

2026-06-15-W-002-h10-execution-decomposition

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-robust-strategy-search-42e199/plans/active/plan-20260615-h10-quiet-benchmark-robustness.md

## Hop ID

W-002

## Work item ID

W-002

## Goal

Add a machine-readable h10 quiet execution decomposition artifact/report for fixed80, fixed85, and diagnostic-only 90k configs.

## Non-goals

- Do not run real runtime artifacts; that is W-003.
- Do not implement the standalone artifact validation CLI; that is W-004.
- Do not change selection thresholds, turnover gates, or paper-tracking status.
- Do not add new strategy families or delayed-buy behavior.

## Plan evidence

W-002 task: "Add funds/execution decomposition for fixed80/fixed85/90k quiet champion configs."

Acceptance Type: `test_pass`

Acceptance Spec: `cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q`

## Source coverage evidence

| Source ID | Source Requirement | W-002 Coverage |
|-----------|--------------------|----------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop for subsequent development. | This run uses lock/state/run records plus MiMo run-plan and code reviews. |
| SRC-004 | Keep 90k as diagnostic boundary research, not a promoted candidate. | The decomposition must label 90k as diagnostic-only and not selected. |
| SRC-005 | Add funds execution decomposition after robustness, covering board-lot, cash, turnover, skip, winner, and funding effects. | The artifact must compare fixed80/fixed85/90k across board-lot, cash deployment, turnover/skip, winner concentration, and funding deltas. |

SRC-002 is not directly covered by W-002; benchmark-first targeting was completed in W-001 and is consumed here.

## Files expected to change

- `src/ashare_evidence/shortpick_v2_h10_execution_decomposition.py`
- `src/ashare_evidence/shortpick_v2_h10_robustness.py`
- `src/ashare_evidence/cli.py`
- `docs/contracts/registry/schemas/shortpick_v2_h10_execution_decomposition_artifact.schema.json`
- `tests/test_shortpick_v2_h10_robustness.py`
- `tests/test_shortpick_v2_strategy_search.py` only if rule-config or CLI coverage needs a focused assertion.
- `plans/active/plan-20260615-h10-quiet-benchmark-robustness.md`
- This run document, later moved to `runs/archive/`.

## Implementation steps

1. Expose enough execution detail from h10 robustness rows for decomposition, including reason counts and target/lot metadata where available; cash deployment is derived from robustness summary fields such as total buy value, final cash, final market value, and mean invested ratio.
2. Add a decomposition builder and writer that derives fixed80/fixed85/90k rows from a h10 robustness artifact or from replay/selection inputs.
3. Register `shortpick-v2-h10-execution-decomposition` in the CLI with the W-003-compatible arguments.
4. Add schema-backed tests for the decomposition artifact and parser/output behavior.

## Acceptance criteria

- The artifact contains fixed80, fixed85, and 90k rows when the source replay contains them.
- 90k is marked diagnostic-only and cannot be interpreted as selected or promoted.
- Rows include board-lot, cash deployment, turnover/skip, winner concentration, and funding delta dimensions.
- Tests validate the artifact shape and CLI parser for the W-003 command.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q

## Planned Evidence

- MiMo run-plan review: pending.
- Code change summary: pending.
- MiMo code-risk review: pending.
- Gate: `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q`.

## Actual Evidence

- Syntax smoke: `python3 -m compileall -q src/ashare_evidence/shortpick_v2_h10_execution_decomposition.py src/ashare_evidence/shortpick_v2_h10_robustness.py src/ashare_evidence/cli.py tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py` exited 0.
- W-002 acceptance gate: `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q` exited 0 with 45 passed in 0.83s.

## Risk and rollback notes

Main risk is overclaiming diagnostic 90k or deriving decomposition from incomplete summary fields. Rollback is limited to the new decomposition module/CLI, h10 robustness metadata additions, tests, and schema file.

## Gate plan

Run the W-002 acceptance command after MiMo code review:

`python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q`

## MiMo plan-review result

Passed. MiMo reported no blocking or major issues. Accepted two minor documentation clarifications: cash deployment derives from robustness summary fields, and SRC-002 is not directly covered by W-002 because W-001 supplies benchmark-first targeting.

## Codex escalation plan-review result

Not required.

## Implementation summary

- Added `shortpick_v2_h10_execution_decomposition.py` with a schema-versioned execution decomposition artifact and writer.
- Decomposition rows cover fixed80, fixed85, and diagnostic-only 90k across board-lot, cash deployment, turnover/skip, winner concentration, and funding deltas versus fixed85.
- Added `reason_counts` and `board_lot_size` metadata to h10 robustness rows/parameter stability so decomposition has machine-readable execution inputs.
- Registered `shortpick-v2-h10-execution-decomposition` CLI with W-003-compatible arguments and default output.
- Added JSON schema and focused tests for artifact shape, parser defaults, and h10 quiet 80/85/90k rule config support.

## MiMo code-review result

Passed after fixes. MiMo reported no blocking or major issues, but found an undefined `lot_policy` reference in `_parameter_stability`; fixed by extracting `lot_policy` from the replay rule row before reading `board_lot_size`. Also added a comment documenting why missing 90k does not block readiness, and strengthened tests to assert 80k/85k/90k target notionals. Second narrow MiMo review confirmed no blocking or major issues remain.

## Codex escalation code-review result

Not required.

## Gate results

Passed. `python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q` exited 0 with 45 passed in 0.83s.

## Plan update summary

Plan W-002 moved from `in_progress` to `done` with MiMo review and pytest evidence.

## Plan archive result

Not applicable for W-002.

## Archive and merge result

Run record ready to archive under `runs/archive/2026-06-15-W-002-h10-execution-decomposition.md`; merge deferred until full plan completion.
