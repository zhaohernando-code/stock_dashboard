from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.feature_v3_source_coverage import audit_feature_v3_source_coverage
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock


def test_feature_v3_source_coverage_audit_passes_complete_market_cap_and_valuation(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'feature-v3.db'}"
    init_database(database_url)
    _seed_stock_with_bars(
        database_url,
        values=[
            {"total_mv": 1_000_000_000.0, "circ_mv": 800_000_000.0, "pe_ttm": 18.0, "pb": 1.8},
            {"total_mv": 1_100_000_000.0, "circ_mv": 850_000_000.0, "pe_ttm": 19.0, "pb": 1.9},
        ],
    )

    with session_scope(database_url) as session:
        audit = audit_feature_v3_source_coverage(session, observed_start=date(2026, 1, 1), observed_end=date(2026, 1, 2))

    assert audit["gate_status"] == "passed"
    assert audit["blocking_gate_ids"] == []
    assert audit["claim_ceiling"] == "source_coverage_audit_only_no_pit_matrix_rebuild_no_model_replay"
    assert audit["row_count"] == 2
    assert audit["fields"]["total_mv"]["positive_ratio"] == 1.0
    assert audit["fields"]["pb"]["positive_ratio"] == 1.0


def test_feature_v3_source_coverage_audit_blocks_sparse_source_fields(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'feature-v3-sparse.db'}"
    init_database(database_url)
    _seed_stock_with_bars(
        database_url,
        values=[
            {"total_mv": None, "circ_mv": 800_000_000.0, "pe_ttm": None, "pb": 1.8},
            {"total_mv": None, "circ_mv": None, "pe_ttm": None, "pb": None},
        ],
    )

    with session_scope(database_url) as session:
        audit = audit_feature_v3_source_coverage(
            session,
            min_market_cap_coverage=0.75,
            min_valuation_coverage=0.75,
        )

    assert audit["gate_status"] == "blocked"
    assert "feature_v3_source_coverage:total_mv_positive_ratio_below_gate" in audit["blocking_gate_ids"]
    assert "feature_v3_source_coverage:circ_mv_positive_ratio_below_gate" in audit["blocking_gate_ids"]
    assert "feature_v3_source_coverage:pe_ttm_positive_ratio_below_gate" in audit["blocking_gate_ids"]
    assert "feature_v3_source_coverage:pb_positive_ratio_below_gate" in audit["blocking_gate_ids"]


def _seed_stock_with_bars(database_url: str, *, values: list[dict[str, float | None]]) -> None:
    with session_scope(database_url) as session:
        stock = Stock(
            symbol="600001.SH",
            ticker="600001",
            exchange="SH",
            name="主板甲",
            provider_symbol="600001.SH",
            listed_date=date(2020, 1, 1),
            status="active",
            profile_payload={"industry": "制造业"},
            license_tag="test",
            usage_scope="internal-test",
            redistribution_scope="none",
            source_uri="test://stock/600001.SH",
            lineage_hash=compute_lineage_hash({"symbol": "600001.SH"}),
        )
        session.add(stock)
        session.flush()
        for index, row in enumerate(values):
            observed_day = date(2026, 1, 1) + timedelta(days=index)
            session.add(
                MarketBar(
                    bar_key=f"bar-600001-{index}",
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
                    open_price=10 + index,
                    high_price=11 + index,
                    low_price=9 + index,
                    close_price=10.5 + index,
                    volume=1000 + index,
                    amount=(10.5 + index) * (1000 + index),
                    turnover_rate=1.0,
                    total_mv=row["total_mv"],
                    circ_mv=row["circ_mv"],
                    pe_ttm=row["pe_ttm"],
                    pb=row["pb"],
                    raw_payload={},
                    license_tag="test",
                    usage_scope="internal-test",
                    redistribution_scope="none",
                    source_uri=f"test://bar/600001/{index}",
                    lineage_hash=compute_lineage_hash({"symbol": "600001.SH", "index": index}),
                )
            )
