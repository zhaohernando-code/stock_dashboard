# Shortpick Portfolio Long-Sample Backtest 2026-05-09

## Why This Was Added

The earlier Short Pick Lab replay evidence was concentrated in the 2026-03/04 market window. That window is useful for sealed LLM replay, but it is not broad enough to support a stable conclusion about a 5-day short-line investment process.

This long-sample pass separates two claims:

- Market-factor strategy robustness can be checked across the available daily-bar history.
- LLM sealed replay remains short-window evidence until enough historical LLM/source packets exist across multiple regimes.

## Run Artifacts

- Portfolio capital-deployment backtest: `output/shortpick-portfolio-backtest-long-sample-20260509.json`
- Market-factor study: `output/shortpick-market-factor-study-long-sample-20260509.json`

Both runs used the runtime database read-only and did not refresh market data or write shortpick candidates.

## Scope

- Window: 2023-04-13 to 2026-05-08.
- Effective signal coverage: 2023-05-25 to 2026-04-27 for the portfolio backtest.
- Coverage: 708 signal days, 734 trade days, 65 stock-like daily-bar series.
- Benchmark: universe equal-weight.
- Cost: 20 bps round trip.
- Entry/exit: signal day plus one trading day close entry, 5 trading-day close exit.
- Tradeability: one-price limit-up entry filter enabled.

## Main Readout

The longer sample weakens the prior short-window optimism.

For the default `10日动量换手降追高` selector:

- Daily rolling 5 x 10k mode: total return `+75.17%`, benchmark total return `+95.08%`, excess `-19.92%`, max drawdown `-57.15%`, 708 completed trades.
- Weekly concentrated 1 x 50k mode: total return `-4.87%`, benchmark total return `+95.08%`, excess `-99.95%`, max drawdown `-76.90%`, 130 completed trades.

The daily rolling mode is better than weekly concentration in this long sample, but the default selector still does not pass a strong "deploy real capital" bar because it underperforms the equal-weight market and carries large drawdown.

## Interpretation

The 2026 holdout remains favorable to `10日动量 + 换手` variants, but 2023 and 2024 are weak. This suggests the strategy is regime-sensitive rather than a stable unconditional edge.

The correct next step is not to tune harder on 2026. The next iteration should add explicit regime gating and risk throttling:

- Only activate aggressive momentum exposure when market breadth or pool continuity is favorable.
- Reduce or skip exposure in weak breadth / weak continuity regimes.
- Keep LLM as a risk and catalyst filter, not as the primary long-sample return proof until sealed replay samples cover more regimes.

## Current Decision

Do not promote the current shortpick default to a confident production strategy solely from 2026 replay performance.

Use `daily_rolling_5x10k` as the preferred test harness over weekly all-in concentration because it has more samples and less concentration risk, but require a regime-gated version before treating expected return as acceptable.

## Optimization Pass

A follow-up optimization added explicit market-state gates to the long-sample portfolio backtest:

- `市场转正后启用降追高`: use the default cooldown selector only when the tradable universe 10-day average return is non-negative.
- `市场转正且不过热时启用降追高`: additionally skip days where the expanded momentum pool's 1-day average return is above 8%.
- `强广度动量共振`: offensive control requiring universe 10-day breadth >= 55% and expanded momentum-pool 10-day average return >= 6%.

Optimized artifact: `output/shortpick-portfolio-backtest-optimized-long-sample-20260509.json`

Best long-sample result:

- Mode: `daily_rolling_5x10k`
- Strategy: `ret10_turnover_cooldown_market_positive_cooldown`
- Completed trades: `383`
- Total return: `+124.36%`
- Equal-weight benchmark return: `+95.08%`
- Excess return: `+29.27%`
- Max drawdown: `-34.41%`

This is a meaningful improvement over the ungated default (`+75.17%` total return, `-19.92%` excess, `-57.15%` max drawdown).

However, robustness is not perfect:

- 2023 still underperformed the equal-weight benchmark by `-16.47%`.
- 2024 was the main contributor, outperforming by `+49.61%`.
- 2025 underperformed by `-8.56%`.
- 2026 outperformed by `+5.66%`.

