# Short Pick Lab V2 Plan

Status: Phase 6 complete, ready for frontend tab planning
Owner: stock_dashboard
Created: 2026-06-12
Scope: planning contract only; not a runbook

## Status Legend

| Status | Meaning |
| --- | --- |
| Draft | Proposed and editable before implementation starts. |
| Pending | Required, but not started or not yet evidenced. |
| In progress | Actively being implemented or validated. |
| Done | Completed with reviewable evidence. |
| Blocked | Cannot proceed without an explicit decision or prerequisite. |

## Core Requirement

Add a new `试验田v2` area for Short Pick Lab that evaluates account-constrained execution strategies under the user's realistic capital limit.

The new area must preserve useful validated stock-selection evidence from the existing Short Pick Lab, but it must not reuse mutable or non-fixed data interfaces from the existing lab in a way that mixes semantics. Frontend layout and visual components may be reused where appropriate. Backend APIs, artifacts, paper ledgers, and non-fixed projections must be separate.

`试验田v2` should only expose two user-facing modules:

| Module | Status | Requirement |
| --- | --- | --- |
| 纸面追踪 | In progress | Backend read API is ready with a contract-ready empty projection or v2 ledger artifact rows; frontend module remains Phase 7. |
| 历史回放 | In progress | Backend read API is ready from precomputed Phase 3/4 artifacts; frontend module remains Phase 7. |

The v2 domain must answer a different question from v1:

| Area | Question |
| --- | --- |
| Existing Short Pick Lab | Did the selected candidates or strategy families have forward evidence? |
| Short Pick Lab V2 | What would a constrained cash account actually buy, skip, hold, and realize under fixed execution rules? |

## Motivation

The existing lab has produced useful stock-selection and forward-tracking evidence, but its assumed execution model is not realistic for the user's current available capital.

The current practical constraint is approximately CNY 200,000 of deployable capital. A-share orders require board-lot quantities, generally at least 100 shares. Under this constraint, assumptions such as buying the same notional amount for every daily signal, or maintaining a rolling 10-trading-day daily-entry portfolio, can become infeasible or materially distorted.

The existing Short Pick Lab structure is already carrying multiple research, feedback, validation, and governance surfaces. It should not absorb a major execution-model redesign. V2 should be a separate constrained-account experiment layer.

## Non-Goals

| Non-goal | Status | Rationale |
| --- | --- | --- |
| Do not retrofit existing Short Pick Lab paper tracking into v2 | Pending | Existing v1 evidence must remain interpretable under its original contract. |
| Do not add delayed buying as an execution option | Done | Delayed entry has weak explanatory value and confounds signal quality with timing. |
| Do not expose a large interactive parameter grid in the first v2 UI | Pending | Governance cost and user confusion would be too high. |
| Do not present v2 as investment advice or production trading automation | Pending | V2 is research and paper validation only. |
| Do not run v2 replay dynamically from page loads | Pending | Heavy replay belongs in offline/precomputed artifacts; UI/API should be read-only. |

## Solution Direction

V2 should be built around fixed historical backtests first, then only a small set of relatively strong, explainable execution configurations should be promoted into user-visible paper tracking.

The first implementation should separate three layers:

| Layer | Status | Contract |
| --- | --- | --- |
| Candidate source layer | Pending | Reads historical and forward candidate pools from existing evidence, but only through a v2 projection contract. |
| Execution simulation layer | Pending | Applies cash, board-lot, position, fallback, and exit rules to produce account-level trades and NAV. |
| Presentation layer | Pending | Shows only selected v2 configurations, paper decisions, replay summaries, and risk notes. |

The default capital profile should start from CNY 200,000 and model board-lot execution explicitly. If Top 1 is not executable under the fixed rules, the strategy may either use a pre-declared fallback candidate or skip the signal. It must not delay the buy to a later day.

## Strategy Design Principles

