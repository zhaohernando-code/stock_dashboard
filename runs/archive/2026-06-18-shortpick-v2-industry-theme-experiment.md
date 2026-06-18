# Run: shortpick v2 industry theme experiment

- Run ID: `2026-06-18-shortpick-v2-industry-theme-experiment`
- Plan path: `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260618-shortpick-v2-industry-theme-experiment/plans/active/plan-20260618-shortpick-v2-industry-theme-experiment.md`
- Hop ID: `W-001..W-005`
- Work item ID: full-plan execution
- Goal: test industry/theme leadership ranking variants as research-only diagnostics.
- Non-goals: no candidate promotion, no paper tracking mutation, no frontend/runtime display change, no refresh/model call.

## Plan Evidence

- Plan status: approved.
- Plan validation: `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260618-shortpick-v2-industry-theme-experiment.md` exited 0.
- MiMo plan review round 1: no blocking; two major findings accepted and fixed.
- MiMo plan rereview round 2: no blocking or major findings.

## Source Coverage Evidence

- SRC-001: covered by this run record, MiMo run-plan review, result review, and plan updates.
- SRC-002: covered by the planned research artifact and markdown report.
- SRC-003: covered by research-only validator, conclusion-language review, and forbidden-path diff check.
- SRC-004: covered by the prior evidence inventory and explicit comparison against known weak simple industry heat variants.

## Production Path Fidelity Evidence

- PF-001: research CLI and artifact validator exercise the offline v2 replay path.
- PF-002: no-promotion proof is `git diff --name-only HEAD` forbidden-path screening.
- PF-003: final report is archived under `docs/archive`.

## Prior Evidence Inventory

Prior evidence inventory: stage summary #11 and #15 are the guardrails for this run.

- Stage summary #11: previous ranking replacement backtest tested `industry_heat_pullback_rank2_mtw`, `industry_heat_amount_rank2_mtw`, and `pullback_low_chase_rank2_mtw`; paper sometimes improved, but holdout/full history were materially weaker than original Rank2, so these simple replacements must not be promoted.
- Stage summary #15: June strong-stock diagnosis found 98% of Top50 winners were in the eligible observation domain, only 2% entered v2 Top5, and 0% were actually bought; this supports researching ranking/theme entry rather than buy amount or simple filters.
- Theme diagnostics: current paper underperformance likely includes mainline miss and position-shape mismatch; winner labels are post-hoc diagnostic only.
- Current experiment boundary: only signal-day-or-earlier ranking features may affect replay results.

## Files Expected To Change

- `src/ashare_evidence/shortpick_v2_industry_theme_experiment.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_industry_theme_experiment.py`
- `docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md`
- `output/shortpick-v2-industry-theme-experiment-20260618.json`
- `plans/active/plan-20260618-shortpick-v2-industry-theme-experiment.md`
- `runs/archive/2026-06-18-shortpick-v2-industry-theme-experiment.md`

## Implementation Steps

1. Add research-only artifact builder and validator for industry/theme variants.
2. Wire CLI generation and validation commands.
3. Add focused tests for variant definitions, research-only status, validator, and CLI parsing.
4. Run experiment through 2026-06-17 and generate JSON/markdown outputs.
5. Review conclusion language and no-promotion path proof.
6. Update plan evidence, archive this run, commit, push, merge, push main, and clean temporary state.

## Acceptance Criteria

- Artifact declares `claim_ceiling: research_observation` and `promotion_status: research_only_no_strategy_promotion`.
- Report is readable Chinese and does not call any variant candidate-ready.
- Report applies the plan threshold: only a variant with holdout total return at least 10 percentage points above baseline, holdout drawdown worsening no more than 5 absolute percentage points, paper-window return improvement, and strong-stock Top5 capture improvement can be called future-research-worthy; all others are dead-end or inconclusive.
- Report records the actual paper-window cutoff date used by the experiment.
- Baseline, required weak-comparison variants, and new theme variants are all visible.
- Holdout, historical, paper, and strong-stock capture diagnostics are included.
- Candidate/paper/frontend/runtime paths are not modified.

