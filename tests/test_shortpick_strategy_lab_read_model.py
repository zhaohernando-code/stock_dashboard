from __future__ import annotations

import importlib.util
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import build_lineage
from ashare_evidence.models import MarketBar, ShortpickCandidate, ShortpickExperimentRun, Stock
from ashare_evidence.rolling_tranche_account_replay import project_shortpick_v3_initial_entry_orders
from ashare_evidence.rolling_tranche_execution_contract import build_shortpick_v3_rolling_tranche_execution_contract
from ashare_evidence.schemas.shortpick import ShortpickStrategyLabHistoricalReplayResponse
from ashare_evidence.shortpick_strategy_lab_read_model import (
    ACTIVE_STRATEGY_CONFIG_IDS,
    ARCHIVED_STRATEGY_CONFIG_IDS,
    INITIAL_CASH_CNY,
    MAIN_CONFIG_ID,
    NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
    PAPER_STATE_SCHEMA_VERSION,
    QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
    UPSTREAM_META_STABILITY_CONTROL_ID,
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
    assert payload["summary"]["baseline_config_count"] == 2
    assert payload["summary"]["active_config_count"] == 3
    assert payload["summary"]["archived_config_count"] == 5
    assert payload["baseline_configs"][0]["config_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
    assert payload["baseline_configs"][0]["goal10_improvements"]["skip_order_reduction_rel"] > 0.20
    assert payload["baseline_configs"][0]["goal10_improvements"]["skip_signal_reduction_rel"] > 0.30
    assert payload["baseline_configs"][0]["summary"]["negative_month_count"] == 2
    assert payload["baseline_configs"][1]["config_id"] == UPSTREAM_META_STABILITY_CONTROL_ID
    assert payload["baseline_configs"][1]["goal10_improvements"]["drawdown_reduction_rel"] > 0.10
    assert payload["strategy_governance"]["active_config_ids"] == list(ACTIVE_STRATEGY_CONFIG_IDS)
    assert payload["strategy_governance"]["archived_config_ids"] == list(ARCHIVED_STRATEGY_CONFIG_IDS)
    assert payload["strategy_governance"]["archived_history_preserved"] is True
    assert payload["metric_groups"]
    assert payload["leakage_audit"]["read_model_policy"] == "static_metrics_only_no_market_scan_no_dynamic_replay"


def test_historical_replay_response_schema_keeps_breakthrough_metrics() -> None:
    payload = build_shortpick_strategy_lab_historical_replay_read_model()

    response_payload = ShortpickStrategyLabHistoricalReplayResponse.model_validate(payload).model_dump(mode="json")

    first_control = response_payload["baseline_configs"][0]
    assert first_control["config_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
    assert first_control["goal10_improvements"]["skip_order_reduction_rel"] > 0.20
    assert first_control["goal10_improvements"]["negative_month_delta"] == 1


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
                    },
                    {
                        "strategy_id": ARCHIVED_STRATEGY_CONFIG_IDS[0],
                        "strategy_label": "已归档策略",
                        "signal_date": "2026-07-08",
                        "planned_entry_date": "2026-07-09",
                        "symbol": "600000.SH",
                        "shares": 100,
                    },
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
        QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
        UPSTREAM_META_STABILITY_CONTROL_ID,
    ]
    assert payload["paper_governance"]["control_config_ids"] == [
        QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
        UPSTREAM_META_STABILITY_CONTROL_ID,
    ]
    assert payload["strategy_governance"]["active_config_ids"] == list(ACTIVE_STRATEGY_CONFIG_IDS)
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


def test_paper_tracking_projects_rank5_observation_progress_and_bounds_summary_rows(tmp_path) -> None:
    state_path = tmp_path / "shortpick-strategy-lab-paper-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": [],
                "planned_orders": [],
                "plan_generation_status": {"status": "ready_no_executable_orders"},
                "rank5_forward_observation": {
                    "artifact_id": "shortpick-v3-rank5-forward-observation-v1",
                    "status": "collecting_forward_observations",
                    "contract_ref": "docs/contracts/SHORTPICK_V3_RANK5_FORWARD_OBSERVATION_CONTRACT_2026-07-15.json",
                    "active_rank5_quality_policy": None,
                    "progress": {
                        "matured_shadow_observation_count": 7,
                        "pending_shadow_observation_count": 3,
                        "research_reopen_ready": False,
                        "data_quality_passed": True,
                    },
                    "rows": [{"observation_key": "rank5-forward-test"}],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    full = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 15),
    )
    summary = build_shortpick_strategy_lab_paper_tracking_read_model(
        include_records=False,
        paper_state_path=state_path,
        today=date(2026, 7, 15),
    )

    assert full["rank5_forward_observation"]["rows"] == [{"observation_key": "rank5-forward-test"}]
    assert summary["rank5_forward_observation"]["rows"] == []
    assert summary["summary"]["rank5_forward_matured_count"] == 7
    assert summary["summary"]["rank5_forward_pending_count"] == 3
    assert summary["paper_governance"]["active_rank5_quality_policy"] is None
    assert summary["leakage_audit"]["synchronized_backfill_eligible_for_rank5_evidence"] is False


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
    assert NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID in candidate_run["model_spec_ids"]
    assert candidate_run["prediction_row_count"] > 0
    rank_adjusted_trial = next(
        row
        for row in candidate_run["trial_diagnostics"]
        if row["model_spec_id"] == NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID
    )
    assert rank_adjusted_trial["ranked_candidate_inventory_top_k"] == 20
    assert isinstance(rank_adjusted_trial["ranked_candidate_inventory_by_date"], list)
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
                    },
                    {
                        "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
                        "selected_top_k": 3,
                        "selected_top_k_picks_by_date": [
                            {
                                "as_of_date": "2026-07-08",
                                "symbol": "002371.SZ",
                                "stock_name": "北方华创",
                                "rank": 1,
                                "portfolio_weight": 1.0,
                                "rank_weight_multiplier": 2.73,
                                "rank_portfolio_adjustment_multiplier": 0.9,
                                "score": 3.9,
                                "target_horizon_days": 20,
                            },
                            {
                                "as_of_date": "2026-07-08",
                                "symbol": "600030.SH",
                                "stock_name": "中信证券",
                                "rank": 2,
                                "portfolio_weight": 1.0,
                                "rank_weight_multiplier": 1.0,
                                "rank_portfolio_adjustment_multiplier": 1.3,
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
                        "ranked_candidate_inventory_by_date": [],
                    },
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
    assert set(module.STRATEGY_LABELS) == set(ACTIVE_STRATEGY_CONFIG_IDS)
    assert module._next_business_day(date(2026, 7, 10)) == date(2026, 7, 13)

    assert module.main() == 0
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["plan_generation_status"]["status"] == "ready"
    assert payload["plan_generation_status"]["signal_date"] == "2026-07-08"
    orders = payload["planned_orders"]
    assert [order["strategy_id"] for order in orders] == [
        MAIN_CONFIG_ID,
        QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
        UPSTREAM_META_STABILITY_CONTROL_ID,
    ]
    assert [order["symbol"] for order in orders] == [
        "600030.SH",
        "600030.SH",
        "600030.SH",
    ]
    assert [order["shares"] for order in orders] == [100, 100, 200]
    assert orders[1]["model_spec_id"] == NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID
    assert orders[1]["conditional_aggressive_overlay_active"] is False
    assert orders[2]["conditional_aggressive_overlay_active"] is True
    assert orders[2]["conditional_aggressive_weight_scale"] == 1.65 * 0.9
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


def test_forward_ledger_fills_active_strategies_from_common_start(tmp_path, monkeypatch) -> None:
    database_url = f"sqlite:///{tmp_path / 'paper-ledger.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        stock = Stock(
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
        session.add(stock)
        session.flush()
        for observed_day, close_price in ((date(2026, 7, 8), 10.0), (date(2026, 7, 9), 11.0)):
            session.add(
                MarketBar(
                    bar_key=f"bar-600030-{observed_day.isoformat()}",
                    stock_id=stock.id,
                    timeframe="1d",
                    observed_at=datetime.combine(observed_day, time(15, 0), tzinfo=UTC),
                    open_price=close_price,
                    high_price=close_price,
                    low_price=close_price,
                    close_price=close_price,
                    volume=1_000_000,
                    amount=close_price * 1_000_000,
                    raw_payload={},
                    **build_lineage(
                        {"symbol": stock.symbol, "date": observed_day.isoformat()},
                        source_uri=f"test://bar/{observed_day.isoformat()}",
                        license_tag="test",
                        usage_scope="test",
                        redistribution_scope="none",
                    ),
                )
            )

    def source_for(signal_day: date, capture_mode: str) -> dict[str, object]:
        pick = {
            "as_of_date": signal_day.isoformat(),
            "symbol": "600030.SH",
            "stock_name": "中信证券",
            "rank": 1,
            "portfolio_weight": 1.0,
            "rank_weight_multiplier": 1.0,
            "rank_portfolio_adjustment_multiplier": 1.0,
            "score": 3.5,
            "target_horizon_days": 20,
            "rank_weight_feature_values": {
                "benchmark_return_20d": 0.01,
                "return_20d_percentile": 0.90,
                "industry_return_20d_excess": 0.10,
                "distance_from_20d_high": -0.01,
            },
        }
        return {
            "artifact_id": f"candidate-{signal_day.isoformat()}",
            "signal_date": signal_day.isoformat(),
            "paper_source_capture_mode": capture_mode,
            "trial_diagnostics": [
                {
                    "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                    "selected_top_k": 3,
                    "selected_top_k_picks_by_date": [pick],
                },
                {
                    "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
                    "selected_top_k": 3,
                    "selected_top_k_picks_by_date": [pick],
                    "ranked_candidate_inventory_by_date": [],
                },
            ],
        }

    monkeypatch.setenv("ASHARE_DATABASE_URL", database_url)
    monkeypatch.setenv("ASHARE_SHORTPICK_STRATEGY_LAB_V3_SOURCE_DATABASE_URL", database_url)
    module = _load_refresh_state_script()
    monkeypatch.setattr(
        module,
        "_market_days",
        lambda _session, *, start_day, end_day: [
            day for day in (date(2026, 7, 8), date(2026, 7, 9)) if start_day <= day <= end_day
        ],
    )

    records, account_states, pending, status, history, events, rank5_observation = module._rebuild_forward_paper_ledger(
        [
            source_for(date(2026, 7, 8), "synchronized_start_backfill"),
            source_for(date(2026, 7, 9), "daily_forward_capture"),
        ]
    )

    buys = [row for row in records if row["action"] == "buy"]
    assert len(account_states) == 3
    assert {row["strategy_id"] for row in buys} == set(account_states)
    assert {row["signal_date"] for row in buys} == {"2026-07-08"}
    assert all(state["cash_cny"] < INITIAL_CASH_CNY for state in account_states.values())
    assert all(state["positions"] for state in account_states.values())
    assert {row["signal_date"] for row in pending} == {"2026-07-09"}, json.dumps(
        {"status": status, "history": history, "events": events}, ensure_ascii=False
    )
    assert status["daily_source_date_from"] == "2026-07-08"
    assert status["daily_source_date_to"] == "2026-07-09"
    assert rank5_observation["progress"]["captured_observation_count"] == 0

    state_path = tmp_path / "rebuilt-paper-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": PAPER_STATE_SCHEMA_VERSION,
                "tracking_start_date": "2026-07-08",
                "records": records,
                "account_states": account_states,
                "planned_orders": pending,
                "plan_generation_status": status,
                "source_coverage": {
                    "start_date": "2026-07-08",
                    "end_date": "2026-07-09",
                    "strategy_count": 3,
                    "common_start_enforced": True,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    read_model = build_shortpick_strategy_lab_paper_tracking_read_model(
        paper_state_path=state_path,
        today=date(2026, 7, 9),
    )
    paper_table = read_model["paper_display"]["table"]
    assert paper_table["columns"][0] == {"key": "trade_date_text", "label": "交易日"}
    assert len(paper_table["rows"]) == len(buys)
    assert {row["trade_date_text"] for row in paper_table["rows"]} == {"2026-07-09"}
    assert len(read_model["paper_display"]["account_curves"]) == 3
    assert read_model["paper_display"]["coverage"]["common_start_enforced"] is True


def test_quality_candidate_replaces_unaffordable_pick_from_same_day_inventory() -> None:
    module = _load_refresh_state_script()
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    config = next(
        row
        for row in contract["candidate_configurations"]
        if row["config_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
    )

    order, rejections, rank5_observations = module._affordable_replacement_order(
        skipped_row={
            "action": "skip",
            "reason": "price_too_high_for_slot",
            "signal_day": "2026-07-08",
            "trade_day": "2026-07-09",
            "target_notional_cny": 10_000.0,
        },
        original_pick={"symbol": "002371.SZ", "rank": 1, "score": 3.90},
        inventory=[
            {"symbol": "600001.SH", "rank": 4, "score": 3.85, "selection_allowed": True},
            {
                "symbol": "600002.SH",
                "rank": 5,
                "score": 3.84,
                "selection_allowed": True,
                "path_feature_observation_count": 20,
                "path_realized_volatility_20d": 0.02,
                "path_downside_semivolatility_20d": 0.01,
                "path_max_drawdown_20d": -0.05,
                "path_up_day_ratio_20d": 0.55,
                "path_trend_efficiency_20d": 0.20,
            },
        ],
        estimated_close_by_symbol={"600001.SH": 25.0, "600002.SH": 8.0},
        selected_symbols={"002371.SZ"},
        config=config,
        strategy_id=QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
    )

    assert rejections == []
    assert order is not None
    assert order["symbol"] == "600001.SH"
    assert order["rank"] == 1
    assert order["shares"] == 300
    assert order["replacement_inventory_rank"] == 4
    assert order["replacement_fill_ratio"] >= 0.75
    assert len(rank5_observations) == 1
    assert rank5_observations[0]["shadow_base_eligible"] is True
    assert rank5_observations[0]["selected_by_current_r14"] is False
    assert rank5_observations[0]["selection_decision"] == "shadow_base_eligible_not_selected"


def test_forward_plan_captures_point_in_time_rank5_observation_and_links_selected_order(
    tmp_path,
    monkeypatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'rank5-forward.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        original = Stock(
            symbol="002371.SZ",
            ticker="002371",
            exchange="SZ",
            name="高价原始标的",
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
        rank5 = Stock(
            symbol="600005.SH",
            ticker="600005",
            exchange="SH",
            name="Rank5影子标的",
            provider_symbol="600005",
            status="active",
            profile_payload={},
            **build_lineage(
                {"symbol": "600005.SH"},
                source_uri="test://stock/600005",
                license_tag="test",
                usage_scope="test",
                redistribution_scope="none",
            ),
        )
        session.add_all([original, rank5])
        session.flush()
        for index in range(21):
            observed_day = date(2026, 6, 25) + timedelta(days=index)
            for stock, close_price in ((original, 800.0), (rank5, 8.0 + index * 0.01)):
                session.add(
                    MarketBar(
                        bar_key=f"rank5-forward-{stock.ticker}-{observed_day.isoformat()}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime.combine(observed_day, time(15, 0), tzinfo=UTC),
                        open_price=close_price,
                        high_price=close_price,
                        low_price=close_price,
                        close_price=close_price,
                        volume=1_000_000,
                        amount=10_000_000,
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

    candidate_run = {
        "artifact_id": "rank5-forward-candidate-2026-07-15",
        "signal_date": "2026-07-15",
        "paper_source_capture_mode": "daily_forward_capture",
        "trial_diagnostics": [
            {
                "model_spec_id": "selected_exhaustion_date_scaled_v3_top3_20d_v1",
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    {
                        "as_of_date": "2026-07-15",
                        "symbol": "002371.SZ",
                        "stock_name": "高价原始标的",
                        "rank": 1,
                        "portfolio_weight": 1.0,
                        "rank_weight_multiplier": 1.0,
                        "score": 3.90,
                        "target_horizon_days": 20,
                    }
                ],
            },
            {
                "model_spec_id": NEGATIVE_MONTH_RANK_ADJUSTED_MODEL_SPEC_ID,
                "selected_top_k": 1,
                "selected_top_k_picks_by_date": [
                    {
                        "as_of_date": "2026-07-15",
                        "symbol": "002371.SZ",
                        "stock_name": "高价原始标的",
                        "rank": 1,
                        "portfolio_weight": 1.0,
                        "rank_weight_multiplier": 1.0,
                        "rank_portfolio_adjustment_multiplier": 1.0,
                        "score": 3.90,
                        "target_horizon_days": 20,
                    }
                ],
                "ranked_candidate_inventory_by_date": [
                    {
                        "as_of_date": "2026-07-15",
                        "symbol": "600005.SH",
                        "stock_name": "Rank5影子标的",
                        "rank": 5,
                        "score": 3.84,
                        "selection_allowed": True,
                    }
                ],
            },
        ],
    }
    monkeypatch.setenv("ASHARE_DATABASE_URL", database_url)
    module = _load_refresh_state_script()

    orders, status = module._v3_model_generated_plan(
        account_states=module._initial_account_states(),
        candidate_run=candidate_run,
    )

    replacement = next(
        order
        for order in orders
        if order["strategy_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
        and order.get("replacement_inventory_rank") == 5
    )
    observations = [
        observation
        for diagnostic in status["diagnostics"]
        for observation in diagnostic.get("rank5_forward_observations") or []
    ]
    assert len(observations) == 1
    assert observations[0]["path_feature_complete"] is True
    assert observations[0]["path_feature_observation_count"] == 20
    assert observations[0]["selected_by_current_r14"] is True
    assert observations[0]["paper_source_capture_mode"] == "daily_forward_capture"
    assert replacement["rank5_forward_observation_key"] == observations[0]["observation_key"]
    assert replacement["paper_source_capture_mode"] == "daily_forward_capture"


def test_forward_replacement_applies_optional_rank5_quality_filter() -> None:
    module = _load_refresh_state_script()
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    config = next(
        row
        for row in contract["candidate_configurations"]
        if row["config_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
    )
    config["affordable_replacement_policy"]["rank5_quality_policy"] = {
        "min_return_20d_percentile": 0.5
    }

    order, rejections, rank5_observations = module._affordable_replacement_order(
        skipped_row={
            "action": "skip",
            "reason": "price_too_high_for_slot",
            "signal_day": "2026-07-08",
            "trade_day": "2026-07-09",
            "target_notional_cny": 10_000.0,
        },
        original_pick={"symbol": "002371.SZ", "rank": 1, "score": 3.90},
        inventory=[
            {
                "symbol": "600002.SH",
                "rank": 5,
                "score": 3.84,
                "return_20d_percentile": 0.3,
                "selection_allowed": True,
            }
        ],
        estimated_close_by_symbol={"600002.SH": 8.0},
        selected_symbols={"002371.SZ"},
        config=config,
        strategy_id=QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
    )

    assert order is None
    assert rejections == [
        {
            "symbol": "600002.SH",
            "inventory_rank": 5,
            "reason": "rank5_quality_return20_below_min",
        }
    ]
    assert rank5_observations[0]["shadow_base_eligible"] is True
    assert rank5_observations[0]["selection_decision"] == "shadow_base_eligible_not_selected"


def test_quality_candidate_plans_board_lot_market_exposure_trim(tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'rebalance.db'}"
    init_database(database_url)
    with session_scope(database_url) as session:
        stock = Stock(
            symbol="600001.SH",
            ticker="600001",
            exchange="SH",
            name="测试持仓",
            provider_symbol="600001",
            status="active",
            profile_payload={},
            **build_lineage(
                {"symbol": "600001.SH"},
                source_uri="test://stock/600001",
                license_tag="test",
                usage_scope="test",
                redistribution_scope="none",
            ),
        )
        session.add(stock)
        session.flush()
        session.add(
            MarketBar(
                bar_key="bar-600001-20260708",
                stock_id=stock.id,
                timeframe="1d",
                observed_at=datetime(2026, 7, 8, 15, 0, tzinfo=UTC),
                open_price=100.0,
                high_price=100.0,
                low_price=100.0,
                close_price=100.0,
                volume=1000,
                amount=100000,
                raw_payload={},
                **build_lineage(
                    {"symbol": "600001.SH", "date": "2026-07-08"},
                    source_uri="test://bar/600001.SH",
                    license_tag="test",
                    usage_scope="test",
                    redistribution_scope="none",
                ),
            )
        )
    module = _load_refresh_state_script()
    contract = build_shortpick_v3_rolling_tranche_execution_contract()
    config = next(
        row
        for row in contract["candidate_configurations"]
        if row["config_id"] == QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID
    )
    with session_scope(database_url) as session:
        orders, diagnostics = module._market_exposure_rebalance_orders(
            session=session,
            account_state={
                "cash_cny": 50_000.0,
                "positions": [{"symbol": "600001.SH", "name": "测试持仓", "shares": 1000}],
            },
            planned_buys=[],
            strategy_id=QUALITY_REPLACEMENT_REBALANCE_CONTROL_ID,
            strategy_label="候选对照",
            signal_date="2026-07-08",
            planned_trade_date="2026-07-09",
            config=config,
        )

    assert len(orders) == 1
    assert orders[0]["action"] == "sell"
    assert orders[0]["shares"] == 700
    assert orders[0]["shares"] % 100 == 0
    assert orders[0]["exposure_before"] > 0.25
    assert orders[0]["exposure_after"] <= 0.25
    assert diagnostics[0]["reason"] == "market_value_concentration_rebalance"
