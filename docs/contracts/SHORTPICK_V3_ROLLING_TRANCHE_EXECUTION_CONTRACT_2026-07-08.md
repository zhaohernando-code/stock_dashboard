# Shortpick v3 Rolling Tranche Execution Contract

Status: contract ready; historical account replay completed for current research candidate
Created: 2026-07-08
Source model candidate: `selected_exhaustion_date_scaled_v3_top3_20d_v1`
Machine-readable builder: `src/ashare_evidence/rolling_tranche_execution_contract.py`

## Purpose

This contract defines the execution-account boundary required before the v3 selected-exhaustion model can be considered for production or dashboard projection.

The current v3 research replay evaluates each signal date independently. It does not prove that the same CNY 200,000 cash account can buy every daily signal while prior 20-trading-day positions are still open. Therefore the next replay must be a rolling cash-account replay, not another independent signal-date return summary.

## Hard Rejection

Monthly full-capital rotation is rejected.

The following path is forbidden:

- buy nearly the full CNY 200,000 pool on one signal date;
- hold roughly 20 trading days;
- ignore intervening signals because the account has no cash;
- rebalance only after the mechanical 20-trading-day exit.

Reason: this concentrates timing and symbol risk into one sleeve and does not match the user's acceptable risk boundary.

## Account Profile

| Field | Required value |
|---|---:|
| Initial cash | `<= 200,000 CNY`; default replay tier `200,000 CNY` |
| Account type | cash account |
| Board lot | `100` shares, rounded down |
| Minimum order notional | `4,000 CNY` |
| Margin / shorting | forbidden |
| Delayed discretionary entry | forbidden |
| Same cash reused across overlapping holds | forbidden |

## Rolling Configurations

These are execution configurations, not new alpha models. The current formal baseline is the 14-tranche compound configuration with layered Rank1 quick-fail and Rank3 entry-pullback late-loss exits; the 15-tranche compound configuration is the lower-concentration control group.

| Config | Cadence | Target active tranches | Per-signal budget at 200k | Account share per signal |
|---|---:|---:|---:|---:|
| `daily_20_tranche_rank_weighted_v1` | every signal day | 20 | `10,000 CNY` | `5%` |
| `daily_14_tranche_rank_weighted_compound_min2500_v1` | every signal day | 14 | current NAV / 14, min order `2,500 CNY` | about `7.14%`; previous baseline |
| `daily_14_tranche_rank_weighted_compound_min2250_rank3_pullback_late_trend_loss_guard_v1` | every signal day | 14 | current NAV / 14, min order `2,250 CNY` | about `7.14%`; previous accepted baseline |
| `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1` | every signal day | 14 | current NAV / 14, min order `2,250 CNY` | about `7.14%`; formal baseline |
| `daily_15_tranche_rank_weighted_compound_min1000_v1` | every signal day | 15 | current NAV / 15, min order `1,000 CNY` | about `6.67%`; lower-concentration control |
| `two_day_10_tranche_rank_weighted_v1` | every 2 trade days | 10 | `20,000 CNY` | `10%` |
| `two_day_10_tranche_rank_weighted_offset1_v1` | every 2 trade days, offset 1 | 10 | `20,000 CNY` | `10%` |
| `weekly_4_tranche_rank_weighted_v1` | every 5 trade days | 4 | `50,000 CNY` | `25%` |

Hard cap: a single signal date must not deploy more than `25%` of the account.

## Dynamic Exit Research Configurations

The following sell-policy configurations are reproducibility hooks. Broad price-action-only dynamic exits are not accepted baselines because the 2026-07-08 replay showed that they lowered return or worsened stability. The accepted exit is deliberately narrow and uses entry-time risk state.

