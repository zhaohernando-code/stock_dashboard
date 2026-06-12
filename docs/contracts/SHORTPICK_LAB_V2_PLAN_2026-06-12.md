# Short Pick Lab V2 Plan

Status: Reviewed, ready for implementation planning
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
| 纸面追踪 | Pending | Track v2 execution decisions forward from the same start window as the existing paper tracking line. |
| 历史回放 | Pending | Replay fixed v2 execution rules over historical candidate pools and account-eligible market data. |

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
| Top1 or skip | Pending | Establish the strictest baseline: buy the highest-ranked candidate only if executable. |
| TopN fallback | Pending | Test whether moving down the ranked list improves deployability without destroying selection quality. |
| Fixed notional with lot rounding | Pending | Preserve a target cash-per-position idea while respecting 100-share lots. |
| Position-cap utilization | Pending | Improve cash use under per-stock caps without explicitly favoring low nominal share price. |
| Conservative cash reserve | Pending | Test whether lower utilization reduces drawdown or forced concentration. |

`小股价加权` should not be treated as an investment thesis. If included, it should be framed as board-lot capital-utilization optimization and bounded by position caps, liquidity checks, and drawdown metrics.

Dynamic action selection should not be part of the first promoted v2 rules. If later introduced, it must use only signal-day-or-earlier data and should be expressed as deterministic gates such as cash sufficiency, position cap, liquidity, volatility, repeated exposure, or market breadth.

## Risk Items

| Risk | Status | Mitigation |
| --- | --- | --- |
| Semantic mixing with v1 | Pending | Use separate v2 API, artifact, and ledger contracts; frontend reuse only for presentation primitives. |
| Overfitting parameter grids | Pending | Use staged screening and promote only a few fixed, explainable configurations. |
| Weak sample size | Pending | Require enough historical signal days and market-regime coverage before promoting any v2 rule. |
| Slow replay execution | Pending | Reuse loaded fixed market series and candidate pools; keep replay offline/precomputed. |
| Unclear skip/fallback attribution | Pending | Persist deterministic action reasons for each signal day. |
| Low-price bias | Pending | Treat share-price effects as lot-rounding efficiency, not as selection alpha. |
| Governance sprawl | Pending | Keep v2 parameters versioned and retire abandoned variants instead of mutating active rules. |
| User-facing overclaim | Pending | Label v2 as paper research and account-path evidence, not production proof. |

## Landing Flow

| Phase | Status | Outcome |
| --- | --- | --- |
| 1. Planning contract | Done | Freeze the v2 scope, non-goals, risk list, and acceptance rules. |
| 2. Historical replay design | Done | Defined the v2 replay artifact contract and limited rule-family matrix in `docs/contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md`, with schema `docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json`. |
| 3. Replay artifact generation | Pending | Produce fixed historical results for selected rule families over adequate data. |
| 4. Candidate rule selection | Pending | Choose a small set of v2 configurations based on replay evidence and governance rules. |
| 5. Paper tracking contract | Pending | Define forward v2 ledger semantics starting from the v1-aligned tracking window. |
| 6. Backend read model | Pending | Add separate v2 read APIs backed by precomputed artifacts or v2 ledger records. |
| 7. Frontend tab | Pending | Add `试验田v2` with only `纸面追踪` and `历史回放`. |
| 8. Verification and publish | Pending | Verify served UI/API behavior only after code changes are implemented. |

## Acceptance Rules

| Rule | Status | Acceptance Criteria |
| --- | --- | --- |
| Separate semantic domain | Pending | V2 has distinct API/artifact/ledger contracts and does not overload v1 paper tracking. |
| Frontend-only reuse boundary | Pending | Shared UI components may be reused, but v2 does not read mutable v1 data projections directly. |
| No delayed-buy option | Done | V2 action taxonomy excludes delayed entry. |
| Account realism | Pending | Replay models total cash, 100-share board lots, position caps, cash release, buy skips, and exits. |
| Historical-first promotion | Pending | User-visible v2 strategies are selected from historical replay evidence, not ad hoc UI parameters. |
| Bounded promoted set | Pending | The first v2 UI shows a small governed set of configurations, not a parameter search surface. |
| Replay data adequacy | Pending | Historical replay reports signal count, trade count, skipped count, market-regime coverage, and data gaps. |
| Efficiency boundary | Pending | Page/API reads do not run heavy replay or fetch market data. |
| Explainability | Pending | Each signal-day decision exposes buy/fallback/skip reason and account-state context. |
| Paper-tracking alignment | Pending | V2 forward tracking start policy is explicitly aligned with the existing paper-tracking start window where feasible. |
| Research labeling | Pending | UI and artifacts avoid production-proof or investment-advice language. |

## Open Decisions

| Decision | Status | Notes |
| --- | --- | --- |
| Exact v2 start date | Pending | Planning assumption is alignment with existing paper tracking, currently observed from 2026-05-08. |
| Initial promoted replay families | Pending | Start from top1-or-skip, TopN fallback, lot-rounded fixed notional, and capped utilization variants. |
| Minimum evidence threshold | Pending | Needs a threshold for signal days, completed trades, drawdown, skipped ratio, and regime coverage. |
| Position and cash defaults | Pending | CNY 200,000 total cash is the planning default; exact caps remain to be selected by replay evidence. |
| Parameter governance location | Pending | V2 tunables should enter the existing policy/config governance model before live-facing use. |

## Review Status

| Reviewer | Status | Result |
| --- | --- | --- |
| Claude + Xiaomi MiMo | Done | Read-only review completed; result: no blocking issues. |
| Claude + DeepSeek | Done | Read-only review completed; result: no blocking issues. |
