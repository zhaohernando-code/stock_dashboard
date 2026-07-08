# Shortpick v3 Rolling Tranche Optimization Result

Status: data coverage extension completed; exploratory optimization candidates rejected under non-degradation gate
Created: 2026-07-08

## Scope

This pass keeps the accepted v3 model strategy unchanged:

- main config: `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1`
- capital pool: `200,000 CNY`
- execution mode: daily rolling 14-tranche account replay
- sell policy: 20-trading-day horizon plus Rank1 quick-spike failure and Rank3 entry-pullback late-loss guard
- retained gate: Rank3 weak-benchmark position gate (`benchmark_return_20d <= 0.03 -> rank_weight_multiplier = 0`)

The hard acceptance rule for exploratory candidates is unchanged: total return, annualized return, max drawdown, negative-month count, and skipped-order rate must not degrade versus the accepted main config.

## Data Coverage Extension

Previous static full-history replay ended at `2026-05-26`. Runtime market data now has full-market daily bars through `2026-06-26`; later days (`2026-06-29` onward) only have partial rows and are excluded from full-history replay.

Generated local research artifacts:

- extended candidate run: `/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_extended_to_20260626_20260708.json`
- extended full-history replay: `/tmp/stock_dashboard_v3_rolling_account_replay_20w_extended_to_20260626_layered_exit_rank3_gate_20260708.json`
- rejected candidate scan: `/tmp/stock_dashboard_v3_rolling_account_replay_20w_extended_to_20260626_candidate_optimization_20260708.json`
- Rank2 minimum-order boundary scan: `/tmp/stock_dashboard_v3_rolling_account_replay_20w_extended_to_20260626_rank2_min_boundary_20260708.json`

Extended validation window:

| Item | Previous | Extended |
|---|---:|---:|
| Signal window end | 2026-05-26 | 2026-06-26 |
| Signal days | 491 | 509 |
| Selected picks | 1473 | 1527 |
| Market symbols | 575 | 593 |

## Extended Baseline

| Replay | Total return | Annualized return | Max drawdown | Negative months | Skipped order rate | Skipped signal rate | Buy orders | Max single-symbol exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Main 14-tranche layered strategy | 311.92% | 65.77% | -7.76% | 4 | 35.23% | 24.56% | 616 | 26.76% |
| 15-tranche low-concentration control | 293.38% | 63.07% | -7.92% | 5 | 21.77% | 21.61% | 744 | 25.32% |

Compared with the previous 2026-05-26 window, the main strategy improved from `298.92%` to `311.92%` total return, annualized return improved from `63.96%` to `65.77%`, max drawdown improved slightly from `-7.81%` to `-7.76%`, negative months stayed at `4`, and skipped order rate improved from `36.12%` to `35.23%`.

Decision: the accepted main strategy remains valid after the coverage extension.

## Exploratory Optimization Results

| Candidate | Total return delta | Max drawdown delta | Negative months | Skipped order rate delta | Result |
|---|---:|---:|---:|---:|---|
| Rank2 minimum order 1000 | +2.44pp | -0.58pp | 4 | -12.20pp | Rejected: drawdown and concentration worsen |
| Rank2 minimum order 1500 | +1.54pp | -0.59pp | 4 | -4.63pp | Rejected: drawdown worsens |
| Rank2 minimum order 1750 | +0.31pp | -0.05pp | 4 | -1.37pp | Rejected: drawdown still worsens |
| Rank2 minimum order 1900 | +0.48pp | -0.01pp | 4 | -1.05pp | Rejected: tiny drawdown degradation remains |
| Rank2 minimum order 1940/1950 | -0.15pp | 0.00pp | 4 | -0.84pp | Rejected: return degrades |
| Single-symbol cost cap 22% | -41.88pp | 0.00pp | 5 | +1.68pp | Rejected: return, negative months, skip rate degrade |
| Single-symbol cost cap 20% | -56.21pp | 0.00pp | 5 | +2.31pp | Rejected: return, negative months, skip rate degrade |
| Rank1 high-momentum pullback late-loss exit | -8.31pp | -0.00pp | 4 | -0.21pp | Rejected: return degrades without material stability benefit |

Interpretation:

- Rank2 small-order handling has signal, but every profitable threshold still slightly worsens max drawdown. It remains a watch-only research direction, not an accepted strategy change.
- Lowering single-symbol cost caps does not reliably lower realized max market exposure and materially harms return.
- The tested Rank1 late-loss rule exits too many recoverable positions. Broadening dynamic sell rules remains rejected.

## Completion State

| Item | Status |
|---|---|
| Extend full-history replay to latest full-market runtime data | completed |
| Update static historical replay read model to 2026-06-26 metrics | completed |
| Explore Rank2 small-order handling | completed, rejected under strict gate |
| Explore 20%-22% single-symbol cap | completed, rejected |
| Explore narrow Rank1 late-loss exit | completed, rejected |
| Promote a new strategy variant | not promoted; no exploratory candidate passed all non-degradation gates |
