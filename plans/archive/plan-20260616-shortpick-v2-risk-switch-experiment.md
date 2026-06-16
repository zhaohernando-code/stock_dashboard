---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-risk-switch-experiment"
title: "Shortpick v2 risk switch experiment"
status: "archived"
created_at: "2026-06-16"
source_request: "Have DeepSeek and Xiaomi MiMo review the next direction; if no issue, land the risk-switch experiment flow for the current v2 H10 quiet Rank2 strategy."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display"
owner: "user"
review_rounds: 1
---

# Plan: Shortpick v2 risk switch experiment

## Compaction-Resistant Summary

Goal: add a research-only risk-switch experiment for the current v2 H10 quiet Rank2 strategy.
Hard scope: no UI/API/paper-tracking promotion, no broad new stock-selection search, no delayed buy, no market-data refresh.
Frozen baseline: MTW, H10, Rank2 primary, Rank3-Rank6 fallback, pool-hot 10%, fixed 8.5w, max5.
Frozen weak rule: CSI300 recent 5 trade-day close return < -2%; not tuned after seeing results.
Key risks: 5-week paper window has only a few trades, so it is a smoke check, not a parameter optimizer.
Approval state: user requested ds/mimo review and approved landing if no blocking issue.

## Goal

Produce a durable, reproducible experiment artifact that tests whether bounded risk switches can improve the current v2 mainline's risk profile without abandoning the historically strong H10 quiet Rank2 selection family.

## Problem / Rationale

The current v2 mainline remains historically strong, but its 2026-05-08 onward paper window has shown a severe short-window drawdown. Prior attribution indicates the paper window is mostly an extreme market/candidate-window headwind plus concentrated exposure, not clear stock-selection failure. The next useful experiment is therefore not another broad selection search, but a small risk-control matrix: weak-market skip, weak-market lower notional, max-position cap, and the v1 drawdown-reversal entry filter.

DeepSeek and Xiaomi MiMo both accepted this direction with guardrails. DeepSeek required freezing the weak-market definition and treating v1 drawdown reversal only as an entry filter. MiMo required evaluating historical and paper windows separately and not using the paper window as a tuning target.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use ds and Xiaomi MiMo to review the proposed direction before landing. | External Review Log,W-001 | covered | in_scope | Review log records both reviewers; blocking items are accepted into frozen experiment rules. |
| SRC-002 | Continue from the current proven v2 direction instead of broad-searching unrelated strategies. | W-001,W-002 | covered | in_scope | Artifact scope freezes MTW/H10/Rank2/pool-hot10/fixed85 baseline and tests only risk switches. |
| SRC-003 | Validate risk controls that may explain or reduce the current paper-window drawdown. | W-001,W-002 | covered | in_scope | Artifact compares baseline, weak skip, weak lower-notional, max3, v1 drawdown entry filter, and bounded combinations. |
| SRC-004 | Do not overfit the 2026-05 paper window. | W-001,W-002,W-003 | covered | in_scope | Artifact records historical-window primary gates and paper-window smoke checks separately; weak rule is frozen before execution. |
| SRC-005 | Keep H10 as the mainline unless evidence proves otherwise. | W-001,W-002 | covered | in_scope | Experiment keeps H10 fixed; H5/H7 only appear as context if already available, not as promotion candidates. |
| SRC-006 | Preserve the no-delayed-buy rule. | W-001,W-002 | covered | in_scope | Rule configs allow only buy primary, buy fallback, or skip; validator rejects delay action text. |
| SRC-007 | Produce readable evidence that explains how each strategy selects stocks and how it performs. | W-002,W-003 | covered | in_scope | Chinese summary table describes selection, risk switch, historical return/risk, paper return/risk, trades, skip, and outcome. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Research operator runs the stock dashboard CLI against local runtime daily bars. | `python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment ...` with local SQLite URL. | CLI artifact builder | none | matches_product_path | CLI exits 0 and writes JSON artifact plus Chinese summary. |
| PF-002 | Existing v2 replay/account mechanics handle lot rounding, fallback-or-skip, position caps, costs, and H10 exits. | Experiment module delegates static variants to existing v2 replay helpers and uses the same private mechanics for dynamic-notional variants. | `shortpick_v2_replay` and experiment builder | none | matches_product_path | Focused tests cover no-delay, dynamic-notional behavior, and validator checks result rows. |
| PF-003 | v1 drawdown-reversal filter uses signal-date-or-prior features only. | Experiment module applies the existing governed filter as an entry-pool filter only. | `shortpick_strategy_governance` | none | matches_product_path | Artifact records v1 rule version and leakage audit. |
| PF-004 | Paper tracking/UI consume only promoted strategies through separate governance work. | This run writes research artifacts only and does not touch frontend/API paper-tracking promotion. | Product UI/read model | none | not_applicable | Changed files and summary state research-only no promotion. |

## Scope

### In Scope

- Add a research-only risk-switch experiment builder and CLI.
- Freeze weak-market definition as CSI300 close-to-close return over the prior 5 trade days below -2%.
- Run a bounded matrix: baseline, weak skip, weak 5w notional, max3, v1 drawdown entry filter, weak skip + max3, weak 5w + max3, and all-defense.
- Evaluate each row on both historical backtest window and current paper stress window.
- Add focused tests and validator coverage.
- Generate and archive JSON plus Chinese markdown evidence.
- Commit and push the task branch; merge to main only if repository state and project hooks allow it.

### Out of Scope

