---
schema_version: 1
plan_id: "plan-20260616-shortpick-paper-divergence-attribution"
title: "Shortpick paper divergence attribution"
status: "archived"
created_at: "2026-06-16"
source_request: "Use subagent, DeepSeek, and Xiaomi MiMo to discuss why v2 paper tracking is weak while v1 constrained paper appears better, then land an evidence-backed attribution artifact through the reviewed plan/run loop."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260616-shortpick-paper-divergence-attribution"
owner: "user"
review_rounds: 2
---

# Plan: Shortpick paper divergence attribution

## Compaction-Resistant Summary

Goal: create a reproducible paper-window attribution artifact comparing v2 H10 Rank2 against v1-derived constrained controls from 2026-05-08 onward.
Hard scope: no strategy promotion, no UI change, no data refresh, no delayed buy, no rewrite of existing v1/v2 paper ledgers.
Evidence: subagent, DeepSeek, and MiMo converged on a same-window account-path attribution matrix, recorded in `docs/archive/SHORTPICK_PAPER_DIVERGENCE_BRAINSTORM_2026-06-16.md`.
Key dependencies: local runtime SQLite bars, existing v1 paper candidate records, v2 H10 replay/read-model helpers.
Major risks: current paper window is short; v1 ledger is candidate-level and must be converted into a separate research-only 20w account simulation.
Approval state: approved for execution; user requested discussion plus landing and previously approved continuing without approval prompts.

## Goal

Land a research-only attribution capability that answers whether the current v2 paper weakness is more consistent with short-window noise, market/regime mismatch, execution and capital constraints, or v1 factor selection being more suitable in the current forward window.

## Problem / Rationale

The three-year historical replay says the H10 quiet Rank2 pool-hot strategy is strong, but the `2026-05-08` onward paper tracking window looks weak. The user observed that v1-style picks under a 20w capital cap and skip-if-unaffordable rule appear better in the same period. Before changing the frozen strategy, the project needs a same-window, same-account-basis attribution artifact so the difference is not judged from mismatched ledgers or raw per-trade returns.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Use subagent, DeepSeek, and Xiaomi MiMo to discuss the next solution before implementation. | Brainstorm record, External Review Log, W-001 | covered | in_scope | `docs/archive/SHORTPICK_PAPER_DIVERGENCE_BRAINSTORM_2026-06-16.md` captures the discussion consensus before implementation. |
| SRC-002 | Explain whether v2 paper weakness versus v1 constrained paper is coincidence or has deeper evidence. | W-001 | covered | in_scope | Artifact and Chinese summary classify short-window noise, regime, execution/capital, v1 factor, and concentration evidence as support/not support/uncertain. |
| SRC-003 | Compare v1 and v2 on the same current paper window beginning at `2026-05-08`. | W-001 | covered | in_scope | CLI output records `tracking_window.start_date=2026-05-08` and per-strategy account summaries. |
| SRC-004 | Treat v1 paper data correctly rather than mixing it into existing v2 ledgers. | W-001 | covered | in_scope | Implementation uses v1 as a research candidate source and writes a separate attribution artifact, not v1/v2 paper ledgers. |
| SRC-005 | Use practical account constraints: 20w initial cash, 100-share lots, no delayed buy, fallback-or-skip where applicable. | W-001 | covered | in_scope | Tests and artifact metadata prove initial cash, board-lot sizing, no delayed actions, and reason counts. |
| SRC-006 | Preserve the H10 quiet Rank2 benchmark as the current historical benchmark, not silently discard it because of one short weak window. | W-001 | covered | in_scope | Summary explicitly compares paper-window evidence against the frozen historical benchmark and marks conclusions as research-only. |
| SRC-007 | Do not make strategy or UI changes before evidence is produced. | W-001 | covered | in_scope | Changed files are limited to offline artifact generation, schema/tests, docs, plan/run records, and CLI entrypoint. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Research operator runs a CLI against local runtime SQLite data to produce strategy evidence artifacts. | `python3 -m ashare_evidence.cli shortpick-paper-divergence-attribution ...` with the local runtime database URL. | CLI artifact builder | none | matches_product_path | CLI exits 0 and writes JSON plus Chinese markdown summary. |
| PF-002 | v2 paper tracking/replay computes H10 fixed-notional, board-lot, fallback-or-skip account paths from existing local bars. | Attribution builder reuses or mirrors the existing v2 account rules for the current paper window. | `shortpick_v2_replay` / attribution builder | none | matches_product_path | Focused tests and artifact metadata prove H10, fixed85, no delayed buy, and account-return basis. |
| PF-003 | v1 paper records are candidate-level observations, not account NAV. | The new attribution module reads v1 candidates as source signals and separately simulates a 20w top1-or-skip research account; it does not reuse v2 paper ledger rows as v1 NAV. | `shortpick_paper_divergence_attribution` | controlled research transformation from candidate rows into account simulation | controlled_simulation | Artifact source notes and tests show the v1 account path is a derived research control, not an existing paper ledger claim. |
| PF-004 | User-facing v1/v2 dashboard routes remain unchanged until evidence supports a later UI or strategy decision. | This run validates JSON/markdown artifacts and focused tests only. | Product UI/read model | none | not_applicable | Git diff contains no frontend or API display route changes. |

