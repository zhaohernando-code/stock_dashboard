# Shortpick v3 Goal Exploration Round

Status: no promoted control candidate
Created: 2026-07-09

## Goal Gate

Find a v3 side-by-side control candidate that is clearly better than the current main strategy on at least one important metric while preserving the core goal: stable profitability.

Current main baseline:

| Metric | Baseline |
|---|---:|
| Total return | 311.92% |
| Annualized return | 65.77% |
| Max drawdown | -7.76% |
| Negative months | 4 |
| Skipped order rate | 35.23% |
| Max single-symbol exposure | 26.76% |

Promotion rule for this round: a candidate must show a material advantage on at least one important metric and must not show obvious degradation in total return, annualized return, max drawdown, negative months, skipped order rate, or single-symbol exposure.

## Direction 1: Market-State And Liquidity Scaling

Artifact:

- `/tmp/stock_dashboard_v3_market_state_scale_scan_20260709.json`

Scanned signal-day-only rules:

- scale all picks or Rank1 picks when benchmark 20-day return is weak
- scale low-turnover Rank1 picks under weak benchmark conditions
- scale industry-overheated pullback picks
- scale hot-benchmark pullback Rank1 picks

Result:

| Best observed profile | Advantage | Degradation | Decision |
|---|---|---|---|
| `all_benchmark_lt_-0.01_scale_0.70` | max drawdown improves from `-7.76%` to `-6.40%`; max single-symbol exposure improves from `26.76%` to `23.27%` | total return drops from `311.92%` to `280.10%`; skipped order rate worsens from `35.23%` to `38.91%` | rejected |
| hot-benchmark pullback Rank1 filters | max drawdown improves into roughly `-7.18%` to `-7.58%` range | total return drops materially, often below `300%` | rejected |

Interpretation: market-state scaling can reduce risk, but in this strategy the return cost is too high. It is not a valid side-by-side control under the current gate.

## Direction 2: Tranche Count And Minimum Order Grid

Artifact:

- `/tmp/stock_dashboard_v3_tranche_min_order_scan_20260709.json`

Scanned:

- target active tranche count from `10` to `21`
- minimum order notional from `1,500` to `3,000 CNY`
- same model, same Rank1/Rank3 layered exit policy

Result:

| Candidate profile | Advantage | Degradation | Decision |
|---|---|---|---|
| 11-tranche, min order 2,500-3,000 | total return rises to about `395%`; negative months improve from `4` to `3` | max drawdown worsens to about `-8.55%` to `-8.63%`; skipped order rate worsens to `39%`-`40%`; max single-symbol exposure rises to `33.92%` | rejected |
| 18-tranche variants | max drawdown improves to about `-6.38%`; max single-symbol exposure falls to about `25%` | total return drops to about `220%`; skipped order rate worsens | rejected |
| 14-tranche min order 2,500-3,000 | total return improves only slightly | skipped order rate worsens materially, and some variants slightly worsen drawdown | rejected |

Interpretation: tranche count is a strong risk/return lever but not a clean control candidate. Fewer tranches become too concentrated; more tranches become too low-return.

## Round Decision

No candidate is promoted from this round.

The most informative rejected directions are:

- risk scaling can improve drawdown, but current simple rules sacrifice too much return
- 11-tranche variants prove the model can produce higher return and fewer negative months, but concentration and drawdown become unacceptable

Next useful direction: search for an ex-ante way to keep the 11-tranche return uplift while controlling concentration and drawdown, for example by combining aggressive tranche sizing only on high-confidence / low-crowding signal days with the default 14-tranche mode elsewhere.
