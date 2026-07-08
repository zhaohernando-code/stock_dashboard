# Shortpick v3 Rolling Tranche Replay Result

Status: candidate gate passed for research replay; production promotion still requires governed handoff
Created: 2026-07-08
Model candidate: `selected_exhaustion_date_scaled_v3_top3_20d_v1`
Execution contract: `docs/contracts/SHORTPICK_V3_ROLLING_TRANCHE_EXECUTION_CONTRACT_2026-07-08.md`

## Valid Artifacts

All valid artifacts use the runtime DB:

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`

Current accepted replay overlays:

- practical cash account: `200,000 CNY`
- primary rolling mode: `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1`
- primary minimum order notional: `2,250 CNY`
- budget mode: current NAV fraction, so gains are redeployed instead of permanently sizing from initial cash
- rank3 gate: `benchmark_return_20d <= 0.03 -> rank3 position scale 0`
- accepted exit overlay: Rank1 early quick-spike failure plus Rank3 entry-pullback late-loss guard before mechanical 20-trading-day exit
- open-ended recent positions: if a signal has not reached its planned 20-trading-day exit by the last available bar, keep the position open and mark to market instead of skipping the order.

Generated artifacts:

- Full history: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_full713_runtime_compound_rank3_gate_20260708.json`
- Recent full paper-tracking artifact window: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_runtime_compound_rank3_gate_20260708.json`
- Recent 2026-05-08+ concern window: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_runtime_compound_rank3_gate_20260708.json`
- Full history with accepted Rank3 pullback exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_full713_rank3_pullback_exit_rank3_gate_20260708.json`
- Recent with accepted Rank3 pullback exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_rank3_pullback_exit_rank3_gate_20260708.json`
- Recent 2026-05-08+ with accepted Rank3 pullback exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_rank3_pullback_exit_rank3_gate_20260708.json`
- Full history with accepted layered exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_full713_layered_exit_rank3_gate_20260708.json`
- Recent with accepted layered exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_layered_exit_rank3_gate_20260708.json`
- Recent 2026-05-08+ with accepted layered exit: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_layered_exit_rank3_gate_20260708.json`

Superseded artifacts using `/private/tmp/ashare_hot_with_dashboard_hs300_backfill_20260708.db` are invalid for this decision because that DB missed historical bars for some selected symbols and could map old signals to much later entry bars.

## Current Baseline And Control

Formal baseline for the next optimization pass:

- config: `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1`
- capital pool: `200,000 CNY`
- entry mode: daily rolling, 14 target active tranches
- sizing mode: current NAV fraction, so profits are reinvested
- minimum order notional: `2,250 CNY`
- rank3 gate: `benchmark_return_20d <= 0.03 -> rank3 target allocation 0`
- exit overlay: Rank1 early quick-spike failure plus Rank3 entry-pullback confirmed late-loss guard
- full-history total return: `298.92%`
- full-history annualized return: `63.96%`
- full-history max drawdown: `-7.81%`
- full-history negative months: `4`
- full-history skipped order rate: `36.12%`

Control group:

- config: `daily_15_tranche_rank_weighted_compound_min1000_v1`
- role: lower-concentration control, not the return baseline
- full-history total return: `275.41%`
- full-history annualized return: `60.44%`
- full-history max drawdown: `-7.91%`
- full-history negative months: `5`
- full-history skipped order rate: `21.79%`

New challengers must not weaken the 14-tranche baseline on total return, annualized return, max drawdown, negative-month count, or skipped order rate. The 15-tranche control is used to judge whether a challenger is merely reducing concentration by giving up too much return.

## Full-History Result

Signal window: 2023-09-07 to 2026-05-26.

| Replay | Total return | Annualized return | Max drawdown | Negative months | Skipped order rate | Skipped signal rate | Buy orders | Max single-symbol exposure |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Static two-day baseline, 5,000 min order, no rank3 gate | 110.23% | ~31% | -5.45% | 6 | 53.10% | 24.80% | 212 | 25.71% |
| Static two-day + rank3 gate, 4,000 min order | 110.69% | ~31% | -5.42% | 5 | 47.34% | 24.39% | 228 | 25.71% |
| Previous 14-tranche compound, 2,500 min order + rank3 gate, mechanical 20d | 290.88% | 62.78% | -7.81% | 5 | 38.07% | 24.85% | 540 | 26.76% |
| Accepted 14-tranche compound, 2,250 min order + rank3 gate + Rank3 pullback late-loss exit | 293.87% | 63.22% | -7.81% | 4 | 35.89% | 24.85% | 559 | 26.76% |
| Accepted layered 14-tranche compound, 2,250 min order + Rank1 quick-fail + Rank3 pullback late-loss exit | 298.92% | 63.96% | -7.81% | 4 | 36.12% | 25.05% | 557 | 26.76% |
| Daily 15-tranche compound, 1,000 min order + rank3 gate | 275.41% | 60.44% | -7.91% | 5 | 21.79% | 22.00% | 682 | 25.31% |

