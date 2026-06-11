from __future__ import annotations

import contextlib
import io
import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import ashare_evidence.shortpick_portfolio_backtest as portfolio_backtest
import ashare_evidence.shortpick_strategy_backtest_runner as governance_backtest_runner
from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_portfolio_backtest import (
    DRAWDOWN_REVERSAL_CONTROL_BACKTEST_STRATEGY,
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    REPEATED_EXPOSURE_CONTROL_BACKTEST_STRATEGY,
    SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY,
    STRONG_BREADTH_RANK2_STRATEGY,
    build_shortpick_portfolio_backtest,
)
from ashare_evidence.shortpick_strategy_backtest_runner import run_shortpick_historical_backtest_request
from ashare_evidence.shortpick_strategy_governance import (
    build_shortpick_historical_backtest_generation_requests,
    build_shortpick_retrospective_forward_replay_requests,
    build_shortpick_same_symbol_cooldown_rule,
)


def _lineage(payload: object, uri: str) -> dict[str, str]:
    return {
        "license_tag": "test",
        "usage_scope": "internal-test",
        "redistribution_scope": "none",
        "source_uri": uri,
        "lineage_hash": compute_lineage_hash(payload),
    }


def _seed_long_sample_fixture(database_url: str) -> None:
    start = date(2026, 1, 1)
    symbols = [
        ("600001.SH", "测试动量一", "电子", 10.0, 0.18),
        ("600002.SH", "测试动量二", "电子", 12.0, 0.10),
        ("600003.SH", "测试换手", "机械", 11.0, 0.04),
        ("600004.SH", "测试防守", "医药", 9.0, -0.02),
        ("688001.SH", "测试科创", "电子", 8.0, 0.35),
        ("000300.SH", "沪深300", "benchmark", 100.0, 0.01),
        ("000905.SH", "中证500", "benchmark", 120.0, 0.015),
        ("000852.SH", "中证1000", "benchmark", 80.0, 0.02),
    ]
    with session_scope(database_url) as session:
        for symbol, name, industry, base, drift in symbols:
            ticker, _, exchange = symbol.partition(".")
            stock = Stock(
                symbol=symbol,
                ticker=ticker,
                exchange=exchange,
                name=name,
                provider_symbol=symbol,
                listed_date=date(2020, 1, 1),
                status="active",
                profile_payload={"industry": industry},
                **_lineage({"symbol": symbol}, f"test://stock/{symbol}"),
            )
            session.add(stock)
            session.flush()
            for index in range(70):
                observed_day = start + timedelta(days=index)
                close = base + index * drift + (0.03 if index % 5 == 0 else 0)
                open_price = close - 0.02
                session.add(
                    MarketBar(
                        bar_key=f"shortpick-backtest-bar-{symbol}-{index}",
                        stock_id=stock.id,
                        timeframe="1d",
                        observed_at=datetime(observed_day.year, observed_day.month, observed_day.day, 7, 0, tzinfo=UTC),
                        open_price=open_price,
                        high_price=close + 0.08,
                        low_price=close - 0.08,
                        close_price=close,
                        volume=100_000 + index * 100,
                        amount=(100_000 + index * 100) * close,
                        turnover_rate=0.8 + (index % 10) * 0.02,
                        total_mv=1_000_000_000 + index * 100_000,
                        circ_mv=900_000_000 + index * 100_000,
                        raw_payload={},
                        **_lineage({"symbol": symbol, "index": index}, f"test://bar/{symbol}/{index}"),
                    )
                )


