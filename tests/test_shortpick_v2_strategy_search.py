from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import jsonschema
import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_market_factor_study import _Bar, _Series
from ashare_evidence.shortpick_v2_rule_selection import build_shortpick_v2_rule_selection_artifact
from ashare_evidence.shortpick_v2_strategy_search import (
    H10_QUIET_CANDIDATE_SOURCE_IDS,
    NEXT_ROUND_CANDIDATE_SOURCE_IDS,
    REFINED_ROUND_CANDIDATE_SOURCE_IDS,
    StrategySearchCandidateSource,
    build_h10_quiet_strategy_search_candidate_sources,
    build_next_strategy_search_candidate_sources,
    build_refined_strategy_search_candidate_sources,
    build_shortpick_v2_strategy_search_artifact_from_series,
)


def _series(symbol: str, prices: list[float]) -> _Series:
    start = date(2026, 1, 1)
    bars = [
        _Bar(
            day=start + timedelta(days=index),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            amount=1_000_000.0,
            turnover=1.0,
        )
        for index, price in enumerate(prices)
    ]
    return _Series(
        symbol=symbol,
        name=f"Test {symbol}",
        industry="test",
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )


def _artifact() -> dict[str, object]:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(8)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", [10, 11, 12, 12, 13, 14, 14, 15]),
        "600002.SH": _series("600002.SH", [19, 20, 21, 21, 22, 22, 23, 24]),
    }
    control = StrategySearchCandidateSource(
        source_id="low_turnover_20d_uptrend_liquid_top120",
        source_ref="market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1",
        selections={days[2]: ["600001.SH", "600002.SH"]},
    )
    quiet = StrategySearchCandidateSource(
        source_id="quiet_breakout_rank2",
        source_ref="market_only_reconstruction:quiet_breakout_rank2:v1",
        selections={days[2]: ["600002.SH", "600001.SH"]},
    )
    return build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=[days[2]],
        trade_days=days[2:7],
        candidate_sources=(control, quiet),
        start_date=days[0],
        end_date=days[6],
        initial_cash=20_000.0,
        horizon_days=2,
        account_profile="new_retail_cash_account",
        generated_at=datetime(2026, 6, 14, 3, 0, tzinfo=UTC),
    )


def test_strategy_search_artifact_merges_controls_and_prefixed_configs() -> None:
    artifact = _artifact()

    result_ids = [result["config_id"] for result in artifact["results"]]  # type: ignore[index]
    assert artifact["artifact_family"] == "shortpick_v2_replay_artifact"
    assert artifact["artifact_id"] == (
        "shortpick_v2_replay_artifact:strategy_search:2026-01-01:2026-01-07:20000:2026-06-14"
    )
    assert len(result_ids) == len(set(result_ids)) == 10
    assert "top1_or_skip_v1" in result_ids
    assert "conservative_cash_reserve_60k_top5_v1" in result_ids
    assert "quiet_breakout_rank2__top1_or_skip_v1" in result_ids
    assert artifact["input_contracts"]["candidate_source"]["source_ref"] == (  # type: ignore[index]
        "market_only_reconstruction:shortpick_v2_strategy_search_batch:v1"
    )
    assert "No delayed-entry" in json.dumps(artifact, ensure_ascii=False)


def test_strategy_search_artifact_validates_schema_and_rule_selection_compatibility() -> None:
    schema = json.loads(
        Path("docs/contracts/registry/schemas/shortpick_v2_replay_artifact.schema.json").read_text(encoding="utf-8")
    )
    artifact = _artifact()

    jsonschema.Draft202012Validator(schema).validate(artifact)
    selection = build_shortpick_v2_rule_selection_artifact(
        artifact,
        replay_artifact_path="/tmp/strategy-search.json",
        generated_at=datetime(2026, 6, 14, 4, 0, tzinfo=UTC),
    )

    assert selection["source_replay_artifact"]["path"] == "/tmp/strategy-search.json"
    assert [item["config_id"] for item in selection["baseline_configs"]] == ["top1_or_skip_v1"]
    assert "quiet_breakout_rank2__top1_or_skip_v1" in {
        item["config_id"] for item in selection["gate_results"]
    }


