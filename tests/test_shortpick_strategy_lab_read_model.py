from __future__ import annotations

import json
import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, ShortpickCandidate, ShortpickExperimentRun, Stock
from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONTROL_CONFIG_ID,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    PAPER_STATE_SCHEMA_VERSION,
    build_shortpick_strategy_lab_historical_replay_read_model,
    build_shortpick_strategy_lab_paper_tracking_read_model,
)


def test_historical_replay_is_static_full_history_metrics() -> None:
    payload = build_shortpick_strategy_lab_historical_replay_read_model()

    assert payload["status"] == "ready"
    assert payload["evidence_basis"] == "static_full_history_account_replay"
    assert payload["data_scope"]["static_read_model"] is True
    assert payload["summary"]["main_total_return"] == 2.9891730075000016
    assert payload["summary"]["main_negative_month_count"] == 4
    assert payload["selected_configs"][0]["config_id"] == MAIN_CONFIG_ID
    assert payload["baseline_configs"][0]["config_id"] == CONTROL_CONFIG_ID
    assert payload["metric_groups"]
    assert payload["leakage_audit"]["read_model_policy"] == "static_metrics_only_no_market_scan_no_dynamic_replay"


def test_paper_tracking_renders_mock_next_order_without_forward_records(tmp_path) -> None:
    state_path = tmp_path / "shortpick-strategy-lab-paper-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": [],
                "planned_orders": [
                    {
                        "strategy_id": MAIN_CONFIG_ID,
                        "strategy_label": "主策略：14 tranche 分层退出",
                        "signal_date": "2026-07-08",
                        "planned_entry_date": "2026-07-09",
                        "symbol": "002371.SZ",
                        "name": "北方华创",
                        "shares": 100,
                        "entry_timing": "次日收盘",
                        "estimated_notional_cny": 12750.0,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 8),
    )

    assert payload["summary"]["record_count"] == 0
    assert payload["summary"]["planned_order_count"] == 1
    assert payload["selected_configs"][0]["summary"]["paper_total_return"] is None
    assert payload["selected_configs"][0]["summary"]["current_nav_cny"] == INITIAL_CASH_CNY
    assert payload["paper_display"]["account_curves"] == []
    assert payload["paper_display"]["charts"] == []
    assert payload["paper_display"]["table"]["rows"] == []
    latest_trade = payload["paper_display"]["latest_trade"]
    assert latest_trade["tag"] == "待执行"
    assert "北方华创" in latest_trade["summary"]
    assert "买 100 股" in latest_trade["summary"]
    assert "次日收盘" in latest_trade["summary"]


def test_refresh_state_generates_affordable_forward_plan_from_latest_candidates(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'ashare.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        expensive = Stock(
            symbol="002371.SZ",
            ticker="002371",
            exchange="SZ",
            name="北方华创",
            provider_symbol="002371",
            status="active",
            profile_payload={},
            **build_lineage(
                {"symbol": "002371.SZ"},
                source_uri="test://stock/002371",
                license_tag="test",
                usage_scope="test",
                redistribution_scope="none",
            ),
        )
        affordable = Stock(
            symbol="603259.SH",
            ticker="603259",
            exchange="SH",
            name="药明康德",
            provider_symbol="603259",
            status="active",
            profile_payload={},
            **build_lineage(
                {"symbol": "603259.SH"},
                source_uri="test://stock/603259",
                license_tag="test",
                usage_scope="test",
                redistribution_scope="none",
            ),
        )
        control = Stock(
            symbol="600030.SH",
            ticker="600030",
            exchange="SH",
            name="中信证券",
            provider_symbol="600030",
            status="active",
            profile_payload={},
            **build_lineage(
                {"symbol": "600030.SH"},
                source_uri="test://stock/600030",
                license_tag="test",
                usage_scope="test",
                redistribution_scope="none",
            ),
        )
        session.add_all([expensive, affordable, control])
        session.flush()
        observed_at = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)
        for stock, close_price in ((expensive, 802.32), (affordable, 115.4), (control, 28.0)):
            session.add(
                MarketBar(
                    bar_key=f"bar-{stock.ticker}-20260708",
                    stock_id=stock.id,
                    timeframe="1d",
                    observed_at=observed_at,
                    open_price=close_price,
                    high_price=close_price,
                    low_price=close_price,
                    close_price=close_price,
                    volume=1000,
                    amount=1000000,
                    raw_payload={},
                    **build_lineage(
                        {"symbol": stock.symbol, "date": "2026-07-08"},
                        source_uri=f"test://bar/{stock.symbol}",
                        license_tag="test",
                        usage_scope="test",
                        redistribution_scope="none",
                    ),
                )
            )
        run = ShortpickExperimentRun(
            run_key="shortpick:test",
            run_date=date(2026, 7, 8),
            prompt_version="test",
            information_mode="native_web_open_discovery",
            status="completed",
            trigger_source="test",
            started_at=datetime(2026, 7, 8, tzinfo=UTC),
            completed_at=datetime(2026, 7, 8, 1, tzinfo=UTC),
            model_config={},
            summary_payload={},
        )
        session.add(run)
        session.flush()
        for index, (stock, score, source_rank, role) in enumerate(
            (
                (expensive, 1.15, 1, "market_factor_control_same_symbol_cooldown_low_turnover_uptrend"),
                (affordable, 1.03, 2, "market_factor_control_repeated_exposure_low_turnover_uptrend"),
                (control, 0.84, 5, "market_factor_control_drawdown_reversal_low_turnover_uptrend"),
            ),
            start=1,
        ):
            session.add(
                ShortpickCandidate(
                    run_id=run.id,
                    candidate_key=f"candidate:{index}",
                    symbol=stock.symbol,
                    name=stock.name,
                    research_priority="market_factor",
                    parse_status="parsed",
                    is_system_external=True,
                    candidate_payload={
                        "candidate_origin": "market_factor_overlay",
                        "tracking_role": role,
                        "market_factor_overlay": {
                            "latest_trade_day": "2026-07-08",
                            "score": score,
                            "source_rank": source_rank,
                            "tracking_role": role,
                        },
                    },
                )
            )

    monkeypatch.setenv("ASHARE_DATABASE_URL", database_url)
    state_path = tmp_path / "paper-state.json"
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_PAPER_STATE", str(state_path))
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "refresh-shortpick-strategy-lab-paper-state.py"
    spec = importlib.util.spec_from_file_location("refresh_shortpick_strategy_lab_paper_state", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.main() == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    orders = payload["planned_orders"]
    assert [order["strategy_id"] for order in orders] == [MAIN_CONFIG_ID, CONTROL_CONFIG_ID]
    assert orders[0]["symbol"] == "603259.SH"
    assert orders[0]["shares"] == 100
    assert orders[0]["planned_entry_date"] == "2026-07-09"
    assert orders[1]["symbol"] == "600030.SH"
    assert orders[1]["shares"] == 400
