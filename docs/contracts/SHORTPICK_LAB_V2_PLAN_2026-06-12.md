# Short Pick Lab V2 Plan

Status: Complete through Phase 10; published runtime served API verified through Phase 9
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
| 纸面追踪 | Done | Backend read API is ready with a contract-ready empty projection or v2 ledger artifact rows; Phase 7 frontend reads it through the separate v2 page. |
| 历史回放 | Done | Backend read API is ready from precomputed Phase 3/4 artifacts; Phase 7 frontend reads it through the separate v2 page. |

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
| Do not retrofit existing Short Pick Lab paper tracking into v2 | Done | Existing v1 evidence remains under its original contract; v2 uses separate read APIs and frontend state. |
| Do not add delayed buying as an execution option | Done | Delayed entry has weak explanatory value and confounds signal quality with timing. |
| Do not expose a large interactive parameter grid in the first v2 UI | Done | Phase 7 shows promoted/baseline/holdout readouts only; no parameter controls are exposed. |
| Do not present v2 as investment advice or production trading automation | Done | Phase 7 preserves research and read-only labeling. |
| Do not run v2 replay dynamically from page loads | Done | Phase 7 calls read APIs only and has no replay generation or market-refresh action. |

## Solution Direction

V2 should be built around fixed historical backtests first, then only a small set of relatively strong, explainable execution configurations should be promoted into user-visible paper tracking.

The first implementation should separate three layers:

| Layer | Status | Contract |
| --- | --- | --- |
| Candidate source layer | Done | Reads fixed historical and forward candidate evidence through v2 artifact/read contracts, not v1 mutable UI projections. |
| Execution simulation layer | Done | Phase 3 artifacts apply cash, board-lot, position, fallback, and exit rules to produce account-level trades and NAV. |
| Presentation layer | Done | Phase 7 shows only selected v2 configurations, paper decisions, replay summaries, and risk notes. |

The default capital profile should start from CNY 200,000 and model board-lot execution explicitly. If Top 1 is not executable under the fixed rules, the strategy may either use a pre-declared fallback candidate or skip the signal. It must not delay the buy to a later day.

## 2026-06-13 Qualification Gate Amendment

The project owner added a stricter v2 promotion rule after reviewing current replay results: any strategy that does not beat the declared market reference is unqualified, and annualized return below 30% is not worth considering for v2 promotion or paper tracking.

This amendment supersedes the original Phase 4 promotion result for current candidate status. The 2026-06-12 Phase 4 output remains a historical record, but `conservative_cash_reserve_60k_top5_v1` and `fixed_notional_40k_top5_v1` are no longer current v2 paper-tracking candidates unless a later governed selection artifact passes the v2 qualification gates.

| Gate | Status | Requirement |
| --- | --- | --- |
| Explicit market reference | Done | Rule selection v2 fails closed when replay results lack a declared market reference return. |
| Market outperformance | Done | Non-baseline configs must have total return strictly above the declared market reference return. |
| Annualized return floor | Done | Non-baseline configs must have annualized return at least 30%. |
| Baseline separation | Done | `top1_or_skip_v1` may remain as baseline/control even when it fails promotion gates, but it cannot be labeled as a promoted candidate. |

## 2026-06-14 Strategy search batch outcome

The first bounded v2 strategy-search batch tested 30 daily-bar-feasible candidate-source and execution-config combinations under the existing v2 account constraints: CNY 200,000 capital, 100-share board lots, no delayed buying, and fallback-or-skip execution only.

| Item | Outcome |
| --- | --- |
| Replay artifact | `output/shortpick-v2-strategy-search-replay-artifact.json` |
| Selection artifact | `output/shortpick-v2-strategy-search-selection-artifact.json` |
| Signal days | 721 |
| Result count | 30 |
| Market reference total return | `+41.8444%` |
| Best tested total return | `+34.0899%` from `quiet_breakout_rank2__fixed_notional_40k_top5_v1` |
| Best tested annualized return | `+10.2012%` |
| Governed selection result | `status=blocked`, 0 selected configs, 1 baseline config, 0 holdout configs, 29 rejected configs |

No configuration from this batch qualifies for v2 paper-tracking promotion. The current decision boundary remains strict: a non-baseline strategy must have explicit market-reference evidence, total return strictly above that reference, and annualized return at least 30% before it can be treated as a current v2 candidate.

The outcome also means the first batch did not find enough value in execution-only variations or daily-bar-only candidate-source variations. The next strategy iteration should change the selection thesis or add a governed data domain before another large replay batch; simply choosing the least-bad parameter set from this batch is not acceptable.

## Strategy Design Principles

