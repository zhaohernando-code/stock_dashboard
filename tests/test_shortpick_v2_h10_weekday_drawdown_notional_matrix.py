from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_market_factor_study import _Bar, _Series
from ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix import (
    DEFAULT_NOTIONAL_VALUES,
    WEEKDAY_MODE_SPECS,
    _build_rank2_primary_top5_selections,
    build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series,
    validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact,
    validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload,
    write_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact,
)


def test_h10_weekday_drawdown_notional_matrix_builds_36_research_rows(monkeypatch) -> None:
    days = [date(2026, 1, 7) + timedelta(days=index) for index in range(24)]
    signal_days = [date(2026, 1, 7), date(2026, 1, 8)]
    symbols = [f"60000{index}.SH" for index in range(1, 7)]
    series_by_symbol = {symbol: _series(symbol, days, start_price=8.0 + index) for index, symbol in enumerate(symbols)}

    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._build_strategy_selections",
        lambda *args, **kwargs: {signal_day: symbols for signal_day in signal_days},
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._regime_features_by_day",
        lambda *args, **kwargs: {signal_day: {"pool_ret1_mean": 0.12} for signal_day in signal_days},
    )

    artifact = build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=days,
        start_date=days[0],
        end_date=days[-5],
        generated_at=datetime(2026, 6, 16, 4, 0, tzinfo=UTC),
        initial_cash=200_000.0,
    )

    assert artifact["artifact_family"] == "shortpick_v2_h10_weekday_drawdown_notional_matrix"
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["analysis_scope"]["horizon_days"] == 10
    assert artifact["analysis_scope"]["promotion_status"] == "research_only_no_paper_tracking_promotion"
    assert len(artifact["matrix_rows"]) == 36
    assert {row["weekday_mode"] for row in artifact["matrix_rows"]} == {"mtw", "all_weekdays"}
    assert {row["drawdown_mode"] for row in artifact["matrix_rows"]} == {"off", "v1_on"}
    assert {row["target_notional"] for row in artifact["matrix_rows"]} == set(DEFAULT_NOTIONAL_VALUES)
    assert all(row["target_notional"] > 0 for row in artifact["matrix_rows"])
    assert all("delay" not in action for row in artifact["matrix_rows"] for action in row["allowed_actions"])
    assert artifact["drawdown_reversal_rule"]["rule_version"] == "drawdown-reversal-filter-v1"
    assert validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload(artifact)["status"] == "passed"
    assert "周一至周五" in json.dumps(artifact, ensure_ascii=False)


def test_h10_weekday_drawdown_notional_matrix_keeps_degenerate_drawdown_rows(monkeypatch) -> None:
    days = [date(2026, 1, 7) + timedelta(days=index) for index in range(24)]
    signal_days = [date(2026, 1, 7)]
    symbols = [f"60001{index}.SH" for index in range(1, 7)]
    series_by_symbol = {symbol: _series(symbol, days, start_price=10.0 + index) for index, symbol in enumerate(symbols)}

    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._build_strategy_selections",
        lambda *args, **kwargs: {signal_day: symbols for signal_day in signal_days},
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._regime_features_by_day",
        lambda *args, **kwargs: {signal_day: {"pool_ret1_mean": 0.12} for signal_day in signal_days},
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._drawdown_reversal_feature_rows",
        lambda _series_by_symbol, selections: [
            {
                "symbol": symbol,
                "feature_date": signal_day.isoformat(),
                "recent_drawdown_return": -0.12,
                "short_window_return": -0.05,
                "price_vs_ma20": -0.01,
                "high_level_reversal_return": -0.08,
            }
            for signal_day, selected_symbols in selections.items()
            for symbol in selected_symbols
        ],
    )

    artifact = build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=days,
        start_date=days[0],
        end_date=days[-5],
        generated_at=datetime(2026, 6, 16, 4, 30, tzinfo=UTC),
        initial_cash=200_000.0,
    )

    drawdown_rows = [row for row in artifact["matrix_rows"] if row["drawdown_mode"] == "v1_on"]
    assert len(drawdown_rows) == 18
    assert {row["degenerate_label_cn"] for row in drawdown_rows} == {"全跳过"}
    assert all(row["drawdown_filter_summary"]["blocked_count"] > 0 for row in drawdown_rows)
    assert validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_payload(artifact)["status"] == "passed"


