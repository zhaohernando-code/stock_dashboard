---
schema_version: 1
plan_id: "plan-20260615-h10-rank-ablation"
title: "H10 Rank Ablation"
status: "executing"
created_at: "2026-06-15"
source_request: "Continue the reviewed plan/run validation by directly testing whether the current H10 quiet benchmark's rank2 choice has same-gate empirical support."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929"
owner: "user"
review_rounds: 2
---

# Plan: H10 Rank Ablation

## Compaction-Resistant Summary

Goal: close the known rank-choice evidence gap in the current `quiet_breakout_rank2_poolhot10_mtw` H10 quiet benchmark line.
Hard scope: keep `horizon_days=10`, MTW weekday gate, poolhot10 threshold, fallback-or-skip action model, and fixed80/fixed85/fixed90 execution configs unchanged; no broad strategy search and no paper-tracking promotion.
Key test: add direct same-gate rank1/rank2/rank3 ablations, with rank4/rank5 allowed only as diagnostic context if cheap to include.
Decision rule: classify rank2 as supported, inconclusive, or challenged from same-window return, drawdown, trade count, period coverage, and stability evidence; the artifact must expose the numeric thresholds used; do not auto-replace the benchmark if another rank wins.
Dependencies: runtime SQLite DB, existing H10 quiet strategy-search/replay machinery, and the prior parameter-significance result that marked rank2 inconclusive.
Major risks: overfitting to rank position, sparse period evidence, broadening the search by accident, and mistaking historical rank dominance for causal proof.

## Goal

Build and run a bounded H10 rank-ablation validation package that answers one question: whether choosing the second candidate from the current quiet selection pool is still defensible when rank1 and rank3 are tested under the exact same H10, MTW, poolhot10, and execution assumptions.

## Problem / Rationale

The current best paper result uses `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`. The previous H10 parameter-significance run kept this as the benchmark but explicitly marked `rank2` as inconclusive because there was no direct same-gate rank1/rank3 comparison.

This plan should close that specific gap without reopening strategy discovery. If rank2 remains strongest or materially safer, it gains bounded support. If rank1 or rank3 wins clearly, the result should be recorded as a challenged benchmark and handed to a later decision plan, not silently promoted.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use the existing reviewed-plan-generator and plan-run-loop process. | W-001,W-002,W-003,W-004 | covered | in-scope | Schema-v1 plan validates; external review is recorded; run-loop status updates are captured. |
| SRC-002 | Keep H10 fixed because prior evidence showed 10 trading days far outperformed other holding periods. | W-001,W-002,W-003,W-004 | covered | in-scope | Artifact and durable doc state `horizon_days=10`; no 1/3/5/20 retest is introduced. |
| SRC-003 | Validate current-strategy parameters that cannot be judged directly by logic. | W-001,W-002,W-003,W-004 | covered | in-scope | Rank1/rank2/rank3 are compared under the same MTW + poolhot10 + H10 gate. |
| SRC-004 | Use the current strong benchmark as the anchor, not unrelated new directions. | W-001,W-002,W-003,W-004 | covered | in-scope | Baseline config remains `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`; no new strategy family is introduced. |
| SRC-005 | Preserve the prior convention that delayed buy is not a valid action. | W-001,W-003,W-004 | covered | in-scope | The artifact remains fallback-or-skip only and includes no delayed-buy semantics. |
| SRC-006 | Do not overclaim historical backtest evidence as paper-tracking readiness. | W-001,W-002,W-003,W-004 | covered | in-scope | Artifact claim ceiling remains `research_observation`; durable doc has a no-promotion statement. |

## Scope

### In Scope

- Add rank1/rank3 same-gate quiet source variants around the existing rank2 benchmark.
- Keep rank4/rank5 optional and diagnostic-only if they are cheap to include in the same candidate batch.
- Preserve the fixed80/fixed85/fixed90 execution variants so the rank comparison can be inspected under the same capital pressure.
- Add a rank-ablation artifact and validation command with machine-checkable fields: rank, config id, support label, sample count, period block count, return delta versus rank2, drawdown delta versus rank2, and evidence basis.
- Require rank1, rank2, and rank3 rows to exist for the primary fixed85 comparison.
- Downgrade any primary fixed85 rank row with `sample_count < 50` or `period_block_count < 3` to `inconclusive`.
- Allow rank2 to be labeled `supported` only when the mandatory fixed85 rank1, rank2, and rank3 rows all meet `sample_count >= 50` and `period_block_count >= 3`.
- Define `period_block_count` as the number of calendar-year blocks covered by the replay signal date range, matching the existing H10 parameter-significance helper.
- Use explicit rank decision thresholds in the artifact policy. The initial threshold is a `0.03` total-return delta versus the best mandatory comparator, with no material drawdown deterioration, so the durable doc can cite the same rule.
- Produce a durable interpretation doc that records whether rank2 is supported, inconclusive, or challenged.