## Scope

### In Scope

- Add a research-only attribution module and CLI command.
- Produce a JSON artifact and Chinese markdown summary for the `2026-05-08` onward paper window.
- Include v2 H10 fixed85 Rank2, v2 fixed80 capital-shadow when the v2 source configs expose it, v1 raw candidate evidence, and v1-derived 20w top1-or-skip control; if fixed80 is not present, mark it `unavailable` rather than guessing.
- Attribute differences across short-window distribution, market/regime, execution/capital, v1 factor overlap, fallback contribution, concentration, and tail-trade sensitivity where data is available.
- Add schema validation and focused tests for artifact schema, v2 H10 account rules, v1 20w top1-or-skip, 100-share board lots, skip-if-unaffordable, and no delayed buy.
- Close the work with reviewed run record, task branch push, merge to `main`, push to `origin/main`, and temporary worktree cleanup.

### Out of Scope

- No promotion or retirement of a strategy.
- No frontend/UI change.
- No change to existing v1 or v2 paper-tracking ledgers.
- No market-data refresh.
- No delayed-buy option.
- No broad parameter search beyond the current paper-window attribution controls.

## Assumptions and Dependencies

- The local runtime SQLite database has the required daily bars and v1 paper candidate rows through the latest available paper date.
- If some latest H10 exits are not mature, the artifact must mark them pending rather than forcing realized results.
- The short current window has low statistical power; conclusions must be framed as attribution evidence, not final strategy invalidation.
- The user has already approved continuing without approval prompts, but source-scope reductions still require explicit evidence and must not be hidden.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Implement the research-only attribution module, CLI commands, schema, and focused tests. | `src/ashare_evidence/shortpick_paper_divergence_attribution.py`, CLI entries, schema, and tests. | test_pass | cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_paper_divergence_attribution.py | Passed `5 passed in 0.56s`; MiMo and DeepSeek found no blocker/major; minor happy-path and metadata fixes were applied. |
| W-002 | done | 2 | W-001 | Generate and validate the real local-data attribution artifact and Chinese summary. | `output/shortpick-paper-divergence-attribution-20260616.json` and `docs/archive/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_2026-06-16.md`. | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-paper-divergence-attribution-validate --artifact output/shortpick-paper-divergence-attribution-20260616.json | Generated with runtime SQLite and explicit v2 rule-selection artifact; validate passed with `failed_check_count=0`; latest available date `2026-06-15`; v2 fixed85/fixed80 `-8.5%`, v1-derived 20w `+2.0%`. |
| W-003 | done | 3 | W-002 | Complete reviewed closeout records and merge-ready cleanup without changing UI or strategy promotion. | Archived run record, approved/done plan evidence, task branch push and base merge evidence. | manual | manual:run record archived, plan evidence updated, task branch pushed, merged to main, origin/main pushed, temporary run state cleaned | Plan/run archive prepared; final git push/merge evidence is recorded by the closeout commands and final response; diff confirmed no frontend/API display or paper ledger mutation path changed. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The artifact starts at `2026-05-08` and records the latest available data date.
- The artifact separates existing raw v1 candidate observations from the derived v1 20w account control.
- The artifact includes at least v2 fixed85 H10 Rank2, v2 fixed80 capital shadow when the source configs expose it, and v1 20w top1-or-skip control; otherwise fixed80 is explicitly marked unavailable.
- Account summaries include total return, annualized return when meaningful, max drawdown, trade count, skip count, fallback count, cash/lot rejection count, invested ratio, turnover, and market excess when available.
- Attribution sections classify the evidence for short-window noise, market/regime, execution/capital, v1 factor overlap, fallback contribution, concentration, and tail sensitivity as `supports`, `does_not_support`, or `uncertain`.
- Chinese summary is readable and explicitly states the conclusion is research-only.
- No existing v1/v2 paper ledger or frontend route is modified.
- Run record is archived and committed; task branch is pushed; work is merged to `main`; `origin/main` is pushed; temporary lock/worktree state is cleaned.

### Validation Gates

