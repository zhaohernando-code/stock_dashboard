---
schema_version: 1
plan_id: "plan-20260614-shortpick-v2-strategy-search"
title: "Shortpick V2 Strategy Search"
status: "executing"
created_at: "2026-06-14"
source_request: "Use reviewed-plan-generator and plan-run-loop to turn the v2 strategy discussion into an audited batch backtest and selection workflow."
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 1
---

# Plan: Shortpick V2 Strategy Search

## Compaction-Resistant Summary

Goal: add an audited `试验田v2` strategy-search batch that reuses loaded market data and ranks data-ready strategy configs.
Hard scope: no frontend surface, no paper-tracking promotion, no delayed buy, no data refresh, no schema migration unless a blocker is found.
Input constraints: CNY 200,000 cash, 100-share board lots, candidate fallback or skip only, market reference required.
First batch should favor daily-bar feasible strategies from the MiMo, DeepSeek, subagent, and local evaluation discussion.
Selection remains governed by the existing market-outperformance and annualized-return >= 30% gates.
Runtime DB reads are allowed for the real-data batch; DB writes are out of scope.
Major risks: overfitting, insufficient data fields for event strategies, long runtime, and accidental promotion claims.
Approval state: executing via plan-run-loop; W-001 is complete and W-002 is pending.

## Goal

Create a controlled, reproducible first-round search path for `试验田v2` strategies that can run many promising daily-bar-feasible configurations without one CLI process per scheme, then use the existing v2 rule-selection gate to identify whether any configuration is worth further paper tracking consideration.

## Problem / Rationale

The current v2 replay proved that execution-only tweaks such as cash reserve, TopN fallback, and fixed notional sizing are not enough. Current best v2 results remain below the market reference and far below the 30% annualized floor. The next useful step is to test materially different candidate-selection mechanisms while preserving the account constraints that motivated v2: limited capital, board lots, no delayed buys, and explicit skip/fallback decisions.

The local capacity assessment showed that a single v2 replay currently takes about 200 seconds and peaks near 3.6GB RSS / 4.85GB footprint. Running many strategies as separate processes is wasteful. The implementation should reuse loaded daily series, signal days, trade days, and market reference in one batch.

## Scope

### In Scope

- Add a reusable v2 strategy-search producer that can evaluate a bounded first batch of daily-bar-feasible candidate pools and execution configs.
- Keep output compatible with the existing `shortpick_v2_replay_artifact` and `shortpick_v2_rule_selection_artifact` flow where practical.
- Include the existing five v2 configs as controls so current rule-selection requirements remain satisfied.
- Encode only explainable daily-bar strategy families for the first batch, such as low-turnover trend extensions, strong-breadth exposure, quiet breakout, rank fallback/de-crowding, industry-relative strength where current fields support it, and drawdown-filtered trend entries.
- Add focused tests for no delayed buying, fallback/skip boundaries, strategy-search artifact shape, and selection-gate compatibility.
- Run one real-data batch against the local runtime SQLite DB and write bounded artifacts under `output/`.
- Update the v2 contract or run evidence with the first-round outcome, including whether any strategy clears the market and 30% annualized gates.

### Out of Scope

- No frontend changes.
- No production paper-tracking enablement.
- No new live API behavior.
- No data refresh, scheduler change, database migration, or runtime publish unless later work explicitly requires it.
- No use of unavailable or weakly defined event data such as announcements, northbound funds, analyst expectations, intraday sealing orders, or policy-catalyst labels in this first batch.
- No delayed buy option; a signal must buy a declared candidate on the declared entry date or skip.
- No broad parameter grid beyond a bounded first batch of explainable fixed configurations.

## Assumptions and Dependencies

