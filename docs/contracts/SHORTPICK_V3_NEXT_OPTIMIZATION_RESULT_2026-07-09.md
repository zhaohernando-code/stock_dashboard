# Shortpick v3 Next Optimization Result

Status: forward-order kernel aligned; exploratory candidates rejected under non-degradation gate
Created: 2026-07-09

## Scope

Accepted strategy remains unchanged:

- main config: `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1`
- capital pool: `200,000 CNY`
- execution mode: daily rolling 14-tranche account replay
- sell policy: 20-trading-day horizon plus Rank1 quick-spike failure and Rank3 entry-pullback late-loss guard

Hard gate remains: total return, annualized return, max drawdown, negative-month count, and skipped-order rate must not degrade.

## Forward Kernel Alignment

Paper-tracking planned orders now call the rolling-account replay buy-order projection helper instead of maintaining a separate board-lot/min-order estimator. This keeps forward planned orders aligned with the historical replay buy semantics for:

- rank-weighted target notional
- current-NAV tranche sizing at initial forward state
- board-lot rounding
- minimum order notional
- price-too-high skip
- zero-allocation no-order

Validation:

- targeted tests: `15 passed`
- real runtime source dry run generated 3 planned orders for signal date `2026-06-26`
- planned entry date now skips the weekend: `2026-06-29` instead of `2026-06-27`

## Data Coverage

Runtime market data still has full-market daily bars only through `2026-06-26`. Rows after that date remain partial (`2` to `6` symbols per day), so no new full-history extension was accepted.

## Exploratory Candidate Scans

Generated local research artifacts:

- conditional Rank2 scan: `/tmp/stock_dashboard_v3_conditional_rank2_scan_20260709.json`
- narrow Rank1 exit scan: `/tmp/stock_dashboard_v3_rank1_narrow_exit_scan_20260709.json`

Baseline used for both scans:

| Metric | Baseline |
|---|---:|
| Total return | 311.92% |
| Annualized return | 65.77% |
| Max drawdown | -7.76% |
| Negative months | 4 |
| Skipped order rate | 35.23% |

Rank2 small-order result:

| Candidate | Total return | Max drawdown | Negative months | Skipped order rate | Decision |
|---|---:|---:|---:|---:|---|
| global min 1900 | 312.43% | -7.82% | 4 | 33.86% | rejected: drawdown degrades |
| block Rank2 strong-benchmark pullback subset | 312.13% | -7.81% | 4 | 33.76% | rejected: drawdown still degrades |
| broader Rank2 pullback filters | 311.69%-311.74% | -7.81% to -7.87% | 4 | 33.79%-33.83% | rejected: return/drawdown not both preserved |

Rank1 narrow sell result:

| Candidate family | Best observed effect | Decision |
|---|---|---|
| Rank1 pullback late-loss guard | negative months can improve from 4 to 3, but total return falls to about 310.55% and max drawdown still degrades slightly | rejected |

Interpretation: both research directions still have signal, but neither clears the strict stability-with-profitability gate. The next valid optimization should focus on ex-ante regime/industry context or a better same-kernel order replay for actual paper fills, not broader stop-loss rules.

## Completion State

| Item | Status |
|---|---|
| Verify latest full-market data coverage | completed; still `2026-06-26` |
| Align forward planned-order buy semantics with replay kernel | completed |
| Prevent weekend planned-entry display | completed |
| Explore conditional Rank2 small-order handling | completed; rejected |
| Explore narrow Rank1 late-loss sell guard | completed; rejected |
| Promote a new strategy variant | not promoted |
