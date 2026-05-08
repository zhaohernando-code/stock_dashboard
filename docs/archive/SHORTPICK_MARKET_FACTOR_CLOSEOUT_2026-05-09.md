# Shortpick Market-Factor Closeout 2026-05-09

This note preserves the research conclusion behind the live Short Pick Lab strategy handoff.

## Decision

Live Short Pick Lab runs should keep LLM open-discovery picks as the control group, then attach two deterministic strategy groups after LLM consensus:

- Default: `momentum_10d_turnover_cooldown_rank`
- Offensive control: `momentum_10d_turnover_rank`

The default expands the momentum-volume pool to 40 names, then ranks by 10-day momentum plus turnover confirmation while subtracting a half-weight same-day chase penalty. The offensive control uses the same pool and ranks by 10-day momentum plus turnover without the chase penalty.

The strategy groups must not enter LLM consensus metrics. They are first-class candidates only so they can share the same 1/3/5/10/20 forward validation surface.

## Research Interpretation

Historical replay and market-only expansion showed that broad LLM filtering/distillation did not reliably improve the market-factor pool. The more defensible edge came from structured market features inside an expanded momentum pool, especially 10-day continuity and turnover confirmation.

The result is still regime-sensitive. The high-return 2026-03/04 replay window should not be treated as unconditional alpha. Regime diagnostics should keep tracking `universe_breadth10` and `pool_ret10_mean`; they are metadata for sizing/interpretation, not a default hard filter until larger samples justify it.

Hard industry diversification lowered concentration but also removed too much alpha in the tested sample. Keep it as risk diagnostics, not the default selector.

## Runtime Closeout

For runtime run `30` on `2026-05-08`, the existing research universe was refreshed to the run date and the live overlay was rebuilt:

- Eligible current market-factor symbols: `61`
- Inserted strategy candidates: `12`
- Default strategy candidates: `6`
- Offensive-control candidates: `6`
- Validation rows updated: `85` across parsed candidates

The market data sync is run only during Short Pick Lab run generation, not when opening the frontend. It commits per symbol to avoid holding a long SQLite write lock.

## Artifact Handling

The JSON outputs from `output/shortpick-market-factor-study*.json` and `output/shortpick-replay-factor-rank*.json` are meaningful research artifacts and are retained in compressed form at `output/shortpick-market-factor-research-20260509.tar.gz`. They document the sensitivity runs that produced the final strategy decision:

- 2025+ CSI300 and universe-equal-weight studies
- 2024+ expanded studies
- 2023-05-25+ long-sample studies
- limit-up sensitivity checks
- ret10+turnover and cooldown replay factor-rank outputs
- portfolio/regime diagnostics

No flash historical replay samples are treated as formal evidence. The formal historical replay sample is DeepSeek V4 Pro.
