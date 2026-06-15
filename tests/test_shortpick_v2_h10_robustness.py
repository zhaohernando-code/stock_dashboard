from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import jsonschema

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_market_factor_study import _Bar, _Series
from ashare_evidence.shortpick_v2_h10_robustness import (
    DIAGNOSTIC_ANALYSIS_ROLE,
    H10_QUIET_DIAGNOSTIC_CONFIG_IDS,
    _risk_flags,
    build_shortpick_v2_h10_robustness_artifact_from_series,
    write_shortpick_v2_h10_robustness_artifact,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_BENCHMARK_CONFIG_IDS,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)
from ashare_evidence.shortpick_v2_strategy_search import (
    CONTROL_CANDIDATE_SOURCE_ID,
    H10_QUIET_CANDIDATE_SOURCE_IDS,
    H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS,
    StrategySearchCandidateSource,
    build_shortpick_v2_strategy_search_artifact_from_series,
)


def _series(symbol: str, prices: list[float], industry: str = "test") -> _Series:
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
        industry=industry,
        bars=bars,
        by_day={bar.day: index for index, bar in enumerate(bars)},
    )


def _selection_artifact(replay_artifact: dict[str, object], selected_config_id: str) -> dict[str, object]:
    return _selection_artifact_with_benchmarks(replay_artifact, selected_config_id, benchmark_config_ids=())


def _selection_artifact_with_benchmarks(
    replay_artifact: dict[str, object],
    selected_config_id: str,
    *,
    benchmark_config_ids: tuple[str, ...],
) -> dict[str, object]:
    results_by_id = {
        str(result["config_id"]): result
        for result in replay_artifact["results"]  # type: ignore[index]
    }

    def selection_row(config_id: str, *, role: str, selection_rank: int | None) -> dict[str, object]:
        result = results_by_id[config_id]
        return {
            "config_id": config_id,
            "role": role,
            "selection_rank": selection_rank,
            "gate_status": "passed",
            "reason": "test",
            "summary": result["summary"],
        }

    return {
        "artifact_family": "shortpick_v2_rule_selection_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_rule_selection_artifact:test",
        "generated_at": "2026-06-14T09:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_selection",
        "source_plan_ref": "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-4",
        "source_replay_artifact": {"artifact_id": replay_artifact["artifact_id"]},
        "selection_policy": {},
        "gate_results": [],
        "benchmark_configs": [
            selection_row(config_id, role="benchmark_control", selection_rank=None)
            for config_id in benchmark_config_ids
        ],
        "selected_configs": [
            selection_row(selected_config_id, role="phase5_contract_candidate", selection_rank=1)
        ],
        "baseline_configs": [],
        "holdout_configs": [],
        "rejected_configs": [],
        "leakage_audit": {"status": "passed"},
        "research_labeling": {},
        "event_refs": ["shortpick_v2.phase4.rule_selection.generated"],
    }


