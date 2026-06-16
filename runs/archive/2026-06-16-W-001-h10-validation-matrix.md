# Run: 2026-06-16-W-001-h10-validation-matrix

## Run ID

2026-06-16-W-001-h10-validation-matrix

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display/plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md

## Hop ID

W-001

## Work item ID

W-001 through W-004 in full-plan mode.

## Goal

Execute the approved H10 validation matrix plan end to end: reviewed plan state, implementation, matrix artifact, readable summary, gates, archive, commit, push, merge, and cleanup.

## Non-goals

- No frontend, API, or paper-tracking promotion.
- No delayed buy option.
- No horizon search beyond H10.
- No single-buy amount above 85k.

## Plan evidence

- Plan schema validation passed before execution.
- MiMo plan review returned PASS with two minor findings.
- The plan was revised to resolve both minor findings and set to approved under explicit user instruction to land this mode.

## Source coverage evidence

| Source ID | Requirement | Run coverage |
|-----------|-------------|--------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop. | This run uses schema-v1 plan validation, run records, MiMo reviews, gates, archive, and merge closeout. |
| SRC-002 | Validate removing weekday hard restriction. | Implementation will compare MTW and all-weekday selection modes. |
| SRC-003 | Compare v1 drawdown reversal off/on. | Implementation will call existing v1 drawdown reversal helpers and record rule signature. |
| SRC-004 | Expand fixed notional controls from 10k to 85k. | Implementation will use exactly nine notional levels: 10k through 80k plus 85k. |
| SRC-005 | Keep H10. | CLI and artifact default to horizon_days 10. |
| SRC-006 | No delayed buy. | Rule configs allow only buy_primary, buy_fallback, and skip. |
| SRC-007 | Readable result table. | Run will generate a Chinese markdown summary with selection description and performance metrics. |
| SRC-008 | No paper tracking promotion. | Expected changed files exclude frontend/API and paper tracking promotion code. |

## Production path fidelity evidence

| Path ID | Fidelity | Run coverage |
|---------|----------|--------------|
| PF-001 | matches_product_path | Matrix generation will run through a real CLI command against the local runtime database. |
| PF-002 | matches_product_path | Matrix rows will delegate to existing v2 replay simulation. |
| PF-003 | matches_product_path | Drawdown-on rows will use existing v1 governance helpers. |
| PF-004 | not_applicable | This run does not touch frontend/API promotion paths. |

## Files expected to change

- `plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md`, later moved to `plans/archive/`.
- `runs/active/2026-06-16-W-001-h10-validation-matrix.md`, later moved to `runs/archive/`.
- New source module for H10 weekday/drawdown/notional matrix generation.
- `src/ashare_evidence/cli.py`.
- New focused tests.
- Generated matrix artifact and readable markdown summary.

## Implementation steps

1. Review this run plan with MiMo.
2. Implement a matrix builder that reuses existing daily-series, quiet breakout, v2 replay, and v1 drawdown reversal helpers.
3. Add CLI generate and validate commands.
4. Add focused tests for matrix shape and governance semantics.
5. Run the matrix on the local runtime DB and write JSON plus Chinese summary.
6. Run gates and MiMo code review.
7. Update and archive plan/run records, commit, push, merge to main, push main, then clean temporary active state and lock.

## Acceptance criteria

- 36 visible matrix rows.
- H10 horizon only.
- MTW and all-weekday modes both present.
- Drawdown off/on modes both present.
- Notional groups are exactly 10k, 20k, 30k, 40k, 50k, 60k, 70k, 80k, 85k.
- Degenerate rows are retained and labeled.
- No delayed-buy action.
- No frontend/API/paper-tracking promotion.

## Acceptance Type

command_exit_0

## Acceptance Spec

cmd:python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md

## Planned Evidence

- Plan validation command exits 0.
- MiMo run-plan review has no blocker.
- Targeted tests pass.
- Matrix generation command exits 0.
- Matrix validation command exits 0.
- Policy audit exits 0.
- MiMo code review has no unresolved blocker.
- Git push and main merge are recorded.

## Actual Evidence

- Plan validation passed.
- MiMo plan review PASS and MiMo run-plan review PASS.
- Targeted pytest passed: `4 passed in 0.69s`.
- Matrix generation passed against `sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`; it produced 36 rows.
- Matrix validation passed all checks.
- Policy audit passed.
- Default fast pytest passed: `935 passed, 173 deselected, 6 subtests passed in 50.64s`.

## Risk and rollback notes

- Research output changes are rollbackable by reverting the task commit.
- Generated artifacts do not alter production runtime state.
- If the local DB is missing required bars, stop with a bounded data-gap report rather than refreshing silently.

## Gate plan

- `python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix-validate --artifact output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`

## MiMo plan-review result

PASS. MiMo found no blocking, major, or minor issue in the run-plan comparison. It confirmed the run scope matches the approved plan: MTW versus all-weekday, drawdown off versus v1 on, fixed notional 10k through 85k, 36 rows, H10 only, no UI/API/paper-tracking promotion, and no delayed buy.

## Codex escalation plan-review result

Not required.

## Implementation summary

Added a dedicated H10 validation matrix builder, CLI generator, CLI validator, focused tests, and a Chinese markdown result summary. The matrix keeps the current quiet-breakout Rank2 primary thesis, uses Rank3-Rank6 as same-day fallback candidates, compares MTW versus all weekdays, compares drawdown off versus v1 drawdown reversal on, and spans fixed notionals from 10k through 85k.

## MiMo code-review result

PASS. MiMo found no blocking or major issues. Minor suggestions were resolved by removing config-id notional parsing coupling, adding selection branch coverage, documenting the original Rank2 offset, and removing a hardcoded date from the CLI summary default.

## Codex escalation code-review result

Not required.

## Gate results

- `python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py`: passed, 4 tests.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json --summary-output docs/archive/SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_NOTIONAL_MATRIX.md`: passed, 36 rows.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix-validate --artifact output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json`: passed.
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`: passed.
- `python3 -m pytest -q`: passed, 935 tests.

## Plan update summary

W-001, W-002, and W-003 marked done. W-004 is in progress pending archive, commit, branch push, merge to main, main push, lock cleanup, and temporary active state cleanup.

## Plan archive result

Plan status set to archived and moved from `plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md` to `plans/archive/plan-20260616-shortpick-v2-h10-validation-matrix.md`.

## Archive and merge result

Run document moved from `runs/active/2026-06-16-W-001-h10-validation-matrix.md` to `runs/archive/2026-06-16-W-001-h10-validation-matrix.md`. Branch push, merge to `main`, `origin/main` push, and temporary state cleanup are the remaining shell closeout steps after the commit is created.