| Principle | Status | Requirement |
| --- | --- | --- |
| Fixed before measured | Done | Phase 3/4/5 fixed replay, selection, and paper-ledger contracts before Phase 7 presentation. |
| Few promoted variants | Done | Phase 7 shows selected, baseline, holdout, and rejected readouts without exposing the full search grid. |
| Explainable actions | Done | Phase 3/5/6 artifacts and read APIs expose deterministic buy, fallback, skip, and reason fields. |
| Candidate quality and account path stay separate | Done | Phase 7 separates historical account replay and paper account path readouts from v1 candidate-level evidence. |
| Reuse fixed data, not live computation | Done | Phase 7 reads precomputed artifacts through v2 APIs and does not trigger replay or refresh work. |
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
| Overfitting parameter grids | Done | Phase 4 uses fixed gates and a risk-first selector over the Phase 3 replay artifact; Phase 7 does not expose the full parameter grid. |
| Weak sample size | Done | Phase 3/4 used 721 signal days, 761 trade days, complete coverage status, and explicit gate thresholds before promotion. |
| Slow replay execution | Done | Phase 3 keeps replay offline/precomputed, Phase 6 read APIs load artifacts only, and Phase 7 UI reads without dynamic replay. |
| Unclear skip/fallback attribution | Done | Phase 3 artifact persists deterministic `buy_primary`, `buy_fallback`, and `skip` reason counts plus bounded decision samples. |
| Low-price bias | Done | V2 treats share-price effects as board-lot execution efficiency and does not expose low-price weighting as alpha or a UI parameter. |
| Governance sprawl | Done | Phase 4/5 fixed selection policy and schema versions; Phase 6/7 expose read-only APIs/UI without mutable parameter controls. |
| User-facing overclaim | Done | Phase 6 read APIs return `claim_ceiling=research_observation`, evidence-basis labels, and paper/research disclaimers; Phase 7 preserves those labels in the UI. |
| Underperforming market reference | Done | Phase 9 adds `shortpick_v2_rule_selection_v2`; strategies missing market reference evidence, failing market excess, or below 30% annualized are blocked from current candidate status. |
| First strategy-search batch underqualified | Done | Phase 10 records that 30 tested configs produced 0 selected strategies under the market-outperformance and annualized-return gates, so no batch result is promoted. |

## Landing Flow

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. Planning contract | Done | Freeze the v2 scope, non-goals, risk list, and acceptance rules. |
| 2. Historical replay design | Done | Defined the v2 replay artifact contract and limited rule-family matrix in `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md`, with schema `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json`. |
| 3. Replay artifact generation | Done | Added offline generator `shortpick-v2-replay`, produced `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-replay-artifact-20260612.json`, and validated the artifact against `shortpick_v2_replay_artifact.schema.json` with 721 signal days, 761 trade days, and five fixed rule-family results. |
| 4. Candidate rule selection | Done | Added offline selector `shortpick-v2-rule-selection`, produced `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`, and initially selected `conservative_cash_reserve_60k_top5_v1` plus `fixed_notional_40k_top5_v1` under the v1 policy. This remains a historical record only after the Phase 9 gate amendment. `top1_or_skip_v1` remains the strict baseline/control. |
| 5. Paper tracking contract | Done | Defined forward v2 paper ledger semantics in `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md` with schema `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`, using the v1-aligned `2026-05-08` start window and rejecting delayed-entry actions. |
| 6. Backend read model | Done | Added separate `shortpick-lab-v2` read APIs for paper tracking and historical replay, backed by precomputed Phase 3/4 artifacts or v2 ledger artifacts. Missing v2 paper ledger returns a contract-ready empty projection instead of v1-derived rows. |
| 7. Frontend tab | Done | Added `试验田v2` with only `纸面追踪` and `历史回放`, backed by separate v2 frontend API calls and static coverage. |
| 8. Verification and publish | Done | Published runtime source/dist for `b62f2a9`; verified backend health, v2 served APIs, frontend asset match, and served `试验田v2` UI behavior. |
| 9. Qualification gate amendment | Done | Backfilled local runtime benchmark index bars, added `shortpick_v2_rule_selection_v2` gates for explicit market reference, market outperformance, and at least 30% annualized return, regenerated runtime v2 replay/selection artifacts with market reference `+41.8444%`, and changed read models so no current config is shown as selected when the gate blocks all candidates. |
| 10. Strategy search batch outcome | Done | Added a bounded first strategy-search batch with 30 daily-bar-feasible combinations. The governed selector returned `status=blocked` with 0 selected configs; the best result still trailed the `+41.8444%` market reference and remained below the 30% annualized floor, so no strategy is promoted. |

