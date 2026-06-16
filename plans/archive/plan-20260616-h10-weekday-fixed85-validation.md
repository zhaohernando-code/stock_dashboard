---
schema_version: 1
plan_id: "plan-20260616-h10-weekday-fixed85-validation"
title: "H10 weekday fixed85 validation"
status: "archived"
created_at: "2026-06-16"
source_request: "Run weekday-combination validation for the H10 quiet Rank2 pool-hot strategy using fixed 85k buy size, comparing 123, 234, 135, 345, 1234, 12345 and drawdown reversal on/off while preserving prior evidence."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-h10-weekday-drawdown-validation"
owner: "user"
review_rounds: 1
---

# Plan: H10 weekday fixed85 validation

## Compaction-Resistant Summary

Goal: validate weekday combinations for the H10 quiet Rank2 pool-hot strategy at fixed 85k notional.
Hard scope: no paper-tracking promotion, no UI/API change, no delayed buy, no horizon search.
Matrix: 123, 234, 135, 345, 1234, 12345 times drawdown reversal off/on, all at 85k.
Key dependency: existing H10 matrix/replay code and local runtime SQLite daily bars.
Major risk: historical replay can rank hypotheses but does not prove future causality.
Approval state: user explicitly requested the run; archived after focused gates and external review.

## Goal

Produce a durable, reproducible fixed-85k weekday validation result for the current H10 quiet champion family so the weekday restriction can be judged against comparable evidence.

## Problem / Rationale

The previous matrix only compared `周一至周三` against `周一至周五` while also scanning many buy notionals. The user asked to hold buy notional fixed at 8.5 万, preserve the important prior data, and directly test `123`, `234`, `135`, `345`, `1234`, and `12345`, with the v1 drawdown reversal filter as an on/off comparison.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Preserve important prior results instead of overwriting the earlier notional matrix. | W-001,W-003 | covered | in_scope | Existing `output/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json` remains; new fixed85 artifact uses a distinct filename. |
| SRC-002 | Run trading-day validation for `123`, `234`, `135`, `345`, `1234`, and `12345`. | W-001,W-002 | covered | in_scope | Artifact scope lists six weekday modes and validator confirms 12 rows. |
| SRC-003 | Add drawdown reversal on/off comparison. | W-001,W-002 | covered | in_scope | Artifact has `drawdown_modes` `off` and `v1_on`; validator checks v1 rule version. |
| SRC-004 | Keep single-buy amount fixed at 8.5 万 for this run. | W-001,W-002 | covered | in_scope | Artifact `notional_values` is exactly `[85000.0]`; summary says only 8.5万. |
| SRC-005 | Keep H10 fixed and do not reopen 1/3/5/20-day horizon search. | W-001,W-002 | covered | in_scope | Artifact and validator confirm `horizon_days=10`. |
| SRC-006 | Do not introduce delayed buy; only primary, fallback, or skip. | W-001,W-002 | covered | in_scope | Validator scans `allowed_actions` and rejects delay actions. |
| SRC-007 | Provide readable evidence showing how each scheme selects stocks and how it performs. | W-002,W-003 | covered | in_scope | Chinese markdown summary table includes selection description, return, annualized return, excess, drawdown, trades, skip, turnover, and invested ratio. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Research operator runs the stock dashboard CLI against local runtime daily bars. | `python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix ...` with local SQLite URL. | CLI artifact builder | none | matches_product_path | CLI exits 0 and writes fixed85 artifact plus summary. |
| PF-002 | Existing v2 replay engine performs account-level fixed-notional, lot-rounded, fallback-or-skip H10 simulation. | Matrix builder delegates to `build_shortpick_v2_replay_artifact_from_series`. | `shortpick_v2_replay` | none | matches_product_path | Focused tests and artifact validation pass. |
| PF-003 | Existing v1 drawdown reversal filter uses signal-date-or-prior features. | Matrix builder calls governed drawdown reversal helper and records the v1 rule. | `shortpick_strategy_governance` | none | matches_product_path | Validator confirms `drawdown-reversal-filter-v1` and leakage audit remains research-only. |
| PF-004 | Paper tracking and frontend only consume strategies through separate promotion/governance work. | This run writes research artifacts only. | Product UI/read model | none | not_applicable | Changed files do not promote fixed85 weekday results into paper tracking. |

## Scope

### In Scope

- Extend the existing H10 weekday/drawdown/notional matrix generator to accept explicit weekday modes and notional values.
- Add the missing weekday mode definitions for `234`, `135`, `345`, and `1234`.
- Generate a distinct fixed85 weekday validation JSON artifact and Chinese summary.
- Add focused tests for custom weekday modes, fixed85-only rows, CLI parsing, and dynamic summary text.
- Run focused tests, artifact generation, artifact validation, and external read-only reviews.

### Out of Scope

- No strategy promotion into paper tracking.
- No UI/API change.
- No delayed buy.
- No horizon validation beyond H10.
- No new market-data refresh.
- No broader closeout gate unrelated to this research artifact.

