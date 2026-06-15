---
schema_version: 1
plan_id: "plan-20260615-h10-parameter-significance"
title: "H10 Parameter Significance"
status: "executing"
created_at: "2026-06-15"
source_request: "Continue from the current strong H10 quiet strategy and use a reviewed plan/run loop to validate whether important parameters, except the already-narrowed H10 horizon, have statistical or logical support."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/20260614-shortpick-v2-robust-strategy-search-42e/20260615-h10-param-significance-adbc6f"
owner: "user"
review_rounds: 2
---

# Plan: H10 Parameter Significance

## Compaction-Resistant Summary

Goal: validate which parameters inside the current `quiet_breakout_rank2_poolhot10_mtw` H10 line have evidence, rather than searching broad new strategy families.
Hard scope: keep horizon fixed at 10 trading days; no 1/3/5/20 retest except citing prior v1 evidence; no paper-tracking promotion; no live publish.
Key parameters: weekday gate, rank choice, pool-hot threshold, fixed notional / execution pressure, fallback/skip outcomes, and concentration/weak-period stability.
Evidence approach: same-window ablation plus period-block stability and bootstrap/permutation-style confidence readouts; sparse samples are downgraded to inconclusive.
Dependencies: runtime SQLite DB, existing h10 quiet strategy-search/replay machinery, and current fixed85/fixed80 benchmark lines.
Major risks: false precision from non-iid market samples, overfitting by parameter grid, winner concentration, and confusing statistical support with causal proof.
Approval state: user requested plan-then-run execution on 2026-06-15; MiMo round 2 passed with no blocking/major findings; plan is approved for execution.

## Goal

Build and run a bounded H10 parameter-significance validation package for the current strong Short Pick Lab V2 line. The output should explain whether each important parameter has enough same-window empirical support, logical support, or both to remain in the benchmark strategy, while keeping the 10-day horizon fixed.

## Problem / Rationale

The current benchmark line, `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`, has strong paper results, but several parameters may be artifacts of the search process. The weekday gate is only one example; other parameters such as rank selection, pool-hot threshold, and fixed notional also need scrutiny.

The next useful step is therefore not a broad new search, but a controlled ablation/significance layer. Parameters with clear logic should be documented as such; parameters without a strong logical basis should be tested using same-window variants and stability readouts. The result should lower governance risk by distinguishing durable evidence from convenient historical fit.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use a reviewed plan/run workflow for the next validation work. | W-001,W-002,W-003,W-004 | covered | in-scope | Schema-v1 plan validates; MiMo review passes; run documents are archived during execution. |
| SRC-002 | Treat H10 as fixed because prior v1 testing showed 10 days far outperformed 1/3/5/20. | W-001,W-002,W-003,W-004 | covered | in-scope | Artifact scope and docs state `horizon_days=10` is fixed and do not reopen horizon search. |
| SRC-003 | Validate many current-strategy parameters, especially those that cannot be judged directly by logic, not just weekday. | W-001,W-002,W-003,W-004 | covered | in-scope | Parameter artifact includes weekday, rank, pool-hot threshold, execution notional, fallback/skip, and concentration/stability sections. |
| SRC-004 | Start from the current paper-strong selection line instead of abandoning it or broad-searching unrelated directions. | W-001,W-002,W-003,W-004 | covered | in-scope | Baseline is fixed85/fixed80 `quiet_breakout_rank2_poolhot10_mtw`; broad ma_accel/dynamic-exit/entry-quality families remain out of scope. |
| SRC-005 | Accept either statistical-test evidence or logic-based advantage as support for a parameter. | W-001,W-003,W-004 | covered | in-scope | Artifact validation requires parameter rows with support labels, sample counts, period block counts, and evidence basis; durable doc classifies each parameter. |
| SRC-006 | Prevent overclaiming: statistical evidence is still historical/research evidence, not paper-tracking or live proof. | W-001,W-002,W-003,W-004 | covered | in-scope | Artifact claim ceiling remains `research_observation`; validation checks no-promotion semantics; durable doc explicitly says no paper-tracking promotion. |

## Scope

### In Scope

