---
schema_version: 1
plan_id: "plan-20260615-h10-quiet-benchmark-robustness"
title: "H10 Quiet Benchmark Robustness"
status: "executing"
created_at: "2026-06-15"
source_request: "Use reviewed-plan-generator and plan-run-loop for the next Short Pick Lab V2 development: pause broad strategy search, prioritize fixed85/fixed80 benchmark-focused robustness, then funds execution decomposition and 90k boundary diagnostics."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-robust-strategy-search-42e199"
owner: "user"
review_rounds: 2
---

# Plan: H10 Quiet Benchmark Robustness

## Compaction-Resistant Summary

Goal: turn the fixed85/fixed80 quiet champion decision into audited benchmark-focused robustness and execution diagnostics.
Hard scope: no frontend, no runtime publish, no paper-tracking promotion, no broad new strategy search, no delayed buy.
Inputs: fixed85/fixed80 are mandatory benchmarks; 90k is diagnostic only; 70/75k, poolhot09/11/12, MT/TW are not paper-tracking candidates.
Key work: make robustness analyze benchmark configs directly, add funds/execution decomposition for 80/85/90k, validate real runtime artifacts, and document the decision.
Dependencies: existing h10 quiet champion replay/selection artifacts and runtime SQLite DB.
Major risks: overfitting, winner concentration, weak-year dependence, turnover-gate drift, and confusing retrospective replay with true forward tracking.
Approval state: approved by user on 2026-06-15 and executing W-001.

## Goal

Create a plan-run-loop-ready development plan that validates whether the `quiet_breakout_rank2_poolhot10_mtw` fixed85/fixed80 pair is robust enough to remain the `试验田v2` benchmark line, and separates true signal strength from funding, board-lot, turnover, winner-concentration, and weak-period effects.

## Problem / Rationale

The h10 quiet champion line has the strongest current historical evidence: fixed85 reproduces about `+271.23%` total return, `53.96%` annualized return, `+229.39%` market excess, and `-11.90%` maximum drawdown; fixed80 reproduces about `+257.25%`, `52.03%`, and the same drawdown. External discussion with DeepSeek, Xiaomi MiMo, and a Codex subagent converged on the same next step: stop broad strategy search and first prove or disprove fixed85/fixed80 robustness.

The current robustness artifact primarily flagged 70k/75k because risk-first selection chose them, while fixed85/fixed80 were only holdout/benchmark rows. That is not enough for a paper-tracking decision. The next development must make fixed85/fixed80 first-class analysis targets, then explain whether 90k is merely a turnover-boundary variant or a genuine improvement, and whether returns depend on a few winners, weak-year luck, or execution artifacts.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use reviewed-plan-generator and plan-run-loop for subsequent development. | W-001,W-002,W-003,W-004,W-005 | covered | in-scope | Schema-v1 plan validates; future execution uses archived run records and plan updates. |
| SRC-002 | Prioritize fixed85/fixed80专项稳健性 instead of new strategy search. | W-001,W-003,W-004,W-005 | covered | in-scope | Benchmark-focused robustness artifact includes fixed85/fixed80 as primary analyzed configs and documents result. |
| SRC-003 | Evaluate annual/period stability and top-winner removal before paper tracking. | W-001,W-003,W-004 | covered | in-scope | Robustness output includes yearly/period reset and top-winner stress evidence for fixed85/fixed80. |
| SRC-004 | Keep 90k as diagnostic boundary research, not a promoted candidate. | W-001,W-002,W-003,W-004,W-005 | covered | in-scope | Execution diagnostics include 90k with explicit diagnostic role and no paper-tracking promotion language. |
| SRC-005 | Add funds execution decomposition after robustness, covering board-lot, cash, turnover, skip, winner, and funding effects. | W-002,W-003,W-004 | covered | in-scope | Execution decomposition artifact/report compares 80k/85k/90k and records cash/lot/turnover/skip/concentration metrics. |
| SRC-006 | Continue banning broad ma_accel, dynamic exit, entry quality, rank2to6, breadth65, poolhot09, poolhot11/12, MT/TW promotion, delayed buy, and true-forward overclaiming. | W-005 | covered | in-scope | Decision/run document records the prohibited directions and no implementation reopens them. |

## Scope

### In Scope

