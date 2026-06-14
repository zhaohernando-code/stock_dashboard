from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import jsonschema
import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_rule_selection import (
    SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE,
    SELECTION_THRESHOLD_PROFILE_STANDARD,
    build_shortpick_v2_rule_selection_artifact,
    build_shortpick_v2_rule_selection_artifact_from_path,
    write_shortpick_v2_rule_selection_artifact,
)


def _result(
    config_id: str,
    *,
    trade_count: int,
    skip_count: int,
    fallback_trade_count: int,
    total_return: float,
    max_drawdown: float,
    mean_invested_ratio: float,
    turnover: float,
    market_reference_total_return: float | None = None,
) -> dict[str, object]:
    signal_count = 721
    summary = {
        "signal_count": signal_count,
        "trade_count": trade_count,
        "skip_count": skip_count,
        "fallback_trade_count": fallback_trade_count,
        "final_nav": 200_000 * (1 + total_return),
        "total_return": total_return,
        "max_drawdown": max_drawdown,
        "mean_invested_ratio": mean_invested_ratio,
        "max_position_count": 5,
        "turnover": turnover,
        "skipped_ratio": round(skip_count / signal_count, 6),
    }
    if market_reference_total_return is not None:
        summary["market_reference_total_return"] = market_reference_total_return
    return {
        "config_id": config_id,
        "status": "ready",
        "summary": summary,
        "reason_counts": {
            "action:buy_primary": max(trade_count - fallback_trade_count, 0),
            "action:buy_fallback": fallback_trade_count,
            "action:skip": skip_count,
        },
        "decision_samples": [],
        "detail_refs": {},
    }


def _replay_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_replay_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_replay_artifact:2023-04-13:2026-05-08:200000:2026-06-12",
        "generated_at": "2026-06-12T08:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay",
        "source_plan_ref": "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-3",
        "data_scope": {
            "signal_day_count": 721,
            "trade_day_count": 761,
            "coverage_status": "complete",
        },
        "input_contracts": {},
        "rule_matrix": [],
        "results": [
            _result(
                "top1_or_skip_v1",
                trade_count=212,
                skip_count=509,
                fallback_trade_count=0,
                total_return=0.113162,
                max_drawdown=-0.308438,
                mean_invested_ratio=0.352473,
                turnover=52.105779,
            ),
            _result(
                "top3_fallback_v1",
                trade_count=352,
                skip_count=369,
                fallback_trade_count=143,
                total_return=0.26501,
                max_drawdown=-0.327548,
                mean_invested_ratio=0.526949,
                turnover=79.638865,
            ),
            _result(
                "fixed_notional_40k_top5_v1",
                trade_count=398,
                skip_count=323,
                fallback_trade_count=126,
                total_return=0.249952,
                max_drawdown=-0.325321,
                mean_invested_ratio=0.421972,
                turnover=62.040153,
            ),
            _result(
                "position_cap_utilization_top5_v1",
                trade_count=372,
                skip_count=349,
                fallback_trade_count=156,
                total_return=0.213425,
                max_drawdown=-0.382083,
                mean_invested_ratio=0.525921,
                turnover=75.0798,
            ),
            _result(
                "conservative_cash_reserve_60k_top5_v1",
                trade_count=363,
                skip_count=358,
                fallback_trade_count=139,
                total_return=0.245516,
                max_drawdown=-0.261957,
                mean_invested_ratio=0.386994,
                turnover=59.527422,
            ),
        ],
        "promotion_gate": {"status": "not_evaluated"},
        "leakage_audit": {"status": "passed"},
        "event_refs": ["shortpick_v2.phase3.replay_artifact.generated"],
    }


def _qualified_replay_artifact() -> dict[str, object]:
    market_reference_total_return = 0.45
    return {
        **_replay_artifact(),
        "results": [
            _result(
                "top1_or_skip_v1",
                trade_count=212,
                skip_count=509,
                fallback_trade_count=0,
                total_return=0.35,
                max_drawdown=-0.308438,
                mean_invested_ratio=0.352473,
                turnover=52.105779,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "top3_fallback_v1",
                trade_count=352,
                skip_count=369,
                fallback_trade_count=143,
                total_return=1.25,
                max_drawdown=-0.327548,
                mean_invested_ratio=0.526949,
                turnover=79.638865,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "fixed_notional_40k_top5_v1",
                trade_count=398,
                skip_count=323,
                fallback_trade_count=126,
                total_return=1.35,
                max_drawdown=-0.325321,
                mean_invested_ratio=0.421972,
                turnover=62.040153,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "position_cap_utilization_top5_v1",
                trade_count=372,
                skip_count=349,
                fallback_trade_count=156,
                total_return=1.4,
                max_drawdown=-0.382083,
                mean_invested_ratio=0.525921,
                turnover=75.0798,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "conservative_cash_reserve_60k_top5_v1",
                trade_count=363,
                skip_count=358,
                fallback_trade_count=139,
                total_return=1.45,
                max_drawdown=-0.261957,
                mean_invested_ratio=0.386994,
                turnover=59.527422,
                market_reference_total_return=market_reference_total_return,
            ),
        ],
    }


