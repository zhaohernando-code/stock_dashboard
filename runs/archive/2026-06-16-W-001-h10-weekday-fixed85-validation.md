# Run: H10 weekday fixed85 validation

- Run ID: `2026-06-16-W-001-h10-weekday-fixed85-validation`
- Plan path: `plans/archive/plan-20260616-h10-weekday-fixed85-validation.md`
- Work item: `W-001` through `W-003`
- Branch: `task/h10-weekday-drawdown-validation`
- Worktree: `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-h10-weekday-drawdown-validation`

## Goal

Run a fixed-85k validation for the H10 quiet Rank2 pool-hot family across `123`, `234`, `135`, `345`, `1234`, and `12345`, with drawdown reversal off/on.

## Non-Goals

- No paper-tracking promotion.
- No UI/API change.
- No horizon search.
- No delayed buy.

## Plan Evidence

The user asked to keep prior important data, then run trading-day validation for `123`, `234`, `135`, `345`, `1234`, and `12345`; drawdown reversal comparison included; buy amount fixed at 8.5 万.

## Production Path Fidelity Evidence

- Used the project CLI entrypoint with local runtime SQLite bars.
- Used existing H10 v2 replay engine and existing v1 drawdown reversal filter.
- Wrote research-only artifacts; no served UI/API path changed.

## Files Changed

- `src/ashare_evidence/shortpick_v2_h10_weekday_drawdown_notional_matrix.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py`
- `output/shortpick-v2-h10-weekday-drawdown-fixed85-validation-artifact.json`
- `docs/archive/SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_FIXED85_VALIDATION.md`
- `plans/archive/plan-20260616-h10-weekday-fixed85-validation.md`
- `runs/archive/2026-06-16-W-001-h10-weekday-fixed85-validation.md`

## Implementation Summary

- Added weekday modes for `234`, `135`, `345`, and `1234`.
- Added optional CLI parameters `--weekday-mode` and `--target-notional`.
- Kept existing default matrix behavior unchanged.
- Added tests for fixed85 custom matrix shape and dynamic summary wording.
- Generated a distinct 12-row fixed85 artifact and summary.

## Actual Evidence

- Focused tests: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py` passed with `6 passed in 0.70s`.
- Generation command exited 0 and wrote `row_count: 12`.
- Artifact validation command exited 0 with `status: passed`, six weekday modes, drawdown modes `off`/`v1_on`, and notional `[85000.0]`.

## Result Snapshot

| Rank | Weekdays | Drawdown Filter | Total Return | Annualized | Max Drawdown | Trades |
|------|----------|-----------------|--------------|------------|--------------|--------|
| 1 | 周一至周三 | off | 271.2% | 53.9% | -11.9% | 192 |
| 2 | 周一至周三 | v1_on | 251.1% | 51.1% | -14.4% | 181 |
| 3 | 周一至周四 | v1_on | 206.5% | 44.5% | -19.8% | 199 |
| 4 | 周一至周五 | v1_on | 181.3% | 40.5% | -22.3% | 222 |
| 5 | 周一至周四 | off | 178.0% | 39.9% | -32.7% | 212 |

## Review Results

- MiMo: passed with no blocker/major. One minor requested coverage for default weekday modes with fixed85; accepted and resolved by adding `test_h10_weekday_drawdown_notional_matrix_supports_fixed85_with_default_weekdays`.
- DeepSeek: passed with no blocker/major. Minor notes: `target_notionals` naming is functional but stylistically uncommon; default summary path can overwrite old summaries if a future custom run omits `--summary-output`. This run used an explicit distinct summary path and force-tracks the JSON artifact, so no blocking change is required.

## Gate Results

- Focused pytest: passed with `6 passed in 0.70s`.
- Artifact generation: passed.
- Artifact validation: passed.
- Full frontend/project closeout gate: not run because this is a research artifact/code-path extension with no served UI/API change.

## Risk Notes

- MTW remains strongest in this historical window, but this is not causal proof.
- Drawdown reversal improves broad weekday rows but does not beat MTW.
- Offline generation took about 106 seconds, so this should remain precomputed research evidence, not an online request path.

## Worktree Note

The standard start-task-worktree helper failed because `/Users/hernando_zhao/codex/projects/stock_dashboard` is currently configured with `core.bare=true`. This run used `git --git-dir=/Users/hernando_zhao/codex/projects/stock_dashboard/.git worktree add -b task/h10-weekday-drawdown-validation ... origin/main` to create an isolated task worktree.
