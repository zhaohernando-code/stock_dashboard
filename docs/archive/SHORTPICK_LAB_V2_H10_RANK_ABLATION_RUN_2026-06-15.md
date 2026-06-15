# Short Pick Lab V2 H10 Rank Ablation Run - 2026-06-15

Acceptance marker: Rank2 status; no paper-tracking promotion; rank1/rank2/rank3.

## Scope

This document records the 2026-06-15 fixed-H10 rank-ablation run for the current quiet benchmark line:

- Baseline source: `quiet_breakout_rank2_poolhot10_mtw`
- Primary benchmark config: `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`
- Mandatory comparison ranks: rank1/rank2/rank3
- Diagnostic ranks: rank4/rank5
- Informational notional context: fixed80 and fixed90
- Artifact: `output/shortpick-v2-h10-rank-ablation-artifact.json`
- Artifact id: `shortpick_v2_h10_rank_ablation:2023-05-16:2026-05-08:20260615`
- Validation: `53` checks passed, `0` failed

H10 remains fixed in this run. The artifact uses the same MTW weekday gate, poolhot10 threshold, fallback-or-skip action model, and 200k initial cash context as the current quiet benchmark validation line.

## Governance Position

This is historical same-window research evidence only. It does not start paper tracking, replace the benchmark, change runtime behavior, authorize fixed90 execution, or publish any live-facing change.

Rank2 status is `supported` for this bounded test because fixed85 rank2 beat the mandatory same-gate rank1 and rank3 comparators by more than the configured `0.03` total-return threshold, while also having materially better drawdown in this sample.

## Decision Policy

| Policy field | Value |
|--------------|-------|
| Minimum sample count | `50` trades per mandatory primary row |
| Minimum period blocks | `3` calendar-year blocks |
| Total-return delta threshold | `0.03` |
| Max drawdown deterioration threshold | `0.03` |
| Claim ceiling | `research_observation` |
| Promotion status | `not_eligible` |

The validator confirmed the mandatory rows had enough coverage: rank1/rank2/rank3 each had at least `175` trades and `4` period blocks.

## Primary Rank Evidence

All rows below use fixed85, H10, MTW, poolhot10, and the same fallback-or-skip action vocabulary.

| Rank | Config | Total return | Market excess | Max drawdown | Trades | Skip ratio | Status |
|------|--------|--------------|---------------|--------------|--------|------------|--------|
| rank1 | `quiet_breakout_rank1_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | `+60.74%` | `+18.90%` | `-25.48%` | `175` | `75.73%` | inconclusive comparator |
| rank2 | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | `+271.23%` | `+229.38%` | `-11.90%` | `190` | `73.65%` | supported baseline |
| rank3 | `quiet_breakout_rank3_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | `+50.80%` | `+8.95%` | `-28.05%` | `177` | `75.45%` | inconclusive comparator |

The mandatory comparison is decisive in this sample: rank2 outperformed rank1 by about `210.49 pp` of total return and rank3 by about `220.43 pp`, with a much smaller maximum drawdown than both.

## Diagnostic Rows

Rank4 and rank5 were included only as diagnostic rows. They do not affect the rank2 support decision.

| Rank | Total return | Max drawdown | Trades | Status |
|------|--------------|--------------|--------|--------|
| rank4 | `+69.47%` | `-29.85%` | `174` | diagnostic only |
| rank5 | `+53.39%` | `-19.02%` | `177` | diagnostic only |

Fixed80 and fixed90 rows are informational execution-pressure context only. They cannot override the fixed85 rank decision. The fixed90 rank2 row again had higher headline return, but the existing governance boundary still treats fixed90 as diagnostic because of turnover pressure.

## Interpretation

This run closes the prior parameter-significance gap that marked rank2 as inconclusive due to missing direct rank1/rank3 same-gate ablations. Under the current gate, rank2 is not just the historical champion label; it directly beats the neighboring mandatory ranks under the same H10 setup.

The result supports continuing to use `quiet_breakout_rank2_poolhot10_mtw` as the current research benchmark anchor. It does not prove a causal rank effect, and it does not remove the need for separate robustness, concentration, and future true-forward checks before any paper-tracking decision.

## Non-Promotion Statement

No paper-tracking promotion is made by this document. No benchmark replacement is made. No runtime publish is required. No database refresh or write was performed for this run.
