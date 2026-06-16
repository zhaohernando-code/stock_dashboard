# Run ID

2026-06-16-W-001-shortpick-v2-risk-switch-experiment

## Plan path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display/plans/active/plan-20260616-shortpick-v2-risk-switch-experiment.md`

## Hop ID

W-001

## Work Item ID

W-001

## Goal

Implement the research-only Shortpick v2 risk-switch experiment builder, CLI, validator, renderer, and focused tests.

## Non-goals

- No UI/API/paper-tracking promotion.
- No delayed buy.
- No market-data refresh or direct database writes.
- No broad stock-selection search.
- No weak-threshold tuning after results are visible.

## Plan Evidence

- Plan status is approved by explicit user instruction to land if ds/mimo found no issue.
- Baseline is fixed as MTW, H10, Rank2 primary, Rank3-Rank6 fallback, pool-hot 10%, fixed 8.5w, max5.
- Weak-market definition is fixed as CSI300 prior 5 trade-day close return < -2%.

## Source Coverage Evidence

- SRC-001: ds/mimo review already completed; findings are embedded in the plan.
- SRC-002/SRC-003: W-001 adds only a risk-switch experiment around the proven H10 quiet Rank2 family.
- SRC-004: W-001 freezes the weak rule and separates historical versus paper-window metrics.
- SRC-006: W-001 validator must reject delayed action text.

## Production Path Fidelity Evidence

- PF-001: CLI command is the production research path.
- PF-002: Static variants use the existing v2 replay engine; dynamic variants reuse the same private entry/exit/cost mechanics.
- PF-003: v1 drawdown reversal is entry-only.
- PF-004: No served paper-tracking path is changed in this hop.

## Files Expected To Change

- `src/ashare_evidence/shortpick_v2_risk_switch_experiment.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_risk_switch_experiment.py`
- `plans/active/plan-20260616-shortpick-v2-risk-switch-experiment.md`
- `runs/active/2026-06-16-W-001-shortpick-v2-risk-switch-experiment.md`

## Implementation Steps

1. Add the artifact builder with frozen variant definitions and weak-market calculation.
2. Add a dynamic-notional simulation path that reuses v2 replay helpers.
3. Add validator and Chinese markdown renderer.
4. Wire CLI generation and validation commands.
5. Add focused tests for weak-day behavior, dynamic notional, no-delay guardrail, renderer, and parser.

## Acceptance Criteria

The focused pytest command exits 0 and the plan validator remains green.

## Acceptance Type and Spec

`test_pass`: `cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py`

## Planned Evidence

- Focused pytest output.
- Plan validator output.
- MiMo plan review and code review outputs.

## Actual Evidence

- MiMo plan review completed before implementation with PASS and no blocking/major findings.
- Implemented `src/ashare_evidence/shortpick_v2_risk_switch_experiment.py`, CLI wiring, and focused tests.
- Focused pytest passed: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py` produced `4 passed`.
- Focused ruff passed: `python3 -m ruff check src/ashare_evidence/shortpick_v2_risk_switch_experiment.py tests/test_shortpick_v2_risk_switch_experiment.py src/ashare_evidence/cli.py`.

## Risk and Rollback Notes

This hop adds research-only code and tests. Rollback is removing the new module, CLI wiring, tests, and plan/run records before merge.

## Gate Plan

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py`
- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-risk-switch-experiment.md`

## MiMo Plan-Review Result

PASS. No blocking or major findings. Minor execution reminders accepted: record that MiMo plan review completed before implementation, and record the weak-market lower-notional rule as 5 万 in the implementation/result summary.

## Codex Escalation Plan-Review Result

Not required.

## Implementation Summary

Added a research-only risk-switch experiment module with fixed variants, frozen CSI300 weak-market definition, entry-only v1 drawdown reversal support, dynamic weak-market 5 万 notional simulation, JSON validation, Chinese markdown rendering, and CLI generation/validation commands.

## MiMo Code-Review Result

PASS. No blocking or major findings. Minor finding accepted and resolved by adding a validator test that rejects non-research-only promotion status. Note accepted: dynamic 5 万 uses the same ranked candidates and switches the `ShortpickV2RuleConfig` target notional at entry evaluation time, preserving v2 lot/cost/fallback/exit mechanics.

## Codex Escalation Code-Review Result

Not required.

## Gate Results

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py`: exit 0, `4 passed`.
- `python3 -m ruff check src/ashare_evidence/shortpick_v2_risk_switch_experiment.py tests/test_shortpick_v2_risk_switch_experiment.py src/ashare_evidence/cli.py`: exit 0, all checks passed.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-risk-switch-experiment-20260616.json --summary-output docs/archive/SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md`: exit 0, generated 8 variants.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment-validate --artifact output/shortpick-v2-risk-switch-experiment-20260616.json`: exit 0, validation passed.
- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-risk-switch-experiment.md`: exit 0 before final archive; final archive validation follows after move.

## Plan Update Summary

W-001, W-002, and W-003 completed. Plan records focused tests, ruff, real-data artifact generation, artifact validation, and MiMo plan/code/result review.

## Plan Archive Result

Plan status set to archived and will be moved from `plans/active/` to `plans/archive/`.

## Archive and Merge Result

Run document archived to `runs/archive/2026-06-16-W-001-shortpick-v2-risk-switch-experiment.md`. Branch commit/push/merge closeout follows after final validation.
