# Shortpick v3 Goal10 Next Breakthrough Exploration

Status: completed, no promotion
Created: 2026-07-09

## Goal

Use `daily_14_tranche_three_part_stability_control_min1000_weak085_strong160_cap28_v1` as the new baseline and search for the next v3 control strategy.

Acceptance requires at least one clear breakthrough:

- total return improves by at least `10%`, or
- maximum drawdown improves by at least `10%`, or
- negative-month count decreases by at least `1`.

All of these guardrails must not degrade:

- total return
- annualized return
- maximum drawdown
- negative-month count
- worst monthly return
- skipped-order rate
- skipped-signal rate
- maximum single-symbol exposure

## Baseline

Validation window: `2023-09-07` to `2026-06-26`

Initial capital: `200,000 CNY`

| Metric | Baseline |
|---|---:|
| Total return | 318.67% |
| Annualized return | 66.74% |
| Max drawdown | -7.56% |
| Negative months | 4 |
| Worst monthly return | -1.77% |
| Skipped-order rate | 23.13% |
| Skipped-signal rate | 22.20% |
| Max single-symbol exposure | 26.10% |

Baseline artifact:

- `/tmp/stock_dashboard_v3_goal10_three_part_stability_control_formal_replay_20260709.json`

## Result

No candidate passed the gate.

The current baseline remains the accepted main v3 strategy and should not be replaced by any candidate from this round.

## Scans

### 1. Representative Execution And Exit Scan

Artifact:

- `/tmp/stock_dashboard_v3_goal10_next_breakthrough_scan1b_20260709.json`

Scope:

- strong-signal scale
- weak-market scale
- tranche count
- existing exit-policy variants
- broad Rank1 overheat de-risk overlays

Runs: `39`

Passed: `0`

Finding:

- The only non-degrading result was the exact baseline reproduction.
- Stronger aggressive scaling could raise return slightly, but worsened skip rate, exposure, negative months, or drawdown.
- Wider tranche counts improved drawdown only by sacrificing return.
- Existing broad exit policies reduced return materially.

### 2. Negative-Month Repair Around Weak Scale

Artifact:

- `/tmp/stock_dashboard_v3_goal10_next_breakthrough_scan2_local_weak09_20260709.json`

Scope:

- local scan around `weak_scale=0.86` to `0.93`
- `strong_scale=1.50` to `1.80`
- min order `800` or `1000`
- single-symbol cap `25%` to `28%`

Runs: `448`

Passed: `0`

Best negative-month repair:

| Metric | Candidate |
|---|---:|
| Total return | 327.88% |
| Annualized return | 68.04% |
| Max drawdown | -7.81% |
| Negative months | 3 |
| Worst monthly return | -1.88% |
| Skipped-order rate | 22.82% |
| Skipped-signal rate | 22.00% |
| Max single-symbol exposure | 26.64% |

Rule:

- `weak_scale=0.93`
- `strong_scale=1.70`
- `min_order=1000`
- `cost_cap=28%`

Rejection reason:

- It reduced negative months from `4` to `3`, but worsened max drawdown, worst month, and max single-symbol exposure.
- This violates the no-degradation guardrail, so it is not promotable.

### 3. Higher Tranche Drawdown Scan

Artifact:

- `/tmp/stock_dashboard_v3_goal10_next_breakthrough_scan3_tranche_dd_20260709.json`

Scope:

- tranche count `15`, `16`, `18`, `20`
- min order `200`, `500`, `800`, `1000`
- strong-signal scale `1.6` to `6.0`
- weak-market scale `0.75`, `0.85`, `0.90`, `1.00`

Runs: `512`

Passed: `0`

Best drawdown-only result:

| Metric | Candidate |
|---|---:|
| Total return | 193.03% |
| Annualized return | 46.79% |
| Max drawdown | -4.71% |
| Negative months | 4 |
| Worst monthly return | -1.12% |
| Skipped-order rate | 34.70% |
| Skipped-signal rate | 22.40% |
| Max single-symbol exposure | 19.13% |

Rule:

- `tranche=20`
- `weak_scale=0.75`
- `strong_scale=2.0`
- `min_order=1000`
- `cost_cap=28%`

Rejection reason:

- Maximum drawdown improved by `37.67%`, but total return fell by `39.43%` and skipped-order rate worsened by `50.00%`.
- This confirms that simple dispersion reduces risk by under-deploying capital rather than improving the model.

### 4. Narrow Rank1 Exhaustion Exit Scan

Artifact:

- `/tmp/stock_dashboard_v3_goal10_next_breakthrough_scan4_custom_exit_20260709.json`

Scope:

- retain current three-part stability allocation
- add Rank1-only late-loss exits for high-momentum, positive-benchmark, high-industry-excess pullback entries
- scan holding-age, position loss, drawdown-from-peak, distance-from-high, and industry-excess thresholds

Runs: `64`

Passed: `0`

Best drawdown-biased result:

| Metric | Candidate |
|---|---:|
| Total return | 264.99% |
| Annualized return | 58.77% |
| Max drawdown | -7.47% |
| Negative months | 4 |
| Worst monthly return | -1.60% |
| Skipped-order rate | 22.92% |
| Skipped-signal rate | 22.40% |
| Max single-symbol exposure | 26.33% |

Rejection reason:

- The exit reduced worst month and drawdown slightly, but total return fell by `16.85%` and max single-symbol exposure worsened.
- The exit cut too many positions that later recovered or contributed to the existing winner distribution.

## Interpretation

The accepted baseline is already near a local optimum for simple execution-layer rules.

This round suggests:

- Reducing negative months by changing weak-market scale is possible, but the small monthly improvement currently comes with worse tail metrics.
- Reducing drawdown by increasing tranche count is possible, but it mostly means lower exposure and much lower return.
- Rank1 late-loss exits are not automatically beneficial; many apparent large-loss controls destroy the strategy's recovery profile.
- The next real breakthrough probably needs model-level signal discrimination, not another thin execution overlay.

## Next Research Direction

Do not promote a new control strategy from this round.

The next goal should move one level upstream:

- classify entry regimes before allocation, especially strong momentum near exhaustion vs healthy continuation
- use industry/market regime features to decide whether strong signals deserve higher or lower capital
- evaluate whether Rank1 losses can be predicted before entry rather than repaired after entry
- keep the same no-degradation gate and require a `10%` breakthrough on return, drawdown, or negative months

