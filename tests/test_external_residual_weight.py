from __future__ import annotations

from datetime import date

from ashare_evidence.external_residual_weight import _rank1_return_labels


def test_rank1_return_labels_use_realized_sell_availability() -> None:
    snapshot = {
        "baseline_output": {
            "order_ledger": [
                {
                    "action": "sell",
                    "rank": 1,
                    "signal_day": "2026-01-02",
                    "trade_day": "2026-01-30",
                    "symbol": "AAA",
                    "return": -0.05,
                },
                {
                    "action": "sell",
                    "rank": 2,
                    "signal_day": "2026-01-02",
                    "trade_day": "2026-01-30",
                    "symbol": "BBB",
                    "return": 0.05,
                },
            ]
        }
    }
    labels = _rank1_return_labels(snapshot, signal_end=date(2026, 1, 31))
    assert labels == {
        "2026-01-02": {
            "signal_day": "2026-01-02",
            "actual_symbol": "AAA",
            "available_day": "2026-01-30",
            "realized_return": -0.05,
        }
    }
