# Run: 2026-06-15-W-004-h10-artifact-validation

## Run ID

2026-06-15-W-004-h10-artifact-validation

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-robust-strategy-search-42e199/plans/active/plan-20260615-h10-quiet-benchmark-robustness.md

## Hop ID

W-004

## Work item ID

W-004

## Goal

Validate the W-003 runtime h10 robustness and execution decomposition artifacts with a machine-checkable structure and content gate.

## Non-goals

- Do not rerun the real-data backtests unless the existing artifacts are missing or invalid for non-code reasons.
- Do not publish runtime/frontend.
- Do not promote paper tracking.
- Do not broaden strategy search or change the fixed80/fixed85/90k scope.

## Plan evidence

W-004 task: "Validate generated robustness and execution decomposition artifacts with machine-checkable structure/content gates."

Acceptance Type: `command_exit_0`

Acceptance Spec: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-artifact-validate --robustness-artifact output/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json --execution-artifact output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json`

## Source coverage evidence

| Source ID | Source Requirement | W-004 Coverage |
|-----------|--------------------|----------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop for subsequent development. | This run uses lock/state/run records plus MiMo review. |
| SRC-002 | Prioritize fixed85/fixed80专项稳健性 instead of new strategy search. | Validator must assert fixed85/fixed80 benchmark rows in the robustness artifact. |
| SRC-003 | Evaluate annual/period stability and top-winner removal before paper tracking. | Validator must assert period reset, risk flags, and top-winner stress content exist for benchmark rows. |
| SRC-004 | Keep 90k as diagnostic boundary research, not a promoted candidate. | Validator must assert 90k diagnostic role and diagnostic-only execution row. |
| SRC-005 | Add funds execution decomposition after robustness, covering board-lot, cash, turnover, skip, winner, and funding effects. | Validator must assert decomposition dimensions for fixed80/fixed85/90k and no missing config IDs. |

## Files expected to change

- `src/ashare_evidence/shortpick_v2_h10_artifact_validation.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_h10_artifact_validation.py`
- `plans/active/plan-20260615-h10-quiet-benchmark-robustness.md`
- This run document, later moved to `runs/archive/`.

## Implementation steps

1. Add a validator that loads both JSON artifacts, validates them against their schemas, and applies h10-specific content gates:
   fixed85/fixed80 benchmark rows, 90k diagnostic-only row, `claim_ceiling == research_observation`, benchmark top-winner stress, period reset rows, no missing execution config IDs, and matching execution source robustness artifact.
2. Register `shortpick-v2-h10-artifact-validate` in the CLI.
3. Add focused tests for parser acceptance, pass/fail validation behavior, and summary output shape.
4. Run focused tests and the exact W-004 acceptance command against the W-003 output files.

## Acceptance criteria

- The CLI command exits 0 for the generated W-003 artifacts.
- Validation fails for missing benchmark or diagnostic-only evidence.
- The validation summary records which checks passed and explicitly proves `claim_ceiling == research_observation` for both artifacts.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-artifact-validate --robustness-artifact output/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json --execution-artifact output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json

## Planned Evidence

- MiMo run-plan review: pending.
- Focused pytest result: pending.
- W-004 acceptance command output: pending.

## Actual Evidence

- Added `shortpick-v2-h10-artifact-validate` as a pure file-validation CLI command.
- Focused pytest gate passed: `python3 -m pytest tests/test_shortpick_v2_h10_artifact_validation.py tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q` passed with 54 tests.
- Focused ruff gate passed for `src/ashare_evidence/shortpick_v2_h10_artifact_validation.py`, `tests/test_shortpick_v2_h10_artifact_validation.py`, and `src/ashare_evidence/cli.py`.
- W-004 acceptance command exited 0.
- Acceptance command summary: `status=passed`, `check_count=25`, `failed_check_count=0`.
- Robustness artifact summary: `claim_ceiling=research_observation`, `recommendation_status=not_ready_for_paper_tracking`, `analyzed_config_count=6`, `risk_flag_count=5`, `high_risk_flag_count=4`.
- Execution artifact summary: `claim_ceiling=research_observation`, `decomposed_config_count=3`, `missing_config_ids=[]`.

## Risk and rollback notes

The code change is read-only validation and CLI registration. If the validator rejects valid artifacts due to an over-specific check, tighten the check to the documented W-004 acceptance contract rather than weakening schema or artifact generation.

## Gate plan

Run focused pytest for h10 robustness/strategy-search coverage, then run the exact W-004 validation command.

## MiMo plan-review result

Passed after accepting feedback. MiMo reported no blocking findings. Accepted major feedback by making `claim_ceiling == research_observation` an explicit content gate and aligning the expected test file with the planned implementation. Accepted minor feedback by moving validation into a dedicated module and listing concrete content checks.

## Codex escalation plan-review result

Not required.

## Implementation summary

Implemented a dedicated artifact validation module and CLI command. The validator reads only local JSON files, validates both artifacts against their schemas, then checks fixed85/fixed80 benchmark rows, 90k diagnostic-only status, research-only claim ceilings, top-winner stress, yearly period rows, preserved risk flags, source robustness linkage, target notionals, execution dimensions, pairwise funding effects, and the no-promotion policy.

## MiMo code-review result

Passed. Initial MiMo code review reported no blocking findings and requested additional failure-path tests for schema-root failure, missing benchmark configs, and execution benchmark drift. Those tests and related defensive checks were added. MiMo re-review reported no blocking or major findings; two minor defensive suggestions were also accepted by protecting `NO_DB_COMMANDS` and rejecting unexpected pairwise funding baselines.

## Codex escalation code-review result

Not required unless MiMo raises a blocker.

## Gate results

Passed.

- `python3 -m pytest tests/test_shortpick_v2_h10_artifact_validation.py tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q`: 54 passed.
- `python3 -m ruff check src/ashare_evidence/shortpick_v2_h10_artifact_validation.py tests/test_shortpick_v2_h10_artifact_validation.py src/ashare_evidence/cli.py`: passed.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-artifact-validate --robustness-artifact output/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json --execution-artifact output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json`: exited 0 with 25 checks passed.

## Plan update summary

Plan W-004 moved from `in_progress` to `done` with validation command, test, ruff, and MiMo evidence.

## Plan archive result

Not applicable for W-004.

## Archive and merge result

Run record ready to archive under `runs/archive/2026-06-15-W-004-h10-artifact-validation.md`; merge deferred until full plan completion.