### Out of Scope

- No horizon search across 1/3/5/20.
- No weekday, pool-hot threshold, notional, fallback, exit, or entry-quality re-optimization.
- No broad new strategy families such as ma_accel, dynamic exit, breadth65, rank2-to-6 widening, or unrelated filters.
- No delayed buy.
- No benchmark replacement, paper-tracking activation, frontend work, runtime publish, database migration, or data refresh.

## Assumptions and Dependencies

- Runtime SQLite DB is available at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Existing H10 quiet replay/selection machinery can generate rank-specific source variants without changing fixed market data.
- Historical samples are non-iid; support labels must be treated as bounded empirical evidence, not causal proof.
- Rank4/rank5 may be omitted from support classification if adding them materially increases runtime or muddies the mandatory rank1/2/3 comparison.
- The branch worktree is `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-rank-ablation-140929`.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Add same-gate rank ablation support for the H10 quiet benchmark family. | Rank source variants, rank-ablation artifact builder, CLI validation, and focused tests covering rank1, rank2, and rank3 source generation plus same-gate comparison semantics | test_pass | cmd:python3 -m pytest tests/test_shortpick_v2_h10_rank_ablation.py tests/test_shortpick_v2_strategy_search.py -q | Exit 0; 45 passed in 0.65s; MiMo code review found no blocking or major issues, and minor threshold/diagnostic-rank coverage feedback was accepted. |
| W-002 | done | 2 | W-001 | Run the real-data H10 rank-ablation artifact against the runtime DB. | Runtime rank-ablation JSON artifact under `output/` | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --horizon-days 10 --initial-cash 200000 --output output/shortpick-v2-h10-rank-ablation-artifact.json | Exit 0; wrote `output/shortpick-v2-h10-rank-ablation-artifact.json`; artifact id `shortpick_v2_h10_rank_ablation:2023-05-16:2026-05-08:20260615`; rank2_status=supported; rank_row_count=5. |
| W-003 | done | 3 | W-002 | Validate the generated rank-ablation artifact with machine-checkable structure and content gates. | Artifact validation command/result covering fixed H10, rank1/2/3 presence, support labels, period coverage, and no-promotion semantics | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-rank-ablation-validate --artifact output/shortpick-v2-h10-rank-ablation-artifact.json; validator must exit non-zero if fixed H10, rank1/2/3 presence, support label, coverage threshold, or no-promotion checks fail | Exit 0; validation status passed; 53 checks, 0 failed; horizon_days=10; rank2_status=supported; rank_row_count=5. |
| W-004 | pending | 4 | W-003 | Record the rank-ablation interpretation and governance outcome. | Durable docs/run notes describing rank2 support status and any challenged-rank follow-up without promotion | file_contains | path:docs/archive/SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md \| pattern:Rank2 status; no paper-tracking promotion; rank1/rank2/rank3 | pending |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The artifact keeps `horizon_days=10` fixed and does not reopen holding-period search.
- Rank1, rank2, and rank3 use the same MTW weekday gate, poolhot10 threshold, replay window, action model, and fixed85 primary comparison.
- Rank2 is classified using explicit same-gate evidence, not only the fact that the current benchmark uses it.
- Primary fixed85 rank rows require `sample_count >= 50` and `period_block_count >= 3` to support any non-inconclusive rank2 decision.
- The artifact and validator expose the numeric rank decision thresholds, including total-return delta and drawdown protection.
- Fixed80 and fixed90 rows are informational execution-pressure context only; they cannot override the primary fixed85 rank support decision.
- Rank4/rank5, if present, are diagnostic rows and cannot redefine the plan's mandatory support decision.
- The durable doc clearly separates supported, inconclusive, and challenged outcomes.
- No paper-tracking promotion, runtime publish, or benchmark replacement is made by this run.

### Validation Gates

- Plan validation: `python3 ${CODEX_HOME:-$HOME/.codex}/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-h10-rank-ablation.md`.
- MiMo plan review before execution.
- Per-hop run-plan and artifact/code review according to plan-run-loop.
- W-001 focused pytest gate.
- W-002 real-data artifact command.
- W-003 artifact validation command.
- W-004 durable doc file_contains gate.
- Default fast regression and policy audit before push because this plan changes code.
- No runtime publish because this plan is research/artifact-only.

## Risks and Mitigations