- Runtime DB is available at `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- Existing index backfill and market reference data remain available for the v2 replay window.
- Current v2 artifact schema remains valid for the first batch; if schema expansion becomes necessary, that is a blocker requiring a separate plan update.
- Existing `shortpick_v2_rule_selection_v2` gates remain authoritative: explicit market reference, positive market excess, and annualized return at least 30%.
- The first batch may validly conclude that no configuration qualifies.
- Real-data batch should run with at most 2-3 worker processes if parallelism is introduced; the preferred design is in-process reuse rather than one process per strategy.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Implement the reusable v2 strategy-search batch producer and CLI entrypoint while preserving no-delayed-buy and existing control configs; focused tests must cover parser registration. | `src/ashare_evidence/shortpick_v2_strategy_search.py`, CLI parser/handler, and focused tests | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_strategy_search.py tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_rule_selection.py | Focused pytest passed: 15 passed in 2.78s; MiMo code review PASS with no blocking/major findings; plan validator passed. |
| W-002 | pending | 2 | W-001 | Run the first real-data strategy-search batch against the local runtime DB with bounded fixed configurations and produce a schema-compatible replay artifact. | `output/shortpick-v2-strategy-search-replay-artifact.json` | file_contains | path:output/shortpick-v2-strategy-search-replay-artifact.json \| pattern:"artifact_family": "shortpick_v2_replay_artifact" | |
| W-003 | pending | 3 | W-002 | Apply the existing v2 rule-selection gate to the strategy-search replay artifact and retain blocked/no-qualified outcomes if gates fail. | `output/shortpick-v2-strategy-search-selection-artifact.json` | file_contains | path:output/shortpick-v2-strategy-search-selection-artifact.json \| pattern:"selection_policy" | |
| W-004 | pending | 4 | W-003 | Record the first-round outcome and next decision boundary in the v2 contract without promoting unqualified strategies. | `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md` status/evidence update | file_contains | path:docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md \| pattern:Strategy search batch outcome | |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The repo contains an audited plan and archived run record for the strategy-search implementation.
- The strategy-search producer evaluates a bounded first batch without requiring one full CLI process per configuration.
- Generated replay output keeps `claim_ceiling=research_observation` and `evidence_basis=historical_account_replay`.
- The existing five v2 configs remain present as controls in the replay artifact.
- Rule selection uses the existing hard gates and does not select any configuration that fails to beat the market reference or annualized 30%.
- The real-data batch result is recorded whether it produces selected configs or a blocked/no-qualified outcome.

### Validation Gates

- Plan validation: `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260614-shortpick-v2-strategy-search.md`.
- Focused pytest from W-001, including CLI parser registration.
- Real-data strategy-search command for W-002: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-strategy-search --database-url sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db --output output/shortpick-v2-strategy-search-replay-artifact.json`.
- Rule-selection command for W-003: `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-v2-rule-selection --replay-artifact output/shortpick-v2-strategy-search-replay-artifact.json --output output/shortpick-v2-strategy-search-selection-artifact.json`.
- If schema-compatible artifacts are produced, validate them against existing registry schemas when practical.
- Do not run full default pytest, runtime integration, frontend build, or publish unless implementation scope unexpectedly reaches those surfaces.

## Risks and Mitigations

- Overfitting risk: keep first batch fixed, explainable, and bounded; do not auto-search large parameter grids.
- Data availability risk: defer event, intraday, northbound, analyst, and announcement-driven strategies until the underlying data fields are confirmed.
- Runtime risk: reuse loaded market series inside a batch and avoid high process concurrency on the 16GB machine.
- Claim risk: keep all artifacts as research observations; use rule-selection gates before any paper-tracking language.
- Schema risk: prefer existing artifact contracts; if a new artifact family is needed, stop for plan revision rather than smuggling unvalidated fields into strict schemas.
- Investment interpretation risk: document results as strategy research, not financial advice or production readiness.

## Open Questions

- If no first-batch strategy qualifies, the follow-up decision is whether to add new data domains such as intraday 14:00 prices, announcements, or northbound flow.
- If one or more strategies qualify historically, a later plan must decide whether and how to start v2 paper tracking without weakening forward-evidence standards.

## Revision History

| Timestamp | Actor | Change |
|-----------|-------|--------|
| 2026-06-14T00:00:00+08:00 | Codex | Drafted schema-v1 plan for audited v2 strategy-search batch and first real-data backtest. |
| 2026-06-14T11:22:00+08:00 | Codex | Incorporated MiMo plan-review findings, strengthened artifact acceptance evidence, and marked the reviewed plan approved for execution under the user's current instruction. |
| 2026-06-14T11:24:00+08:00 | Codex | Started plan-run-loop execution; changed plan status from approved to executing and W-001 from pending to in_progress. |
| 2026-06-14T11:31:00+08:00 | Codex | Completed W-001; added strategy-search producer, CLI entrypoint, focused tests, MiMo code review evidence, and passing focused pytest evidence. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | Draft status would block plan-run-loop execution. | blocking | resolved | Review completed and the user explicitly requested using plan-run-loop to complete the task, so status was advanced to approved before execution. | W-001,W-002,W-003,W-004 |
| 1 | MiMo | W-002 command-only acceptance did not prove artifact structure. | major | resolved | W-002 acceptance now checks the generated replay artifact contains the expected artifact family; the command remains a validation gate. | W-002 |
| 1 | MiMo | W-001 tests should cover CLI subcommand registration before W-002 relies on it. | major | resolved | W-001 task and validation gate now explicitly require CLI parser registration coverage in focused tests. | W-001 |
| 1 | MiMo | W-003 assumes replay artifact compatibility with existing rule-selection. | major | resolved | W-002 now requires a schema-compatible replay artifact and W-003 retains use of the existing selector as the compatibility gate. | W-002,W-003 |
| 1 | MiMo | W-004 document acceptance was too loose. | minor | resolved | W-004 acceptance now requires the more specific `Strategy search batch outcome` marker. | W-004 |
| 1 | MiMo | Runtime DB path is environment-specific. | minor | rejected | This is intentional for this local repo/run and is declared in assumptions; path absence will be treated as an environment failure. | W-002 |

## User Review Notes

- User requested `reviewed-plan-generator` and `plan-run-loop` to complete the next task, after approving non-blocking execution in this thread.
- This message is treated as approval to execute the reviewed plan because it asks to complete the task with plan-run-loop rather than only draft or inspect a plan.
