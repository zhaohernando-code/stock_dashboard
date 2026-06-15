# Run ID

2026-06-15-W-003-h10-rank-ablation-validate

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929/plans/active/plan-20260615-h10-rank-ablation.md

## Hop ID

W-003

## Work item ID

W-003

## Goal

Validate the generated H10 rank-ablation artifact with the machine-checkable CLI validator.

## Non-goals

- Do not regenerate the artifact unless validation shows a code or artifact defect.
- Do not interpret the strategy outcome in this hop; W-004 owns durable interpretation.
- Do not publish runtime/frontend changes.
- Do not write to the runtime database or refresh market data.

## Plan evidence

W-003 acceptance is the exact validation command:

`PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation-validate --artifact output/shortpick-v2-h10-rank-ablation-artifact.json`

The validator must exit non-zero if fixed H10, rank1/2/3 presence, support label, coverage threshold, or no-promotion checks fail.

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run continues the reviewed plan/run workflow after W-002 completed. |
| SRC-002 | Validation checks `horizon_days=10`. |
| SRC-003 | Validation checks mandatory rank1/rank2/rank3 rows. |
| SRC-004 | Validation checks the rank2 baseline source. |
| SRC-005 | Validation checks no-delayed-buy/no-promotion semantics through artifact policy fields. |
| SRC-006 | Validation checks `claim_ceiling=research_observation` and research-only recommendation. |

## Files expected to change

- `plans/active/plan-20260615-h10-rank-ablation.md`
- `runs/archive/2026-06-15-W-003-h10-rank-ablation-validate.md`

## Implementation steps

1. Run MiMo run-plan review.
2. Run the W-003 validation command exactly as specified.
3. Record exit code and validation summary.
4. Update the plan's W-003 row and mark W-003 done if the command exits 0.

## Acceptance criteria

The W-003 validation command exits 0 and reports `status=passed`.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation-validate --artifact output/shortpick-v2-h10-rank-ablation-artifact.json

## Planned Evidence

- MiMo run-plan review has no blocking or major findings.
- Validation command exits 0.
- Validation output reports `status=passed`.

## Actual Evidence

- MiMo run-plan review passed with no blocking, major, or minor findings.
- Command exited 0: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation-validate --artifact output/shortpick-v2-h10-rank-ablation-artifact.json`.
- Validation output reported `status=passed`, `check_count=53`, `failed_check_count=0`.
- Artifact summary: artifact id `shortpick_v2_h10_rank_ablation:2023-05-16:2026-05-08:20260615`, `horizon_days=10`, `rank2_status=supported`, `rank_row_count=5`.

## Risk and rollback notes

If validation fails, the run should stop and repair either W-001 validator logic or the generated artifact path before proceeding. Rollback is no-op for source state because validation is read-only.

## Gate plan

- Plan validator before command execution.
- MiMo run-plan review before command execution.
- W-003 command exit 0.

## MiMo plan-review result

Passed with no blocking, major, or minor findings. MiMo confirmed the run plan is narrow and W-004 owns interpretation.

## Codex escalation plan-review result

Not required unless MiMo reports blocking/major issues.

## Implementation summary

Ran the rank-ablation validator against the W-002 output artifact. The validator confirmed fixed H10, rank1/rank2/rank3 row presence, thresholds, support-label consistency, no-delayed-buy semantics, research-only claim ceiling, and no-promotion semantics.

## MiMo code-review result

Not applicable unless validation exposes a code defect.

## Codex escalation code-review result

Not required.

## Gate results

- W-003 validation command: exit 0.
- Validation status: passed.
- Check count: 53; failed check count: 0.

## Plan update summary

W-003 was updated from pending to in_progress after W-002 completion, then to done after the validation command exited 0 with `status=passed`.

## Plan archive result

Not applicable until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-003-h10-rank-ablation-validate.md` before the W-003 commit.
