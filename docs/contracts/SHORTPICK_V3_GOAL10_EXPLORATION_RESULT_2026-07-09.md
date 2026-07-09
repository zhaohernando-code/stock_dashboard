# Shortpick v3 Goal10 Exploration Result

Status: accepted side-by-side control candidate
Created: 2026-07-09

## Goal Gate

This round tightened the prior "material advantage" rule:

- at least one important metric must improve by `>= 10%` relative to the current v3 main strategy
- no degradation is allowed on total return, annualized return, max drawdown, negative-month count, worst month, skipped-order rate, skipped-signal rate, or max single-symbol exposure
- the candidate must stay inside the v3 selected-top-k model and rolling-tranche cash-account execution family

Current main baseline:

| Metric | Main |
|---|---:|
| Total return | 311.92% |
| Annualized return | 65.77% |
| Max drawdown | -7.76% |
| Negative months | 4 |
| Worst monthly return | -1.78% |
| Skipped order rate | 35.23% |
| Skipped signal rate | 24.56% |
| Max single-symbol exposure | 26.76% |

## Accepted Candidate

Config id:

- `daily_14_tranche_three_part_stability_control_min1000_weak085_strong160_cap28_v1`

Rule:

- keep the accepted 14-tranche account structure
- keep the accepted Rank1 quick-fail + Rank3 pullback late-loss sell policy
- set minimum order notional to `1000 CNY`
- tighten max single-symbol cost-basis cap to `28%`
- if Rank1 `benchmark_return_20d < -0.02`, scale the signal day's portfolio weights by `0.85`
- if Rank1 satisfies all strong-signal conditions, scale the signal day's portfolio weights by `1.60`:
  - `benchmark_return_20d >= 0`
  - `return_20d_percentile >= 0.98`
  - `industry_return_20d_excess <= 0.50`
  - `distance_from_20d_high >= -0.08`

Formal replay artifact:

- `/tmp/stock_dashboard_v3_goal10_three_part_stability_control_formal_replay_20260709.json`

Scan artifacts:

- `/tmp/stock_dashboard_v3_goal10_small_conditional_aggressive_scan_20260709.json`
- `/tmp/stock_dashboard_v3_goal10_aggressive_min_order_combo_scan_20260709.json`
- `/tmp/stock_dashboard_v3_goal10_min_order_risk_repair_scan_20260709.json`
- `/tmp/stock_dashboard_v3_goal10_three_part_combo_scan_20260709.json`

## Result

Validation window:

- `2023-09-07` to `2026-06-26`
- `20w CNY` initial capital
- rolling cash account with board-lot rounding, cash release, costs, min order, and concentration cap

| Metric | Main | Three-part stability control | Relative change |
|---|---:|---:|---:|
| Total return | 311.92% | 318.67% | +2.17% |
| Annualized return | 65.77% | 66.74% | +1.47% |
| Max drawdown | -7.76% | -7.56% | +2.52% better |
| Negative months | 4 | 4 | no degradation |
| Worst monthly return | -1.78% | -1.77% | better |
| Skipped order rate | 35.23% | 23.13% | +34.33% better |
| Skipped signal rate | 24.56% | 22.20% | +9.60% better |
| Max single-symbol exposure | 26.76% | 26.10% | +2.47% better |
| Buy orders | 616 | 731 | +115 |
| Final NAV | 823,833.71 CNY | 837,342.33 CNY | +13,508.61 CNY |

Primary 10% advantage:

- skipped order rate improves by `34.33%`

## Rejected Directions

Pure conditional aggression can reach more than 10% return improvement, but it worsens skipped-order rate, max drawdown, or concentration.

Lowering the minimum order amount alone improves skipped-order rate, but `1500 CNY` variants worsened max drawdown.

Weak-market scaling alone improves drawdown materially, but broad weak filters sacrifice too much total return.

The accepted candidate is the first tested combination that clears the 10% advantage rule while preserving all declared non-degradation constraints.

## Decision

Promote as a side-by-side control candidate focused on execution stability, not as the new main strategy.

This candidate is now safe to observe next to the main strategy because it keeps profitability intact while materially reducing cash-friction skips. Main-strategy replacement should still require forward paper evidence because the rule changes three execution levers at once: min order, weak-market scale, and single-symbol cap.