def test_shortpick_portfolio_backtest_compares_daily_and_weekly_modes() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)

        with session_scope(database_url) as session:
            payload = build_shortpick_portfolio_backtest(
                session,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 5),
                min_signal_symbol_count=3,
                benchmark_mode="csi300",
            )

        assert payload["experiment"] == "shortpick_portfolio_backtest"
        assert payload["config"]["account_profile"] == "new_retail_cash_account"
        assert payload["config"]["entry_price_source"] == "next_close"
        assert payload["data_scope"]["raw_stock_like_series_count"] == 5
        assert payload["data_scope"]["stock_like_series_count"] == 4
        assert payload["data_scope"]["account_eligibility"]["excluded_board_counts"]["star"] == 1
        assert payload["data_scope"]["signal_day_count"] > 10
        daily = payload["results"]["daily_rolling_5x10k"]["ret10_turnover_cooldown"]["summary"]
        gated = payload["results"]["daily_rolling_5x10k"]["ret10_turnover_cooldown_market_positive_cooldown"]["summary"]
        second_pick = payload["results"]["daily_rolling_5x10k"]["ret10_turnover_second_market_positive_cooldown_stop8"]["summary"]
        strong_breadth_rank2 = payload["results"]["daily_rolling_5x10k"][STRONG_BREADTH_RANK2_STRATEGY]["summary"]
        low_turnover_uptrend = payload["results"]["daily_rolling_5x10k"][LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY]["summary"]
        top3_equal = payload["results"]["daily_rolling_5x10k"]["ret10_turnover_top3_market_positive_cooldown_equal_weight"]["summary"]
        golden_cross = payload["results"]["daily_rolling_5x10k"]["momentum_volume_golden_cross_10_200"]["summary"]
        weekly = payload["results"]["weekly_concentrated_1x50k"]["ret10_turnover_cooldown"]["summary"]
        assert daily["trade_count"] > weekly["trade_count"]
        assert gated["trade_count"] <= daily["trade_count"]
        assert second_pick["trade_count"] <= daily["trade_count"]
        assert top3_equal["trade_count"] <= second_pick["trade_count"] * 3
        assert isinstance(golden_cross["trade_count"], int)
        assert isinstance(strong_breadth_rank2["trade_count"], int)
        assert isinstance(low_turnover_uptrend["trade_count"], int)
        assert isinstance(second_pick["exit_reason_counts"], dict)
        assert isinstance(second_pick["blocked_exit_count"], int)
        assert daily["max_capital_deployed"] <= 50_000 * 1.5
        assert "000300.SH" in payload["benchmark_references"]
        assert payload["benchmark_references"]["000300.SH"]["available"] is True
        assert payload["benchmark_references"]["000905.SH"]["available"] is True
        assert payload["benchmark_references"]["000852.SH"]["available"] is True
        assert payload["config"]["strategy_variants"]["ret10_turnover_cooldown_market_positive_cooldown"]["base_strategy"] == "ret10_turnover_cooldown"
        assert payload["config"]["strategy_variants"]["ret10_turnover_second_market_positive_cooldown_stop8"]["stop_loss_pct"] == 0.08
        assert payload["config"]["strategy_variants"][STRONG_BREADTH_RANK2_STRATEGY]["candidate_rank"] == 2
        assert payload["config"]["strategy_variants"][LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY]["candidate_rank"] == 1
        assert payload["config"]["strategy_variants"]["ret10_turnover_top3_market_positive_cooldown_equal_weight"]["candidate_rank"] == "top3_equal_weight"
        assert payload["config"]["strategy_variants"]["momentum_volume_golden_cross_10_200"]["technical_filter"] == "10日均线当日上穿200日均线"
        assert payload["comparison"]["recommended"]["mode"] in {"daily_rolling_5x10k", "weekly_concentrated_1x50k"}
        assert all(
            not trade["symbol"].startswith("688")
            for result_by_strategy in payload["results"]["daily_rolling_5x10k"].values()
            for trade in result_by_strategy["trades_sample"]
        )
        assert payload["production_evidence"]["leading_mode"] == "daily_rolling_5x10k"
        assert payload["production_evidence"]["leading_strategy"] == LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY
        assert payload["production_evidence"]["status"] in {
            "paper_tracking_candidate",
            "near_production_needs_forward_tracking",
            "production_evidence_passed",
        }
        assert payload["production_evidence"]["checks"]
        assert "100" in payload["production_evidence"]["cost_stress"]
        assert "ret10" in payload["production_evidence"]["control_comparison"]["daily_rolling_controls"]


def test_shortpick_portfolio_backtest_supports_next_open_and_same_day_proxy_entries() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)

        with session_scope(database_url) as session:
            next_open = build_shortpick_portfolio_backtest(
                session,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 5),
                min_signal_symbol_count=3,
                benchmark_mode="csi300",
                entry_price_source="next_open",
            )
            same_close_proxy = build_shortpick_portfolio_backtest(
                session,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 5),
                min_signal_symbol_count=3,
                benchmark_mode="csi300",
                entry_price_source="same_close_proxy",
            )

        assert next_open["config"]["entry_price_source"] == "next_open"
        assert "开盘价买入" in next_open["config"]["entry_price_source_note"]
        assert same_close_proxy["config"]["entry_price_source"] == "same_close_proxy"
        assert "14点同日买入" in same_close_proxy["config"]["entry_price_source_note"]
        assert next_open["results"]["daily_rolling_5x10k"]["ret10_turnover_cooldown"]["summary"]["trade_count"] > 0
        assert same_close_proxy["results"]["daily_rolling_5x10k"]["ret10_turnover_cooldown"]["summary"]["trade_count"] > 0


