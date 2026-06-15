from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_h10_rank_ablation import (
    build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact,
    validate_shortpick_v2_h10_rank_ablation_artifact,
    validate_shortpick_v2_h10_rank_ablation_payload,
    write_shortpick_v2_h10_rank_ablation_artifact,
)


def test_h10_rank_ablation_builds_supported_rank2_research_artifact() -> None:
    artifact = build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        _replay_artifact(),
        generated_at=datetime(2026, 6, 15, 7, 0, tzinfo=UTC),
    )

    assert artifact["artifact_family"] == "shortpick_v2_h10_rank_ablation_artifact"
    assert artifact["status"] == "ready"
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["analysis_scope"]["horizon_days"] == 10
    assert artifact["analysis_scope"]["period_block_definition"].startswith("calendar years")
    assert artifact["rank2_decision"]["support_label"] == "supported"
    assert artifact["rank2_decision"]["thresholds"]["total_return_delta_threshold"] == 0.03
    assert artifact["recommendation"]["status"] == "research_only_no_paper_tracking_promotion"
    assert len(artifact["execution_context_rows"]) == 6
    assert {row["informational_only"] for row in artifact["execution_context_rows"]} == {True}

    rows_by_rank = {row["rank"]: row for row in artifact["rank_rows"]}
    assert rows_by_rank[1]["support_label"] == "inconclusive"
    assert rows_by_rank[2]["support_label"] == "supported"
    assert rows_by_rank[3]["support_label"] == "inconclusive"
    assert rows_by_rank[4]["support_label"] == "inconclusive"
    assert rows_by_rank[5]["support_label"] == "inconclusive"

    validation = validate_shortpick_v2_h10_rank_ablation_payload(artifact)
    assert validation["status"] == "passed"


def test_h10_rank_ablation_threshold_is_inclusive_for_rank2_support() -> None:
    artifact = build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        _replay_artifact(rank_returns={1: 2.68, 2: 2.71, 3: 2.60, 4: 3.20, 5: 3.10}),
        generated_at=datetime(2026, 6, 15, 7, 0, tzinfo=UTC),
    )

    assert artifact["rank2_decision"]["support_label"] == "supported"

    rows_by_rank = {row["rank"]: row for row in artifact["rank_rows"]}
    assert rows_by_rank[4]["support_label"] == "inconclusive"
    assert rows_by_rank[5]["support_label"] == "inconclusive"


def test_h10_rank_ablation_marks_rank2_challenged_when_rank1_wins_cleanly() -> None:
    artifact = build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        _replay_artifact(rank_returns={1: 2.83, 2: 2.71, 3: 2.50}),
        generated_at=datetime(2026, 6, 15, 7, 0, tzinfo=UTC),
    )

    assert artifact["rank2_decision"]["support_label"] == "challenged"
    assert artifact["rank2_decision"]["challenger_ranks"] == [1]

    rows_by_rank = {row["rank"]: row for row in artifact["rank_rows"]}
    assert rows_by_rank[1]["support_label"] == "challenged"
    assert rows_by_rank[2]["support_label"] == "challenged"

    validation = validate_shortpick_v2_h10_rank_ablation_payload(artifact)
    assert validation["status"] == "passed"


def test_h10_rank_ablation_sparse_rows_are_forced_inconclusive() -> None:
    artifact = build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        _replay_artifact(signal_date_from="2025-01-02", signal_date_to="2026-01-30", trade_count=40),
        generated_at=datetime(2026, 6, 15, 7, 0, tzinfo=UTC),
    )

    assert artifact["analysis_scope"]["period_block_count"] == 2
    assert artifact["rank2_decision"]["support_label"] == "inconclusive"
    assert {row["support_label"] for row in artifact["rank_rows"]} == {"inconclusive"}

    invalid = deepcopy(artifact)
    invalid["rank_rows"][0]["support_label"] = "challenged"
    validation = validate_shortpick_v2_h10_rank_ablation_payload(invalid)
    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "rank_1_sparse_rows_inconclusive" in failed_check_ids


