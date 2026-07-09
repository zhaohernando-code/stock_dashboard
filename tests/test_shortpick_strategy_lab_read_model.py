from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, ShortpickCandidate, ShortpickExperimentRun, Stock
from ashare_evidence.rolling_tranche_account_replay import project_shortpick_v3_initial_entry_orders
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract
from ashare_evidence.shortpick_strategy_lab_read_model import (
    CONDITIONAL_AGGRESSIVE_CONTROL_ID,
    CONTROL_CONFIG_ID,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    META_SIGNAL_QUALITY_CONTROL_ID,
    PAPER_STATE_SCHEMA_VERSION,
    THREE_PART_STABILITY_CONTROL_ID,
    build_shortpick_strategy_lab_historical_replay_read_model,
    build_shortpick_strategy_lab_paper_tracking_read_model,
)


def test_historical_replay_is_static_full_history_metrics() -> None:
    payload = build_shortpick_strategy_lab_historical_replay_read_model()

    assert payload["status"] == "ready"
    assert payload["evidence_basis"] == "static_full_history_account_replay"
    assert payload["data_scope"]["static_read_model"] is True
    assert payload["data_scope"]["signal_date_to"] == "2026-06-26"
    assert payload["summary"]["main_total_return"] == 3.119168564999999
    assert payload["summary"]["main_negative_month_count"] == 4
    assert payload["selected_configs"][0]["config_id"] == MAIN_CONFIG_ID
    assert payload["summary"]["baseline_config_count"] == 4
    assert payload["baseline_configs"][0]["config_id"] == META_SIGNAL_QUALITY_CONTROL_ID
    assert payload["baseline_configs"][0]["goal10_improvements"]["negative_month_delta"] == 1
    assert payload["baseline_configs"][0]["summary"]["total_return"] > payload["summary"]["main_total_return"]
    assert payload["baseline_configs"][0]["summary"]["max_drawdown"] > payload["summary"]["main_max_drawdown"]
    assert payload["baseline_configs"][1]["config_id"] == THREE_PART_STABILITY_CONTROL_ID
    assert payload["baseline_configs"][1]["goal10_improvements"]["skip_order_reduction_rel"] > 0.10
    assert payload["baseline_configs"][2]["config_id"] == CONDITIONAL_AGGRESSIVE_CONTROL_ID
    assert payload["baseline_configs"][3]["config_id"] == CONTROL_CONFIG_ID
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
                "plan_generation_status": {
                    "status": "ready",
                    "message": "test v3 selected_top_k source",
                },
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
    assert [row["config_id"] for row in payload["baseline_configs"]] == [
        META_SIGNAL_QUALITY_CONTROL_ID,
        THREE_PART_STABILITY_CONTROL_ID,
        CONDITIONAL_AGGRESSIVE_CONTROL_ID,
        CONTROL_CONFIG_ID,
    ]
    assert payload["paper_governance"]["control_config_ids"] == [
        META_SIGNAL_QUALITY_CONTROL_ID,
        THREE_PART_STABILITY_CONTROL_ID,
        CONDITIONAL_AGGRESSIVE_CONTROL_ID,
        CONTROL_CONFIG_ID,
    ]
    assert payload["paper_display"]["account_curves"] == []
    assert payload["paper_display"]["charts"] == []
    assert payload["paper_display"]["table"]["rows"] == []
    latest_trade = payload["paper_display"]["latest_trade"]
    assert latest_trade["tag"] == "待执行"
    assert "北方华创" in latest_trade["summary"]
    assert "买 100 股" in latest_trade["summary"]
    assert "次日收盘" in latest_trade["summary"]


def test_paper_tracking_distinguishes_ready_no_executable_orders(tmp_path) -> None:
    state_path = tmp_path / "shortpick-strategy-lab-paper-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": [],
                "planned_orders": [],
                "plan_generation_status": {
                    "status": "ready_no_executable_orders",
                    "signal_date": "2026-07-08",
                    "message": "模型当天选择现金。",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 8),
    )

    assert payload["status"] == "active"
    assert payload["current_status"] == "model_cash_or_no_executable_order"
    assert payload["current_message"] == "模型当天选择现金。"
    assert payload["summary"]["planned_order_count"] == 0