def test_cli_shortpick_portfolio_backtest_can_write_output() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        output_path = Path(temp_dir) / "shortpick-portfolio-backtest.json"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-portfolio-backtest",
                    "--database-url",
                    database_url,
                    "--start-date",
                    "2026-01-01",
                    "--end-date",
                    "2026-03-05",
                    "--min-signal-symbol-count",
                    "3",
                    "--benchmark-mode",
                    "csi300",
                    "--entry-price-source",
                    "next_open",
                    "--output",
                    str(output_path),
                ]
            )

        assert exit_code == 0
        rendered = json.loads(stdout.getvalue())
        assert rendered["artifact"]["path"] == str(output_path)
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        assert saved["version"] == "shortpick-portfolio-backtest-v1"
        assert saved["config"]["account_profile"] == "new_retail_cash_account"
        assert saved["config"]["entry_price_source"] == "next_open"
        assert saved["config"]["apply_limit_down_exit_filter"] is True
        assert saved["production_evidence"]["leading_strategy"] == LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY


def test_governance_historical_backtest_runner_blocks_unmapped_control_request() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        output_path = Path(temp_dir) / "blocked-evidence.json"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)
        request = build_shortpick_historical_backtest_generation_requests(
            [build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")],
            start_date="2026-01-01",
            end_date="2026-03-05",
            min_signal_symbol_count=3,
        )["requests"][0]
        request.pop("portfolio_strategies")

        with session_scope(database_url) as session:
            evidence = run_shortpick_historical_backtest_request(
                session,
                request,
                evidence_output_path=output_path,
            )

        assert evidence["status"] == "blocked"
        assert evidence["gate_status"] == "blocked"
        assert evidence["gate_reasons"] == ["no_executable_control_backtest_mapping"]
        assert evidence["leakage_audit_status"] == "blocked"
        assert evidence["paper_tracking_write_policy"] == "forbidden"
        assert evidence["true_forward_tracking_eligible"] is False
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        assert saved["artifact_id"] == evidence["artifact_id"]
        assert not output_path.with_name("blocked-evidence.portfolio-backtest.json").exists()


def test_governance_historical_backtest_runner_executes_explicit_strategy_mapping() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        output_path = Path(temp_dir) / "passed-evidence.json"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)
        request = {
            **build_shortpick_historical_backtest_generation_requests(
                [build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")],
                start_date="2026-01-01",
                end_date="2026-03-05",
                min_signal_symbol_count=3,
            )["requests"][0],
            "portfolio_strategies": ["ret10_turnover_cooldown"],
        }

        with session_scope(database_url) as session:
            evidence = run_shortpick_historical_backtest_request(
                session,
                request,
                evidence_output_path=output_path,
            )

        assert evidence["status"] == "ready"
        assert evidence["gate_status"] == "passed"
        assert evidence["gate_reasons"] == []
        assert evidence["evidence_basis"] == "historical_backtest"
        assert evidence["leakage_audit_status"] == "passed"
        assert evidence["paper_tracking_write_policy"] == "forbidden"
        assert evidence["true_forward_tracking_eligible"] is False
        assert evidence["portfolio_strategies"] == ["ret10_turnover_cooldown"]
        assert any(row["trade_count"] > 0 for row in evidence["metrics_by_mode_strategy"])

        saved = json.loads(output_path.read_text(encoding="utf-8"))
        portfolio_path = Path(saved["portfolio_backtest_artifact_path"])
        portfolio_payload = json.loads(portfolio_path.read_text(encoding="utf-8"))
        assert saved["artifact_id"] == evidence["artifact_id"]
        assert portfolio_payload["version"] == "shortpick-portfolio-backtest-v1"
        assert portfolio_payload["config"]["strategies"] == ["ret10_turnover_cooldown"]


def test_governance_historical_backtest_runner_executes_generated_p3_control_mapping() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        output_path = Path(temp_dir) / "p3-control-evidence.json"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)
        request = build_shortpick_historical_backtest_generation_requests(
            [build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")],
            start_date="2026-01-01",
            end_date="2026-03-05",
            min_signal_symbol_count=3,
        )["requests"][0]

        with session_scope(database_url) as session:
            evidence = run_shortpick_historical_backtest_request(
                session,
                request,
                evidence_output_path=output_path,
            )

        assert evidence["status"] == "ready"
        assert evidence["gate_status"] == "passed"
        assert evidence["leakage_audit_status"] == "passed"
        assert evidence["portfolio_strategies"] == [SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY]
        portfolio_payload = json.loads(Path(evidence["portfolio_backtest_artifact_path"]).read_text(encoding="utf-8"))
        assert portfolio_payload["config"]["strategies"] == [SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY]
        variant = portfolio_payload["config"]["strategy_variants"][SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY]
        assert variant["control_group_id"] == "control_same_symbol_cooldown:v1"


def test_shortpick_portfolio_backtest_supports_registered_p3_control_strategy_mappings() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)

        with session_scope(database_url) as session:
            payload = build_shortpick_portfolio_backtest(
                session,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 5),
                min_signal_symbol_count=3,
                benchmark_mode="csi300",
                strategies=(
                    SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY,
                    DRAWDOWN_REVERSAL_CONTROL_BACKTEST_STRATEGY,
                    REPEATED_EXPOSURE_CONTROL_BACKTEST_STRATEGY,
                ),
            )

        assert payload["config"]["strategies"] == [
            SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY,
            DRAWDOWN_REVERSAL_CONTROL_BACKTEST_STRATEGY,
            REPEATED_EXPOSURE_CONTROL_BACKTEST_STRATEGY,
        ]
        for strategy in payload["config"]["strategies"]:
            assert payload["config"]["strategy_variants"][strategy]["base_strategy"]
            summary = payload["results"]["daily_rolling_5x10k"][strategy]["summary"]
            assert isinstance(summary["trade_count"], int)


