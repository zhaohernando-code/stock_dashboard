# Run ID

2026-06-15-W-001-h10-rank-ablation

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929/plans/active/plan-20260615-h10-rank-ablation.md

## Hop ID

W-001

## Work item ID

W-001

## Goal

Add bounded same-gate H10 rank-ablation support for the current quiet benchmark family, including rank source variants, a rank-ablation artifact builder, validation CLI, and focused tests.

## Non-goals

- Do not run the real-data artifact command in this hop; W-002 owns that.
- Do not validate real output in this hop; W-003 owns generated artifact validation.
- Do not reopen horizon, weekday, pool-hot, notional, exit, entry-quality, or broad strategy search.
- Do not promote paper tracking, replace the benchmark, publish runtime, or write to the database.

## Plan evidence

W-001 requires same-gate rank source variants, rank-ablation artifact builder, CLI validation, and tests covering rank1, rank2, and rank3 source generation plus same-gate comparison semantics.

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run is W-001 inside the reviewed plan/run workflow and has MiMo run-plan review before implementation. |
| SRC-002 | The builder and validator must keep `horizon_days=10`; non-H10 payloads should fail validation or generation. |
| SRC-003 | Rank1/rank2/rank3 are compared under the same MTW + poolhot10 + H10 gate. |
| SRC-004 | Baseline remains `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`; no unrelated families are introduced. |
| SRC-005 | Artifact policy keeps fallback-or-skip semantics and introduces no delayed-buy action. |
| SRC-006 | Claim ceiling remains `research_observation` and validation must enforce no paper-tracking promotion. |

## Files expected to change

- `src/ashare_evidence/shortpick_v2_strategy_search.py`
- `src/ashare_evidence/shortpick_v2_h10_rank_ablation.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_h10_rank_ablation.py`
- `tests/test_shortpick_v2_strategy_search.py`
- Possibly adjacent CLI command allowlists if command classification requires it.

## Implementation steps

1. Inspect existing H10 quiet candidate generation and parameter-significance artifact patterns.
2. Add same-gate rank source IDs in `src/ashare_evidence/shortpick_v2_strategy_search.py` for mandatory rank1/rank3 and best-effort diagnostic rank4/rank5 without introducing broad families.
3. Add a compact rank-ablation artifact builder and payload validator.
4. Register generation and validation CLI commands.
5. Add focused tests for rank source generation in `tests/test_shortpick_v2_strategy_search.py`, plus fixed H10, required rank1/2/3 rows, coverage thresholds, numeric decision thresholds, and no-promotion semantics in `tests/test_shortpick_v2_h10_rank_ablation.py`.
6. Run the W-001 pytest gate.

## Acceptance criteria

`python3 -m pytest tests/test_shortpick_v2_h10_rank_ablation.py tests/test_shortpick_v2_strategy_search.py -q` exits 0.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest tests/test_shortpick_v2_h10_rank_ablation.py tests/test_shortpick_v2_strategy_search.py -q

## Planned Evidence

- MiMo run-plan review has no blocking or major findings.
- Focused pytest command exits 0.
- Code review finds no unresolved blocking drift from W-001 scope.

## Actual Evidence

- Added rank1/rank3/rank4/rank5 same-gate H10 quiet champion source IDs and rank-position parsing in `shortpick_v2_strategy_search.py`.
- Added `src/ashare_evidence/shortpick_v2_h10_rank_ablation.py` with artifact builder, payload validator, artifact validation reader, and JSON writer.
- Added CLI commands `shortpick-v2-h10-rank-ablation` and `shortpick-v2-h10-rank-ablation-validate`.
- Added `tests/test_shortpick_v2_h10_rank_ablation.py` and extended `tests/test_shortpick_v2_strategy_search.py`.
- `python3 -m pytest tests/test_shortpick_v2_h10_rank_ablation.py tests/test_shortpick_v2_strategy_search.py -q` exited 0 with 45 passed in 0.65s after accepting MiMo minor test-coverage feedback.

## Risk and rollback notes

The main risk is accidentally converting a rank ablation into a new strategy search. Rollback is deleting the new rank-ablation module/CLI/tests and removing the added rank source IDs before W-002 runs.

## Gate plan

- Plan validator before implementation.
- MiMo run-plan review before implementation.
- MiMo code review after implementation.
- W-001 pytest gate after implementation.

## MiMo plan-review result

Passed with no blocking or major findings. Minor clarifications were accepted: rank4/rank5 are best-effort diagnostic extras only, and the run document now ties rank source IDs to `shortpick_v2_strategy_search.py` plus source-generation tests in `tests/test_shortpick_v2_strategy_search.py`.

## Codex escalation plan-review result

Not required unless MiMo reports blocking/major issues.

## Implementation summary

Implemented a research-only H10 rank-ablation artifact and validator. The builder consumes the existing h10 quiet champion replay path, compares mandatory fixed85 rank1/rank2/rank3 rows under the same MTW + poolhot10 + H10 gate, keeps rank4/rank5 diagnostic-only, exposes numeric support thresholds, and preserves no-promotion semantics. CLI generation and validation commands were added.

## MiMo code-review result

Passed with no blocking or major findings. MiMo reported minor notes around non-baseline label semantics, exact 0.03 threshold coverage, and diagnostic rank4/rank5 assertions. Accepted the useful coverage feedback by adding tests for inclusive threshold behavior and diagnostic-only rank4/rank5 labels; the follow-up pytest gate passed.

## Codex escalation code-review result

Not required unless MiMo is inconclusive or reports material disagreement.

## Gate results

- `python3 -m pytest tests/test_shortpick_v2_h10_rank_ablation.py tests/test_shortpick_v2_strategy_search.py -q`: exit 0; 45 passed in 0.65s.

## Plan update summary

W-001 started and plan status changed to executing before implementation. W-001 was later updated from in_progress to done with pytest and MiMo evidence in the plan.

## Plan archive result

Not applicable until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-001-h10-rank-ablation.md` before the W-001 commit.