def _load_refresh_state_script() -> object:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "refresh-shortpick-strategy-lab-paper-state.py"
    spec = importlib.util.spec_from_file_location("refresh_shortpick_strategy_lab_paper_state", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_projection_market_data(database_url: str) -> None:
    symbols = [
        ("000300.SH", "沪深300", "benchmark", 100.0, 0.05),
        ("600030.SH", "中信证券", "证券", 18.0, 0.12),
        ("600028.SH", "中国石化", "石油加工", 6.0, 0.04),
        ("601628.SH", "中国人寿", "保险", 28.0, 0.10),
        ("000001.SZ", "平安银行", "银行", 10.0, 0.03),
    ]
    start_day = date(2026, 3, 21)
    with session_scope(database_url) as session:
        stocks: list[Stock] = []
        for symbol, name, industry, _, _ in symbols:
            ticker, _, exchange = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange,
                name=name,
                provider_symbol=ticker,
                status="active",
                profile_payload={"industry": industry},
                **build_lineage(
                    {"symbol": symbol},
                    source_uri=f"test://stock/{symbol}",
                    license_tag="test",
                    usage_scope="test",
                    redistribution_scope="none",
                ),
            )
            session.add(stock)
            stocks.append(stock)
        session.flush()
        for stock, (_, _, _, base_price, slope) in zip(stocks, symbols, strict=True):
            for index in range(110):
                observed_day = start_day + timedelta(days=index)
                close_price = base_price + index * slope
                volume = 2_000_000 + index * 10_000
                session.add(
                    MarketBar(
                        bar_key=f"bar-{stock.ticker}-{observed_day.isoformat()}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 15, 0, tzinfo=UTC),
                        open_price=close_price * 0.99,
                        high_price=close_price * 1.02,
                        low_price=close_price * 0.98,
                        close_price=close_price,
                        volume=volume,
                        amount=close_price * volume,
                        turnover_rate=0.8 + index / 1000,
                        total_mv=20_000_000_000 + index * 10_000_000,
                        circ_mv=15_000_000_000 + index * 8_000_000,
                        pe_ttm=10.0 + index / 100,
                        pb=1.0 + index / 1000,
                        raw_payload={},
                        **build_lineage(
                            {"symbol": stock.symbol, "date": observed_day.isoformat()},
                            source_uri=f"test://bar/{stock.symbol}/{observed_day.isoformat()}",
                            license_tag="test",
                            usage_scope="test",
                            redistribution_scope="none",
                        ),
                    )
                )


def test_refresh_state_builds_v3_source_instead_of_accepting_missing_source(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'ashare.db'}"
    init_database(database_url)
    _seed_projection_market_data(database_url)
    with session_scope(database_url) as session:
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
        session.add(
            ShortpickCandidate(
                run_id=run.id,
                candidate_key="candidate:legacy",
                symbol="603259.SH",
                name="药明康德",
                research_priority="market_factor",
                parse_status="parsed",
                is_system_external=True,
                candidate_payload={
                    "candidate_origin": "market_factor_overlay",
                    "tracking_role": "market_factor_control_repeated_exposure_low_turnover_uptrend",
                    "market_factor_overlay": {
                        "latest_trade_day": "2026-07-08",
                        "score": 1.03,
                        "source_rank": 2,
                    },
                },
            )
        )

    monkeypatch.setenv("ASHARE_DATABASE_URL", database_url)
    state_path = tmp_path / "paper-state.json"
    candidate_run_path = tmp_path / "v3-candidate-run-source.json"
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_PAPER_STATE", str(state_path))
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_V3_CANDIDATE_RUN_SOURCE", str(candidate_run_path))
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": [],
                "planned_orders": [{"strategy_id": MAIN_CONFIG_ID, "symbol": "SHOULD_CLEAR"}],
            }
        ),
        encoding="utf-8",
    )
    module = _load_refresh_state_script()

    assert module.main() == 0
    assert candidate_run_path.exists()
    candidate_run = json.loads(candidate_run_path.read_text(encoding="utf-8"))
    assert candidate_run["artifact_type"] == "shortpick_strategy_lab_v3_candidate_run_source"
    assert candidate_run["model_spec_id"] == "selected_exhaustion_date_scaled_v3_top3_20d_v1"
    assert candidate_run["prediction_row_count"] > 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert all(row.get("symbol") != "SHOULD_CLEAR" for row in payload["planned_orders"])
    assert payload["plan_generation_status"]["status"].startswith("ready")
    assert payload["plan_generation_status"]["signal_date"] == "2026-07-08"
    read_model = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 8),
    )
    assert read_model["status"] == "active"
    assert read_model["summary"]["latest_plan_signal_date"] == "2026-07-08"
    assert read_model["paper_display"]["latest_trade"]["tag"] in {"模型现金", "待执行"}
    assert read_model["current_status"] in {
        "awaiting_first_forward_fill",
        "awaiting_v3_plan",
        "model_cash_or_no_executable_order",
    }


