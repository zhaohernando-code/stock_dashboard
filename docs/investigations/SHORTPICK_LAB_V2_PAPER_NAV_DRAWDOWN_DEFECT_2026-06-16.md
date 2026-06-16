# Shortpick Lab V2 Paper NAV Drawdown Defect Investigation

## rawProblem

User report on 2026-06-16:

> 在历史回测中。这两个策略的最大回撤在10%多一点，但在纸面验证里面已经超过20%了，查看一下是不是有什么问题

Follow-up instruction:

> 修复纸面追踪的计算问题

## normalizedProblem

`试验田v2 -> 纸面追踪` shows a drawdown-like paper curve that can exceed 20% for the fixed80/fixed85 strategies, while historical replay reports max drawdown about `-11.90%`. The paper chart is not using a comparable account NAV basis.

## expectedBehavior

- Paper tracking should display cumulative return and drawdown using an account-level NAV basis for each strategy, not single-trade stock returns compounded as if each trade used the full account.
- The visible chart should separate fixed85 and fixed80 as independent strategy curves.
- Historical replay drawdown and paper-tracking drawdown should be described as different windows but compatible account-level metrics.
- Replay-tagged rows remain research/paper display only and must not be presented as true-forward proof.

## actualBehavior

- `frontend/src/components/ShortpickLabV2View.tsx` currently maps table rows to `returnValue` from `return_text`, then does `cumulative *= 1 + row.returnValue`.
- That turns each single-stock exit return into a full-account return.
- The line also mixes both fixed85 and fixed80 rows into one series unless the user filters the table first.

## reproductionEvidence

Read-only runtime API checks on 2026-06-16:

- `/shortpick-lab-v2/historical-replay?sample_limit=0`
  - fixed85 `max_drawdown = -0.119033`
  - fixed80 `max_drawdown = -0.119033`
- `/shortpick-lab-v2/paper-tracking`
  - coverage `2026-05-08` to `2026-06-15`
  - `available=27`, `replay rows=54`, `true_forward=0`
  - completed exit rows: six per strategy

Computed from the served paper table rows:

| Strategy | Completed Trades | Current frontend-like full-trade compounding drawdown | Realized P/L on 200k account | Realized account return | Approx daily marked account drawdown |
|----------|------------------|--------------------------------------------------------|------------------------------|-------------------------|--------------------------------------|
| 8.5 万目标买入方案 | 6 | `-25.41%` | about `-16,889` | `-8.44%` | about `-17.65%` |
| 8 万目标买入方案 | 6 | `-25.41%` | about `-16,889` | `-8.44%` | about `-17.65%` |

The 2026-05-08 paper window does show a weak recent path, but the visible `>20%` result is inflated by the frontend calculation basis.

The two strategy rows are identical in this bounded paper window because 100-share board-lot rounding and the selected stock prices caused fixed80 and fixed85 to buy the same quantities for the completed trades. This short-window equality does not mean fixed80 and fixed85 are generally equivalent; the three-year historical replay still has separate trade counts and returns.

## directCause

Confirmed direct defect:

- `PaperReturnCharts` in `frontend/src/components/ShortpickLabV2View.tsx` computes cumulative values from `return_text` only.
- `return_text` is a single trade stock return, not account return.
- The chart does not account for initial cash, actual cost, cash balance, overlapping holdings, position market value, or per-strategy separation.

Secondary display issue:

- The chart title `累计纸面收益` implies an account-like cumulative paper result, but the implementation is single-trade compounding.

## rootCauseChain

1. Previous closeout added exit/return visibility quickly to satisfy v1-like paper display parity.
2. The plan/review gates verified chart presence and raw-key readability, but did not require account NAV semantics.
3. Tests checked table row exit fields but not whether the chart matched account-level accounting.
4. Runtime served verifier required visible chart labels but did not validate the chart data basis.

## missedInterceptors

- Requirement intake missed the distinction between single-trade return chart and account NAV chart.
- Code review did not reject `cumulative *= 1 + row.returnValue` as a portfolio-account calculation.
- Test design lacked a fixture where two losing trades would make single-trade compounding diverge from account P/L.
- Runtime verifier checked visible text, not semantic chart data.

## downstreamImpactScan

Checked areas:

- `frontend/src/components/ShortpickLabV2View.tsx`: affected chart computation.
- `src/ashare_evidence/shortpick_v2_read_model.py`: already exposes numeric `cash_before`, `cash_after`, `quantity`, `return`, `entry_date`, and `exit_date`; backend does not currently expose NAV series.
- `tests/test_shortpick_v2_read_model_api.py`: tests exit/return projection but not account NAV.
- `scripts/verify-shortpick-v2-paper-tracking-display-runtime.sh`: verifies chart text and API shape but not NAV semantics.

Findings:

- Historical replay readout is not the source of the >20% display.
- Backend single-trade return projection appears reasonable for row-level trade detail.
- The user-visible chart should stop computing cumulative account-like results from row-level `return_text`.

Scan limitations:

- This investigation did not rerun a full historical backtest.
- The daily marked-account drawdown estimate uses runtime daily closes and served paper rows, not a persisted official NAV ledger.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Replaced frontend single-trade compounding with backend account-basis strategy curves sourced from `paper_display.account_curves`. | Tests prove account NAV differs from full-trade compounding; runtime verifier checks account curves after publish. |
| process_gap | fixed | Added regression tests and verifier assertions that prevent account charts from reverting to row-level return compounding. | Unit tests cover completed-trade and open-position drawdown paths; verifier computes the old full-trade compounding drawdown and fails if the account curve matches it. |
| downstream_impact | fixed | Updated served verifier to require account/NAV wording and account curve data, and to keep raw-key display checks. | Runtime verifier must pass against the served route before closeout. |

## confidence

High. The offending frontend code is direct and the runtime reproduction explains the discrepancy numerically. The identical fixed80/fixed85 short-window paper numbers are understood as a board-lot rounding artifact for the current completed rows, not as a sign that the investigation mixed the strategies.

## openQuestions

- None blocking. Marked-to-market daily NAV is implemented when daily closes are available; if future true-forward rows exist, the backend attempts a combined replay + true-forward account curve and labels the scope in coverage.
