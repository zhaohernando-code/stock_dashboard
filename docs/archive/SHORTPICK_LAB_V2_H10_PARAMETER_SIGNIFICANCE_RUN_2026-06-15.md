# Short Pick Lab V2 H10 Parameter Significance Run - 2026-06-15

Classification anchor: supported parameters; inconclusive parameters; rejected parameters.

## Scope

This document records the 2026-06-15 fixed-H10 parameter-significance run for the current quiet benchmark line:

- Primary benchmark: `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`
- Capital-shadow benchmark: `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1`
- Diagnostic boundary: `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1`
- Artifact: `output/shortpick-v2-h10-parameter-significance-artifact.json`
- Artifact id: `shortpick_v2_h10_parameter_significance:2023-05-16:2026-05-08:20260615`
- Validation: `63` checks passed, `0` failed

H10 is fixed in this run. The prior v1 horizon result is treated as a scope boundary, so this run does not retest 1, 3, 5, or 20 trading-day holding periods.

## Governance Position

This is historical research evidence only. It does not promote paper tracking, change the benchmark strategy, change runtime behavior, or authorize 90k execution. Supported labels mean the parameter survived this bounded same-window evidence check; they do not prove causality.

## Supported Parameters

| Parameter | Evidence basis | Evidence summary | Governance outcome |
|-----------|----------------|------------------|--------------------|
| MTW weekday gate versus MT/TW controls | statistical | Fixed85 MTW total return `+271.23%`, trade count `190`, max drawdown `-11.90%`; MT control `+200.39%`, trade count `141`; TW control `+161.98%`, trade count `145`. | Keep MTW as the benchmark gate for now. Do not describe it as a causal weekday effect. |
| Pool-hot threshold 0.10 versus 0.09/0.11/0.12 | statistical | Fixed85 poolhot10 total return `+271.23%`; poolhot09 `+158.48%` with wider drawdown `-27.22%`; poolhot11 and poolhot12 produced no trades in this window. The no-trade controls are coverage-poor controls, not rejected strategies. | Keep 0.10 as the current threshold. Do not promote nearby thresholds from this run. |
| Fixed notional 85k versus 80k | mixed | Fixed85 total return `+271.23%`, trade count `190`, turnover `76.67`; fixed80 total return `+257.25%`, trade count `192`, turnover `73.02`; both summaries independently report max drawdown `-11.90%` in the artifact. | Keep fixed85 as the primary benchmark and fixed80 as the capital-shadow control. |
| Fallback-or-skip action model with no delayed buy | logical | Allowed actions are `buy_primary`, `buy_fallback`, `skip`; delayed buy is absent; real run had `531` skips and `0` fallback buys for the benchmark. | Keep the action vocabulary. The no-delayed-buy rule remains required. |

## Inconclusive Parameters

| Parameter | Evidence basis | Why inconclusive | Follow-up need |
|-----------|----------------|------------------|----------------|
| Rank2 selection | logical | The current source chooses rank2, but the replay batch does not include direct same-gate rank1/rank3 ablations. | Add direct rank1/rank2/rank3 same-gate ablation before claiming rank2 is independently supported. |
| 90k fixed-notional boundary | diagnostic | 90k showed higher headline return `+284.35%`, but turnover was `80.29`, above the existing governance boundary. | Keep 90k diagnostic-only. Do not promote it without a separate governance decision. |
| Winner concentration and weak-period stability | mixed | The parameter-significance artifact has summary metrics but not enough trade-contribution or period-reset detail to support concentration/stability claims. | Use robustness and execution-decomposition artifacts for winner concentration, weak-period, and period-reset judgment. |

## Rejected Parameters

No tested parameter was labeled `rejected` by the 2026-06-15 parameter-significance validator. This does not mean every parameter is proven; unsupported items above remain explicitly inconclusive.

## Interpretation

The current quiet benchmark remains a viable research baseline after this check, but the support is uneven. The strongest same-window evidence is around MTW, poolhot10, and fixed85 versus fixed80. The weakest governance area is rank choice, because rank2 still lacks a clean direct same-gate ablation.

The next useful validation should focus on direct rank ablations and better concentration/stability evidence, not broad unrelated strategy families.

## Non-Promotion Statement

No paper-tracking promotion is made by this document. No runtime publish is required. No database refresh or write was performed for this run.