def test_shortpick_v2_strategy_search_cli_parser_defaults_to_search_output() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-strategy-search"])

    assert args.initial_cash == 200_000.0
    assert args.entry_price_source == "next_close"
    assert args.candidate_batch == "initial"
    assert args.output == "output/shortpick-v2-strategy-search-replay-artifact.json"


def test_shortpick_v2_strategy_search_cli_parser_accepts_next_batch() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-strategy-search", "--candidate-batch", "next"])

    assert args.candidate_batch == "next"


def test_shortpick_v2_strategy_search_cli_parser_accepts_refined_batch() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-strategy-search", "--candidate-batch", "refined"])

    assert args.candidate_batch == "refined"


def test_shortpick_v2_strategy_search_cli_parser_accepts_h10_quiet_batch() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-strategy-search", "--candidate-batch", "h10_quiet"])

    assert args.candidate_batch == "h10_quiet"


def test_h10_quiet_strategy_search_requires_ten_day_horizon() -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(8)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", [10, 11, 12, 12, 13, 14, 14, 15]),
        "600002.SH": _series("600002.SH", [19, 20, 21, 21, 22, 22, 23, 24]),
    }
    control = StrategySearchCandidateSource(
        source_id="low_turnover_20d_uptrend_liquid_top120",
        source_ref="market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1",
        selections={days[2]: ["600001.SH"]},
    )

    with pytest.raises(ValueError, match="h10_quiet requires horizon_days=10"):
        build_shortpick_v2_strategy_search_artifact_from_series(
            series_by_symbol,
            signal_days=[days[2]],
            trade_days=days[2:7],
            candidate_sources=(control,),
            start_date=days[0],
            end_date=days[6],
            initial_cash=20_000.0,
            horizon_days=2,
            account_profile="new_retail_cash_account",
            candidate_batch="h10_quiet",
            generated_at=datetime(2026, 6, 14, 3, 0, tzinfo=UTC),
        )


def test_next_strategy_search_candidate_sources_include_expected_batch_ids() -> None:
    days = [date(2025, 1, 1) + timedelta(days=index) for index in range(140)]
    series_by_symbol = {
        "000300.SH": _series("000300.SH", [100 + index * 0.15 for index in range(140)]),
        "600001.SH": _series("600001.SH", [10 + index * 0.04 for index in range(140)]),
        "600002.SH": _series("600002.SH", [12 + index * 0.05 for index in range(140)]),
    }

    sources = build_next_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=days[125:130],
        pool_limit=40,
        rank_limit=6,
    )

    assert [source.source_id for source in sources] == [
        "low_turnover_20d_uptrend_liquid_top120",
        *NEXT_ROUND_CANDIDATE_SOURCE_IDS,
    ]


def test_refined_strategy_search_candidate_sources_include_expected_batch_ids() -> None:
    days = [date(2025, 1, 1) + timedelta(days=index) for index in range(140)]
    series_by_symbol = {
        "000300.SH": _series("000300.SH", [100 + index * 0.15 for index in range(140)]),
        "600001.SH": _series("600001.SH", [10 + index * 0.04 for index in range(140)]),
        "600002.SH": _series("600002.SH", [12 + index * 0.05 for index in range(140)]),
    }

    sources = build_refined_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=days[125:130],
        pool_limit=40,
        rank_limit=6,
    )

    assert [source.source_id for source in sources] == [
        "low_turnover_20d_uptrend_liquid_top120",
        *REFINED_ROUND_CANDIDATE_SOURCE_IDS,
    ]


def test_h10_quiet_strategy_search_candidate_sources_include_expected_batch_ids() -> None:
    days = [date(2025, 1, 1) + timedelta(days=index) for index in range(140)]
    series_by_symbol = {
        "000300.SH": _series("000300.SH", [100 + index * 0.15 for index in range(140)]),
        "600001.SH": _series("600001.SH", [10 + index * 0.04 for index in range(140)]),
        "600002.SH": _series("600002.SH", [12 + index * 0.05 for index in range(140)]),
    }

    sources = build_h10_quiet_strategy_search_candidate_sources(
        series_by_symbol,
        signal_days=days[125:130],
        pool_limit=40,
        rank_limit=6,
    )

    assert [source.source_id for source in sources] == [
        "low_turnover_20d_uptrend_liquid_top120",
        *H10_QUIET_CANDIDATE_SOURCE_IDS,
    ]