def test_shortpick_v2_rule_selection_blocks_missing_market_reference_and_annualized_floor() -> None:
    artifact = build_shortpick_v2_rule_selection_artifact(
        _replay_artifact(),
        replay_artifact_path="/tmp/replay.json",
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )

    assert artifact["artifact_family"] == "shortpick_v2_rule_selection_artifact"
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["status"] == "blocked"
    assert artifact["selected_configs"] == []
    assert [item["config_id"] for item in artifact["baseline_configs"]] == ["top1_or_skip_v1"]
    assert {item["config_id"] for item in artifact["rejected_configs"]} == {
        "conservative_cash_reserve_60k_top5_v1",
        "fixed_notional_40k_top5_v1",
        "position_cap_utilization_top5_v1",
        "top3_fallback_v1",
    }
    conservative = next(
        item for item in artifact["gate_results"] if item["config_id"] == "conservative_cash_reserve_60k_top5_v1"
    )
    failed_checks = {check["check_id"] for check in conservative["checks"] if not check["passed"]}
    assert {"annualized_return", "market_reference_total_return", "market_excess_total_return"} <= failed_checks


def test_shortpick_v2_rule_selection_selects_bounded_risk_first_candidates_when_qualified() -> None:
    artifact = build_shortpick_v2_rule_selection_artifact(
        _qualified_replay_artifact(),
        replay_artifact_path="/tmp/replay.json",
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )

    assert artifact["status"] == "ready"
    assert [item["config_id"] for item in artifact["selected_configs"]] == [
        "conservative_cash_reserve_60k_top5_v1",
        "fixed_notional_40k_top5_v1",
    ]
    assert [item["role"] for item in artifact["selected_configs"]] == [
        "phase5_contract_candidate",
        "phase5_contract_candidate",
    ]
    assert [item["config_id"] for item in artifact["baseline_configs"]] == ["top1_or_skip_v1"]
    assert [item["config_id"] for item in artifact["holdout_configs"]] == ["top3_fallback_v1"]
    assert [item["config_id"] for item in artifact["rejected_configs"]] == ["position_cap_utilization_top5_v1"]
    assert artifact["leakage_audit"]["status"] == "passed"
    assert artifact["research_labeling"]["selected_role_label"] == "phase5_contract_candidate"
    assert artifact["gate_results"][0]["config_id"] == "conservative_cash_reserve_60k_top5_v1"


def test_shortpick_v2_rule_selection_respects_max_selected() -> None:
    artifact = build_shortpick_v2_rule_selection_artifact(
        _qualified_replay_artifact(),
        max_selected=1,
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )

    assert [item["config_id"] for item in artifact["selected_configs"]] == [
        "conservative_cash_reserve_60k_top5_v1"
    ]
    assert [item["config_id"] for item in artifact["holdout_configs"]] == [
        "fixed_notional_40k_top5_v1",
        "top3_fallback_v1",
    ]