Updated interpretation: the optimized rule is good enough to become the next candidate strategy for paper tracking, but not good enough to call a final production edge. The next improvement should focus on reducing weak-year underperformance rather than chasing a higher full-sample return.

## Optimization Pass 2

A second pass tested whether the top-ranked name was too crowded. The stronger candidate was:

- Start from `10日动量 + 换手`.
- Use the second-ranked candidate rather than the first-ranked candidate.
- Keep the same market-positive / not-overheated gate.
- Add an 8% close-based stop loss during the 5-trading-day holding window.

Optimized v2 artifact: `output/shortpick-portfolio-backtest-optimized-v2-long-sample-20260509.json`

Best v2 long-sample result:

- Mode: `daily_rolling_5x10k`
- Strategy: `ret10_turnover_second_market_positive_cooldown_stop8`
- Completed trades: `385`
- Total return: `+157.73%`
- Equal-weight benchmark return: `+95.08%`
- Excess return: `+62.64%`
- Max drawdown: `-27.20%`
- Exit reasons: `96` close-stop-loss exits, `289` planned 5-day exits.
- Limit-down exit handling: `4` exits were blocked and delayed because one-price limit-down days are not treated as sellable.

This is a material improvement over both the original ungated default and the first gated strategy:

- Ungated default: `-19.92%` excess, `-57.15%` max drawdown.
- First gated default: `+29.27%` excess, `-34.41%` max drawdown.
- Second-pick + 8% stop: `+62.64%` excess, `-27.20%` max drawdown.

Residual weakness remains:

- 2023 excess: `-13.77%`
- 2024 excess: `+66.43%`
- 2025 excess: `-5.84%`
- 2026 excess: `+6.32%`

Updated decision: use this v2 rule as the leading paper-tracking candidate. The no-stop second-pick variant now has higher full-sample return after the limit-down execution fix, but its max drawdown remains above the 30% paper-tracking gate. The stop-loss variant is therefore kept as the leading risk-controlled candidate, not because it maximizes return. It still needs regime diagnostics and live observation before any real-money conclusion.

## Production Evidence Gate

The v2 artifact now embeds a production-evidence gate so the result is not interpreted only by full-sample return ranking.

Current status: `paper_tracking_candidate`

Passed checks:

- Long-sample trade count: `385` trades, threshold `180`.
- Positive total excess return: `+62.64%`, threshold `> 0`.
- Max drawdown control: `-27.20%`, threshold no worse than `-30%`.

Failed checks:

- Positive excess year rate: `50%` of years, threshold `75%`.
- Worst-year excess floor: `-13.77%`, threshold no worse than `-10%`.
- Conservative cost stress: at `100 bps`, excess return falls to `-7.35%`.
- Frozen forward tracking: `0` observed forward days, threshold `40`.

Cost stress:

- `20 bps`: total return `+157.73%`, excess `+62.64%`, max drawdown `-27.20%`.
- `50 bps`: total return `+133.67%`, excess `+38.58%`, max drawdown `-30.37%`.
- `100 bps`: total return `+87.73%`, excess `-7.35%`, max drawdown `-39.40%`.
- `150 bps`: total return `+23.22%`, excess `-71.86%`, max drawdown `-45.81%`.

External audit follow-up:

- Report: `output/external-reviews/shortpick-deepseek-claude-review-20260509.md`
- Action taken: added conservative one-price limit-down exit blocking, explicit multi-index references, and simple momentum control comparison into the backtest artifact.
- Multi-index references over overlapping trade days: HS300 `+32.22%` / max drawdown `-15.66%`, CSI500 `+53.66%` / max drawdown `-21.52%`, CSI1000 `+44.24%` / max drawdown `-31.35%`.

Decision: the current rule is appropriate for frozen paper tracking and frontend surfacing as the leading experimental strategy. It is not yet a production-proven strategy. The next proof step should freeze the rule, record at least 40 forward trading days without changing thresholds, and separately improve weak-year robustness or execution-cost tolerance before any real-money conclusion.