- Extend or adapt the h10 robustness path so `benchmark_configs` such as fixed85/fixed80 can be analyzed as first-class targets, not only selected/holdout side rows.
- Preserve fixed85 as primary benchmark and fixed80 as conservative twin in outputs and docs.
- Include 90k only as a boundary diagnostic for turnover/funding sensitivity.
- Add a funds/execution decomposition artifact or report for fixed80/fixed85/90k, focused on cash deployment, board-lot rounding, skip/fallback reasons, turnover, position overlap, and contribution concentration.
- Add or reuse machine-checkable validation for generated robustness and execution decomposition artifacts.
- Run real-data runtime commands against `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Validate generated artifacts against existing or newly introduced schemas when schemas are used.
- Update durable docs with the robustness outcome and the next decision boundary.

### Out of Scope

- No frontend UI changes.
- No runtime publish.
- No production paper-tracking enablement.
- No strategy family expansion beyond fixed80/fixed85/90k quiet champion diagnostics.
- No delayed buy option.
- No weakening turnover, annualized-return, market-excess, or drawdown gates without an explicit future governance decision.
- No database migration unless a later run records a blocker and creates a separate approved plan.

## Assumptions and Dependencies

- The current isolated worktree is `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-robust-strategy-search-42e199`.
- Runtime SQLite DB is available at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Existing h10 quiet champion replay and selection commands can be rerun if local `output/` artifacts are missing.
- Existing robustness schema may be reused if the new benchmark-focused output fits it; otherwise schema changes must be explicit, tested, and reviewed.
- Retrospective artifacts remain research observations and do not start true-forward tracking.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Make h10 robustness benchmark-focused so fixed85/fixed80 are primary analyzed configs, with 90k allowed only as a diagnostic row. | Robustness code/tests supporting benchmark configs and diagnostic config inclusion | test_pass | cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q | MiMo run-plan/code reviews passed; pytest `tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_rule_selection.py -q` passed with 14 tests. |
| W-002 | pending | 2 | W-001 | Add funds/execution decomposition for fixed80/fixed85/90k quiet champion configs. | Execution decomposition artifact/report code, artifact validation support, and focused tests | test_pass | cmd:python3 -m pytest tests/test_shortpick_v2_h10_robustness.py tests/test_shortpick_v2_strategy_search.py -q |  |
| W-003 | pending | 3 | W-002 | Run real-data benchmark-focused robustness and execution decomposition against the runtime DB. | Runtime output artifacts under `output/` for benchmark robustness and execution decomposition | command_exit_0 | cmd:bash -lc 'PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-robustness --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --replay-artifact output/shortpick-v2-h10-quiet-champion-replay-artifact.json --selection-artifact output/shortpick-v2-h10-quiet-champion-selection-artifact.json --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json && PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-execution-decomposition --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --replay-artifact output/shortpick-v2-h10-quiet-champion-replay-artifact.json --selection-artifact output/shortpick-v2-h10-quiet-champion-selection-artifact.json --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json' |  |
| W-004 | pending | 4 | W-003 | Validate generated robustness and execution decomposition artifacts with machine-checkable structure/content gates. | Artifact validation command/result covering both runtime JSON outputs | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-artifact-validate --robustness-artifact output/shortpick-v2-h10-quiet-benchmark-robustness-artifact.json --execution-artifact output/shortpick-v2-h10-quiet-execution-decomposition-artifact.json |  |
| W-005 | pending | 5 | W-004 | Record the decision outcome and freeze/prohibit directions after evidence review. | Durable docs/run notes updated with fixed85/fixed80 robustness decision, 90k diagnostic status, and prohibited directions | file_contains | path:docs/archive/SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md \| pattern:Benchmark-focused robustness; 90k diagnostic only; Prohibited directions |  |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- fixed85 and fixed80 are analyzed directly as benchmark targets, not merely inferred from holdout rows.
- The plan produces concrete annual/period, top-winner removal, concentration, execution/funding evidence, and machine-checked artifact validation for fixed85/fixed80.
- 90k remains labeled as diagnostic and cannot bypass the turnover gate.
- No broad strategy-search family is reopened.
- All artifacts and docs keep `claim_ceiling=research_observation` semantics where applicable.
- If the evidence is negative, the result is recorded as such rather than hidden or re-optimized.

### Validation Gates

- Plan validation: `python3 ${CODEX_HOME:-$HOME/.codex}/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-h10-quiet-benchmark-robustness.md`.
- MiMo plan review before execution.
- For implementation hops: MiMo run-plan and code-risk reviews per plan-run-loop.
- Focused pytest gates in W-001 and W-002.
- Real-data runtime command in W-003.
- Default fast regression and policy audit before push when code or threshold contracts change.
- No runtime publish unless a later approved plan adds live-facing changes.

## Risks and Mitigations

- Overfitting risk: only analyze fixed80/fixed85/90k and do not add new strategy families.
- Winner concentration risk: require top-winner removal and symbol/month/industry concentration evidence before any promotion language.
- Weak-year risk: require annual or period reset evidence and do not hide years below the 30% floor.
- Turnover drift risk: keep 90k diagnostic unless a future governance decision changes the turnover gate.
- Execution artifact risk: decompose board-lot rounding, cash deployment, and skip/fallback reasons before preferring 85k over 80k.
- Claim risk: maintain research-observation labels and explicitly avoid paper-tracking activation in this plan.

## Open Questions

- If fixed85 passes robustness but fixed80 has materially better execution risk, the follow-up decision is whether to track both or designate one primary and one shadow.
- If 90k passes every robustness check except turnover by a marginal amount, a separate governance decision is needed before changing the turnover gate.

## Revision History

| Timestamp | Actor | Change |
|-----------|-------|--------|
| 2026-06-15T10:37:55+08:00 | Codex | Drafted schema-v1 plan for h10 quiet fixed85/fixed80 benchmark-focused robustness and execution diagnostics. |
| 2026-06-15T10:49:30+08:00 | Codex | Incorporated MiMo round 1 feedback: added artifact validation work, tightened final doc evidence, and kept existing test-file gates after confirming files exist. |
| 2026-06-15T10:58:10+08:00 | Codex | Completed MiMo round 2 review and marked the plan reviewed with no blocking or major findings. |
| 2026-06-15T11:05:00+08:00 | Codex | User approved the reviewed plan; set plan to executing and W-001 to in_progress. |
| 2026-06-15T11:40:00+08:00 | Codex | Completed W-001: benchmark-first h10 robustness analysis, diagnostic-only 90k inclusion, focused tests, MiMo reviews, and W-001 pytest gate. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-003 generated artifacts had no machine-checkable schema or structure validation gate. | minor | accepted | Added W-004 artifact validation command for both robustness and execution decomposition outputs. | W-003,W-004 |
| 1 | MiMo | Referenced focused pytest files might be missing. | minor | rejected | Verified `tests/test_shortpick_v2_h10_robustness.py`, `tests/test_shortpick_v2_rule_selection.py`, and `tests/test_shortpick_v2_strategy_search.py` all exist. | W-001,W-002 |
| 1 | MiMo | Final decision doc evidence pattern was too coarse to prove 90k diagnostic status and prohibited directions were recorded. | minor | accepted | Tightened W-005 file_contains pattern to require benchmark robustness, 90k diagnostic-only language, and prohibited directions in one evidence line. | W-005 |
| 1 | MiMo | Plan validation command used a hardcoded home path. | note | accepted | Changed the validation gate to use `${CODEX_HOME:-$HOME/.codex}`. | Validation Gates |
| 2 | MiMo | Changed plan remains executable and prior minor findings are resolved. | note | accepted | No further plan changes required; reviewer reported no blocking or major issues. | W-001,W-002,W-003,W-004,W-005 |
| 2 | MiMo | W-003 depends on source replay/selection artifacts that may need regeneration if missing. | note | rejected | Assumptions already state these artifacts can be rerun if missing; W-003 command will fail loudly if the dependency is absent and cannot be restored in the run. | W-003 |
| 2 | MiMo | Newly referenced execution-decomposition and artifact-validation CLI entries must be registered by implementation. | note | rejected | The command_exit_0 gates in W-003 and W-004 are intended to catch missing CLI registration during execution. | W-002,W-003,W-004 |

## User Review Notes

- User requested future development use `reviewed-plan-generator` and `plan-run-loop`.
- User approved execution with "批准" on 2026-06-15; plan-run-loop execution is active.