def test_shortpick_portfolio_backtest_p3_control_mappings_invoke_control_helpers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)
        calls: list[tuple[str, int, str]] = []

        def fake_same_symbol(
            candidate_rows: list[dict[str, object]],
            completed_outcome_rows: list[dict[str, object]],
            **kwargs: object,
        ) -> dict[str, object]:
            calls.append(("same_symbol", len(completed_outcome_rows), str(kwargs.get("evidence_basis"))))
            return {"rows": [{**row, "cooldown_action": "allowed"} for row in candidate_rows]}

        def fake_drawdown(
            candidate_rows: list[dict[str, object]],
            signal_feature_rows: list[dict[str, object]],
            **kwargs: object,
        ) -> dict[str, object]:
            calls.append(("drawdown", len(signal_feature_rows), str(kwargs.get("evidence_basis"))))
            return {"rows": [{**row, "filter_action": "allowed"} for row in candidate_rows]}

        def fake_exposure(
            candidate_rows: list[dict[str, object]],
            exposure_signal_rows: list[dict[str, object]],
            **kwargs: object,
        ) -> dict[str, object]:
            calls.append(("repeated_exposure", len(exposure_signal_rows), str(kwargs.get("evidence_basis"))))
            return {"rows": [{**row, "exposure_action": "allowed"} for row in candidate_rows]}

        monkeypatch.setattr(portfolio_backtest, "apply_shortpick_same_symbol_cooldown_control", fake_same_symbol)
        monkeypatch.setattr(portfolio_backtest, "apply_shortpick_drawdown_reversal_filter_control", fake_drawdown)
        monkeypatch.setattr(portfolio_backtest, "apply_shortpick_repeated_exposure_limit_control", fake_exposure)

        with session_scope(database_url) as session:
            payload = build_shortpick_portfolio_backtest(
                session,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 5),
                min_signal_symbol_count=3,
                benchmark_mode="csi300",
                strategies=(
                    SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY,
                    DRAWDOWN_REVERSAL_CONTROL_BACKTEST_STRATEGY,
                    REPEATED_EXPOSURE_CONTROL_BACKTEST_STRATEGY,
                ),
            )

        assert [item[0] for item in calls] == ["same_symbol", "drawdown", "repeated_exposure"]
        assert all(item[1] > 0 for item in calls)
        assert all(item[2] == "historical_backtest" for item in calls)
        assert set(payload["results"]["daily_rolling_5x10k"]) == {
            SAME_SYMBOL_COOLDOWN_CONTROL_BACKTEST_STRATEGY,
            DRAWDOWN_REVERSAL_CONTROL_BACKTEST_STRATEGY,
            REPEATED_EXPOSURE_CONTROL_BACKTEST_STRATEGY,
        }


