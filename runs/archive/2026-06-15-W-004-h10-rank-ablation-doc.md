# Run ID

2026-06-15-W-004-h10-rank-ablation-doc

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929/plans/active/plan-20260615-h10-rank-ablation.md

## Hop ID

W-004

## Work item ID

W-004

## Goal

Record the H10 rank-ablation interpretation and governance outcome in a durable archive document.

## Non-goals

- Do not change benchmark strategy configuration or paper-tracking state.
- Do not rerun artifact generation or validation unless documentation reveals an evidence mismatch.
- Do not publish runtime/frontend changes.
- Do not introduce new strategy-search directions.

## Plan evidence

W-004 acceptance is a file_contains gate:

`path:docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md | pattern:Rank2 status; no paper-tracking promotion; rank1/rank2/rank3`

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run completes the reviewed plan/run workflow with a durable decision record. Evidence paths: `output/shortpick-v2-h10-rank-ablation-artifact.json` and `runs/archive/2026-06-15-W-003-h10-rank-ablation-validate.md`. |
| SRC-002 | The document states H10 remains fixed and does not reopen holding-period search, citing `analysis_scope.horizon_days=10` from `output/shortpick-v2-h10-rank-ablation-artifact.json`. |
| SRC-003 | The document records direct rank1/rank2/rank3 same-gate evidence from `rank_rows` in `output/shortpick-v2-h10-rank-ablation-artifact.json`. |
| SRC-004 | The document keeps `quiet_breakout_rank2_poolhot10_mtw` as the benchmark anchor, citing `analysis_scope.baseline_source_id` from the artifact. |
| SRC-005 | The document records fallback-or-skip/no-delayed-buy as unchanged context, citing the validator no-delayed-buy check in `runs/archive/2026-06-15-W-003-h10-rank-ablation-validate.md`. |
| SRC-006 | The document states no paper-tracking promotion and research-only claim ceiling, citing the W-003 validation checks and artifact recommendation status. |

## Files expected to change

- `docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md`
- `plans/active/plan-20260615-h10-rank-ablation.md`
- `runs/archive/2026-06-15-W-004-h10-rank-ablation-doc.md`

## Implementation steps

1. Draft the durable interpretation doc from `output/shortpick-v2-h10-rank-ablation-artifact.json` and `runs/archive/2026-06-15-W-003-h10-rank-ablation-validate.md`.
2. Run the file_contains acceptance gate.
3. Run MiMo documentation review.
4. Update the plan's W-004 row and mark W-004 done if the file_contains gate and review pass.

## Acceptance criteria

The durable doc exists and contains `Rank2 status`, `no paper-tracking promotion`, and `rank1/rank2/rank3`.

## Acceptance Type

file_contains

## Acceptance Spec

path:docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md | pattern:Rank2 status; no paper-tracking promotion; rank1/rank2/rank3

## Planned Evidence

- file_contains gate passes.
- MiMo doc review has no blocking or major findings.
- Plan W-004 row records doc outcome and no-promotion semantics.

## Actual Evidence

- Created `docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md`.
- file_contains gate passed for `Rank2 status; no paper-tracking promotion; rank1/rank2/rank3`.
- MiMo doc review passed with no blocking or major findings. One minor style nit was accepted by changing the return-delta sentence to use `pp`; the rank3 market-excess value was spot-checked against the artifact and confirmed as `+8.95%`.

## Risk and rollback notes

The main risk is overstating a historical same-window result as live paper-tracking evidence. Rollback is editing the durable doc before commit to remove unsupported claims.

## Gate plan

- Plan validator before documentation.
- file_contains gate after documentation.
- MiMo doc review after documentation.

## MiMo plan-review result

Required for this final durable documentation hop. Initial run-plan review found two major clarity issues: inconsistent MiMo-doc-review requirement and missing W-002/W-003 evidence paths. Both were accepted and resolved before drafting the document.

## Codex escalation plan-review result

Not required.

## Implementation summary

Documented the validated H10 rank-ablation result. The durable doc records rank2 as `supported` under the bounded same-gate fixed85 test, lists rank1/rank2/rank3 primary evidence, keeps rank4/rank5 diagnostic-only, and states no paper-tracking promotion, benchmark replacement, runtime publish, or database write.

## MiMo code-review result

Passed with no blocking or major findings. MiMo confirmed the document records the required rank2 status, no-promotion guardrail, and rank1/rank2/rank3 evidence without overclaiming. Minor wording feedback was accepted.

## Codex escalation code-review result

Not required unless MiMo reports blocking/major issues.

## Gate results

- `rg -n "Rank2 status; no paper-tracking promotion; rank1/rank2/rank3" docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md`: exit 0.
- MiMo doc review: no blocking or major findings.

## Plan update summary

W-004 was updated from pending to in_progress after W-003 validation, then to done after the durable doc, file_contains gate, and MiMo doc review passed.

## Plan archive result

Plan moved from `plans/active/plan-20260615-h10-rank-ablation.md` to `plans/archive/plan-20260615-h10-rank-ablation.md` after all work items completed.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-004-h10-rank-ablation-doc.md` before the W-004 commit.
