# Shortpick v3 Selected Exhaustion Date Scale Result

Status: research candidate found; production promotion requires a new <=200,000 CNY execution-capacity contract
Created: 2026-07-08

## Metric Contract

This result follows `docs/contracts/SHORTPICK_V3_STABILITY_OPTIMIZATION_METRIC_CONTRACT_2026-07-08.md`.

The optimization target is not to avoid `20d`. The target is to preserve v3 profitability while reducing clustered downside from:

- industry crowding or same-industry synchronous collapse;
- strong-terminal exhaustion after high-volume momentum;
- medium industry strength that is positive but not a broad main-wave surge;
- pullback from recent highs under weak-to-neutral benchmark conditions.

## Candidate

Model spec:

- `selected_exhaustion_date_scaled_v3_top3_20d_v1`

Implementation:

- Keeps the current v3 frontier model type: `regime_adaptive_breakout_defensive_ranker`.
- Keeps the current v3 ranking, replacement, exit horizon, rank weighting, gross exposure, and position weighting.
- Adds one post-selection date-level exposure control:
  - scan final selected top3;
  - if any selected pick has high 20d and 5d momentum, high amount expansion, high turnover, pullback from 20d high, benchmark 20d return not above 3%, and industry 20d excess return between 10% and 19.7476%;
  - set date exposure to 1% tracking size rather than full cash.

Reason for 1% instead of 0%:

- 0% fixed the June 2026 failure but reduced active capacity denominator, creating a tiny capacity full-fill rate regression.
- 1% keeps the economic result close to cash while preserving the active capacity denominator, so capacity metrics are not worse than the v3 baseline.

## Formal Artifacts

Full-history replay:

- Root: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_full713_20260708`
- Candidate run: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_full713_20260708/research_validation/walk_forward_model_candidate_runs/walk-forward-model-candidate-run-dc0ac67564031a15.json`
- Comparison report: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_full713_20260708/research_validation/model_comparison_reports/model-comparison-report-dc9ee5f34720c27f.json`

Recent replay:

- Root: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_recent_20260708`
- Candidate run: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_recent_20260708/research_validation/walk_forward_model_candidate_runs/walk-forward-model-candidate-run-a0e4ff4a776a8e92.json`
- Comparison report: `/private/tmp/stock_dashboard_v3_selected_exhaustion_date_scaled_1pct_recent_20260708/research_validation/model_comparison_reports/model-comparison-report-c937bbb09143ac74.json`

## Full-History Result

Window: 2023-09-07 to 2026-05-26

| Metric | v3 baseline | candidate | Status |
|---|---:|---:|---|
| evaluated dates | 653 | 653 | pass |
| mean net excess | 0.0349798612 | 0.0356102124 | pass |
| mean total return after cost | 0.0396109815 | 0.0399224255 | pass |
| positive date rate | 0.4594180704 | 0.4594180704 | pass |
| negative month count | 0 | 0 | pass |
| worst monthly mean net excess | 0.0008524690 | 0.0008524690 | pass |
| 3x cost-stress mean net excess | 0.0329798612 | 0.0335730161 | pass |
| deflated Sharpe confidence | 0.9999999997 | 0.9999999999 | pass |
| alpha t-stat | 7.8791938868 | 8.0454719069 | pass |
| walk-forward split count | 33 | 33 | pass |
| active capacity full-fill rate | 0.9967141292 | 0.9967141292 | pass |
| capacity p05 fill rate | 2.5605386951 | 2.5605386951 | pass |

Trigger count:

- 7 full-history dates hit `selected_exhaustion_medium_industry_pullback_date_scale`.

## Recent Result

Window represented by recent replay artifacts: 2026-04-08 to 2026-06-05.

| Metric | recent v3 baseline | candidate | Status |
|---|---:|---:|---|
| mean net excess | 0.1437790864 | 0.1559464307 | pass |
| negative month count | 1 | 0 | pass |
| June mean net excess | -0.0946339163 | 0.0027048377 | pass |
| June worst daily net excess | -0.2450413231 | -0.0846235108 | pass |

Recent trigger dates:

- 2026-06-02
- 2026-06-03
- 2026-06-04

## Failed Path Kept For Context

The earlier `exhaustion_aware_medium_industry_pullback_v3_top3_20d_v1` reranker improved June but failed full-history gates. The cause was not the exhaustion concept itself; it was replacement side effect:

- risky high-momentum names were penalized out of the top ranks;
- low-volatility, low-turnover defensive names filled the top ranks;
- the original v3 date/rank risk memory disappeared;
- 2025-11 became a negative month.

This is why the accepted candidate uses post-selection date exposure control instead of score-only reranking.

## Capacity Interpretation

The full-history comparison report still carries an existing configured capacity stress at 1,000,000 CNY. That number is a legacy production stress notional in the research governance report. It is not the intended real capital pool for this strategy iteration and must not be treated as the current business constraint.

For the current practical evaluation, the relevant capital pool is 200,000 CNY or lower. The correct blocker is therefore not "failed at 1,000,000 CNY"; the blocker is "the <=200,000 CNY execution-capacity contract has not yet been formally defined and replayed."

Execution contract:

- `docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_EXECUTION_CONTRACT_2026-07-08.md`
- machine-readable builder: `src/ashare_evidence/rolling_tranche_execution_contract.py`

Rolling account replay result:

- `docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_REPLAY_RESULT_2026-07-08.md`
- full-history output: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_full713_20260708.json`
- recent output: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260708.json`
- recent 2026-05-08+ output: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_20260708.json`

Execution-mode constraint:

- Monthly full-capital rotation is explicitly rejected. A rule that buys nearly the full <=200,000 CNY pool on one signal date and waits roughly 20 trading days before the next full rebalance is not an acceptable deployment path.
- Production promotion must use rolling tranche execution. The account replay must keep capital distributed across signal dates instead of concentrating the entire pool into one 20-trading-day sleeve.
- The original research replay evaluates each signal date independently, so it must not be interpreted as "the same 200,000 CNY cash can be fully redeployed every day."
- The rolling replay has now run, but production/dashboard promotion remains blocked until the execution layer reduces skipped-order drag without weakening drawdown, negative-month, and concentration metrics.

Capacity envelope:

- 120,000 CNY is fully fillable under current governance proxy.
- 200,000 CNY is not fully cleared by the current strict 5% ADV proxy because of the same three historical low-liquidity 603117.SH picks that also block the v3 baseline.
- 1,000,000 CNY remains blocked by the same historical low-liquidity picks as the baseline, but this stress size is outside the current practical scope.

Required next contract before production/dashboard projection:

- set the governed notional tier to <=200,000 CNY, not 1,000,000 CNY;
- enforce rolling tranche execution and reject monthly full-capital rotation;
- define whether low-liquidity picks are handled by single-stock notional cap, low-average-amount exclusion, staged execution, or partial-fill replay;
- rerun the full-history and recent replay under that <=200,000 CNY execution rule;
- keep the profitability and stability gates from this result unchanged.

This candidate is therefore a research candidate, not a production/dashboard projection candidate, until the <=200,000 CNY execution-capacity contract is defined and replayed.