Decision: the current high-return research frontier is the accepted layered 14-tranche compound candidate with `2,250 CNY` minimum order, Rank1 quick-spike failure exit, and Rank3 pullback late-loss exit. It improves total return, annualized return, negative-month count, and skipped-order rate versus the previous 14-tranche mechanical-exit baseline while keeping max drawdown and concentration unchanged. The daily 15-tranche compound candidate remains the lower-concentration control if the 14-tranche single-symbol exposure is considered too high.

## Dynamic Exit Challenger Result

Follow-up sell-policy experiments reused the same 200,000 CNY rolling account, the same selected picks, and the same rank3 gate. They only changed the exit policy.

Generated artifacts:

- Full history with dynamic-exit challengers: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_full713_dynamic_exit_rank3_gate_20260708.json`
- Recent dynamic-exit window: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_dynamic_exit_rank3_gate_20260708.json`
- Recent 2026-05-08+ dynamic-exit window: `/private/tmp/stock_dashboard_v3_rolling_account_replay_20w_recent_20260508_dynamic_exit_rank3_gate_20260708.json`

Full-history readout:

| Replay | Total return | Annualized return | Max drawdown | Negative months | Skipped order rate | Buy orders | Sell policy result |
|---|---:|---:|---:|---:|---:|---:|---|
| 14-tranche baseline, mechanical 20d | 290.88% | 62.78% | -7.81% | 5 | 38.07% | 540 | previous baseline |
| 14-tranche profit guard + quick fail + trend break | 186.75% | 45.72% | -8.19% | 8 | 40.71% | 517 | rejected: return, drawdown, negative months all worse |
| 14-tranche 12% loss guard | 269.42% | 59.52% | -7.76% | 6 | 39.79% | 525 | rejected: return lower and negative months worse |
| 14-tranche late trend loss guard | 257.38% | 57.65% | -7.76% | 4 | 40.02% | 523 | rejected: fewer negative months but return materially lower |
| 14-tranche Rank2/3 late trend loss guard | 280.67% | 61.24% | -7.80% | 5 | 38.30% | 538 | rejected: closest challenger, but still below return baseline |
| 14-tranche Rank3 pullback late trend loss guard, 2,500 min order | 295.65% | 63.48% | -7.81% | 4 | 38.30% | 538 | near pass: return/stability improved, skipped-order rate slightly worse |
| 14-tranche Rank3 pullback late trend loss guard, 2,250 min order | 293.87% | 63.22% | -7.81% | 4 | 35.89% | 559 | accepted: improves return, negative months, and skipped-order rate |
| 14-tranche layered Rank1 quick-fail + Rank3 pullback late-loss guard, 2,250 min order | 298.92% | 63.96% | -7.81% | 4 | 36.12% | 557 | accepted: improves return and recent drawdown while keeping skipped-order rate below old baseline |
| 15-tranche control, mechanical 20d | 275.41% | 60.44% | -7.91% | 5 | 21.79% | 682 | control group |
| 15-tranche Rank2/3 late trend loss guard | 265.10% | 58.85% | -7.91% | 5 | 21.90% | 681 | rejected: lower return without stability improvement |

Mechanism readout:

- Broad dynamic exits are harmful because they sell too many positions that later recover inside the original 20-trading-day window.
- The all-rank late trend loss guard reduced negative months from `5` to `4`, but gave up about `33.50 percentage points` of total return.
- The Rank2/3-only late trend loss guard preserved most of the baseline behavior and was the closest challenger, but it still gave up about `10.20 percentage points` of total return without improving negative months or drawdown enough.
- Current evidence supports only narrow layered exits: Rank1 early quick-spike failure and Rank3 positions that were already below their 20-day high at entry and later confirm a late trend loss. Broad price-action-only dynamic exits remain rejected.
- Industry-crowding and weak-market broad exits were scanned but rejected as direct rules because applying them to Rank1/Rank2 frequently exits positions before the original 20-day recovery. They remain research risk descriptors, not accepted executable exits.

