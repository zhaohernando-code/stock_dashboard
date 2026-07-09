# Shortpick v3 Goal10 Meta Signal Quality Result

Status: accepted side-by-side control candidate
Created: 2026-07-09

## Goal Gate

This round used the accepted three-part stability control as the baseline:

- `daily_14_tranche_three_part_stability_control_min1000_weak085_strong160_cap28_v1`

Acceptance requires at least one breakthrough:

- total return improves by `>= 10%`, or
- maximum drawdown improves by `>= 10%`, or
- negative-month count decreases by at least `1`.

No degradation is allowed on:

- total return
- annualized return
- maximum drawdown
- negative-month count
- worst monthly return
- skipped-order rate
- skipped-signal rate
- maximum single-symbol exposure

## Direction

The prior round showed that simple execution-layer changes were near a local optimum. This round moved one level upstream:

- diagnose entry-time signal regimes using historical labels
- keep only rules that use fields known before entry
- apply signal-day portfolio scaling before order projection
- preserve the same rolling tranche account replay and sell policy

## Accepted Candidate

Config id:

- `daily_14_tranche_meta_signal_quality_industry_leadership_min1000_weak092_strong165_lead135_low090_cap28_v1`

Rule:

- keep 14 tranche rolling account replay
- keep `1000 CNY` minimum order
- keep `28%` max single-symbol cost-basis cap
- keep Rank1 quick-fail + Rank3 pullback late-loss sell policy
- weak baseline segment:
  - if Rank1 `benchmark_return_20d < -0.02`, scale signal-day weights by `0.92`
- strong signal segment:
  - if Rank1 `benchmark_return_20d >= 0`
  - and `return_20d_percentile >= 0.98`
  - and `industry_return_20d_excess <= 0.50`
  - and `distance_from_20d_high >= -0.08`
  - scale signal-day weights by `1.65`
- industry leadership segment:
  - if Rank1 `industry_return_20d_excess >= 0.35`
  - and `benchmark_return_20d >= 0.05`
  - scale signal-day weights by `1.35`
- low-quality segment:
  - if Rank1 `industry_return_20d_excess <= 0.20`
  - and `benchmark_return_20d <= 0.08`
  - scale signal-day weights by `0.90`

Formal replay artifact:

- `/tmp/stock_dashboard_v3_goal10_meta_signal_quality_formal_replay_20260709.json`

Scan artifacts:

- `/tmp/stock_dashboard_v3_goal10_meta_industry_leadership_scan_compact_20260709.json`
- `/tmp/stock_dashboard_v3_goal10_meta_industry_weak_combo_scan_20260709.json`

## Result

Validation window:

- `2023-09-07` to `2026-06-26`
- `20w CNY` initial capital
- rolling cash account with board-lot rounding, cash release, costs, min order, and concentration cap

| Metric | Baseline | Meta signal quality | Change |
|---|---:|---:|---:|
| Total return | 318.67% | 322.83% | +1.31% |
| Annualized return | 66.74% | 67.33% | +0.88% |
| Max drawdown | -7.56% | -7.28% | +3.75% better |
| Negative months | 4 | 3 | passed |
| Worst monthly return | -1.77% | -1.55% | better |
| Skipped-order rate | 23.13% | 23.03% | better |
| Skipped-signal rate | 22.20% | 21.61% | better |
| Max single-symbol exposure | 26.10% | 25.21% | better |
| Buy orders | 731 | 732 | +1 |
| Final NAV | 837,342.33 CNY | 845,665.45 CNY | +8,323.13 CNY |

Primary accepted breakthrough:

- negative-month count decreases from `4` to `3`

## Trigger Counts

| Segment | Signal days |
|---|---:|
| Weak baseline | 137 |
| Strong signal | 41 |
| Industry leadership | 14 |
| Low quality | 339 |
| Multi-segment overlap | 142 |

Remaining negative months:

| Month | Return |
|---|---:|
| 2023-10 | -1.55% |
| 2023-12 | -0.87% |
| 2025-04 | -0.46% |

The removed negative month is `2025-01`.

## Decision

Promote as a side-by-side control candidate, not as an immediate primary replacement.

Reason:

- it passes the agreed gate by reducing negative months without degrading any declared guardrail
- it improves stability more than profitability
- forward paper tracking should confirm whether the new entry-time segmentation remains useful outside the historical replay window

The candidate is connected to the v3 strategy lab static historical read model and daily paper-tracking plan generation.

