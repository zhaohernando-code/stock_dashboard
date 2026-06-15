# Run ID

2026-06-15-W-001-h10-parameter-significance

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/20260614-shortpick-v2-robust-strategy-search-42e/20260615-h10-param-significance-adbc6f/plans/active/plan-20260615-h10-parameter-significance.md

## Hop ID

W-001

## Work item ID

W-001

## Goal

Add a bounded H10 parameter-significance artifact builder, CLI surface, validation helpers, and focused tests for the current quiet benchmark family.

## Non-goals

- Do not reopen horizon search; H10 stays fixed.
- Do not run real-data artifact generation in this hop.
- Do not promote 90k, paper tracking, or runtime/frontend changes.
- Do not broaden into rejected strategy families.

## Plan evidence

W-001 requires code and tests covering fixed H10 scope, ablation families, support labels, sparse-sample downgrade, and no-promotion semantics.

## Source coverage evidence

| Source ID | Run evidence |
|-----------|--------------|
| SRC-001 | This run is W-001 inside the reviewed plan/run workflow and has MiMo run-plan review before implementation. |
| SRC-002 | Artifact and tests must keep `horizon_days=10` fixed and reject non-H10 artifact validation. |
| SRC-003 | Artifact structure must include weekday, rank, pool-hot, execution notional, fallback/skip, and concentration/stability sections. |
| SRC-004 | Benchmark context stays fixed85/fixed80 `quiet_breakout_rank2_poolhot10_mtw`; implementation must not broaden to unrelated families. |
| SRC-005 | Parameter rows must expose support label, sample count, period block count, and evidence basis. |
| SRC-006 | Claim ceiling remains research-only; tests must cover no paper-tracking promotion semantics. |

## Files expected to change

- `src/ashare_evidence/shortpick_v2_h10_parameter_significance.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_h10_parameter_significance.py`
- `tests/test_shortpick_v2_strategy_search.py`
- Possibly adjacent existing strategy-search tests if integration import behavior requires it.

## Implementation steps

1. Inspect the existing H10 quiet strategy-search and CLI patterns.
2. Add a compact artifact builder with typed rows and validation helpers.
3. Add CLI commands for artifact generation and artifact validation.
4. Add focused synthetic tests for fixed H10, parameter families, support labels, sparse-sample downgrade, and no-promotion semantics.
5. Run the W-001 pytest gate.

## Acceptance criteria

`python3 -m pytest tests/test_shortpick_v2_h10_parameter_significance.py tests/test_shortpick_v2_strategy_search.py -q` exits 0.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest tests/test_shortpick_v2_h10_parameter_significance.py tests/test_shortpick_v2_strategy_search.py -q

## Planned Evidence

- MiMo run-plan review has no blocking or major findings.
- Focused pytest command exits 0.
- Code review finds no unresolved blocking drift from W-001 scope.

## Actual Evidence

- Added `src/ashare_evidence/shortpick_v2_h10_parameter_significance.py`.
- Added CLI commands `shortpick-v2-h10-parameter-significance` and `shortpick-v2-h10-parameter-significance-validate`.
- Added `tests/test_shortpick_v2_h10_parameter_significance.py`.
- `python3 -m pytest tests/test_shortpick_v2_h10_parameter_significance.py tests/test_shortpick_v2_strategy_search.py -q` exited 0 with 42 passed in 0.72s.

## Risk and rollback notes

The main risk is false precision: this hop must build research classification and validation structure, not produce final investment claims. Rollback is deleting the new module, CLI commands, and tests.

## Gate plan

- Plan validator before implementation.
- MiMo run-plan review before implementation.
- MiMo code review after implementation.
- W-001 pytest gate after implementation.

## MiMo plan-review result

Passed with no blocking or major findings. Minor documentation notes were accepted: the run document now lists the existing strategy-search test target and expands source coverage evidence into a table.

## Codex escalation plan-review result

Not required by policy for this hop unless MiMo reports material issues.

## Implementation summary

Implemented a research-only H10 parameter-significance artifact and validator. The builder can generate from the h10 quiet champion replay path and the validator enforces fixed H10, required parameter families, support labels, `period_block_count < 3` downgrade, machine-readable evidence for directional claims, and diagnostic-only 90k semantics. CLI generation and validation commands were added.

## MiMo code-review result

Passed with no blocking or major findings. MiMo reported one minor note: non-10 `--horizon-days` values are rejected by the builder rather than argparse, matching the existing h10 robustness/decomposition command pattern. No code change was made for that consistency note.

## Codex escalation code-review result

Not required by policy unless MiMo is inconclusive or reports material disagreement.

## Gate results

- `python3 -m pytest tests/test_shortpick_v2_h10_parameter_significance.py tests/test_shortpick_v2_strategy_search.py -q`: exit 0; 42 passed in 0.72s.

## Plan update summary

W-001 was updated from in_progress to done with pytest and MiMo evidence in the plan.

## Plan archive result

Not applicable until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-15-W-001-h10-parameter-significance.md` before the W-001 commit.