## Recent Result

Signal window: 2026-04-08 to 2026-06-05.

| Replay | Total return | Max drawdown | Negative months | Skipped order rate | Skipped signal rate | Buy orders | Max single-symbol exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| Static two-day + rank3 gate, 4,000 min order | 18.14% | -2.58% | 0 | 35.71% | 20.00% | 18 | 14.42% |
| Previous 14-tranche compound, 2,500 min order + rank3 gate, mechanical 20d | 45.18% | -2.22% | 0 | 40.35% | 16.67% | 34 | 23.79% |
| Accepted 14-tranche compound, 2,250 min order + rank3 gate + Rank3 pullback late-loss exit | 45.45% | -2.22% | 0 | 40.35% | 16.67% | 34 | 23.77% |
| Accepted layered 14-tranche compound, 2,250 min order + Rank1 quick-fail + Rank3 pullback late-loss exit | 46.39% | -1.75% | 0 | 40.35% | 16.67% | 34 | 23.60% |
| Daily 15-tranche compound, 1,000 min order + rank3 gate | 40.75% | -2.09% | 0 | 31.58% | 16.67% | 39 | 20.93% |

Decision: both compound candidates improve recent return and drawdown versus the static two-day candidate while keeping skipped order rate below 50%.

## Recent 2026-05-08+ Result

The filtered signal window starts at 2026-05-11 because the candidate artifact has no selected signal on 2026-05-08.

| Replay | Total return | Max drawdown | Negative months | Skipped order rate | Skipped signal rate | Buy orders | Max single-symbol exposure |
|---|---:|---:|---:|---:|---:|---:|---:|
| Static two-day + rank3 gate, 4,000 min order | 13.90% | -2.69% | 1 | 41.18% | 30.00% | 10 | 14.97% |
| Previous 14-tranche compound, 2,500 min order + rank3 gate, mechanical 20d | 30.63% | -2.21% | 0 | 44.44% | 25.00% | 20 | 22.62% |
| Accepted 14-tranche compound, 2,250 min order + rank3 gate + Rank3 pullback late-loss exit | 30.90% | -2.21% | 0 | 44.44% | 25.00% | 20 | 22.59% |
| Accepted layered 14-tranche compound, 2,250 min order + Rank1 quick-fail + Rank3 pullback late-loss exit | 31.76% | -1.73% | 0 | 44.44% | 25.00% | 20 | 22.44% |
| Daily 15-tranche compound, 1,000 min order + rank3 gate | 30.31% | -2.12% | 0 | 36.11% | 25.00% | 23 | 22.65% |

Decision: the 2026-05-08+ concern window no longer shows the prior June weakness under either compound candidate. The daily 14 candidate has slightly higher return; the daily 15 candidate has lower skipped-order rate and slightly shallower drawdown.

## Mechanism Finding

The 3,000 min-order replay initially reduced skipped orders but introduced an extra negative month. Order-ledger attribution showed the incremental orders were all rank3. Those rank3 orders had slightly positive average PnL but low win rate and included several high-momentum, high-amount exhaustion failures.

The accepted gate therefore only affects rank3 tail exposure:

- rank1 has one accepted early quick-spike failure exit: peak gain at least 6% within 8 calendar days, then fallback to -2% or worse;
- rank2 exit behavior remains unchanged under the accepted overlay;
- rank3 is allowed only when broad 20-day benchmark momentum is stronger than 3%;
- rank3 is set to zero exposure when `benchmark_return_20d <= 0.03`;
- accepted Rank3 dynamic exit additionally requires entry-time pullback from 20-day high and a later confirmed loss trend;
- zero target allocations are recorded as `no_order`, not execution skips.

## Completion State

| Item | Status |
|---|---|
| Runtime DB replay rerun | completed |
| Invalid hot DB artifacts marked superseded | completed |
| 20w rolling cash account replay | completed |
| Missing-exit recent positions held open and marked to market | completed |
| Skipped order rate below 50% in full-history and recent windows | completed |
| Full-history annualized return restored above 60% | completed |
| Production/dashboard promotion | blocked pending governed review and live handoff |