| Principle | Status | Requirement |
| --- | --- | --- |
| Fixed before measured | Pending | Execution rules must be declared before measuring outcomes. |
| Few promoted variants | Pending | The v2 UI should show a small selected set, not the full search grid. |
| Explainable actions | Pending | Every buy, fallback, skip, and exit must have a deterministic reason. |
| Candidate quality and account path stay separate | Pending | Candidate-level forward returns must not be mixed with account-level NAV claims. |
| Reuse fixed data, not live computation | Pending | Daily bars, candidate pools, and derived fixed inputs should be loaded once per replay artifact where possible. |
| No delayed entry | Done | The action set is buy candidate, buy fallback, or skip. |

## Initial Rule Families

These are planning-level families, not final strategy IDs.

| Family | Status | Purpose |
| --- | --- | --- |
| Top1 or skip | Done | Established the strictest baseline in the Phase 3 replay artifact: buy the highest-ranked candidate only if executable. |
| TopN fallback | Done | Tested moving down the ranked list in the Phase 3 replay artifact. |
| Fixed notional with lot rounding | Done | Tested fixed cash-per-position behavior with 100-share board-lot rounding. |
| Position-cap utilization | Done | Tested cash use under per-position and account position caps. |
| Conservative cash reserve | Done | Tested a fixed cash reserve configuration against drawdown and utilization. |

`小股价加权` should not be treated as an investment thesis. If included, it should be framed as board-lot capital-utilization optimization and bounded by position caps, liquidity checks, and drawdown metrics.

Dynamic action selection should not be part of the first promoted v2 rules. If later introduced, it must use only signal-day-or-earlier data and should be expressed as deterministic gates such as cash sufficiency, position cap, liquidity, volatility, repeated exposure, or market breadth.

## Risk Items

| Risk | Status | Mitigation |
| --- | --- | --- |
| Semantic mixing with v1 | Done | Phase 5 defines a separate v2 paper ledger contract/schema, and Phase 6 adds separate `shortpick-lab-v2` read APIs that do not infer v2 account state from v1 paper tracking. |
| Overfitting parameter grids | In progress | Phase 4 uses fixed gates and a risk-first selector over the Phase 3 replay artifact; later UI must not expose the full parameter grid. |
| Weak sample size | Pending | Require enough historical signal days and market-regime coverage before promoting any v2 rule. |
| Slow replay execution | In progress | Phase 3 keeps replay offline/precomputed and reuses loaded series/candidate pools; Phase 6 read APIs load artifacts only and do not run replay on demand. Phase 7 UI must keep the same boundary. |
| Unclear skip/fallback attribution | Done | Phase 3 artifact persists deterministic `buy_primary`, `buy_fallback`, and `skip` reason counts plus bounded decision samples. |
| Low-price bias | Pending | Treat share-price effects as lot-rounding efficiency, not as selection alpha. |
| Governance sprawl | In progress | Phase 4 records fixed selection policy `shortpick_v2_rule_selection_v1`; later paper-tracking parameters still need governed placement before live-facing use. |
| User-facing overclaim | In progress | Phase 6 read APIs return `claim_ceiling=research_observation`, evidence-basis labels, and paper/research disclaimers; frontend copy remains Phase 7. |

## Landing Flow

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. Planning contract | Done | Freeze the v2 scope, non-goals, risk list, and acceptance rules. |
| 2. Historical replay design | Done | Defined the v2 replay artifact contract and limited rule-family matrix in `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md`, with schema `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json`. |
| 3. Replay artifact generation | Done | Added offline generator `shortpick-v2-replay`, produced `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json`, and validated the artifact against `shortpick_v2_replay_artifact.schema.json` with 721 signal days, 761 trade days, and five fixed rule-family results. |
| 4. Candidate rule selection | Done | Added offline selector `shortpick-v2-rule-selection`, produced `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`, and selected `conservative_cash_reserve_60k_top5_v1` plus `fixed_notional_40k_top5_v1` as Phase 5 contract candidates. `top1_or_skip_v1` remains the strict baseline/control. |
| 5. Paper tracking contract | Done | Defined forward v2 paper ledger semantics in `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md` with schema `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`, using the v1-aligned `2026-05-08` start window and rejecting delayed-entry actions. |
| 6. Backend read model | Done | Added separate `shortpick-lab-v2` read APIs for paper tracking and historical replay, backed by precomputed Phase 3/4 artifacts or v2 ledger artifacts. Missing v2 paper ledger returns a contract-ready empty projection instead of v1-derived rows. |
| 7. Frontend tab | Pending | Add `试验田v2` with only `纸面追踪` and `历史回放`. |
| 8. Verification and publish | Pending | Verify served UI/API behavior only after code changes are implemented. |

