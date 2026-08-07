from __future__ import annotations

from ashare_evidence.external_sector_momentum_rerank import _hybrid_gate


def test_hybrid_gate_uses_frozen_economics_and_instrumented_skip_rates() -> None:
    frozen = {
        "total_return": 1.0,
        "annualized_return": 1.0,
        "max_drawdown": -0.1,
        "negative_month_count": 1,
        "worst_monthly_return": -0.01,
        "skipped_order_rate": 0.1,
        "skipped_signal_rate": 0.1,
        "max_single_symbol_exposure_pct": 0.2,
    }
    instrumented = {**frozen, "skipped_order_rate": 0.3, "skipped_signal_rate": 0.4}
    candidate = {**frozen, "skipped_order_rate": 0.3, "skipped_signal_rate": 0.4}
    assert _hybrid_gate(candidate, frozen_v3=frozen, instrumented_lambda_zero=instrumented)["passed"]
