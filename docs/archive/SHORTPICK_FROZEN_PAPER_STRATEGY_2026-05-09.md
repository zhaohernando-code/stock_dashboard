# Short Pick Lab Frozen Paper Strategy 2026-05-09

## Frozen Rule

Status: frozen for paper tracking. Revised before the first post-freeze sample on 2026-05-09 to monitor four exit tracks side by side.

- Version: `shortpick-v3-exit-tracks-2026-05-09`
- Capital plan: daily rolling sleeves, 10k per signal, initial paper capital 50k.
- Entry: signal day plus one trading day close.
- Primary selection: from the expanded momentum pool, rank by 10-day momentum plus turnover, then choose the second candidate.
- Activation gate: tradable universe 10-day average return >= 0 and expanded momentum pool 1-day average return <= 8%.
- Exit monitoring, all counted by trading days:
  - mechanical 5 trading-day close exit;
  - mechanical 10 trading-day close exit;
  - conditional 5-to-10 trading-day check window: hold at least 5 trading days, then close exit if trend weakens, peak giveback is too large, or close-based loss reaches 8%;
  - 10% take-profit: if daily high touches +10% within the first 10 trading days, paper exit at +10%; otherwise day-10 close.
- Execution realism: one-price limit-up entries are not treated as buyable; one-price limit-down exits are not treated as sellable.
- Forward proof: at least 40 real forward trading days before reassessing production readiness.

## Current Evidence

Long-sample artifact: `output/shortpick-portfolio-backtest-optimized-v2-long-sample-20260509.json`

- Sample: 2023-05-25 to 2026-04-27 effective signal window.
- Trades: 385.
- Total return: +157.73%.
- Equal-weight market benchmark: +95.08%.
- Excess return: +62.64%.
- Max drawdown: -27.20%.
- Limit-down blocked exits: 4.
- Cost stress at 100 bps: -7.35% excess.

## Decision

This rule is allowed to run as the Short Pick Lab paper-tracking strategy. It is not production-proven and must not be adjusted during the first 40 real forward trading days. The 2026-05-09 v3 change happened before the first post-freeze sample, so it does not contaminate forward tracking. LLM free-form stock picking remains as a control group, not as the production strategy.
