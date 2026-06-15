from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_h10_parameter_significance import (
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
    REQUIRED_PARAMETER_FAMILIES,
    build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact,
    validate_shortpick_v2_h10_parameter_significance_artifact,
    validate_shortpick_v2_h10_parameter_significance_payload,
    write_shortpick_v2_h10_parameter_significance_artifact,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)


def test_h10_parameter_significance_builds_fixed_h10_research_artifact() -> None:
    artifact = build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(
        _replay_artifact(),
        generated_at=datetime(2026, 6, 15, 5, 0, tzinfo=UTC),
    )

    assert artifact["artifact_family"] == "shortpick_v2_h10_parameter_significance_artifact"
    assert artifact["status"] == "ready"
    assert artifact["claim_ceiling"] == "research_observation"
    assert artifact["analysis_scope"]["horizon_days"] == 10
    assert artifact["recommendation"]["status"] == "research_only_no_paper_tracking_promotion"
    assert {row["parameter_family"] for row in artifact["parameter_rows"]} >= set(REQUIRED_PARAMETER_FAMILIES)

    validation = validate_shortpick_v2_h10_parameter_significance_payload(artifact)
    assert validation["status"] == "passed"

    rows_by_id = {row["parameter_id"]: row for row in artifact["parameter_rows"]}
    assert rows_by_id["action_choice_fallback_or_skip_no_delay"]["support_label"] == "supported"
    assert rows_by_id["fixed_notional_90k_diagnostic_boundary"]["support_label"] == "inconclusive"
    assert rows_by_id["fixed_notional_90k_diagnostic_boundary"]["diagnostic_only"] is True
    assert rows_by_id["fixed_notional_90k_diagnostic_boundary"]["promotion_status"] == "not_eligible"


def test_h10_parameter_significance_rejects_non_h10_source() -> None:
    replay = _replay_artifact()
    replay["input_contracts"]["exit_model"]["holding_days"] = 5

    with pytest.raises(ValueError, match="horizon_days=10"):
        build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(replay)


def test_h10_parameter_significance_sparse_blocks_are_forced_inconclusive() -> None:
    artifact = build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(
        _replay_artifact(signal_date_from="2025-01-02", signal_date_to="2026-01-30"),
        generated_at=datetime(2026, 6, 15, 5, 0, tzinfo=UTC),
    )

    assert artifact["analysis_scope"]["period_block_count"] == 2
    assert {row["support_label"] for row in artifact["parameter_rows"]} == {"inconclusive"}

    invalid = deepcopy(artifact)
    invalid["parameter_rows"][0]["support_label"] = "supported"
    validation = validate_shortpick_v2_h10_parameter_significance_payload(invalid)
    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "parameter_row_0_sparse_blocks_inconclusive" in failed_check_ids


def test_h10_parameter_significance_validate_cli_parser_and_main_output(
    tmp_path: Path,
    capsys,
) -> None:
    artifact = build_shortpick_v2_h10_parameter_significance_artifact_from_replay_artifact(
        _replay_artifact(),
        generated_at=datetime(2026, 6, 15, 5, 0, tzinfo=UTC),
    )
    artifact_path = write_shortpick_v2_h10_parameter_significance_artifact(
        artifact,
        output_path=tmp_path / "parameter-significance.json",
    )

    assert "shortpick-v2-h10-parameter-significance-validate" in cli_module.NO_DB_COMMANDS
    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-h10-parameter-significance",
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
            "shortpick-v2-h10-parameter-significance-validate",
            "--artifact",
            str(artifact_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["artifact_summary"]["horizon_days"] == 10

    direct_validation = validate_shortpick_v2_h10_parameter_significance_artifact(artifact_path=artifact_path)
    assert direct_validation["status"] == "passed"


def _replay_artifact(
    *,
    signal_date_from: str = "2023-01-02",
    signal_date_to: str = "2025-12-31",
) -> dict[str, object]:
    config_returns = {
        H10_QUIET_CHAMPION_CONFIG_ID: 2.71,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID: 2.57,
        H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID: 2.84,
        _fixed85_config_id("quiet_breakout_rank2_poolhot10_mt"): 2.05,
        _fixed85_config_id("quiet_breakout_rank2_poolhot10_tw"): 2.12,
        _fixed85_config_id("quiet_breakout_rank2_poolhot09_mtw"): 2.24,
        _fixed85_config_id("quiet_breakout_rank2_poolhot11_mtw"): 2.41,
        _fixed85_config_id("quiet_breakout_rank2_poolhot12_mtw"): 2.31,
    }
    return {
        "artifact_family": "shortpick_v2_replay_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_replay_artifact:test:h10_quiet_champion",
        "generated_at": "2026-06-15T05:00:00+00:00",
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
        "rule_matrix": [_rule_row(config_id) for config_id in config_returns],
        "results": [
            _result_row(
                config_id,
                total_return=total_return,
                trade_count=190 if config_id == H10_QUIET_CHAMPION_CONFIG_ID else 180,
                fallback_trade_count=30 if config_id == H10_QUIET_CHAMPION_CONFIG_ID else 20,
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
    fallback_trade_count: int,
) -> dict[str, object]:
    return {
        "config_id": config_id,
        "status": "ready",
        "summary": {
            "signal_count": 720,
            "trade_count": trade_count,
            "skip_count": 530,
            "fallback_trade_count": fallback_trade_count,
            "total_return": total_return,
            "market_excess_total_return": total_return - 0.42,
            "max_drawdown": -0.119,
            "turnover": 76.0,
            "skipped_ratio": 0.736,
        },
    }


def _rule_row(config_id: str) -> dict[str, object]:
    return {
        "config_id": config_id,
        "family": "fixed_notional_lot_rounding",
        "allowed_actions": ["buy_primary", "buy_fallback", "skip"],
        "candidate_rank_limit": 5,
        "fallback_policy": {"enabled": True, "max_rank": 5},
        "cash_policy": {"target_mode": "fixed_notional", "target_notional": 85_000.0},
        "position_policy": {"max_position_count": 5, "max_position_pct": 0.35},
        "lot_policy": {"board_lot_size": 100, "rounding": "floor_to_board_lot"},
    }


def _fixed85_config_id(source_id: str) -> str:
    return f"{source_id}__fixed_notional_85k_top5_h10_v1"