def test_shortpick_v2_h10_robustness_replays_selected_config_and_validates_schema(
    tmp_path: Path,
) -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(60)]
    prices_a = [10.0 + index * 0.12 for index in range(60)]
    prices_b = [14.0 + index * 0.03 for index in range(60)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", prices_a, industry="alpha"),
        "600002.SH": _series("600002.SH", prices_b, industry="beta"),
    }
    signal_days = days[5:25]
    trade_days = days[5:45]
    selections = {signal_day: ["600001.SH", "600002.SH"] for signal_day in signal_days}
    control_source = StrategySearchCandidateSource(
        source_id=CONTROL_CANDIDATE_SOURCE_ID,
        source_ref="market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1",
        selections=selections,
    )
    source_id = H10_QUIET_CANDIDATE_SOURCE_IDS[0]
    quiet_source = StrategySearchCandidateSource(
        source_id=source_id,
        source_ref=f"market_only_reconstruction:shortpick_v2_h10_quiet_round:{source_id}",
        selections=selections,
    )
    replay_artifact = build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, quiet_source),
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        account_profile="new_retail_cash_account",
        candidate_batch="h10_quiet",
        generated_at=datetime(2026, 6, 14, 8, 0, tzinfo=UTC),
    )
    selected_config_id = f"{source_id}__fixed_notional_70k_top5_h10_v1"
    selection_artifact = _selection_artifact(replay_artifact, selected_config_id)

    artifact = build_shortpick_v2_h10_robustness_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, quiet_source),
        replay_artifact=replay_artifact,
        selection_artifact=selection_artifact,
        replay_artifact_path=tmp_path / "replay.json",
        selection_artifact_path=tmp_path / "selection.json",
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        generated_at=datetime(2026, 6, 14, 10, 0, tzinfo=UTC),
    )

    assert artifact["artifact_family"] == "shortpick_v2_h10_robustness_artifact"
    assert artifact["status"] == "ready"
    assert artifact["recommendation"]["status"] in {
        "candidate_requires_forward_tracking",
        "not_ready_for_paper_tracking",
    }
    assert artifact["analyzed_configs"][0]["config_id"] == selected_config_id
    assert artifact["analyzed_configs"][0]["source_replay_consistency"]["status"] == "passed"
    assert artifact["period_reset_results"]["yearly"]
    assert artifact["analyzed_configs"][0]["trade_contribution_stress"][0]["method"] == (
        "post_hoc_trade_pnl_subtraction_not_resimulated"
    )

    schema = json.loads(
        Path("docs/contracts/registry/schemas/shortpick_v2_h10_robustness_artifact.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.Draft202012Validator(schema).validate(artifact)
    output_path = write_shortpick_v2_h10_robustness_artifact(artifact, output_path=tmp_path / "robustness.json")
    assert json.loads(output_path.read_text(encoding="utf-8"))["artifact_id"] == artifact["artifact_id"]

    drifted_replay_artifact = deepcopy(replay_artifact)
    drifted_result = next(
        result for result in drifted_replay_artifact["results"] if result["config_id"] == selected_config_id
    )
    drifted_result["summary"]["total_return"] = 999.0
    drifted_artifact = build_shortpick_v2_h10_robustness_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, quiet_source),
        replay_artifact=drifted_replay_artifact,
        selection_artifact=selection_artifact,
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        generated_at=datetime(2026, 6, 14, 10, 0, tzinfo=UTC),
    )

    assert drifted_artifact["leakage_audit"]["status"] == "failed"
    assert drifted_artifact["analyzed_configs"][0]["source_replay_consistency"]["status"] == "failed"
    assert {
        flag["flag_id"] for flag in drifted_artifact["risk_flags"]
    } >= {"source_replay_consistency_failed"}


def test_shortpick_v2_h10_robustness_accepts_quiet_champion_microgrid_sources() -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(60)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", [10.0 + index * 0.12 for index in range(60)]),
        "600002.SH": _series("600002.SH", [14.0 + index * 0.03 for index in range(60)]),
    }
    signal_days = days[5:25]
    trade_days = days[5:45]
    selections = {signal_day: ["600001.SH", "600002.SH"] for signal_day in signal_days}
    control_source = StrategySearchCandidateSource(
        source_id=CONTROL_CANDIDATE_SOURCE_ID,
        source_ref="market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1",
        selections=selections,
    )
    source_id = H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS[1]
    champion_source = StrategySearchCandidateSource(
        source_id=source_id,
        source_ref=f"market_only_reconstruction:shortpick_v2_h10_quiet_champion_round:{source_id}",
        selections=selections,
    )
    replay_artifact = build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, champion_source),
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        account_profile="new_retail_cash_account",
        candidate_batch="h10_quiet_champion",
        generated_at=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
    )
    selected_config_id = f"{source_id}__fixed_notional_70k_top5_h10_v1"

    artifact = build_shortpick_v2_h10_robustness_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, champion_source),
        replay_artifact=replay_artifact,
        selection_artifact=_selection_artifact(replay_artifact, selected_config_id),
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        generated_at=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
    )

    assert artifact["status"] == "ready"
    assert any(row["source_id"] == source_id for row in artifact["parameter_stability"]["rows"])