| Config family | Exit policy | Current decision |
|---|---|---|
| `*_profit_guard_v1` | 10% stop loss, quick spike failure, profit giveback, and trend-break loss | rejected: materially lower return and worse negative-month count |
| `*_loss_guard_v1` | 12% stop loss only | rejected: lower return and more negative months |
| `*_late_trend_loss_guard_v1` | all ranks can exit after confirmed late trend loss | rejected: fewer negative months for 14-tranche, but materially lower return |
| `*_rank23_late_trend_loss_guard_v1` | only Rank2/Rank3 can exit after confirmed late trend loss | rejected but closest challenger; lower return without enough stability improvement |
| `*_rank3_pullback_late_trend_loss_guard_v1` | only Rank3 positions with entry-time pullback from 20-day high can exit after confirmed late trend loss | previous accepted baseline |
| `*_layered_rank1_quickfail_rank3_pullback_exit_v1` | Rank1 exits only on early quick-spike failure; Rank3 exits only on entry-pullback confirmed late loss | formal baseline |
| broad industry-crowding / weak-market exits | apply industry or benchmark stress exits across Rank1/Rank2 | rejected: direct scans frequently exited recovering winners before the original 20-day horizon |

Future sell-policy work should not promote broader policies unless a new replay beats the formal 14-tranche baseline without weakening total return, annualized return, max drawdown, negative-month count, or skipped order rate.

## Order Rules

Each signal-date tranche must allocate its own tranche budget, not the full account.

Required behavior:

- use the model's selected top3 and model rank weights inside the tranche;
- round each order down to 100-share board lots;
- skip a slot when one board lot costs more than the slot's available rank budget;
- skip a slot when rounded notional is below the governed minimum order notional;
- apply same-day or signal-day-known fallback only if the fallback rule is declared before replay;
- record every buy, skip, fallback, and sell with deterministic reason codes.
- record zero target allocations as `no_order`, not as execution skips.
- if a recent signal has not reached its planned exit by the last available bar, keep it open and mark to market instead of skipping it as `missing_exit_bar`.

Price-too-high rule:

A candidate is price-too-high for a slot when one board lot costs more than that slot's available rank budget after cash and concentration caps.

## Required Inputs

- selected top-k picks by signal date, including rank, symbol, score, model rank weight, target horizon, and risk scales;
- daily market bars for entry, mark-to-market, exit, limit-state checks, and board-lot price checks;
- trading calendar for entry, exit, cash release, and overlapping holds;
- cost model with buy cost, sell cost, and stamp tax;
- source lineage proving buy, skip, fallback, and sizing decisions used only signal-day-or-earlier data.

## Required Outputs

- daily NAV and cash ledger;
- order ledger with buy, skip, fallback, sell, quantity, price, cash before, and cash after;
- open-position ledger with cost basis, market value, planned exit, actual exit, and exit reason;
- reason counts for board-lot block, price-too-high, insufficient cash, concentration cap, low liquidity, missing bar, and no fallback;
- monthly account return, max drawdown, invested ratio, turnover, skipped-signal rate, and concentration metrics.

## Promotion Gate

The replay can only move this v3 candidate beyond research when all of the following are true:

- no monthly full-capital rotation is used;
- all three rolling configurations above are replayed or explicitly marked infeasible with deterministic reasons;
- account-level total return, max drawdown, negative-month count, invested ratio, skipped-signal rate, and concentration are reported;
- profitability and stability gates from `SHORTPICK_V3_SELECTED_EXHAUSTION_DATE_SCALE_RESULT_2026-07-08.md` are not weakened;
- leakage audit passes;
- the output is clearly marked as account-level replay, not independent signal-date replay.

## Completion State

| Item | Status |
|---|---|
| Rolling execution boundary defined | completed |
| Monthly full-capital rotation rejected | completed |
| Machine-readable contract builder | completed |
| Historical account replay implementation | completed |
| Full-history account replay result | completed |
| Recent-window account replay result | completed |
| Skipped order rate below 50% for accepted research candidate | completed |
| Production/dashboard eligibility | blocked pending governed review and live handoff |