def test_governance_historical_backtest_runner_blocks_leakage_window_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "leakage-failed-evidence.json"
        request = {
            "evidence_basis": "historical_backtest",
            "request_id": "shortpick-historical-backtest-request:test",
            "control_group_id": "control_same_symbol_cooldown:v1",
            "rule_signature": "sha256:test",
            "start_date": "2026-01-10",
            "end_date": "2026-03-05",
            "output_path": str(output_path),
            "portfolio_strategies": ["ret10_turnover_cooldown"],
        }

        def fake_build_shortpick_portfolio_backtest(*args: object, **kwargs: object) -> dict[str, object]:
            return {
                "data_scope": {
                    "signal_day_count": 1,
                    "signal_date_from": "2026-01-09",
                    "signal_date_to": "2026-03-06",
                },
                "results": {
                    "daily_rolling_5x10k": {
                        "ret10_turnover_cooldown": {"summary": {"trade_count": 1}},
                    }
                },
            }

        def fake_write_shortpick_portfolio_backtest(payload: object, *, output_path: str | Path) -> Path:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
            return path

        monkeypatch.setattr(
            governance_backtest_runner,
            "build_shortpick_portfolio_backtest",
            fake_build_shortpick_portfolio_backtest,
        )
        monkeypatch.setattr(
            governance_backtest_runner,
            "write_shortpick_portfolio_backtest",
            fake_write_shortpick_portfolio_backtest,
        )

        evidence = governance_backtest_runner.run_shortpick_historical_backtest_request(
            object(),  # type: ignore[arg-type]
            request,
        )

        assert evidence["status"] == "blocked"
        assert evidence["gate_status"] == "blocked"
        assert "leakage_audit_failed" in evidence["gate_reasons"]
        assert evidence["leakage_audit_status"] == "failed"
        assert evidence["leakage_audit_reasons"] == [
            "signal_date_from_before_requested_start",
            "signal_date_to_after_requested_end",
        ]
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        assert saved["leakage_audit"]["observed_signal_date_from"] == "2026-01-09"
        assert saved["leakage_audit"]["observed_signal_date_to"] == "2026-03-06"


def test_cli_governance_historical_backtest_runs_request_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_url = f"sqlite:///{Path(temp_dir) / 'portfolio-backtest.db'}"
        output_dir = Path(temp_dir) / "evidence"
        request_path = Path(temp_dir) / "request.json"
        init_database(database_url)
        _seed_long_sample_fixture(database_url)
        request = {
            **build_shortpick_historical_backtest_generation_requests(
                [build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")],
                start_date="2026-01-01",
                end_date="2026-03-05",
                min_signal_symbol_count=3,
            )["requests"][0],
            "portfolio_strategies": ["ret10_turnover_cooldown"],
        }
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-governance-historical-backtest",
                    "--database-url",
                    database_url,
                    "--request-path",
                    str(request_path),
                    "--output-dir",
                    str(output_dir),
                ]
            )

        assert exit_code == 0
        rendered = json.loads(stdout.getvalue())
        assert rendered["passed_count"] == 1
        evidence_path = Path(rendered["evidence"][0]["artifact"]["path"])
        assert evidence_path.parent == output_dir
        assert json.loads(evidence_path.read_text(encoding="utf-8"))["gate_status"] == "passed"


def test_cli_governance_retrospective_replay_runs_request_file() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        request_path = Path(temp_dir) / "request.json"
        paper_tracking_path = Path(temp_dir) / "paper-tracking.json"
        output_dir = Path(temp_dir) / "replay"
        rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
        paper_tracking = {
            "items": [
                {
                    "candidate_id": "a",
                    "signal_date": "2026-05-20",
                    "symbol": "002028.SZ",
                    "validation_by_horizon": [
                        {"horizon_days": 10, "status": "completed", "stock_return": -0.09, "exit_date": "2026-05-24"}
                    ],
                },
                {"candidate_id": "b", "signal_date": "2026-05-26", "symbol": "002028.SZ"},
            ]
        }
        request = build_shortpick_retrospective_forward_replay_requests([rule], paper_tracking)["requests"][0]
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        paper_tracking_path.write_text(json.dumps(paper_tracking, ensure_ascii=False), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-governance-retrospective-replay",
                    "--request-path",
                    str(request_path),
                    "--paper-tracking-path",
                    str(paper_tracking_path),
                    "--output-dir",
                    str(output_dir),
                ]
            )

        assert exit_code == 0
        rendered = json.loads(stdout.getvalue())
        assert rendered["ready_count"] == 1
        artifact_path = Path(rendered["artifacts"][0]["artifact"]["path"])
        assert artifact_path.parent == output_dir
        saved = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert saved["evidence_basis"] == "retrospective_forward_replay"
        assert saved["paper_tracking_write_policy"] == "forbidden"