def test_shortpick_v2_h10_robustness_analyzes_benchmarks_before_selected_and_diagnostic_only_90k() -> None:
    days = [date(2026, 1, 1) + timedelta(days=index) for index in range(60)]
    series_by_symbol = {
        "600001.SH": _series("600001.SH", [10.0 + index * 0.12 for index in range(60)]),
        "600002.SH": _series("600002.SH", [14.0 + index * 0.03 for index in range(60)]),
    }
    signal_days = days[5:25]
    trade_days = days[5:45]
    selections = {signal_day: ["600001.SH", "600002.SH"] for signal_day in signal_days}
    control_source = StrategySearchCandidateSource(
        source_id=CONTROL_CANDIDATE_SOURCE_ID,
        source_ref="market_only_reconstruction:low_turnover_20d_uptrend_liquid_top120:v1",
        selections=selections,
    )
    source_id = H10_QUIET_CHAMPION_CANDIDATE_SOURCE_IDS[0]
    champion_source = StrategySearchCandidateSource(
        source_id=source_id,
        source_ref=f"market_only_reconstruction:shortpick_v2_h10_quiet_champion_round:{source_id}",
        selections=selections,
    )
    replay_artifact = build_shortpick_v2_strategy_search_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, champion_source),
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        account_profile="new_retail_cash_account",
        candidate_batch="h10_quiet_champion",
        generated_at=datetime(2026, 6, 15, 8, 0, tzinfo=UTC),
    )
    selected_config_id = f"{source_id}__fixed_notional_70k_top5_h10_v1"

    artifact = build_shortpick_v2_h10_robustness_artifact_from_series(
        series_by_symbol,
        signal_days=signal_days,
        trade_days=trade_days,
        candidate_sources=(control_source, champion_source),
        replay_artifact=replay_artifact,
        selection_artifact=_selection_artifact_with_benchmarks(
            replay_artifact,
            selected_config_id,
            benchmark_config_ids=H10_QUIET_BENCHMARK_CONFIG_IDS,
        ),
        start_date=days[0],
        end_date=days[44],
        initial_cash=200_000.0,
        horizon_days=10,
        generated_at=datetime(2026, 6, 15, 10, 0, tzinfo=UTC),
    )

    analyzed = artifact["analyzed_configs"]
    assert [row["config_id"] for row in analyzed[:3]] == [
        H10_QUIET_CHAMPION_CONFIG_ID,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
        H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
    ]
    role_by_config = {row["config_id"]: row["role"] for row in analyzed}
    assert role_by_config[H10_QUIET_CHAMPION_CONFIG_ID] == "benchmark_control"
    assert role_by_config[H10_QUIET_CAPITAL_SHADOW_CONFIG_ID] == "benchmark_control"
    assert role_by_config[H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]] == DIAGNOSTIC_ANALYSIS_ROLE
    assert role_by_config[selected_config_id] == "phase5_contract_candidate"

    yearly_config_ids = {row["config_id"] for row in artifact["period_reset_results"]["yearly"]}
    assert set(H10_QUIET_BENCHMARK_CONFIG_IDS) <= yearly_config_ids
    assert H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0] in yearly_config_ids
    assert all(
        next(row for row in analyzed if row["config_id"] == config_id)["trade_contribution_stress"]
        for config_id in H10_QUIET_BENCHMARK_CONFIG_IDS
    )


def test_shortpick_v2_h10_robustness_risk_targets_benchmarks_when_available() -> None:
    selected_config_id = "quiet_breakout_rank2_poolhot10_mtw__fixed_notional_70k_top5_h10_v1"
    diagnostic_config_id = H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]
    full_results = [
        _risk_result(H10_QUIET_CHAMPION_CONFIG_ID, role="benchmark_control"),
        _risk_result(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, role="benchmark_control"),
        _risk_result(selected_config_id, role="phase5_contract_candidate"),
        _risk_result(diagnostic_config_id, role=DIAGNOSTIC_ANALYSIS_ROLE),
    ]

    flags = _risk_flags(
        full_results,
        period_reset_results={
            "yearly": [
                _period_row(H10_QUIET_CHAMPION_CONFIG_ID, annualized_return=0.10),
                _period_row(selected_config_id, annualized_return=0.05),
                _period_row(diagnostic_config_id, annualized_return=0.04),
            ],
            "quarterly": [],
        },
        market_reference_total_return=0.20,
    )

    flag_config_ids = {flag.get("config_id") for flag in flags}
    assert H10_QUIET_CHAMPION_CONFIG_ID in flag_config_ids
    assert selected_config_id not in flag_config_ids
    assert diagnostic_config_id not in flag_config_ids


def test_shortpick_v2_h10_robustness_cli_parser_defaults_to_h10_quiet_artifacts() -> None:
    args = cli_module.build_parser().parse_args(["shortpick-v2-h10-robustness"])

    assert args.replay_artifact == "output/shortpick-v2-h10-quiet-strategy-search-replay-artifact.json"
    assert args.selection_artifact == "output/shortpick-v2-h10-quiet-sparse-selection-artifact.json"
    assert args.horizon_days == 10
    assert args.output == "output/shortpick-v2-h10-quiet-robustness-artifact.json"


def _risk_result(config_id: str, *, role: str) -> dict[str, object]:
    return {
        "config_id": config_id,
        "role": role,
        "source_replay_consistency": {"status": "passed"},
        "symbol_concentration": {"largest_abs_pnl_share": 0.40},
        "trade_contribution_stress": [
            {
                "remove_top_winner_count": 1,
                "annualized_return_proxy": 0.10,
                "market_excess_total_return_proxy": -0.10,
            }
        ],
    }


def _period_row(config_id: str, *, annualized_return: float) -> dict[str, object]:
    return {
        "period_id": "2026",
        "config_id": config_id,
        "summary": {
            "annualized_return": annualized_return,
            "market_excess_total_return": -0.01,
        },
    }
