from __future__ import annotations

import json
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_h10_artifact_validation import validate_shortpick_v2_h10_artifacts
from ashare_evidence.shortpick_v2_h10_robustness import DIAGNOSTIC_ANALYSIS_ROLE, H10_QUIET_DIAGNOSTIC_CONFIG_IDS
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)


def test_h10_artifact_validator_passes_complete_benchmark_artifacts(tmp_path: Path) -> None:
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), _execution_artifact())

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    assert summary["status"] == "passed"
    assert summary["failed_check_count"] == 0
    check_ids = {check["check_id"] for check in summary["checks"]}
    assert {
        "robustness_claim_ceiling_research_only",
        "robustness_benchmark_roles",
        "execution_90k_diagnostic_only",
        "execution_source_matches_robustness",
    } <= check_ids
    assert summary["robustness_summary"]["recommendation_status"] == "not_ready_for_paper_tracking"


def test_h10_artifact_validator_fails_when_research_claim_or_benchmark_role_drifts(tmp_path: Path) -> None:
    robustness = _robustness_artifact()
    robustness["claim_ceiling"] = "paper_tracking_candidate"
    robustness["analyzed_configs"][0]["role"] = "phase5_contract_candidate"
    robustness_path, execution_path = _write_artifacts(tmp_path, robustness, _execution_artifact())

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "robustness_schema_valid" in failed_check_ids
    assert "robustness_claim_ceiling_research_only" in failed_check_ids
    assert "robustness_benchmark_roles" in failed_check_ids


def test_h10_artifact_validator_fails_when_schema_root_is_missing(tmp_path: Path) -> None:
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), _execution_artifact())

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
        schema_root=tmp_path / "missing-schemas",
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert {"robustness_schema_valid", "execution_schema_valid"} <= failed_check_ids


def test_h10_artifact_validator_fails_when_benchmark_config_is_missing(tmp_path: Path) -> None:
    robustness = _robustness_artifact()
    robustness["analyzed_configs"] = [
        row
        for row in robustness["analyzed_configs"]
        if row["config_id"] != H10_QUIET_CHAMPION_CONFIG_ID
    ]
    robustness_path, execution_path = _write_artifacts(tmp_path, robustness, _execution_artifact())

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "robustness_benchmark_rows_present" in failed_check_ids
    assert "robustness_benchmark_roles" in failed_check_ids


def test_h10_artifact_validator_fails_when_execution_90k_is_promoted(tmp_path: Path) -> None:
    execution = _execution_artifact()
    diagnostic = next(
        row
        for row in execution["config_decompositions"]
        if row["config_id"] == H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]
    )
    diagnostic["role"] = "benchmark_control"
    diagnostic["diagnostic_only"] = False
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), execution)

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "execution_90k_diagnostic_only" in failed_check_ids


def test_h10_artifact_validator_fails_when_execution_benchmark_row_is_missing(tmp_path: Path) -> None:
    execution = _execution_artifact()
    execution["config_decompositions"] = [
        row
        for row in execution["config_decompositions"]
        if row["config_id"] != H10_QUIET_CAPITAL_SHADOW_CONFIG_ID
    ]
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), execution)

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "execution_required_rows_present" in failed_check_ids
    assert "execution_benchmark_rows_not_diagnostic" in failed_check_ids


def test_h10_artifact_validator_fails_when_execution_benchmark_row_is_diagnostic(tmp_path: Path) -> None:
    execution = _execution_artifact()
    capital_shadow = next(
        row
        for row in execution["config_decompositions"]
        if row["config_id"] == H10_QUIET_CAPITAL_SHADOW_CONFIG_ID
    )
    capital_shadow["role"] = DIAGNOSTIC_ANALYSIS_ROLE
    capital_shadow["diagnostic_only"] = True
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), execution)

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "execution_benchmark_rows_not_diagnostic" in failed_check_ids


def test_h10_artifact_validator_fails_when_pairwise_baseline_is_unexpected(tmp_path: Path) -> None:
    execution = _execution_artifact()
    execution["pairwise_funding_effects"].append(
        {
            "config_id": "unexpected",
            "baseline_config_id": "unexpected_baseline",
            "total_return_delta": 0.0,
            "turnover_delta": 0.0,
            "skip_count_delta": 0,
        }
    )
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), execution)

    summary = validate_shortpick_v2_h10_artifacts(
        robustness_artifact_path=robustness_path,
        execution_artifact_path=execution_path,
    )

    failed_check_ids = {check["check_id"] for check in summary["checks"] if not check["passed"]}
    assert summary["status"] == "failed"
    assert "execution_pairwise_funding_effects" in failed_check_ids


