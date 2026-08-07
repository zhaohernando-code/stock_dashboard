from __future__ import annotations

from datetime import UTC, date, datetime

from ashare_evidence.external_context_sector_flow_research import (
    normalize_sector_flow_rows,
    sector_flow_state_by_decision_date,
)


def test_sector_flow_is_lagged_to_next_day_and_aggregated() -> None:
    rows = normalize_sector_flow_rows(
        {
            "industry": [
                {"trade_date": "20260102", "ts_code": "I1", "industry": "半导体", "net_amount": 2, "net_buy_amount": 5, "net_sell_amount": 3},
                {"trade_date": "20260102", "ts_code": "I2", "industry": "银行", "net_amount": -1, "net_buy_amount": 2, "net_sell_amount": 3},
            ],
            "concept": [
                {"trade_date": "20260102", "ts_code": "C1", "name": "人工智能", "net_amount": 3, "net_buy_amount": 5, "net_sell_amount": 2}
            ],
        },
        retrieved_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert rows[0]["available_at"] == "2026-01-03T08:00:00+08:00"
    assert sector_flow_state_by_decision_date(rows, decision_dates=[date(2026, 1, 2)]) == {}
    state = sector_flow_state_by_decision_date(rows, decision_dates=[date(2026, 1, 3)])["2026-01-03"]
    assert state["industry_positive_flow_breadth"] == 0.5
    assert state["tech_positive_flow_breadth"] == 1.0