## Acceptance Rules

| Rule | Status | Acceptance Criteria |
| --- | --- | --- |
| Separate semantic domain | Done | Phase 3/4/5 define distinct v2 replay, rule-selection, and paper-ledger artifact contracts; Phase 6 exposes separate `shortpick-lab-v2` read APIs. |
| Frontend-only reuse boundary | In progress | Backend v2 read APIs avoid mutable v1 data projections; Phase 7 frontend may reuse layout/components without sharing v1 data interfaces. |
| No delayed-buy option | Done | V2 action taxonomy excludes delayed entry. |
| Account realism | Done | Phase 3 replay models CNY 200,000 default cash, 100-share board lots, position caps, cash reserve, cash release, buy skips, and mechanical exits. |
| Historical-first promotion | Done | Phase 4 selected candidates from the fixed Phase 3 replay artifact only, without UI parameters, DB writes, model calls, or manual overrides. |
| Bounded promoted set | Done | Phase 4 selected two configurations for Phase 5 contract design and retained the remaining passing config as a holdout. |
| Replay data adequacy | In progress | Phase 3 artifact reports signal count, trade count, skipped count, trade-day count, coverage status, and data gaps; Phase 4 still needs explicit promotion thresholds. |
| Efficiency boundary | In progress | Phase 3 replay is offline/precomputed, and Phase 6 read APIs load artifacts without market fetches or dynamic replay. Phase 7 page work must keep this boundary. |
| Explainability | Done | Phase 3 artifact exposes buy/fallback/skip reason counts and bounded account-state decision samples. |
| Paper-tracking alignment | Done | Phase 5 contract fixes the v2 forward tracking start policy at the v1-aligned `2026-05-08` window and requires explicit source-gap records instead of silent date shifts. |
| Research labeling | In progress | Phase 3/4 artifacts, Phase 5 contract, and Phase 6 read APIs are capped at `claim_ceiling=research_observation`; UI must preserve the same no-overclaim language. |

## Open Decisions

| Decision | Status | Notes |
| --- | --- | --- |
| Exact v2 start date | Done | Phase 5 contract fixes the initial v2 paper-tracking start policy at `2026-05-08`, with source gaps recorded explicitly. |
| Initial promoted replay families | Done | Phase 4 selected `conservative_cash_reserve_60k_top5_v1` and `fixed_notional_40k_top5_v1` as Phase 5 contract candidates; `top1_or_skip_v1` is retained as baseline/control. |
| Minimum evidence threshold | In progress | Phase 4 fixed first thresholds for signal count, trade count, skip ratio, return, drawdown, invested ratio, turnover, reason counts, and leakage audit; Phase 5 still needs forward tracking acceptance thresholds. |
| Position and cash defaults | Pending | CNY 200,000 total cash is the planning default; exact caps remain to be selected by replay evidence. |
| Parameter governance location | In progress | Phase 4/5 contracts name fixed policy/schema versions; live-facing parameter governance still needs placement before API/UI activation. |

## Review Status

| Reviewer | Status | Result |
| --- | --- | --- |
| Claude + Xiaomi MiMo | Done | Read-only plan, Phase 3, Phase 4, Phase 5, and Phase 6 reviews completed; result: no remaining blocking issues. |
| Claude + DeepSeek | Done | Read-only review completed; result: no blocking issues. |