def test_refresh_state_generates_plan_from_v3_selected_top_k_candidate_run(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'ashare.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        stocks = [
            Stock(
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
            ),
            Stock(
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
            ),
            Stock(
                symbol="600028.SH",
                ticker="600028",
                exchange="SH",
                name="中国石化",
                provider_symbol="600028",
                status="active",
                profile_payload={},
                **build_lineage(
                    {"symbol": "600028.SH"},
                    source_uri="test://stock/600028",
                    license_tag="test",
                    usage_scope="test",
                    redistribution_scope="none",
                ),
            ),
        ]
        session.add_all(stocks)
        session.flush()
        observed_at = datetime(2026, 7, 8, 15, 0, tzinfo=UTC)
        for stock, close_price in ((stocks[0], 802.32), (stocks[1], 28.0), (stocks[2], 6.2)):
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
    candidate_run_path = tmp_path / "v3-candidate-run.json"
    candidate_run_path.write_text(
        json.dumps(
            {
                "artifact_id": "walk-forward-model-candidate-run-test",
                "trial_diagnostics": [
                    {
                        "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                        "selected_top_k": 3,
                        "selected_top_k_picks_by_date": [
                            {
                                "as_of_date": "2026-07-08",
                                "symbol": "002371.SZ",
                                "stock_name": "北方华创",
                                "rank": 1,
                                "portfolio_weight": 1.0,
                                "rank_weight_multiplier": 2.73,
                                "score": 3.9,
                                "target_horizon_days": 20,
                                "rank_weight_feature_values": {
                                    "benchmark_return_20d": 0.01,
                                    "return_20d_percentile": 0.99,
                                    "industry_return_20d_excess": 0.20,
                                    "distance_from_20d_high": -0.03,
                                },
                            },
                            {
                                "as_of_date": "2026-07-08",
                                "symbol": "600030.SH",
                                "stock_name": "中信证券",
                                "rank": 2,
                                "portfolio_weight": 1.0,
                                "rank_weight_multiplier": 1.0,
                                "score": 3.2,
                                "target_horizon_days": 20,
                            },
                            {
                                "as_of_date": "2026-07-08",
                                "symbol": "600028.SH",
                                "stock_name": "中国石化",
                                "rank": 3,
                                "portfolio_weight": 1.0,
                                "rank_weight_multiplier": 0.0,
                                "score": 3.1,
                                "target_horizon_days": 20,
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("ASHARE_DATABASE_URL", database_url)
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_V3_CANDIDATE_RUN_SOURCE", str(candidate_run_path))
    state_path = tmp_path / "paper-state.json"
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_PAPER_STATE", str(state_path))
    module = _load_refresh_state_script()
    assert module._next_business_day(date(2026, 7, 10)) == date(2026, 7, 13)

    assert module.main() == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["plan_generation_status"]["status"] == "ready"
    assert payload["plan_generation_status"]["signal_date"] == "2026-07-08"
    orders = payload["planned_orders"]
    assert [order["strategy_id"] for order in orders] == [
        MAIN_CONFIG_ID,
        META_SIGNAL_QUALITY_CONTROL_ID,
        THREE_PART_STABILITY_CONTROL_ID,
        CONDITIONAL_AGGRESSIVE_CONTROL_ID,
        CONTROL_CONFIG_ID,
    ]
    assert [order["symbol"] for order in orders] == [
        "600030.SH",
        "600030.SH",
        "600030.SH",
        "600030.SH",
        "600030.SH",
    ]
    assert [order["shares"] for order in orders] == [100, 200, 200, 200, 100]
    assert orders[1]["conditional_aggressive_overlay_active"] is True
    assert orders[1]["conditional_aggressive_weight_scale"] == 1.65 * 0.9
    assert orders[2]["conditional_aggressive_overlay_active"] is True
    assert orders[2]["conditional_aggressive_weight_scale"] == 1.6
    assert orders[3]["conditional_aggressive_overlay_active"] is True
    assert orders[3]["conditional_aggressive_weight_scale"] == 14 / 11
    assert all(order["plan_source"] == "selected_top_k_candidate_run_rolling_tranche_engine" for order in orders)
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    main_config = next(config for config in contract["candidate_configurations"] if config["config_id"] == MAIN_CONFIG_ID)
    projected_rows = project_shortpick_v3_initial_entry_orders(
        config=main_config,
        picks=json.loads(candidate_run_path.read_text(encoding="utf-8"))["trial_diagnostics"][0][
            "selected_top_k_picks_by_date"
        ],
        signal_day=date(2026, 7, 8),
        planned_entry_day=date(2026, 7, 9),
        estimated_close_by_symbol={"002371.SZ": 802.32, "600030.SH": 28.0, "600028.SH": 6.2},
        selected_top_k=3,
        initial_cash_cny=INITIAL_CASH_CNY,
    )
    projected_main_buy = next(row for row in projected_rows if row["action"] == "buy")
    assert orders[0]["symbol"] == projected_main_buy["symbol"]
    assert orders[0]["shares"] == projected_main_buy["shares"]
    assert orders[0]["estimated_entry_price_cny"] == projected_main_buy["price"]
    assert orders[0]["target_notional_cny"] == round(projected_main_buy["target_notional_cny"], 2)
    diagnostics = payload["plan_generation_status"]["diagnostics"]
    assert any(row["symbol"] == "002371.SZ" and row["reason"] == "price_too_high_for_slot" for row in diagnostics)
    assert any(row["symbol"] == "600028.SH" and row["reason"] == "zero_target_allocation" for row in diagnostics)
