# Shortpick v3 Goal Exploration Breakthrough

Status: promoted as side-by-side control candidate, not main-strategy replacement
Created: 2026-07-09

## Candidate

Config id:

- `daily_14_tranche_conditional_aggressive_ret20_98_benchmark_nonweak_industry35_dist8_scale14_11_v1`

Rule:

- keep the accepted 14-tranche account structure
- keep the accepted Rank1 quick-fail + Rank3 pullback late-loss sell policy
- on signal days where Rank1 satisfies all of the following ex-ante conditions, scale that signal day's portfolio weights by `14/11`:
  - `benchmark_return_20d >= 0`
  - `return_20d_percentile >= 0.98`
  - `industry_return_20d_excess <= 0.35`
  - `distance_from_20d_high >= -0.08`

The rule triggers on `26` signal days in the full-history window.

## Evidence

Artifacts:

- scan: `/tmp/stock_dashboard_v3_conditional_aggressive_fast_scan_20260709.json`
- formal replay: `/tmp/stock_dashboard_v3_conditional_aggressive_control_formal_replay_20260709.json`

Validation window:

- `2023-09-07` to `2026-06-26`
- `20w CNY` initial capital
- rolling cash account with board-lot rounding, min order notional, cash release, costs, and concentration cap

## Result

| Metric | Current main | Conditional aggressive control | Delta |
|---|---:|---:|---:|
| Total return | 311.92% | 318.97% | +7.05pp |
| Annualized return | 65.77% | 66.78% | +1.01pp |
| Max drawdown | -7.76% | -7.73% | +0.03pp |
| Negative months | 4 | 4 | 0 |
| Skipped order rate | 35.23% | 35.54% | -0.32pp |
| Skipped signal rate | 24.56% | 24.95% | -0.39pp |
| Max single-symbol exposure | 26.76% | 26.77% | about flat |
| Buy orders | 616 | 613 | -3 |
| Final NAV | 823,833.71 CNY | 837,943.74 CNY | +14,110.02 CNY |

## Decision

Promote as a side-by-side historical control candidate because:

- it materially improves total return and annualized return
- max drawdown is slightly better, not worse
- negative-month count is unchanged
- max single-symbol exposure is effectively unchanged
- skipped order/signal rates worsen slightly, but not enough to be an obvious strategic disadvantage

It is not promoted as the main strategy yet because the skip-rate and cash-friction changes need forward observation and at least one more robustness pass.

## Follow-Up

Next research should stress this candidate specifically:

- month-by-month comparison against the main strategy
- contribution concentration of the 26 aggressive days
- recent-window behavior after `2026-05-08`
- whether the same condition remains valid after newer full-market data becomes available