- No UI/API/read-model change.
- No paper-tracking strategy promotion.
- No new market-data refresh or direct DB writes.
- No delayed buy.
- No new broad选股方向 search.
- No threshold grid search or post-result threshold tuning.

## Assumptions and Dependencies

- Runtime DB exists at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Existing daily-bar rows are sufficient for 2023-04-13 to 2026-06-15.
- Existing H10 quiet Rank2 matrix helpers remain the source for candidate construction.
- The current worktree is isolated and on `codex/shortpick-v2-risk-governance`.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Implement the risk-switch experiment builder, validator, renderer, and CLI parser/handler. | `src/ashare_evidence/shortpick_v2_risk_switch_experiment.py`, CLI wiring, focused tests. | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py | Focused pytest passed `4 passed`; ruff passed; MiMo code review PASS with no blocking/major findings and minor validator test added. |
| W-002 | done | 2 | W-001 | Run the real-data bounded risk-switch experiment for historical and paper windows. | `output/shortpick-v2-risk-switch-experiment-20260616.json` and `docs/archive/SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md`. | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment-validate --artifact output/shortpick-v2-risk-switch-experiment-20260616.json | Real-data CLI generated 8 variants; artifact validator passed; MiMo result review PASS with no blocking/major findings. |
| W-003 | done | 3 | W-002 | Close out the plan with evidence, archived run record, and no-promotion summary. | Archived run document and archived plan. | file_contains | path:docs/archive/SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md \| pattern:研究结论 | Summary contains `研究结论`; plan archived; run record moved to `runs/archive/2026-06-16-W-001-shortpick-v2-risk-switch-experiment.md`. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- JSON artifact validates and contains the bounded risk-switch rows for both historical and paper windows.
- Baseline row exactly documents the current mainline: MTW, H10, Rank2 primary, Rank3-Rank6 fallback, pool-hot 10%, fixed 8.5w, max5, no v1 drawdown filter.
- Weak-market rule is fixed before execution and visible in the artifact.
- v1 drawdown reversal is used only as an entry filter and does not alter H10 exit behavior.
- Summary is Chinese-readable and explicitly says research-only no promotion.
- No live-facing UI/API/runtime publish is required unless code changes touch served behavior.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-risk-switch-experiment.md`
- MiMo read-only plan review.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_risk_switch_experiment.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-risk-switch-experiment-20260616.json --summary-output docs/archive/SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-risk-switch-experiment-validate --artifact output/shortpick-v2-risk-switch-experiment-20260616.json`
- MiMo read-only code/result review.

## Risks and Mitigations

- Risk: paper window has too few trades for parameter selection. Mitigation: paper window is only a smoke check; historical gates remain primary.
- Risk: weak-market threshold can become hindsight-tuned. Mitigation: freeze CSI300 5-trade-day return < -2% before execution and do not iterate within this run.
- Risk: dynamic notional could drift from v2 replay accounting. Mitigation: reuse v2 private entry/exit/cost mechanics and cover behavior with focused tests.
- Risk: max3 may reduce diversification rather than risk. Mitigation: report both historical and paper drawdown/return/trades/skip instead of assuming it helps.
- Risk: research artifact could be mistaken for promotion. Mitigation: artifact, summary, and recommendation status all state no paper-tracking promotion.

## Open Questions

- If no risk switch improves both historical quality and paper smoke metrics, the next plan should likely explore rolling train/test governance rather than more current-window tuning.

## Revision History

| Timestamp | Actor | Work Item | Old Status | New Status | Summary |
|-----------|-------|-----------|------------|------------|---------|
| 2026-06-16T18:30:00+08:00 | Codex | - | - | approved | User requested ds/mimo review and approved landing if no issue; plan created with external-review constraints embedded. |
| 2026-06-16T18:45:00+08:00 | Codex | W-001 | pending | in_progress | MiMo plan review passed; starting implementation. |
| 2026-06-16T19:05:00+08:00 | Codex | W-001,W-002 | in_progress,pending | done,in_progress | W-001 focused tests and MiMo code review passed; W-002 real-data generation started. |
| 2026-06-16T19:35:00+08:00 | Codex | W-002,W-003 | in_progress,pending | done,done | Real-data artifact and validator passed; MiMo result review passed; plan archived. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | Xiaomi MiMo | Direction is reasonable with no hard blocker; evaluate historical and paper windows separately and do not use the 5-week paper window as a tuning target. | major | accepted | Plan freezes threshold before execution and records paper window as smoke check only. | W-001,W-002 |
| 1 | Xiaomi MiMo | H5/H7 should remain second-round controls rather than first-round cross-products. | minor | accepted | This plan keeps H10 fixed and excludes H5/H7 from the risk-switch matrix. | W-001,W-002 |
| 1 | DeepSeek | Weak-market definition must be frozen before experiment or results are not reproducible. | blocking | resolved | Plan freezes CSI300 prior 5 trade-day close return < -2%. | W-001,W-002 |
| 1 | DeepSeek | v1 drawdown reversal compatibility must be defined; it should be entry-only if used with v2 H10. | blocking | resolved | Plan limits v1 drawdown reversal to entry-pool filtering and preserves H10 exits. | W-001,W-002 |
| 1 | DeepSeek | Avoid max2 and large matrix combinations in the first run. | major | accepted | Matrix uses max3 only and bounded combinations, no max2. | W-001,W-002 |

## User Review Notes

- User has standing instruction not to request approval during this goal.
- User asked to retain important results and use them as the benchmark for future work.