def test_cli_governance_combined_ledger_backfill_materializes_replay_artifact() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        replay_artifact_path = Path(temp_dir) / "replay.json"
        output_path = Path(temp_dir) / "combined-ledger.json"
        rule = build_shortpick_same_symbol_cooldown_rule(rule_defined_at="2026-06-10")
        replay_artifact = {
            "artifact_id": "shortpick-retrospective-forward-replay:test",
            "artifact_type": "shortpick_retrospective_forward_replay",
            "status": "ready",
            "evidence_basis": "retrospective_forward_replay",
            "retrospective": True,
            "request": {
                "control_group_id": rule["control_group_id"],
                "rule_signature": rule["rule_signature"],
                "rule_defined_at": "2026-06-10",
            },
            "rows": [
                {
                    "candidate_id": "a",
                    "signal_date": "2026-05-20",
                    "symbol": "002028.SZ",
                    "control_group_id": rule["control_group_id"],
                    "rule_signature": rule["rule_signature"],
                    "rule_defined_at": "2026-06-10",
                    "leakage_audit_status": "passed",
                }
            ],
        }
        replay_artifact_path.write_text(json.dumps(replay_artifact, ensure_ascii=False), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-governance-combined-ledger-backfill",
                    "--replay-artifact-path",
                    str(replay_artifact_path),
                    "--generated-at",
                    "2026-06-11T12:00:00+08:00",
                    "--output-path",
                    str(output_path),
                ]
            )

        assert exit_code == 0
        rendered = json.loads(stdout.getvalue())
        assert rendered["status"] == "ready"
        assert rendered["artifact"]["path"] == str(output_path)
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        assert saved["artifact_type"] == "shortpick_combined_ledger_backfill"
        assert saved["retrospective_count"] == 1
        assert saved["combined_rows"][0]["evidence_basis"] == "retrospective_forward_replay"
        assert saved["combined_rows"][0]["paper_tracking_write_policy"] == (
            "combined_ledger_backfill_only_with_evidence_basis"
        )


def test_cli_governance_retirement_artifact_writes_ready_artifact() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        evidence_path = Path(temp_dir) / "evidence.json"
        recommendation_path = Path(temp_dir) / "recommendations.json"
        output_path = Path(temp_dir) / "retirement.json"
        strategy_id = "strategy:test"
        evidence = {
            "packs": [
                {
                    "strategy_id": strategy_id,
                    "evidence_basis": "true_forward_tracking",
                    "historical_evidence": {"evidence_basis": "historical_backtest"},
                }
            ]
        }
        recommendations = {
            "recommendations": [
                {
                    "strategy_id": strategy_id,
                    "recommended_status": "retire_candidate",
                    "reasons": ["historical_after_cost_excess_negative"],
                }
            ]
        }
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
        recommendation_path.write_text(json.dumps(recommendations, ensure_ascii=False), encoding="utf-8")

        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(
                [
                    "shortpick-governance-retirement-artifact",
                    "--evidence-pack-path",
                    str(evidence_path),
                    "--status-recommendation-path",
                    str(recommendation_path),
                    "--strategy-id",
                    strategy_id,
                    "--decision-log-ref",
                    "docs/DECISIONS.md#2026-06-11-retirement",
                    "--evidence-snapshot-ref",
                    "output/shortpick/evidence.json",
                    "--retired-at",
                    "2026-06-11T12:00:00+08:00",
                    "--output-path",
                    str(output_path),
                ]
            )

        assert exit_code == 0
        rendered = json.loads(stdout.getvalue())
        assert rendered["status"] == "ready"
        assert rendered["artifact"]["path"] == str(output_path)
        saved = json.loads(output_path.read_text(encoding="utf-8"))
        assert saved["artifact_family"] == "shortpick_strategy_retirement"
        assert saved["strategy_id"] == strategy_id
        assert saved["retirement_reason_code"] == "persistent_negative_after_cost_excess"
        assert saved["evidence_basis_refs"] == ["historical_backtest", "true_forward_tracking"]