- Overfitting risk: only test direct rank neighbors under the current same-gate benchmark family.
- Search-drift risk: reject unrelated source families and keep rank4/rank5 diagnostic-only.
- Sparse-sample risk: require sample counts and period block counts; weak coverage downgrades support.
- Drawdown tradeoff risk: compare return and drawdown deltas versus rank2, not headline return alone.
- Claim risk: keep `research_observation` claim ceiling and no-promotion language.
- Runtime risk: reuse fixed daily-bar data and current replay machinery; keep the candidate grid small.

## Open Questions

- If rank1 or rank3 beats rank2 materially, the follow-up is a separate benchmark-governance plan, not an automatic replacement in this task.
- If rank2 has lower return but meaningfully better drawdown or stability, the interpretation should state that tradeoff instead of forcing a binary winner.
- If all rank rows are sample-poor, the outcome should remain `inconclusive`.

## Revision History

| Timestamp | Actor | Change |
|-----------|-------|--------|
| 2026-06-15T14:15:00+08:00 | Codex | Drafted schema-v1 plan for direct same-gate H10 rank ablation around the current quiet benchmark. |
| 2026-06-15T14:32:00+08:00 | Codex | Accepted MiMo round 1 feedback by adding concrete sample/period coverage thresholds, explicit rank1/rank2/rank3 test coverage, fixed80/fixed90 informational-only semantics, and non-zero validator content gates. |
| 2026-06-15T14:43:00+08:00 | Codex | Accepted MiMo round 2 minor clarifications by defining period blocks as calendar-year blocks and requiring artifact-visible numeric rank decision thresholds. |
| 2026-06-15T14:45:00+08:00 | Codex | Set plan status to approved after MiMo round 2 reported no blocking or major findings and the user requested continuing the established flow. |
| 2026-06-15T14:50:00+08:00 | Codex | Started W-001 execution; plan status changed to executing and W-001 to in_progress. |
| 2026-06-15T15:20:00+08:00 | Codex | Completed W-001 after adding rank source variants, rank-ablation artifact/CLI/validator/tests, accepting MiMo minor test feedback, and passing the W-001 focused pytest gate. |
| 2026-06-15T15:25:00+08:00 | Codex | Started W-002 real-data rank-ablation artifact generation after W-001 completion. |
| 2026-06-15T15:38:00+08:00 | Codex | Completed W-002 after the real-data rank-ablation command exited 0 and wrote the local output artifact with rank2_status=supported. |
| 2026-06-15T15:42:00+08:00 | Codex | Started W-003 artifact validation after W-002 completed. |
| 2026-06-15T15:45:00+08:00 | Codex | Completed W-003 after the rank-ablation artifact validator passed 53 checks with 0 failures. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Weak period coverage downgrade had no numeric threshold. | major | accepted | Added `sample_count >= 50` and `period_block_count >= 3` thresholds for primary fixed85 rows, plus a rule that rank2 can be supported only when rank1/2/3 all meet coverage. | W-001,W-003 |
| 1 | MiMo | W-001 acceptance test was generic and did not guarantee rank1/rank3 same-gate coverage. | major | accepted | W-001 now requires focused tests for rank1, rank2, and rank3 source generation plus same-gate comparison semantics. | W-001 |
| 1 | MiMo | Fixed80/fixed90 comparison role was mentioned but not required or classified. | minor | accepted | Overall acceptance now states fixed80/fixed90 are informational execution-pressure context only and cannot override fixed85 rank support. | W-002,W-003 |
| 1 | MiMo | W-003 command spec did not explicitly state validator failure conditions. | minor | accepted | W-003 acceptance spec now requires non-zero exit when fixed H10, rank1/2/3, support labels, coverage thresholds, or no-promotion checks fail. | W-003 |
| 1 | MiMo | W-004 durable doc date path is hardcoded. | minor | rejected | Execution is planned for 2026-06-15 and the hardcoded archive path matches the run date. | W-004 |
| 2 | MiMo | Supported versus challenged numeric thresholds were implicit in implementation. | minor | accepted | Plan now requires the artifact and validator to expose total-return delta and drawdown-protection thresholds; initial return delta is `0.03`. | W-001,W-003,W-004 |
| 2 | MiMo | `period_block_count` was not defined. | minor | accepted | Plan now defines it as calendar-year blocks covered by the replay signal date range, matching existing H10 parameter-significance machinery. | W-001,W-003 |
| 2 | MiMo | No blocking or major findings remained after revision. | note | accepted | Plan is ready for execution under the established reviewed run-loop. | W-001,W-002,W-003,W-004 |

## User Review Notes

- User approved continuing with the existing reviewed plan/run process.
- User explicitly wants parameter validation around the current strong H10 strategy rather than broad unrelated search.
- Prior run classified rank2 as inconclusive due to missing direct same-gate rank1/rank3 ablation.