def test_h10_artifact_validate_cli_parser_and_main_output(tmp_path: Path, capsys) -> None:
    robustness_path, execution_path = _write_artifacts(tmp_path, _robustness_artifact(), _execution_artifact())

    assert "shortpick-v2-h10-artifact-validate" in cli_module.NO_DB_COMMANDS

    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-h10-artifact-validate",
            "--robustness-artifact",
            str(robustness_path),
            "--execution-artifact",
            str(execution_path),
        ]
    )
    assert args.robustness_artifact == str(robustness_path)
    assert args.execution_artifact == str(execution_path)

    exit_code = cli_module.main(
        [
            "shortpick-v2-h10-artifact-validate",
            "--robustness-artifact",
            str(robustness_path),
            "--execution-artifact",
            str(execution_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "passed"
    assert output["check_count"] > 10


def _write_artifacts(
    tmp_path: Path,
    robustness_artifact: dict[str, object],
    execution_artifact: dict[str, object],
) -> tuple[Path, Path]:
    robustness_path = tmp_path / "robustness.json"
    execution_path = tmp_path / "execution.json"
    robustness_path.write_text(json.dumps(robustness_artifact, ensure_ascii=False), encoding="utf-8")
    execution_path.write_text(json.dumps(execution_artifact, ensure_ascii=False), encoding="utf-8")
    return robustness_path, execution_path


def _robustness_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_h10_robustness_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_robustness:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_robustness",
        "source_plan_ref": "docs/contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md#phase-4",
        "source_replay_artifact": _source_artifact("shortpick_v2_replay_artifact:test", "replay.json"),
        "source_selection_artifact": _source_artifact("shortpick_v2_rule_selection_artifact:test", "selection.json"),
        "analysis_scope": {
            "candidate_batch": "h10_quiet",
            "signal_day_count": 10,
            "trade_day_count": 20,
            "analyzed_config_count": 3,
        },
        "analysis_policy": {
            "period_reset_policy": "reset",
            "trade_contribution_policy": "post-hoc",
            "promotion_policy": "cannot promote paper tracking",
        },
        "analyzed_configs": [
            _analyzed_row(H10_QUIET_CHAMPION_CONFIG_ID, role="benchmark_control"),
            _analyzed_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, role="benchmark_control"),
            _analyzed_row(H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0], role=DIAGNOSTIC_ANALYSIS_ROLE),
        ],
        "period_reset_results": {
            "yearly": [
                _period_row(H10_QUIET_CHAMPION_CONFIG_ID),
                _period_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID),
                _period_row(H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]),
            ],
            "quarterly": [],
        },
        "parameter_stability": {"rows": [], "notes": []},
        "risk_flags": [{"flag_id": "weak_year", "severity": "high", "message": "test"}],
        "recommendation": {"status": "not_ready_for_paper_tracking", "notes": ["test"]},
        "leakage_audit": {"status": "passed"},
        "event_refs": ["shortpick_v2.h10_quiet.robustness.generated"],
    }


def _execution_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_h10_execution_decomposition_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_execution_decomposition:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_execution_decomposition",
        "source_robustness_artifact": {
            "artifact_id": "shortpick_v2_h10_robustness:test",
            "artifact_family": "shortpick_v2_h10_robustness_artifact",
            "schema_version": "v1",
            "status": "ready",
            "claim_ceiling": "research_observation",
        },
        "analysis_scope": {
            "config_ids": [
                H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
                H10_QUIET_CHAMPION_CONFIG_ID,
                H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
            ],
            "decomposed_config_count": 3,
            "missing_config_ids": [],
        },
        "decomposition_policy": {
            "promotion_policy": "90k remains diagnostic-only and cannot be promoted by this artifact.",
        },
        "config_decompositions": [
            _execution_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, role="benchmark_control", notional=80_000.0),
            _execution_row(H10_QUIET_CHAMPION_CONFIG_ID, role="benchmark_control", notional=85_000.0),
            _execution_row(
                H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
                role=DIAGNOSTIC_ANALYSIS_ROLE,
                notional=90_000.0,
                diagnostic_only=True,
            ),
        ],
        "pairwise_funding_effects": [
            {
                "config_id": H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
                "baseline_config_id": H10_QUIET_CHAMPION_CONFIG_ID,
                "total_return_delta": -0.1,
                "turnover_delta": -0.2,
                "skip_count_delta": 1,
            },
            {
                "config_id": H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
                "baseline_config_id": H10_QUIET_CHAMPION_CONFIG_ID,
                "total_return_delta": 0.1,
                "turnover_delta": 0.2,
                "skip_count_delta": -1,
            },
        ],
        "event_refs": ["shortpick_v2.h10_quiet.execution_decomposition.generated"],
    }


def _source_artifact(artifact_id: str, path: str) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "artifact_family": artifact_id.split(":")[0],
        "schema_version": "v1",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "test",
        "path": path,
    }


def _analyzed_row(config_id: str, *, role: str) -> dict[str, object]:
    return {
        "config_id": config_id,
        "role": role,
        "source_id": "quiet_breakout_rank2_poolhot10_mtw",
        "summary": {"total_return": 1.0},
        "source_replay_consistency": {"status": "passed"},
        "trade_contribution_stress": [
            {
                "remove_top_winner_count": 1,
                "total_return_proxy": 0.8,
                "annualized_return_proxy": 0.4,
                "market_excess_total_return_proxy": 0.3,
                "method": "post_hoc_trade_pnl_subtraction_not_resimulated",
            }
        ],
    }


def _period_row(config_id: str) -> dict[str, object]:
    return {"period_id": "2026", "config_id": config_id, "summary": {"annualized_return": 0.1}}


def _execution_row(
    config_id: str,
    *,
    role: str,
    notional: float,
    diagnostic_only: bool = False,
) -> dict[str, object]:
    return {
        "config_id": config_id,
        "role": role,
        "diagnostic_only": diagnostic_only,
        "target_notional": notional,
        "board_lot": {
            "board_lot_size": 100,
            "board_lot_block_count": 0,
            "insufficient_cash_count": 0,
        },
        "cash_deployment": {
            "initial_cash": 200_000.0,
            "mean_invested_ratio": 0.9,
            "cash_drag_proxy": 0.1,
            "total_buy_value": 1_000_000.0,
        },
        "turnover_skip": {
            "turnover": 10.0,
            "trade_count": 10,
            "skip_count": 1,
            "skipped_ratio": 0.1,
            "fallback_trade_count": 2,
        },
        "winner_concentration": {
            "largest_symbol_abs_pnl_share": 0.2,
            "top_winner_net_pnl": 10_000.0,
        },
        "funding_effect_vs_fixed85": {
            "total_return_delta": 0.0,
            "turnover_delta": 0.0,
            "skip_count_delta": 0,
        },
    }