- Create an H10 parameter-significance artifact and CLI for the current quiet benchmark family.
- Keep `horizon_days=10` fixed in the generated artifact and validation commands.
- Use fixed85 as the primary baseline and fixed80 as the capital-shadow baseline.
- Evaluate bounded ablations for:
  - weekday gate: MTW, all weekdays, individual weekdays, and existing MT/TW controls when sample size permits;
  - rank choice: rank1, rank2, rank3, and nearby rank choices under the same pool-hot / H10 constraints;
  - pool-hot threshold: local thresholds around 0.10, with explicit coverage and drawdown tradeoffs;
  - fixed notional: 80k/85k/90k plus existing lower-notional risk variants as execution sensitivity, not as new selection logic;
  - fallback/skip and cash/lot pressure;
  - winner concentration, monthly/quarterly/yearly stability, and weak-period behavior.
- Add statistical support readouts that are robust to small and dependent samples where practical: period-block stability, block bootstrap confidence intervals, and permutation/sign-style paired deltas.
- Require every parameter row to expose `support_label`, `sample_count`, `period_block_count`, and `evidence_basis`; any row with `period_block_count < 3` must be labeled `inconclusive`.
- Validate that supported or rejected labels are backed by non-empty comparison evidence, not only by a narrative caveat.
- Produce a durable interpretation doc separating supported, inconclusive, and rejected parameters.

### Out of Scope

- No horizon search across 1/3/5/20 in this plan; H10 is fixed per SRC-002.
- No broad strategy family search, including ma_accel, dynamic exit, entry-quality replacement, rank2-to-6 widening as a candidate family, breadth65 promotion, poolhot09/11/12 promotion, or MT/TW promotion.
- No delayed buy.
- No paper-tracking activation, runtime publish, frontend work, or live-facing API changes.
- No database writes or refresh jobs.

## Assumptions and Dependencies

- Runtime SQLite DB is available at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Existing H10 quiet replay/selection artifacts can be reused or regenerated from read-only daily bars if the run requires it.
- The same-window historical sample is finite and non-iid; statistical readouts must be framed as evidence strength, not formal causal proof.
- Sample-size limits may make individual weekday or high-threshold variants inconclusive rather than rejected.
- The branch worktree is `/Users/hernando_zhao/codex/worker-workspaces/20260614-shortpick-v2-robust-strategy-search-42e/20260615-h10-param-significance-adbc6f`.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Add the H10 parameter-significance artifact builder, CLI, schemas if needed, and focused tests. | Parameter-significance artifact code and tests covering fixed H10 scope, ablation families, support labels, sparse-sample downgrade, and no-promotion semantics | test_pass | cmd:python3 -m pytest tests/test_shortpick_v2_h10_parameter_significance.py tests/test_shortpick_v2_strategy_search.py -q | Exit 0; 42 passed in 0.72s; MiMo code review found no blocking/major issues. |
| W-002 | pending | 2 | W-001 | Run the real-data H10 parameter-significance artifact against the runtime DB. | Runtime parameter-significance JSON artifact under `output/` | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-parameter-significance --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-parameter-significance-artifact.json |  |
| W-003 | pending | 3 | W-002 | Validate the generated parameter-significance artifact with machine-checkable structure and content gates. | Artifact validation command/result covering support labels, sample counts, period blocks, fixed H10, and no-promotion semantics | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-parameter-significance-validate --artifact output/shortpick-v2-h10-parameter-significance-artifact.json |  |
| W-004 | pending | 4 | W-003 | Record the interpretation and governance outcome for each tested parameter. | Durable docs/run notes describing supported, inconclusive, and rejected parameters without paper-tracking promotion | file_contains | path:docs/archive/SHORTPICK_LAB_V2_H10_PARAMETER_SIGNIFICANCE_RUN_2026-06-15.md \| pattern:supported parameters; inconclusive parameters; rejected parameters |  |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The artifact keeps `horizon_days=10` fixed and does not reopen 1/3/5/20 search.
- The artifact uses fixed85/fixed80 `quiet_breakout_rank2_poolhot10_mtw` as mandatory benchmark context.
- Each tested parameter receives a support classification and cites the evidence basis: statistical, logical, mixed, inconclusive, or rejected.
- Statistical support readouts include sample counts, period block counts, and period/block caveats; no p-value or confidence interval is presented as causal proof.
- Rows with `period_block_count < 3` are automatically labeled `inconclusive`, and focused tests must cover this downgrade boundary.
- 90k is reported only as execution sensitivity / diagnostic context in this plan; no promotion decision is made for 90k even if returns look stronger.
- The durable doc records which parameters deserve continued use, which require more evidence, and which should not be promoted.