def test_shortpick_v2_rule_selection_sparse_profile_allows_high_confidence_sparse_candidates(
    tmp_path: Path,
) -> None:
    market_reference_total_return = 0.45
    replay = {
        **_replay_artifact(),
        "results": [
            _result(
                "top1_or_skip_v1",
                trade_count=212,
                skip_count=509,
                fallback_trade_count=0,
                total_return=0.35,
                max_drawdown=-0.308438,
                mean_invested_ratio=0.352473,
                turnover=52.105779,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "top3_fallback_v1",
                trade_count=190,
                skip_count=531,
                fallback_trade_count=4,
                total_return=2.5,
                max_drawdown=-0.12,
                mean_invested_ratio=0.45,
                turnover=73.0,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "fixed_notional_40k_top5_v1",
                trade_count=170,
                skip_count=551,
                fallback_trade_count=0,
                total_return=2.5,
                max_drawdown=-0.12,
                mean_invested_ratio=0.45,
                turnover=73.0,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "position_cap_utilization_top5_v1",
                trade_count=190,
                skip_count=531,
                fallback_trade_count=0,
                total_return=2.5,
                max_drawdown=-0.40,
                mean_invested_ratio=0.45,
                turnover=73.0,
                market_reference_total_return=market_reference_total_return,
            ),
            _result(
                "conservative_cash_reserve_60k_top5_v1",
                trade_count=190,
                skip_count=531,
                fallback_trade_count=0,
                total_return=2.5,
                max_drawdown=-0.12,
                mean_invested_ratio=0.45,
                turnover=83.0,
                market_reference_total_return=market_reference_total_return,
            ),
        ],
    }
    replay_path = tmp_path / "sparse-replay.json"
    replay_path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")

    standard = build_shortpick_v2_rule_selection_artifact_from_path(
        replay_path,
        threshold_profile=SELECTION_THRESHOLD_PROFILE_STANDARD,
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )
    sparse = build_shortpick_v2_rule_selection_artifact_from_path(
        replay_path,
        threshold_profile=SELECTION_THRESHOLD_PROFILE_SPARSE_HIGH_CONFIDENCE,
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )

    assert standard["selected_configs"] == []
    assert sparse["status"] == "ready"
    assert sparse["selection_policy"]["gate_thresholds"]["threshold_profile"] == "sparse_high_confidence"
    assert sparse["selection_policy"]["gate_thresholds"]["skip_ratio_max"] == 0.75
    assert [item["config_id"] for item in sparse["selected_configs"]] == ["top3_fallback_v1"]


def test_shortpick_v2_rule_selection_requires_passed_source_leakage_audit() -> None:
    replay = _replay_artifact()
    replay["leakage_audit"] = {"status": "failed"}

    with pytest.raises(ValueError, match="leakage_audit.status must be passed"):
        build_shortpick_v2_rule_selection_artifact(replay)


def test_shortpick_v2_rule_selection_requires_ready_v1_source_replay() -> None:
    replay = _replay_artifact()
    replay["status"] = "blocked"
    with pytest.raises(ValueError, match="status must be ready"):
        build_shortpick_v2_rule_selection_artifact(replay)

    replay = _replay_artifact()
    replay["schema_version"] = "v0"
    with pytest.raises(ValueError, match="schema_version must be v1"):
        build_shortpick_v2_rule_selection_artifact(replay)


def test_shortpick_v2_rule_selection_schema_and_writer(tmp_path: Path) -> None:
    schema = json.loads(
        Path("docs/contracts/registry/schemas/shortpick_v2_rule_selection_artifact.schema.json").read_text(
            encoding="utf-8"
        )
    )
    artifact = build_shortpick_v2_rule_selection_artifact(
        _qualified_replay_artifact(),
        replay_artifact_path=tmp_path / "replay.json",
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )

    jsonschema.Draft202012Validator(schema).validate(artifact)
    output_path = write_shortpick_v2_rule_selection_artifact(artifact, output_path=tmp_path / "selection.json")
    assert json.loads(output_path.read_text(encoding="utf-8"))["artifact_id"] == artifact["artifact_id"]


def test_shortpick_v2_rule_selection_from_path_and_cli_parser(tmp_path: Path) -> None:
    replay_path = tmp_path / "replay.json"
    replay_path.write_text(json.dumps(_replay_artifact(), ensure_ascii=False), encoding="utf-8")

    artifact = build_shortpick_v2_rule_selection_artifact_from_path(
        replay_path,
        generated_at=datetime(2026, 6, 12, 9, 0, tzinfo=UTC),
    )
    assert artifact["source_replay_artifact"]["path"] == str(replay_path)

    args = cli_module.build_parser().parse_args(
        ["shortpick-v2-rule-selection", "--replay-artifact", str(replay_path)]
    )
    assert args.output == "output/shortpick-v2-rule-selection-artifact.json"
    assert args.max_selected == 2
    assert args.threshold_profile == "standard"

    sparse_args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-rule-selection",
            "--replay-artifact",
            str(replay_path),
            "--threshold-profile",
            "sparse_high_confidence",
        ]
    )
    assert sparse_args.threshold_profile == "sparse_high_confidence"
