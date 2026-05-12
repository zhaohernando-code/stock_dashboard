from __future__ import annotations

import contextlib
import io
import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from ashare_evidence.cli import main
from ashare_evidence.db import init_database, session_scope
from ashare_evidence.lineage import compute_lineage_hash
from ashare_evidence.models import MarketBar, Stock
from ashare_evidence.shortpick_portfolio_backtest import (
    LOW_TURNOVER_UPTREND_PORTFOLIO_STRATEGY,
    STRONG_BREADTH_RANK2_STRATEGY,
    build_shortpick_portfolio_backtest,
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