def test_h10_rank_ablation_rejects_non_h10_source() -> None:
    replay = _replay_artifact()
    replay["input_contracts"]["exit_model"]["holding_days"] = 5

    with pytest.raises(ValueError, match="horizon_days=10"):
        build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(replay)


def test_h10_rank_ablation_validate_cli_parser_and_main_output(tmp_path: Path, capsys) -> None:
    artifact = build_shortpick_v2_h10_rank_ablation_artifact_from_replay_artifact(
        _replay_artifact(),
        generated_at=datetime(2026, 6, 15, 7, 0, tzinfo=UTC),
    )
    artifact_path = write_shortpick_v2_h10_rank_ablation_artifact(
        artifact,
        output_path=tmp_path / "rank-ablation.json",
    )

    assert "shortpick-v2-h10-rank-ablation-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-h10-rank-ablation",
            "--horizon-days",
            "10",
            "--output",
            str(tmp_path / "generated.json"),
        ]
    )
    assert args.horizon_days == 10
    assert args.output == str(tmp_path / "generated.json")

    exit_code = cli_module.main(
        [
            "shortpick-v2-h10-rank-ablation-validate",
            "--artifact",
            str(artifact_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["artifact_summary"]["rank2_status"] == "supported"

    direct_validation = validate_shortpick_v2_h10_rank_ablation_artifact(artifact_path=artifact_path)
    assert direct_validation["status"] == "passed"


def _replay_artifact(
    *,
    signal_date_from: str = "2023-01-02",
    signal_date_to: str = "2025-12-31",
    trade_count: int = 190,
    rank_returns: dict[int, float] | None = None,
) -> dict[str, object]:
    rank_returns = rank_returns or {1: 2.62, 2: 2.71, 3: 2.50, 4: 2.40, 5: 2.30}
    config_returns: dict[str, float] = {}
    for rank, total_return in rank_returns.items():
        config_returns[_fixed_config_id(rank, 85_000)] = total_return
    for notional in (80_000, 90_000):
        for rank in (1, 2, 3):
            config_returns[_fixed_config_id(rank, notional)] = rank_returns[rank] - 0.05
    return {
        "artifact_family": "shortpick_v2_replay_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_replay_artifact:test:h10_rank_ablation",
        "generated_at": "2026-06-15T07:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay",
        "source_plan_ref": "test",
        "data_scope": {
            "signal_date_from": signal_date_from,
            "signal_date_to": signal_date_to,
            "signal_day_count": 360,
            "trade_day_count": 760,
        },
        "input_contracts": {
            "candidate_source": {
                "source_ref": "market_only_reconstruction:shortpick_v2_strategy_search_batch:h10_quiet_champion:v1",
            },
            "account": {"initial_cash": 200_000.0},
            "exit_model": {"holding_days": 10},
        },
        "results": [
            _result_row(
                config_id,
                total_return=total_return,
                trade_count=trade_count,
                max_drawdown=-0.119,
            )
            for config_id, total_return in config_returns.items()
        ],
        "promotion_gate": {"status": "not_evaluated", "claim_ceiling": "research_observation"},
        "leakage_audit": {"status": "passed"},
    }


def _result_row(
    config_id: str,
    *,
    total_return: float,
    trade_count: int,
    max_drawdown: float,
) -> dict[str, object]:
    return {
        "config_id": config_id,
        "status": "ready",
        "summary": {
            "signal_count": 720,
            "trade_count": trade_count,
            "skip_count": 530,
            "fallback_trade_count": 0,
            "total_return": total_return,
            "annualized_return": 0.50,
            "market_excess_total_return": total_return - 0.42,
            "max_drawdown": max_drawdown,
            "turnover": 76.0,
            "skipped_ratio": 0.736,
        },
    }


def _fixed_config_id(rank: int, notional: int) -> str:
    return f"quiet_breakout_rank{rank}_poolhot10_mtw__fixed_notional_{int(notional / 1000)}k_top5_h10_v1"
