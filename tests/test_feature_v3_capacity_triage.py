from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.feature_v3_capacity_triage import build_feature_v3_capacity_triage
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock


def test_feature_v3_capacity_triage_compares_small_source_with_liquid_candidates(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'capacity-triage.db'}"
    init_database(database_url)
    _seed_day(
        database_url,
        observed_day=date(2024, 6, 5),
        rows=[
            {"symbol": "603117.SH", "name": "万林物流", "amount": 2_200_000.0, "total_mv": 10.0, "circ_mv": 9.0},
            {"symbol": "601777.SH", "name": "千里科技", "amount": 52_000_000.0, "total_mv": 80.0, "circ_mv": 70.0},
            {"symbol": "605116.SH", "name": "奥锐特", "amount": 31_000_000.0, "total_mv": 90.0, "circ_mv": 75.0},
        ],
    )
    summary_path = _write_summary(
        tmp_path,
        source_symbol="603117.SH",
        source_net=0.6278,
        best_symbol="605116.SH",
        best_net=0.2607,
    )

    with session_scope(database_url) as session:
        triage = build_feature_v3_capacity_triage(session, top_candidate_summary_artifact=summary_path)

    assert triage["gate_status"] == "passed"
    assert triage["claim_ceiling"] == "triage_only_no_pit_matrix_rebuild_no_model_replay"
    assert triage["date_count"] == 1
    assert triage["source_total_mv_percentile_range"] == [1 / 3, 1 / 3]
    assert triage["median_liquid_total_mv_percentile_range"] == pytest.approx([5 / 6, 5 / 6])
    assert triage["future_return_gap_to_best_liquid_range"] == pytest.approx([0.3671, 0.3671])
    selected = triage["dates"][0]["selected_symbols"]
    assert selected[0]["role"] == "source_underfilled_winner"
    assert selected[0]["summary_avg_amount_20d"] == 2_200_000.0


def test_feature_v3_capacity_triage_blocks_missing_selected_market_bar(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'capacity-triage-missing.db'}"
    init_database(database_url)
    _seed_day(
        database_url,
        observed_day=date(2024, 6, 5),
        rows=[
            {"symbol": "603117.SH", "name": "万林物流", "amount": 2_200_000.0, "total_mv": 10.0, "circ_mv": 9.0},
        ],
    )
    summary_path = _write_summary(
        tmp_path,
        source_symbol="603117.SH",
        source_net=0.6278,
        best_symbol="605116.SH",
        best_net=0.2607,
    )

    with session_scope(database_url) as session:
        triage = build_feature_v3_capacity_triage(session, top_candidate_summary_artifact=summary_path)

    assert triage["gate_status"] == "blocked"
    assert "feature_v3_capacity_triage:missing_selected_market_bar" in triage["blocking_gate_ids"]
    assert triage["dates"][0]["missing_symbols"] == ["605116.SH", "601777.SH"]


def _write_summary(
    tmp_path: Path,
    *,
    source_symbol: str,
    source_net: float,
    best_symbol: str,
    best_net: float,
) -> Path:
    summary = {
        "artifact_type": "capacity_cluster_remaining_603117_top200_oracle_summary",
        "summary": [
            {
                "as_of_date": "2024-06-05",
                "source_symbol": source_symbol,
                "source_net_excess_return": source_net,
                "source_avg_amount_20d": 2_200_000.0,
                "best_liquid_candidate": {
                    "symbol": best_symbol,
                    "rank": 153,
                    "avg_amount_20d": 31_000_000.0,
                    "net_excess_return": best_net,
                },
                "top10_liquid_by_future_return": [
                    {
                        "symbol": best_symbol,
                        "rank": 153,
                        "avg_amount_20d": 31_000_000.0,
                        "net_excess_return": best_net,
                    },
                    {
                        "symbol": "601777.SH",
                        "rank": 172,
                        "avg_amount_20d": 52_000_000.0,
                        "net_excess_return": 0.2445,
                    },
                ],
            }
        ],
    }
    path = tmp_path / "top200-summary.json"
    path.write_text(json.dumps(summary), encoding="utf-8")
    return path


def _seed_day(database_url: str, *, observed_day: date, rows: list[dict[str, float | str]]) -> None:
    with session_scope(database_url) as session:
        for index, row in enumerate(rows):
            symbol = str(row["symbol"])
            stock = Stock(
                symbol=symbol,
                ticker=symbol.split(".")[0],
                exchange=symbol.split(".")[1],
                name=str(row["name"]),
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={},
                license_tag="test",
                usage_scope="internal-test",
                redistribution_scope="none",
                source_uri=f"test://stock/{symbol}",
                lineage_hash=compute_lineage_hash({"symbol": symbol}),
            )
            session.add(stock)
            session.flush()
            session.add(
                MarketBar(
                    bar_key=f"bar-{symbol}-{observed_day.isoformat()}",
                    stock_id=stock.id,
                    timeframe="1d",
                    observed_at=datetime(
                        observed_day.year,
                        observed_day.month,
                        observed_day.day,
                        7,
                        0,
                        tzinfo=UTC,
                    ),
                    open_price=10.0 + index,
                    high_price=11.0 + index,
                    low_price=9.0 + index,
                    close_price=10.5 + index,
                    volume=1000.0 + index,
                    amount=float(row["amount"]),
                    turnover_rate=1.0 + index,
                    total_mv=float(row["total_mv"]),
                    circ_mv=float(row["circ_mv"]),
                    pe_ttm=10.0 + index,
                    pb=1.0 + index,
                    raw_payload={},
                    license_tag="test",
                    usage_scope="internal-test",
                    redistribution_scope="none",
                    source_uri=f"test://bar/{symbol}/{observed_day.isoformat()}",
                    lineage_hash=compute_lineage_hash({"symbol": symbol, "date": observed_day.isoformat()}),
                )
            )