## Acceptance Rules

| Rule | Status | Acceptance Criteria |
| --- | --- | --- |
| Separate semantic domain | Done | Phase 3/4/5 define distinct v2 replay, rule-selection, and paper-ledger artifact contracts; Phase 6 exposes separate `shortpick-lab-v2` read APIs. |
| Frontend-only reuse boundary | Done | Backend v2 read APIs avoid mutable v1 data projections; Phase 7 frontend reuses shell/layout only while keeping separate v2 APIs, types, and view state. |
| No delayed-buy option | Done | V2 action taxonomy excludes delayed entry. |
| Account realism | Done | Phase 3 replay models CNY 200,000 default cash, 100-share board lots, position caps, cash reserve, cash release, buy skips, and mechanical exits. |
| Historical-first promotion | Done | Phase 4 selected candidates from the fixed Phase 3 replay artifact only, without UI parameters, DB writes, model calls, or manual overrides. |
| Bounded promoted set | Done | Phase 4 selected two configurations for Phase 5 contract design and retained the remaining passing config as a holdout. |
| Market and annualized qualification | Done | Current selection policy requires explicit market reference evidence, total return strictly above that reference, and annualized return at least 30%; current low-return v2 results are blocked rather than promoted. |
| Strategy search batch outcome | Done | Phase 10 records the first bounded strategy-search batch result, including replay and selection artifact paths, best tested return, market reference, selected count, and the no-promotion decision. |
| Replay data adequacy | Done | Phase 3 artifact reports signal count, trade count, skipped count, trade-day count, coverage status, and data gaps; Phase 4 applies explicit promotion thresholds. |
| Efficiency boundary | Done | Phase 3 replay is offline/precomputed, Phase 6 read APIs load artifacts without market fetches or dynamic replay, and Phase 7 only reads those APIs. |
| Explainability | Done | Phase 3 artifact exposes buy/fallback/skip reason counts and bounded account-state decision samples. |
| Paper-tracking alignment | Done | Phase 5 contract fixes the v2 forward tracking start policy at the v1-aligned `2026-05-08` window and requires explicit source-gap records instead of silent date shifts. |
| Research labeling | Done | Phase 3/4 artifacts, Phase 5 contract, Phase 6 read APIs, and Phase 7 UI are capped at `claim_ceiling=research_observation` or equivalent read-only research language. |
| Runtime verification | Done | Phase 8 served backend returned `200 /health`, v2 paper tracking returned `contract_ready` with `2026-05-08`, v2 replay returned `ready`, and Browser verification confirmed the v2 page/tabs render without v1 module labels or console errors. Phase 9 published commit `9fbe6f2`, regenerated v2 runtime artifacts, verified v2 historical replay API returns `blocked` with selected count `0` and market reference `+41.8444%`, verified v2 paper tracking API returns `blocked`, and confirmed the public route no longer returns the prior `ECONNREFUSED 127.0.0.1:5173` error. |

## Open Decisions

| Decision | Status | Notes |
| --- | --- | --- |
| Exact v2 start date | Done | Phase 5 contract fixes the initial v2 paper-tracking start policy at `2026-05-08`, with source gaps recorded explicitly. |
| Initial promoted replay families | Done | Phase 4 selected `conservative_cash_reserve_60k_top5_v1` and `fixed_notional_40k_top5_v1` under policy v1; policy v2 supersedes that current-candidate status, so no non-baseline config is currently qualified until a later governed artifact passes the market and annualized gates. |
| Minimum evidence threshold | Done | Phase 4 fixed first thresholds for signal count, trade count, skip ratio, return, drawdown, invested ratio, turnover, reason counts, and leakage audit; forward tracking remains read-only contract observation until rows exist. |
| Position and cash defaults | Done | V2 uses CNY 200,000 default cash; promoted configs fix the cash reserve/notional and position-cap behavior selected from replay evidence. |
| Parameter governance location | Done | Current live-facing scope is read-only and governed by fixed Phase 4/5 policy/schema versions; no mutable UI/API parameter surface is active. |
| Next strategy-search direction | Blocked | Phase 10 found no qualified strategy in the first bounded batch. A later plan must either change the stock-selection thesis or add a governed data domain before another large search; no current batch result may be promoted. |

## Review Status

| Reviewer | Status | Result |
| --- | --- | --- |
| Claude + Xiaomi MiMo | Done | Read-only plan, Phase 3, Phase 4, Phase 5, Phase 6, and Phase 7 frontend reviews completed; result: no remaining blocking issues. |
| Claude + DeepSeek | Done | Read-only review completed; result: no blocking issues. |