## Assumptions and Dependencies

- The local runtime database at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` contains the required historical daily bars.
- `quiet_breakout_rank2_poolhot10_mtw` remains the benchmark family for this validation.
- The canonical checkout is currently configured as a bare Git repository, so this run used a manually created Git worktree from `origin/main`.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Parameterize the H10 matrix generator and CLI for explicit weekday modes and fixed notional values. | Source changes in matrix builder and CLI. | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py | Passed `6 passed in 0.70s`; added MiMo-requested coverage for default weekday modes with fixed85. |
| W-002 | done | 2 | W-001 | Generate and validate the fixed85 weekday/drawdown artifact from local database bars. | `output/shortpick-v2-h10-weekday-drawdown-fixed85-validation-artifact.json` and summary markdown. | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix-validate --artifact output/shortpick-v2-h10-weekday-drawdown-fixed85-validation-artifact.json | Validator passed; artifact has 12 rows, six weekday modes, two drawdown modes, and notional `[85000.0]`. |
| W-003 | done | 3 | W-002 | Preserve and summarize results without overwriting prior notional matrix evidence. | Archived plan/run and result summary. | file_contains | path:docs/archive/SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_FIXED85_VALIDATION.md \| pattern:周一至周三，不加回撤反转过滤，单笔约 8.5 万 | Summary exists; prior notional matrix artifact remains at its original path. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- Artifact has exactly 12 rows: six weekday combinations times drawdown reversal off/on.
- Every row uses H10 and fixed 8.5 万 notional.
- Prior notional-matrix evidence remains available under its original file name.
- Result summary is Chinese-readable and does not claim promotion into paper tracking.
- External reviews find no blocking issue or any blocking finding is dispositioned before closeout.

### Validation Gates

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_weekday_drawdown_notional_matrix.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix ... --target-notional 85000 ...`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-h10-weekday-drawdown-notional-matrix-validate --artifact output/shortpick-v2-h10-weekday-drawdown-fixed85-validation-artifact.json`
- MiMo read-only review.
- DeepSeek read-only review.

## Risks and Mitigations

- Risk: weekday result may be overfit to this historical window. Mitigation: output is research-only and does not promote strategies.
- Risk: adding CLI options could accidentally affect default old matrix runs. Mitigation: defaults remain the old MTW/all-weekdays and 10k-85k matrix; tests cover default and custom modes.
- Risk: fixed 85k is capital-concentrated. Mitigation: the result table includes drawdown, invested ratio, trade count, and skip rate for risk interpretation.
- Risk: generation is still slow for interactive requests. Mitigation: artifact generation is offline research work; runtime UI should consume precomputed summaries only.

## Open Questions

- Whether the current MTW advantage is robust across alternative train/test windows remains a follow-up statistical validation question.

## Revision History

| Timestamp | Actor | Work Item | Old Status | New Status | Summary |
|-----------|-------|-----------|------------|------------|---------|
| 2026-06-16T12:30:00+08:00 | Codex | - | - | approved | User requested fixed85 weekday validation and had standing approval to proceed. |
| 2026-06-16T12:42:00+08:00 | Codex | W-001 | pending | done | Implemented parameterized weekday and notional matrix support. |
| 2026-06-16T12:48:00+08:00 | Codex | W-002 | pending | done | Generated 12-row fixed85 artifact and validated it. |
| 2026-06-16T12:55:00+08:00 | Codex | W-003 | pending | done | Archived summary, plan, and run record. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Add coverage for default weekday modes with fixed 8.5w, because existing tests covered default full-notional matrix and custom six-weekday fixed85 matrix separately. | minor | resolved | Added `test_h10_weekday_drawdown_notional_matrix_supports_fixed85_with_default_weekdays`; focused pytest now passes `6 passed`. | W-001 |
| 1 | MiMo | No blocker or major; CLI compatibility, matrix coverage, research-only guardrail, leakage audit, and Chinese summary passed review. | note | accepted | Confirms the implementation matches the requested validation scope. | W-001,W-002,W-003 |
| 1 | DeepSeek | `target_notionals` is a slightly uncommon variable name. | minor | accepted | Functional mapping is correct and tested; renaming is not needed for this bounded research run. | W-001 |
| 1 | DeepSeek | Default summary output path can be overwritten by later custom matrix runs if `--summary-output` is omitted. | minor | accepted | This run uses an explicit distinct summary path and force-tracked JSON artifact; broader CLI default-path governance is follow-up, not a blocker. | W-002,W-003 |
| 1 | DeepSeek | No blocker or major; weekday mappings, fixed85 coverage, drawdown filter, no-promotion guardrails, and leakage posture are acceptable. | note | accepted | Confirms the fixed85 validation is suitable to merge as research evidence. | W-001,W-002,W-003 |

## User Review Notes

- User explicitly requested preserving important data before running this validation.
- User explicitly requested no approval prompts during the ongoing goal.