## Acceptance Type And Spec

- Full plan: combined `file_contains`, `test_pass`, and `command_exit_0` specs from W-001 through W-005.

## Planned Evidence

- Plan validator exit 0.
- MiMo run-plan review no blocking drift.
- Focused pytest exit 0.
- Experiment CLI exit 0.
- Artifact validator exit 0.
- Policy audit exit 0.
- MiMo code/result review no blocking.
- Forbidden-path diff check exit 0.

## Risk And Rollback Notes

- If all variants fail, the correct result is a documented dead end, not a candidate.
- Rollback is removing the research module/tests/artifacts/docs from the branch before merge.

## Gate Plan

1. `python3 -m pytest -q tests/test_shortpick_v2_industry_theme_experiment.py tests/test_shortpick_v2_ranking_backtest.py`
2. `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment --paper-end-date 2026-06-17 --output output/shortpick-v2-industry-theme-experiment-20260618.json --summary-output docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md`
3. `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment-validate --artifact output/shortpick-v2-industry-theme-experiment-20260618.json`
4. `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`

## MiMo Plan-Review Result

Passed. MiMo found no blocking or major drift. Accepted minor notes by adding the quantitative classification threshold and actual cutoff-date requirement to this run document.

## Codex Escalation Plan-Review Result

Not required.

## Implementation Summary

Implemented a research-only industry/theme experiment CLI and artifact builder.

- Added `shortpick_v2_industry_theme_experiment.py` with baseline, three known-weak controls, and four new theme-ranking variants.
- Added CLI commands `shortpick-v2-industry-theme-experiment` and `shortpick-v2-industry-theme-experiment-validate`.
- Added focused tests for validator, CLI, no-promotion contract, future-research separation, and paper-only improvement rejection.
- Ran the experiment against runtime DB `sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` through 2026-06-17.
- Generated `output/shortpick-v2-industry-theme-experiment-20260618.json` and `docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md`.

Result summary:

- No variant reached the future-research threshold.
- New theme variants improved paper in some cases, especially `theme_breakout_cluster_rank2_mtw` at +45.7% in the paper window, but holdout was far weaker than the baseline: +12.2% versus baseline +113.5%, with much worse drawdown.
- Strong-stock Top5 capture improved for several theme variants, but only from 2% to 6-8%, and this did not survive holdout replay.
- Final interpretation: no industry/theme variant is promoted or added to paper candidates.

## MiMo Code-Review Result

Passed. MiMo found no blocking or major issues.

- Confirmed research-only status and no direct candidate promotion.
- Confirmed replay ranking inputs use signal-day-or-earlier context, while winner labels are only post-hoc capture diagnostics.
- Confirmed the report does not soften paper-only improvements into candidate language.
- Accepted one minor recommendation by adding a test that rejects paper/capture improvement when holdout is weak.

## Codex Escalation Code-Review Result

Not required.

## Gate Results

- `python3 -m pytest -q tests/test_shortpick_v2_industry_theme_experiment.py tests/test_shortpick_v2_ranking_backtest.py`: passed, 7 tests.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --paper-end-date 2026-06-17 --output output/shortpick-v2-industry-theme-experiment-20260618.json --summary-output docs/archive/SHORTPICK_V2_INDUSTRY_THEME_EXPERIMENT_2026-06-18.md`: passed.
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-industry-theme-experiment-validate --artifact output/shortpick-v2-industry-theme-experiment-20260618.json`: passed.
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`: passed.
- `python3 -m pytest -q`: passed, 967 passed, 1 skipped, 173 deselected, 6 subtests passed.
- Plan validator: passed.

## Plan Update Summary

Plan work items W-001 through W-005 marked done with evidence. Plan validator passed after the update.

## Plan Archive Result

Plan will be moved from `plans/active/plan-20260618-shortpick-v2-industry-theme-experiment.md` to `plans/archive/plan-20260618-shortpick-v2-industry-theme-experiment.md` with status `archived`.

## Archive And Merge Result

Run document archived. Git commit, push, merge to main, main push, and temporary lock/state cleanup remain pending.
