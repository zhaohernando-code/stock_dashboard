---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-h10-validation-matrix"
title: "Shortpick v2 H10 validation matrix"
status: "archived"
created_at: "2026-06-16"
source_request: "Use reviewed-plan-generator and plan-run-loop to validate the H10 quiet breakout family by removing the weekday hard gate, comparing the v1 drawdown reversal filter, and expanding fixed notional groups from 10k to 85k."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display"
owner: "user"
review_rounds: 1
---

# Plan: Shortpick v2 H10 validation matrix

## Compaction-Resistant Summary

Goal: implement and run a reproducible H10 quiet breakout validation matrix for weekday gate, v1 drawdown reversal filter, and fixed notional sizing.
Scope boundary: no UI/API/paper-tracking promotion; this is research artifact generation, validation, and durable summary only.
Matrix: weekday baseline MTW versus all weekdays, drawdown reversal off versus v1 on, fixed notionals 10k, 20k, 30k, 40k, 50k, 60k, 70k, 80k, 85k.
Base strategy: quiet breakout rank2 plus pool-hot 10 percent plus H10 horizon, with fallback-or-skip execution and no delayed buy.
Key risk: historical backtest evidence can rank hypotheses but cannot prove future causality.
Approval state: MiMo plan review passed; approved by the user's explicit instruction to land this mode.

## Goal

Create a governed, reproducible validation path for the current strongest H10 quiet breakout line so later strategy discussion is based on comparable evidence instead of ad hoc parameter claims.

## Problem / Rationale

The current promising family is `quiet_breakout_rank2_poolhot10_mtw` with fixed notional sizing around 80k to 85k. The user questioned two parts of that result:

- A hard weekday rule is not acceptable unless data shows it has independent value.
- 80k to 85k sizing may be too concentrated for a 200k account and conflicts with the desire to control drawdown.

The v1 drawdown reversal filter has separately shown strong value and should be tested as an orthogonal control. This plan creates a bounded matrix that directly tests these disputed parameters while preserving the successful base selection thesis.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Validate the same mode discussed with the user through reviewed-plan-generator and plan-run-loop. | W-001, W-004 | covered | in_scope | Schema-v1 plan validates; run document is archived after execution. |
| SRC-002 | Test removing the weekday hard restriction instead of assuming MTW is justified. | W-002, W-003 | covered | in_scope | Artifact contains MTW and all-weekday rows with comparable metrics. |
| SRC-003 | Compare v1 drawdown reversal filter off versus on. | W-002, W-003 | covered | in_scope | Artifact records filter state, v1 rule signature, and off/on result deltas. |
| SRC-004 | Expand single-buy fixed notional controls downward from 10k to 85k and do not add larger sizes. | W-002, W-003 | covered | in_scope | Artifact includes exactly 10k, 20k, 30k, 40k, 50k, 60k, 70k, 80k, and 85k groups. |
| SRC-005 | Preserve H10 as the holding horizon and do not revisit 1, 3, 5, or 20 day horizons in this run. | W-002, W-003 | covered | in_scope | CLI defaults and artifact scope show horizon_days equals 10. |
| SRC-006 | Keep no delayed-buy semantics; buy fallback or skip only. | W-002, W-003 | covered | in_scope | Rule matrix allowed_actions contain buy_primary, buy_fallback, skip and no delay action. |
| SRC-007 | Provide a readable result table showing how each scheme selects stocks and how it performs. | W-003 | covered | in_scope | Markdown summary includes Chinese descriptions plus return, annualized return, excess, drawdown, trades, skip ratio, turnover, and position metrics. |
| SRC-008 | Do not promote a winning parameter into paper tracking merely because this validation runs. | W-003, W-004 | covered | in_scope | Summary labels results as research validation and final plan notes no UI/API promotion. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Research operator runs a CLI against the configured local stock dashboard database to produce replay artifacts from existing daily bars. | New CLI command runs through `python3 -m ashare_evidence.cli ...` against the local database path. | CLI artifact builder | none | matches_product_path | Command exits 0 and writes the artifact. |
| PF-002 | Replay engine executes same fixed-notional, lot-rounding, fallback-or-skip H10 account simulation used by v2 research artifacts. | New matrix builder delegates to existing v2 replay artifact builder for each comparable selection and rule config. | shortpick_v2_replay | none | matches_product_path | Tests assert allowed actions and target notionals; artifact validates row count and metrics. |
| PF-003 | v1 drawdown reversal control uses signal-date-or-prior features and the governed v1 rule. | Matrix builder calls existing drawdown reversal rule and filter helpers with historical backtest evidence basis. | shortpick_strategy_governance | none | matches_product_path | Tests or artifact metadata expose the v1 rule signature and leakage policy. |
| PF-004 | Frontend and paper tracking consume promoted strategies only after separate product work. | This run produces research docs and output artifacts only. | Product UI and paper tracking modules | none | not_applicable | Changed files exclude frontend/API paper tracking promotion. |

## Scope

### In Scope

- Add a reproducible H10 validation matrix artifact builder and CLI entrypoint.
- Reuse existing daily-series loading, account eligibility, quiet breakout selection, v2 replay, and v1 drawdown reversal filter helpers.
- Generate and archive the current matrix artifact plus a concise Chinese result summary.
- Add targeted automated tests for matrix shape, labels, allowed actions, notional grid, and validation behavior.
- Run targeted gates plus policy audit because this touches strategy parameter governance.
- Commit, push task branch, merge to `main`, push `origin/main`, archive the run record and plan according to plan-run-loop.