### Validation Gates

- Plan validation: `python3 ${CODEX_HOME:-$HOME/.codex}/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-h10-parameter-significance.md`.
- MiMo plan review before execution.
- For implementation hops: MiMo run-plan and code/artifact reviews per plan-run-loop.
- W-001 focused pytest gate.
- W-002 real-data artifact command.
- W-003 artifact validation command.
- W-004 durable doc file_contains gate.
- Default fast regression and policy audit before push if code changes are committed.
- No runtime publish because this plan is research/artifact-only.

## Risks and Mitigations

- False precision risk: use support labels and caveats instead of declaring causal weekday/rank effects.
- Multiple-comparison risk: keep the grid bounded around the current strategy and do not select a new champion from this plan alone.
- Sample-size risk: label sparse variants as inconclusive when trade counts or period coverage are weak.
- Winner-concentration risk: include top-winner and concentration readouts alongside return deltas.
- Execution-confounding risk: separate selection parameters from fixed-notional/cash/lot execution sensitivity.
- Scope drift risk: keep H10 fixed and keep broad rejected strategy families out of the candidate generation path.

## Open Questions

- If a parameter has strong return delta but weak sample size, the likely outcome is `inconclusive`, not promotion.
- If an ablation suggests the current parameter is not supported, a separate follow-up plan should decide whether to alter the benchmark or run true-forward paper tracking.
- 90k is not classified as supported/rejected in this plan; it is reported as execution sensitivity and remains subject to the existing turnover/governance boundary.

## Revision History

| Timestamp | Actor | Change |
|-----------|-------|--------|
| 2026-06-15T12:10:00+08:00 | Codex | Drafted schema-v1 plan for fixed-H10 parameter-significance validation around the current quiet benchmark line. |
| 2026-06-15T12:18:00+08:00 | Codex | Accepted MiMo round 1 feedback: added artifact validation work item, minimum sample/block fields, sparse-sample downgrade rule, stricter doc acceptance pattern, and explicit 90k diagnostic-only interpretation. |
| 2026-06-15T12:28:00+08:00 | Codex | Accepted MiMo round 2 minor feedback by making the sparse-sample downgrade boundary an explicit W-001 test requirement. |
| 2026-06-15T12:35:00+08:00 | Codex | Set plan status to approved after MiMo round 2 reported no blocking or major findings and the user had requested plan-then-run execution. |
| 2026-06-15T12:55:00+08:00 | Codex | W-001 status changed from pending to in_progress; plan status changed from approved to executing for the run-loop. |
| 2026-06-15T13:07:00+08:00 | Codex | W-001 status changed from in_progress to done after adding the parameter-significance artifact/CLI/validator/tests and passing the focused pytest gate. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-002 command_exit_0 alone does not prove the artifact contains meaningful parameter support labels or statistical content. | major | accepted | Added W-003 artifact validation command requiring support labels, sample counts, period block counts, fixed H10, and no-promotion semantics. | W-002,W-003 |
| 1 | MiMo | Non-iid risk mitigation was too narrative; implementation needed minimum statistical fields and sparse-sample downgrade rules. | major | accepted | Added required `sample_count`, `period_block_count`, `evidence_basis`, support-label constraints, and automatic `period_block_count < 3` inconclusive rule. | W-001,W-003 |
| 1 | MiMo | 90k was positioned inconsistently between execution sensitivity and possible promotion judgement. | minor | accepted | Clarified 90k is execution sensitivity / diagnostic context only and gets no promotion decision in this plan. | W-001,W-004 |
| 1 | MiMo | Durable doc acceptance pattern was too weak. | minor | accepted | Replaced it with a pattern requiring supported, inconclusive, and rejected parameter sections. | W-004 |
| 2 | MiMo | W-001 did not explicitly require a test that `period_block_count < 3` downgrades to `inconclusive`. | minor | accepted | W-001 deliverable and overall criteria now require focused sparse-sample downgrade boundary coverage. | W-001,W-003 |

## User Review Notes

- User clarified that H10 can be treated as fixed because v1 results showed 10-day results far exceeded 1, 3, 5, and 20 days.
- User requested plan-then-run style validation for the remaining current-strategy parameters.
- Current 2026-06-15 request is treated as approval to execute this exact plan after MiMo review.
