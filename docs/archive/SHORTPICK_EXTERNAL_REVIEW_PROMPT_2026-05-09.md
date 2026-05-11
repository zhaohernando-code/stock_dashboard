# Short Pick Lab External Review Prompt

You are Claude Code running on DeepSeek v4 Pro, acting as an independent senior quant/research auditor. The repository is the current working tree and includes uncommitted changes. Your job is to review the current Short Pick Lab strategy research from a professional, skeptical perspective. Do not modify source code, do not refresh market data, do not start servers, and do not write to the runtime database.

Context:

- Project: A-share stock dashboard Short Pick Lab.
- User goal: evaluate whether a 5-trading-day short-line speculative stock selection process can produce a reliable positive expectation.
- Current leading paper strategy: daily rolling capital deployment, buy one selected stock per signal day with 10k sleeve, hold about 5 trading days, using the second-ranked 10-day momentum + turnover candidate when the market is positive and the expanded momentum pool is not overheated, with an 8% close-based stop loss.
- Current long-sample result from `output/shortpick-portfolio-backtest-optimized-v2-long-sample-20260509.json`:
  - sample window: 2023-04-13 to 2026-05-08
  - effective signal coverage: 2023-05-25 to 2026-04-27
  - signal days: 708
  - trade days: 734
  - stock-like daily-bar series: 65
  - benchmark: universe equal-weight
  - default transaction cost: 20 bps
  - leading strategy trade count: 385
  - total return: +162.07%
  - benchmark return: +95.08%
  - excess return: +66.98%
  - max drawdown: -27.26%
  - production evidence status: `paper_tracking_candidate`
  - failed checks: positive excess year rate, worst-year excess floor, 100 bps cost stress, frozen forward tracking
  - yearly excess: 2023 -13.77%, 2024 +66.43%, 2025 -5.84%, 2026 +6.32%
  - cost stress: 20 bps +66.98% excess, 50 bps +43.10% excess, 100 bps -3.00% excess, 150 bps -62.44% excess

Files to inspect:

- `src/ashare_evidence/shortpick_portfolio_backtest.py`
- `tests/test_shortpick_portfolio_backtest.py`
- `src/ashare_evidence/shortpick_market_factor_study.py`
- `src/ashare_evidence/shortpick_replay.py` only as needed for LLM replay context
- `docs/archive/SHORTPICK_PORTFOLIO_LONG_SAMPLE_2026-05-09.md`
- `output/shortpick-portfolio-backtest-optimized-v2-long-sample-20260509.json`
- `output/shortpick-market-factor-study-long-sample-20260509.json`
- current `git status` and relevant diffs

Your tasks:

1. Inspect the current code, uncommitted diff, tests, docs, and output artifacts.
2. Build an independent audit packet in your own working memory: strategy definition, assumptions, code/diff summary, key metrics, failed production gates, and the specific questions below.
3. Return one Markdown report in Chinese.

Questions to answer:

- Does the current result look like a real edge, a regime-specific effect, or likely overfitting?
- What are the highest-risk methodological problems in the current backtest?
- Is the universe equal-weight benchmark sufficient, or should another benchmark/control be added?
- Is the 65-stock universe too narrow to support the conclusion?
- Is the second-candidate + 8% stop-loss optimization defensible or suspiciously tuned?
- What should be changed before frontend/paper tracking?
- What should not be changed because it would increase overfitting?
- What exact next experiment would most improve confidence?

Output report structure:

1. `结论摘要`: direct verdict.
2. `DeepSeek v4 Pro 独立审计`: findings from your inspection.
3. `是否应调整当前策略`: answer yes/no/partial, with rationale.
4. `建议落地项`: split into `现在应做`, `纸面跟踪期间做`, `暂时不要做`.
5. `需要用户知道的风险`: concise and concrete.

Important:

- Do not claim production readiness.
- Do not recommend another round of full-sample parameter tuning as the main solution.
- Prefer validation design changes over cosmetic metric optimization.
- Treat the current uncommitted working tree as the code under review.
