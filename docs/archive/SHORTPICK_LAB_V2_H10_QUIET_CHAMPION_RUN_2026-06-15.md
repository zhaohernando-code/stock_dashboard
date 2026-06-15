# Short Pick Lab V2 H10 Quiet Champion Run 2026-06-15

## Scope

- Runtime DB: `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`
- Replay artifact: `output/shortpick-v2-h10-quiet-champion-replay-artifact.json`
- Selection artifact: `output/shortpick-v2-h10-quiet-champion-selection-artifact.json`
- Candidate batch: `h10_quiet_champion`
- Horizon: 10 trading days
- Initial cash: 200000
- Entry: `next_close`
- Signal days: 721
- Result rows: 35

## Durable Benchmark

The mandatory comparison benchmark remains:

| Role | Config | Total Return | Annualized | Market Excess | Max Drawdown | Trades | Skip | Turnover |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| champion | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | +271.23% | +53.96% | +229.39% | -11.90% | 190 | 73.65% | 76.67 |
| capital shadow | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1` | +257.25% | +52.03% | +215.40% | -11.90% | 192 | 73.37% | 73.02 |

`benchmark_configs` in the selection artifact explicitly carries these two rows. Later strategy-search rounds must compare against these rows before claiming replacement.

## First Narrow-Grid Readout

Risk-first selection picked smaller notional variants, not a benchmark replacement:

| Role | Config | Total Return | Annualized | Market Excess | Max Drawdown | Trades | Skip | Turnover |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| selected | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_70k_top5_h10_v1` | +223.03% | +47.07% | +181.18% | -11.44% | 192 | 73.37% | 65.01 |
| selected | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_75k_top5_h10_v1` | +241.87% | +49.84% | +200.03% | -11.83% | 193 | 73.23% | 69.19 |

Initial interpretation:

- The original `poolhot10_mtw` family reproduces the known strong line and remains the only main direction.
- 70k/75k improve drawdown and turnover but trail fixed85 materially on annualized return, so they are risk variants, not replacements.
- 90k produced the highest total return in this batch (`+284.35%`) with the same max drawdown (`-11.90%`), but failed the current turnover gate by a small margin (`80.29 > 80.0`). It should be treated as a diagnostic candidate, not promoted without a deliberate turnover-gate decision.
- `poolhot09` increased trade coverage but drawdown deteriorated to about `-27%`; this supports not relaxing pool-hot to chase lower skip.
- `poolhot11` and `poolhot12` produced zero trades in this dataset; tightening the pool-hot threshold above 0.10 is not useful under current reconstruction.
- `MT` and `TW` weekday tightening stayed profitable but failed the 180-trade minimum, so they are not benchmark replacements.

## Current Decision

Keep fixed85 and fixed80 as mandatory benchmark rows. Continue only with quiet champion local sensitivity checks; do not reopen broad ma-accel, dynamic-exit, entry-quality, rank2-to-6, breadth65, or weekday-relaxation directions unless a future same-window replay explicitly beats the benchmark.