- `python3 ${CODEX_HOME:-$HOME/.codex}/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-paper-divergence-attribution.md`
- MiMo read-only plan review.
- DeepSeek read-only plan review.
- MiMo read-only implementation review.
- DeepSeek read-only implementation review.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_paper_divergence_attribution.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-paper-divergence-attribution --start-date 2026-05-08 --initial-cash 200000 --output output/shortpick-paper-divergence-attribution-20260616.json --summary-output docs/archive/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_2026-06-16.md`
- `PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-paper-divergence-attribution-validate --artifact output/shortpick-paper-divergence-attribution-20260616.json`

## Risks and Mitigations

- Risk: the paper window is too short for statistical significance. Mitigation: artifact must label low sample size and use `uncertain` where evidence is weak.
- Risk: v1 paper data is not an account ledger. Mitigation: keep v1 raw observations separate from a clearly labeled derived 20w account simulation.
- Risk: implementation might accidentally imply strategy promotion. Mitigation: artifact claim ceiling is research observation and no UI/governance promotion path is changed.
- Risk: local data may be stale or partial. Mitigation: artifact records latest available data date, mature/pending counts, and data limitations.
- Risk: reusing private helper functions can couple the artifact to display internals. Mitigation: prefer a dedicated attribution module with focused adapters and tests.

## Open Questions

- None blocking. If the runtime data lacks enough mature H10 exits, the artifact should still close with an explicit `sample_size_limited` conclusion.

## Revision History

| Timestamp | Actor | Work Item | Old Status | New Status | Summary |
|-----------|-------|-----------|------------|------------|---------|
| 2026-06-16T18:10:00+08:00 | Codex | - | - | draft | Drafted attribution plan after subagent, MiMo, and DeepSeek brainstorm converged on same-window account-path diagnostics. |
| 2026-06-16T18:25:00+08:00 | Codex | - | draft | approved | Added durable brainstorm record, split the work items for run-loop recoverability, incorporated plan-review feedback, and marked approved based on the user's explicit request to land the solution without approval prompts. |
| 2026-06-16T13:02:38+08:00 | Codex | W-001 | pending | in_progress | Registered run state and started implementation of the attribution module, CLI, schema, and tests. |
| 2026-06-16T13:18:00+08:00 | Codex | W-001 | in_progress | done | Implemented attribution module, CLI, schema, and tests; focused pytest passed and external implementation reviews had no blocker/major. |
| 2026-06-16T13:18:00+08:00 | Codex | W-002 | pending | in_progress | Started real local-data artifact generation and validation. |
| 2026-06-16T13:25:00+08:00 | Codex | W-002 | in_progress | done | Generated real attribution JSON and Chinese summary from runtime SQLite; validation passed. |
| 2026-06-16T13:25:00+08:00 | Codex | W-003 | pending | in_progress | Started closeout, archive, commit, push, and merge steps. |
| 2026-06-16T13:32:00+08:00 | Codex | W-003 | in_progress | done | Prepared archived plan/run records and merge-ready closeout evidence; task branch and base push are completed by the final closeout commands. |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | PF-003 should clarify that the v1 20w account simulation belongs to the new attribution module and must not blur v1/v2 account helpers. | minor | resolved | PF-003 now names `shortpick_paper_divergence_attribution` as the owner and states the v1 control is a separate research transformation. | PF-003,W-001 |
| 1 | MiMo | W-001 evidence was empty and could omit expected outputs. | minor | resolved | W-001 now names expected test coverage; W-002/W-003 name concrete artifact and closeout evidence. | W-001,W-002,W-003 |
| 1 | MiMo | DeepSeek plan review fallback wording was vague. | note | resolved | Validation gates now require DeepSeek plan review; no fallback wording remains. | W-001 |
| 1 | DeepSeek | Single work item was too coarse for plan-run-loop recovery. | major | resolved | Work items were split into implementation, artifact generation/validation, and closeout. | W-001,W-002,W-003 |
| 1 | DeepSeek | Brainstorm evidence should exist before implementation instead of only in a future run record. | major | resolved | Added `docs/archive/SHORTPICK_PAPER_DIVERGENCE_BRAINSTORM_2026-06-16.md` and referenced it in Source Coverage and summary. | SRC-001 |
| 1 | DeepSeek | Test coverage expectations and closeout conditions needed clearer traceability. | minor | resolved | W-001 lists required test scenarios and W-003 carries closeout acceptance. | W-001,W-003 |
| 1 | DeepSeek | Fixed80 availability should have a deterministic rule. | minor | resolved | Scope and acceptance now require fixed80 when source configs expose it and `unavailable` otherwise. | W-002 |
| 2 | MiMo | Implementation had no blocker/major; v2 curve matching currently relies on Chinese labels and open positions are valued at cost until exit return exists. | minor | accepted | Label matching is kept within the current read-model contract; open/unresolved position metadata and valuation basis were added. | W-001 |
| 2 | DeepSeek | Implementation had no blocker/major; add a normal buy happy-path test and avoid misleading v2 cash/lot rejection count. | minor | resolved | Added rank1 buy happy-path test, fixed final closeout settlement for matured exits, set v2 cash/lot rejection count to null with basis, and read initial cash from the v2 curve. | W-001 |

## User Review Notes

- User asked to proceed with subagent, DeepSeek, and Xiaomi MiMo discussion, then land the solution through the established plan/run flow.
- User previously approved continuing without approval prompts.