def test_h10_weekday_drawdown_notional_selection_respects_weekday_and_pool_hot() -> None:
    wednesday = date(2026, 1, 7)
    thursday = date(2026, 1, 8)
    quiet_base = {
        wednesday: ["rank1", "rank2", "rank3", "rank4", "rank5", "rank6"],
        thursday: ["rank1", "rank2", "rank3", "rank4", "rank5", "rank6"],
    }

    mtw = _build_rank2_primary_top5_selections(
        [wednesday, thursday],
        quiet_base_selections=quiet_base,
        regime_features={
            wednesday: {"pool_ret1_mean": 0.12},
            thursday: {"pool_ret1_mean": 0.12},
        },
        weekday_spec=WEEKDAY_MODE_SPECS["mtw"],
    )
    all_weekdays_cool_pool = _build_rank2_primary_top5_selections(
        [wednesday, thursday],
        quiet_base_selections=quiet_base,
        regime_features={
            wednesday: {"pool_ret1_mean": 0.08},
            thursday: {"pool_ret1_mean": 0.12},
        },
        weekday_spec=WEEKDAY_MODE_SPECS["all_weekdays"],
    )

    assert mtw[wednesday] == ["rank2", "rank3", "rank4", "rank5", "rank6"]
    assert mtw[thursday] == []
    assert all_weekdays_cool_pool[wednesday] == []
    assert all_weekdays_cool_pool[thursday] == ["rank2", "rank3", "rank4", "rank5", "rank6"]


def test_h10_weekday_drawdown_notional_matrix_write_validate_and_cli_parser(tmp_path: Path, monkeypatch) -> None:
    days = [date(2026, 1, 7) + timedelta(days=index) for index in range(24)]
    signal_days = [date(2026, 1, 7)]
    symbols = [f"60002{index}.SH" for index in range(1, 7)]
    series_by_symbol = {symbol: _series(symbol, days, start_price=9.0 + index) for index, symbol in enumerate(symbols)}

    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._build_strategy_selections",
        lambda *args, **kwargs: {signal_day: symbols for signal_day in signal_days},
    )
    monkeypatch.setattr(
        "ashare_evidence.shortpick_v2_h10_weekday_drawdown_notional_matrix._regime_features_by_day",
        lambda *args, **kwargs: {signal_day: {"pool_ret1_mean": 0.12} for signal_day in signal_days},
    )
    artifact = build_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=days,
        start_date=days[0],
        end_date=days[-5],
        generated_at=datetime(2026, 6, 16, 5, 0, tzinfo=UTC),
        initial_cash=200_000.0,
    )
    paths = write_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
        artifact,
        output_path=tmp_path / "matrix.json",
        summary_path=tmp_path / "matrix.md",
    )

    assert "shortpick-v2-h10-weekday-drawdown-notional-matrix-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-h10-weekday-drawdown-notional-matrix",
            "--horizon-days",
            "10",
            "--output",
            str(tmp_path / "generated.json"),
        ]
    )
    assert args.horizon_days == 10
    assert args.output == str(tmp_path / "generated.json")

    validation = validate_shortpick_v2_h10_weekday_drawdown_notional_matrix_artifact(
        artifact_path=paths["artifact"],
    )
    assert validation["status"] == "passed"
    assert Path(paths["summary"]).read_text(encoding="utf-8").startswith("# 试验田 v2 H10 参数验证矩阵")


def _series(symbol: str, days: list[date], *, start_price: float) -> _Series:
    bars = [
        _Bar(
            day=day,
            open=start_price + index * 0.1,
            high=(start_price + index * 0.1) * 1.01,
            low=(start_price + index * 0.1) * 0.99,
            close=start_price + index * 0.1,
            amount=2_000_000.0,
            turnover=1.0,
        )
        for index, day in enumerate(days)
    ]
    return _Series(
        symbol=symbol,
        name=f"Test {symbol}",
        industry="test",
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )
