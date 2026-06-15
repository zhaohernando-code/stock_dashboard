# Short Pick Lab V2 Paper Tracking Contract

Status: Contract draft ready for producer implementation; H10 fixed85/fixed80 are future-observation candidates with no true-forward paper rows yet
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Source selection artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`
H10 paper governance artifact: `output/shortpick-v2-h10-paper-governance-artifact.json`
Schema: `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`

## Purpose

This contract defines the forward `试验田v2` paper-tracking ledger semantics.

The v2 paper ledger answers an account-path question: after a fixed selected v2 rule sees a new signal, what would the constrained cash account buy, skip, hold, and close? It must not reuse or mutate the existing Short Pick Lab v1 paper-tracking ledger. It must not mix v1 candidate forward-return rows with v2 account-level cash, position, and NAV claims.

This is a contract only. It does not write paper-tracking rows, backfill historical replay as true forward tracking, implement backend APIs, add frontend tabs, refresh market data, call models, or start services.

## Source Artifacts

| Source | Required value |
| --- | --- |
| Replay artifact | `shortpick_v2_replay_artifact` from Phase 3 |
| Rule selection artifact | `shortpick_v2_rule_selection_artifact` from Phase 4 |
| H10 paper governance artifact | `shortpick_v2_h10_paper_governance_artifact` carrying fixed85/fixed80 future-observation eligibility |
| Selection policy | `shortpick_v2_rule_selection_v2` |
| Claim ceiling | `research_observation` until true forward tracking has enough evidence |

Only configurations selected by the current governed rule-selection artifact or an explicitly validated H10 paper-governance overlay are eligible for v2 forward ledger rows. Under the H10 overlay, historical replay remains governance evidence only; it does not count as paper-tracking performance.

H10 paper governance; future true-forward only; fixed90 diagnostic only.

| Ledger role | Config ID | Write policy |
| --- | --- | --- |
| Future observation candidate | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | Eligible for future true-forward paper rows only after new source rows exist; no historical backfill. |
| Future observation candidate | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1` | Eligible as capital-shadow future observation under the same no-backfill policy. |
| Diagnostic only | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1` | Not eligible for active paper rows without separate turnover and boundary governance. |
| Baseline/control | `top1_or_skip_v1` | May be tracked as a labeled baseline/control, not as a promoted candidate. |
| Rejected under policy v2 | `conservative_cash_reserve_60k_top5_v1` | Historical Phase 4 v1 candidate only; not eligible for current v2 paper rows. |
| Rejected under policy v2 | `fixed_notional_40k_top5_v1` | Historical Phase 4 v1 candidate only; not eligible for current v2 paper rows. |
| Rejected under policy v2 | `top3_fallback_v1` | Not eligible for current v2 paper rows. |
| Rejected under policy v2 | `position_cap_utilization_top5_v1` | Not eligible for current v2 paper rows. |

Rejected, diagnostic-only, or historical-candidate configs must not be written as active v2 paper-tracking candidates unless a later governed selection artifact changes the config scope.

## Qualification Gates

The current selection policy fails closed unless each promoted non-baseline config has explicit replay evidence for:

| Gate | Required value |
| --- | --- |
| Market reference | Present in the replay-derived selection summary. |
| Market excess | Strategy total return is strictly above the declared market reference return. |
| Annualized return | At least 30%. |
| Existing replay gates | Signal count, trade count, skip ratio, drawdown, invested ratio, turnover, reason-count, and leakage audit gates remain required. |
| H10 governance overlay | fixed85/fixed80 eligibility must come from the validated paper-governance artifact and must preserve open robustness risks. |

## Tracking Window

The v2 forward ledger start policy is aligned to the existing Short Pick Lab paper-tracking start window where feasible:

| Field | Value |
| --- | --- |
| Tracking start date | `2026-05-08` |
| Start policy | v1-aligned forward window |
| Source-gap policy | Record gaps explicitly; do not silently shift the start date. |
| Backfill policy | Historical replay rows must not be backfilled as true forward paper tracking. |

If a selected v2 source signal is unavailable on or after `2026-05-08`, the future writer must record a `source_gap` or `not_observed` state. It must not move the effective start date forward without a new governed contract.

## Action Taxonomy

Signal-day decision actions are limited to:

| Action | Meaning |
| --- | --- |
| `buy_primary` | Buy the rank-1 candidate when it passes the selected config's account and execution constraints. |
| `buy_fallback` | Buy a lower-ranked candidate only when the selected config predeclares fallback and the higher-ranked candidates are not executable. |
| `skip` | Buy nothing because no candidate satisfies the selected config's fixed rules. |

No delayed-entry action is allowed. If the declared entry trade date cannot be executed, the future writer must choose an eligible fallback candidate on the declared entry date or record `skip`. It must not create `delay_buy`, `later_buy`, `retry_buy`, or any equivalent later discretionary buy action.

## Ledger Row Lifecycle

Each v2 paper row represents one selected config's decision for one signal date.

| Stage | Required behavior |
| --- | --- |
| Signal decision | Record config ID, config role, signal date, decision date, action, reason, candidate rank, symbol, and source state. |
| Entry | Record declared entry trade date, entry price source, quantity, board-lot size, cash before and after, and account constraints used. |
| Holding / marking | Later API/projection work may add prepared account snapshots, but page loads must not recompute trading decisions. |
| Exit | Record exit trade date, exit reason, cash release, and final position state once closed. |
| Missing data | Use `source_gap`, `not_observed`, or `blocked`; never infer a buy from absent source rows. |

Rows must be deterministic and reconstructable from fixed source artifacts, account state, and market observations available under the declared policy.

H10 fixed85/fixed80 governance readiness is metadata only and does not write paper-tracking rows. The read API may expose this readiness while `record_count = 0`; consumers must not interpret that state as historical paper performance.

## Required Row Fields

Every row must carry at least:

| Domain | Required fields |
| --- | --- |
| Identity | `record_id`, `config_id`, `config_role`, `signal_date`, `decision_date` |
| Decision | `decision_action`, `reason`, `selected_rank`, `symbol`, `source_state` |
| Entry | `entry_trade_date`, `entry_price_source`, `quantity`, `board_lot_size` |
| Account | `cash_before`, `cash_after`, `position_state` |
| Validation | `evidence_basis`, `validation_status`, `exit_trade_date`, `exit_reason` |
| Governance | `notes` for deterministic caveats and source gaps |

## Research Labels

V2 paper tracking remains paper research. The ledger and future UI must not claim production readiness, investment advice, or automated trading.

| Field | Required value |
| --- | --- |
| Evidence basis | `true_forward_tracking` |
| Claim ceiling | `research_observation` |
| Selected role label | `phase5_contract_candidate` or `phase6_forward_observation_candidate` |
| UI language | Paper/research account-path evidence only |

## Future Consumer Boundary

Future Phase 6 read APIs and Phase 7 frontend views should read prepared v2 ledger/projection data. They must not:

- run v2 replay from page loads;
- fetch or refresh market data on demand;
- call models from the read path;
- infer v2 account state from v1 paper-tracking rows;
- treat missing rows as implicit buys;
- expose a large parameter-search UI.

## Fail-Closed Conditions

The future writer or projection must fail closed when:

- the Phase 4 selection artifact is missing or not `research_observation`;
- a row uses any action outside `buy_primary`, `buy_fallback`, or `skip`;
- a row attempts delayed or discretionary later-day entry;
- selected configs do not match the governed Phase 4 selection artifact;
- the current selection artifact or validated H10 paper-governance overlay has no non-baseline configs passing market-outperformance and 30% annualized gates;
- `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1` is promoted from diagnostic-only to an active paper config;
- `2026-05-08` alignment is silently shifted;
- v1 paper-tracking rows are written or mutated as v2 rows;
- claim labels imply production proof or investment advice.
