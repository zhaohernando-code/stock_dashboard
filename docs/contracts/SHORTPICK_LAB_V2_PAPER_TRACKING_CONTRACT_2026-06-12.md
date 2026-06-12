# Short Pick Lab V2 Paper Tracking Contract

Status: Contract draft ready for producer implementation
Owner: stock_dashboard
Created: 2026-06-12
Source plan: `docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md`
Source selection artifact: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/shortpick-v2-rule-selection-artifact-20260612.json`
Schema: `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`

## Purpose

This contract defines the forward `试验田v2` paper-tracking ledger semantics.

The v2 paper ledger answers an account-path question: after a fixed selected v2 rule sees a new signal, what would the constrained cash account buy, skip, hold, and close? It must not reuse or mutate the existing Short Pick Lab v1 paper-tracking ledger. It must not mix v1 candidate forward-return rows with v2 account-level cash, position, and NAV claims.

This is a contract only. It does not write paper-tracking rows, backfill historical replay as true forward tracking, expose backend APIs, add frontend tabs, refresh market data, call models, or start services.

## Source Artifacts

| Source | Required value |
| --- | --- |
| Replay artifact | `shortpick_v2_replay_artifact` from Phase 3 |
| Rule selection artifact | `shortpick_v2_rule_selection_artifact` from Phase 4 |
| Selection policy | `shortpick_v2_rule_selection_v1` |
| Claim ceiling | `research_observation` until true forward tracking has enough evidence |

Only Phase 4-selected configurations are eligible for the first v2 forward ledger:

| Ledger role | Config ID | Write policy |
| --- | --- | --- |
| Phase 5 contract candidate | `conservative_cash_reserve_60k_top5_v1` | Eligible for future v2 paper rows after writer implementation. |
| Phase 5 contract candidate | `fixed_notional_40k_top5_v1` | Eligible for future v2 paper rows after writer implementation. |
| Baseline/control | `top1_or_skip_v1` | May be tracked as a labeled baseline/control, not as a promoted candidate. |

`top3_fallback_v1` remains a Phase 4 holdout and `position_cap_utilization_top5_v1` remains rejected. They must not be written as active v2 paper-tracking candidates unless a later governed selection artifact changes the config scope.

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
| Selected role label | `phase5_contract_candidate` |
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
- `2026-05-08` alignment is silently shifted;
- v1 paper-tracking rows are written or mutated as v2 rows;
- claim labels imply production proof or investment advice.