### Out of Scope

- No frontend tab, API route, or paper-tracking display change.
- No promotion of a new frozen strategy.
- No delayed buy option.
- No horizon search beyond H10.
- No larger single-buy notional above 85k.
- No data refresh or external market data fetch unless the existing local database is missing required daily bars.

## Assumptions and Dependencies

- The local database already contains enough daily bars for `2023-04-13` through `2026-05-08`.
- Existing `quiet_breakout_rank2_poolhot10_mtw` implementation remains the baseline selection thesis.
- Existing v1 drawdown reversal helper is the intended v1 control unless tests reveal a mismatch.
- The result can be considered a research comparison, not a statistically final proof of future performance.
- MiMo review is available through the local wrapper; if it times out, the run will shard the review or record an inconclusive reviewer result before deciding whether to proceed.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Normalize and review this schema-v1 plan, then create the plan-run-loop run record. | Reviewed and approved plan plus active run document. | command_exit_0 | cmd:python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md | Plan validation passed; MiMo plan review PASS; MiMo run-plan review PASS. |
| W-002 | done | 2 | W-001 | Implement the H10 validation matrix builder, validator, CLI command, and focused tests. | Source and test files for matrix generation. | test_pass | cmd:python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py | Added builder/CLI/tests; targeted pytest passed: 4 passed. |
| W-003 | done | 3 | W-002 | Run the matrix against the local database, validate the artifact, and archive readable research outputs. | JSON artifact and Chinese markdown summary under project outputs/docs. | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json | Generated 36-row artifact and markdown summary; artifact validation passed. |
| W-004 | done | 4 | W-003 | Complete closeout: reviewer pass, gates, archived run record, plan archive, commit, branch push, merge to main, and origin/main push. | Archived run and plan with merge evidence. | manual | manual:task branch pushed, merged to main, origin/main pushed, lock and temporary run state cleaned | Run and plan archived for closeout; gate evidence is recorded in the archived run. Branch push, main merge, main push, and cleanup are executed after the closeout commit and recorded in final response. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The produced matrix has exactly 36 comparable rows: 2 weekday modes times 2 drawdown modes times 9 fixed-notional groups.
- Every row uses H10 horizon, fixed-notional lot rounding, fallback-or-skip execution, and no delayed-buy action.
- The all-weekday mode is present and is not described as superior unless metrics support it.
- The drawdown-on mode uses the existing v1 drawdown reversal rule and records enough metadata to audit the rule.
- The result summary is readable in Chinese and includes both selection description and performance metrics.
- Degenerate rows, including rows with full skip or no trades, remain visible and are labeled instead of being silently dropped.
- No UI/API/paper tracking promotion is included.
- The run is archived and the completed plan is archived before final merge.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-h10-validation-matrix.md`
- MiMo read-only plan review.
- MiMo read-only run-plan review.
- `python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix-validate --artifact output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- Git hook pre-push gate through normal branch push.

## Risks and Mitigations

- Risk: all-weekday rows may increase trades and degrade risk metrics. Mitigation: report metrics neutrally and keep MTW as baseline, not as causal truth.
- Risk: 10k to 30k notional rows may underinvest and look poor despite lower risk. Mitigation: include invested ratio, skip ratio, and turnover so low return is interpreted correctly.
- Risk: v1 drawdown filter may reduce signal coverage too much in v2. Mitigation: include blocked count and skip ratio in the artifact summary.
- Risk: running every row by rebuilding selections separately could be slow. Mitigation: cache base selections and only run 36 replay configurations over shared loaded series.
- Risk: policy-audit may flag new strategy literals. Mitigation: use existing governed helpers where possible and classify only if the project policy requires it.
- Risk: historical backtest may overfit. Mitigation: label the output as research validation and avoid paper promotion in this plan.

## Open Questions

- None blocking. Further statistical significance work across windows or holdouts should be a follow-up plan after this matrix shows which combinations remain competitive.

## Revision History

| Timestamp | Actor | Work Item | Old Status | New Status | Summary |
|-----------|-------|-----------|------------|------------|---------|
| 2026-06-16T00:00:00+08:00 | Codex | - | - | draft | Initial schema-v1 plan drafted from the user's accepted validation mode. |
| 2026-06-16T00:20:00+08:00 | Codex | - | draft | approved | MiMo plan review passed with minor clarifications; execution approved by explicit user instruction. |
| 2026-06-16T12:05:00+08:00 | Codex | W-001 | approved | executing | Started full-plan run; MiMo run-plan review passed. |
| 2026-06-16T12:18:00+08:00 | Codex | W-001,W-002,W-003,W-004 | executing | executing | W-001 through W-003 completed; W-004 closeout started after tests, matrix generation, validation, and policy audit passed. |
| 2026-06-16T12:25:00+08:00 | Codex | W-004 | executing | archived | Completed plan work items and archived the plan for branch closeout. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-003 should distinguish matrix generation from artifact validation. | minor | resolved | W-003 acceptance now runs generation and validation remains an explicit gate. | W-003 |
| 1 | MiMo | Degenerate rows such as full-skip notional combinations should remain visible and labeled. | minor | resolved | Overall acceptance now requires retaining and labeling degenerate rows. | W-003 |

## User Review Notes

- The user explicitly requested using reviewed-plan-generator and plan-run-loop to land this work.
- The user gave standing approval to avoid approval-blocking execution prompts.
