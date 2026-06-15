from __future__ import annotations

import json
from pathlib import Path

import ashare_evidence.cli as cli_module
from ashare_evidence.shortpick_v2_h10_paper_governance import (
    ENTRY_POLICY,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
    LEDGER_POLICY,
    build_shortpick_v2_h10_paper_governance_artifact,
    validate_shortpick_v2_h10_paper_governance_artifact,
    validate_shortpick_v2_h10_paper_governance_payload,
    write_shortpick_v2_h10_paper_governance_artifact,
)


def test_h10_paper_governance_builds_forward_observation_artifact(tmp_path: Path) -> None:
    artifact = _governance_artifact()
    artifact_path = write_shortpick_v2_h10_paper_governance_artifact(
        artifact,
        output_path=tmp_path / "paper-governance.json",
    )

    validation = validate_shortpick_v2_h10_paper_governance_artifact(artifact_path=artifact_path)

    assert artifact["status"] == "ready"
    assert validation["status"] == "passed"
    assert validation["failed_check_count"] == 0
    assert artifact["recommendation"]["paper_tracking_status"] == "not_started_no_true_forward_rows"
    assert artifact["ledger_contract_overlay"]["current_true_forward_record_count"] == 0
    assert artifact["ledger_contract_overlay"]["ledger_policy"] == LEDGER_POLICY
    assert artifact["ledger_contract_overlay"]["entry_policy"] == ENTRY_POLICY
    assert artifact["source_disposition"]["robustness_recommendation_status"] == "not_ready_for_paper_tracking"
    assert artifact["source_disposition"]["high_risk_flag_count"] == 1
    assert [row["config_id"] for row in artifact["candidate_configs"]] == [
        H10_QUIET_CHAMPION_CONFIG_ID,
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    ]


def test_h10_paper_governance_requires_parameter_significance_source() -> None:
    artifact = _governance_artifact()
    artifact["source_artifacts"].pop("parameter_significance")
    artifact["source_validation"]["parameter_significance"] = {"status": "missing"}

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "source_parameter_significance_ref_present" in failed_check_ids
    assert "source_validation_parameter_significance_passed" in failed_check_ids


def test_h10_paper_governance_fails_without_prior_not_ready_risk_disposition() -> None:
    artifact = _governance_artifact()
    artifact["source_disposition"]["robustness_recommendation_status"] = "candidate_requires_forward_tracking"
    artifact["source_disposition"]["high_risk_flag_count"] = 0
    artifact["source_disposition"]["risk_flag_disposition"] = "ignored_after_return_gate"
    artifact["source_validation"]["robustness"]["recommendation_status"] = "candidate_requires_forward_tracking"

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "source_disposition_risk_flags_preserved" in failed_check_ids
    assert "source_disposition_robustness_status_preserved" in failed_check_ids
    assert "source_validation_robustness_not_ready_disposed" in failed_check_ids


def test_h10_paper_governance_rejects_historical_paper_performance_claim() -> None:
    artifact = _governance_artifact()
    artifact["recommendation"]["status"] = "paper_tracking_ready"
    artifact["recommendation"]["paper_tracking_status"] = "started_from_historical_replay"
    artifact["candidate_configs"][0]["paper_tracking_performance_claim"] = True
    artifact["candidate_configs"][0]["current_true_forward_record_count"] = 190

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "recommendation_forward_observation_only" in failed_check_ids
    assert f"candidate_{H10_QUIET_CHAMPION_CONFIG_ID}_role_and_status" in failed_check_ids


def test_h10_paper_governance_rejects_candidate_below_return_floor() -> None:
    artifact = _governance_artifact()
    qualification = artifact["candidate_configs"][1]["qualification_checks"]
    qualification["passed"] = False
    qualification["annualized_return"] = 0.2
    qualification["annualized_return_meets_floor"] = False

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert f"candidate_{H10_QUIET_CAPITAL_SHADOW_CONFIG_ID}_qualification" in failed_check_ids


def test_h10_paper_governance_rejects_summary_below_return_floor_with_stale_flags() -> None:
    artifact = _governance_artifact()
    artifact["candidate_configs"][1]["summary"]["annualized_return"] = 0.2

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert f"candidate_{H10_QUIET_CAPITAL_SHADOW_CONFIG_ID}_summary_return_floor" in failed_check_ids
    assert f"candidate_{H10_QUIET_CAPITAL_SHADOW_CONFIG_ID}_qualification" in failed_check_ids


def test_h10_paper_governance_rejects_negative_market_excess_with_stale_flags() -> None:
    artifact = _governance_artifact()
    artifact["candidate_configs"][0]["summary"]["market_excess_total_return"] = -0.01

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert f"candidate_{H10_QUIET_CHAMPION_CONFIG_ID}_summary_return_floor" in failed_check_ids
    assert f"candidate_{H10_QUIET_CHAMPION_CONFIG_ID}_qualification" in failed_check_ids


def test_h10_paper_governance_rejects_fixed90_as_candidate_config() -> None:
    artifact = _governance_artifact()
    promoted_fixed90 = dict(artifact["candidate_configs"][0])
    promoted_fixed90["config_id"] = H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID
    artifact["candidate_configs"].append(promoted_fixed90)

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "candidate_configs_exact_fixed85_fixed80_only" in failed_check_ids


def test_h10_paper_governance_rejects_fixed90_promotion() -> None:
    artifact = _governance_artifact()
    artifact["diagnostic_configs"][0]["paper_tracking_eligible"] = True
    artifact["diagnostic_configs"][0]["diagnostic_only"] = False

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)

    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert validation["status"] == "failed"
    assert "diagnostic_fixed90_not_eligible" in failed_check_ids


def test_h10_paper_governance_cli_parser_and_main_output(tmp_path: Path, capsys) -> None:
    rank_path, parameter_path, robustness_path, execution_path = _write_source_artifacts(tmp_path)
    output_path = tmp_path / "paper-governance.json"
    published_path = tmp_path / "published-paper-governance.json"

    assert "shortpick-v2-h10-paper-governance" in cli_module.NO_DB_COMMANDS
    assert "shortpick-v2-h10-paper-governance-validate" in cli_module.NO_DB_COMMANDS

    args = cli_module.build_parser().parse_args(
        [
            "shortpick-v2-h10-paper-governance",
            "--rank-ablation-artifact",
            str(rank_path),
            "--parameter-significance-artifact",
            str(parameter_path),
            "--robustness-artifact",
            str(robustness_path),
            "--execution-artifact",
            str(execution_path),
            "--output",
            str(output_path),
            "--published-artifact",
            str(published_path),
        ]
    )
    assert args.parameter_significance_artifact == str(parameter_path)

    exit_code = cli_module.main(
        [
            "shortpick-v2-h10-paper-governance",
            "--rank-ablation-artifact",
            str(rank_path),
            "--parameter-significance-artifact",
            str(parameter_path),
            "--robustness-artifact",
            str(robustness_path),
            "--execution-artifact",
            str(execution_path),
            "--output",
            str(output_path),
            "--published-artifact",
            str(published_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "ok"
    assert output["validation_status"] == "passed"
    assert output_path.exists()
    assert published_path.exists()

    validate_exit = cli_module.main(
        [
            "shortpick-v2-h10-paper-governance-validate",
            "--artifact",
            str(output_path),
        ]
    )
    validate_output = json.loads(capsys.readouterr().out)
    assert validate_exit == 0
    assert validate_output["status"] == "passed"


def test_h10_paper_governance_builder_blocks_invalid_parameter_source() -> None:
    parameter = _parameter_significance_artifact()
    parameter["parameter_rows"] = []

    artifact = build_shortpick_v2_h10_paper_governance_artifact(
        rank_ablation_artifact=_rank_ablation_artifact(),
        parameter_significance_artifact=parameter,
        robustness_artifact=_robustness_artifact(),
        execution_artifact=_execution_artifact(),
    )

    validation = validate_shortpick_v2_h10_paper_governance_payload(artifact)
    failed_check_ids = {check["check_id"] for check in validation["checks"] if not check["passed"]}
    assert artifact["status"] == "blocked"
    assert "paper_governance_family_ready" in failed_check_ids
    assert "source_validation_parameter_significance_passed" in failed_check_ids


def _governance_artifact() -> dict[str, object]:
    return build_shortpick_v2_h10_paper_governance_artifact(
        rank_ablation_artifact=_rank_ablation_artifact(),
        parameter_significance_artifact=_parameter_significance_artifact(),
        robustness_artifact=_robustness_artifact(),
        execution_artifact=_execution_artifact(),
        artifact_paths={
            "rank_ablation": "rank.json",
            "parameter_significance": "parameter.json",
            "robustness": "robustness.json",
            "execution_decomposition": "execution.json",
        },
    )


def _write_source_artifacts(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    paths = (
        tmp_path / "rank.json",
        tmp_path / "parameter.json",
        tmp_path / "robustness.json",
        tmp_path / "execution.json",
    )
    payloads = (
        _rank_ablation_artifact(),
        _parameter_significance_artifact(),
        _robustness_artifact(),
        _execution_artifact(),
    )
    for path, payload in zip(paths, payloads, strict=True):
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return paths


def _rank_ablation_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_h10_rank_ablation_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_rank_ablation:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_same_gate_rank_ablation",
        "rank2_decision": {"support_label": "supported"},
        "recommendation": {"status": "research_only_no_paper_tracking_promotion"},
    }


def _parameter_significance_artifact() -> dict[str, object]:
    rows = [
        _parameter_row("weekday_gate", "weekday_gate_mtw_vs_mt_tw", support_label="supported"),
        _parameter_row("rank_choice", "rank_choice_rank2_direct_ablation", support_label="supported"),
        _parameter_row("pool_hot_threshold", "pool_hot_threshold_10_vs_neighbors", support_label="supported"),
        _parameter_row("fixed_notional", "fixed_notional_85k_vs_80k", support_label="supported"),
        _parameter_row(
            "fixed_notional",
            "fixed_notional_90k_diagnostic_boundary",
            support_label="inconclusive",
            evidence_basis="diagnostic",
            diagnostic_only=True,
        ),
        _parameter_row("fallback_skip", "fallback_skip_no_delay", support_label="supported"),
        _parameter_row("concentration_stability", "winner_concentration_stability", support_label="inconclusive"),
    ]
    return {
        "artifact_family": "shortpick_v2_h10_parameter_significance_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_parameter_significance:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_parameter_ablation_and_governance_validation",
        "source_plan_ref": "plans/active/plan-20260615-h10-parameter-significance.md",
        "analysis_scope": {
            "horizon_days": 10,
            "benchmark_config_ids": [H10_QUIET_CHAMPION_CONFIG_ID, H10_QUIET_CAPITAL_SHADOW_CONFIG_ID],
        },
        "parameter_rows": rows,
        "recommendation": {"status": "research_only_no_paper_tracking_promotion", "notes": []},
        "leakage_audit": {"status": "passed", "no_delayed_buy_action": True},
    }


def _parameter_row(
    family: str,
    parameter_id: str,
    *,
    support_label: str,
    evidence_basis: str = "statistical",
    diagnostic_only: bool = False,
) -> dict[str, object]:
    row = {
        "parameter_family": family,
        "parameter_id": parameter_id,
        "support_label": support_label,
        "sample_count": 190,
        "period_block_count": 4,
        "evidence_basis": evidence_basis,
        "comparison_evidence": {"baseline_config_id": H10_QUIET_CHAMPION_CONFIG_ID},
    }
    if diagnostic_only:
        row["diagnostic_only"] = True
        row["promotion_status"] = "not_eligible"
    return row


def _robustness_artifact() -> dict[str, object]:
    return {
        "artifact_family": "shortpick_v2_h10_robustness_artifact",
        "schema_version": "v1",
        "artifact_id": "shortpick_v2_h10_robustness:test",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "status": "ready",
        "claim_ceiling": "research_observation",
        "evidence_basis": "historical_account_replay_robustness",
        "analysis_scope": {
            "horizon_days": 10,
            "initial_cash": 200_000.0,
            "signal_date_from": "2023-04-13",
            "signal_date_to": "2026-05-08",
        },
        "analyzed_configs": [
            _analyzed_row(H10_QUIET_CHAMPION_CONFIG_ID, role="benchmark_control", annualized_return=0.5396),
            _analyzed_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, role="benchmark_control", annualized_return=0.5203),
            _analyzed_row(
                H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
                role="diagnostic_boundary",
                annualized_return=0.6,
            ),
        ],
        "risk_flags": [{"flag_id": "weak_year", "severity": "high", "message": "test high risk"}],
        "recommendation": {"status": "not_ready_for_paper_tracking", "notes": ["test"]},
    }


def _analyzed_row(config_id: str, *, role: str, annualized_return: float) -> dict[str, object]:
    return {
        "config_id": config_id,
        "role": role,
        "summary": {
            "total_return": 2.7,
            "annualized_return": annualized_return,
            "market_reference_total_return": 0.418,
            "market_excess_total_return": 2.282,
            "max_drawdown": -0.119,
            "trade_count": 190,
            "turnover": 76.67,
            "skipped_ratio": 0.7365,
        },
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
        "analysis_scope": {"missing_config_ids": []},
        "config_decompositions": [
            _execution_row(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, role="benchmark_control", notional=80_000.0),
            _execution_row(H10_QUIET_CHAMPION_CONFIG_ID, role="benchmark_control", notional=85_000.0),
            _execution_row(
                H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID,
                role="diagnostic_boundary",
                notional=90_000.0,
                diagnostic_only=True,
            ),
        ],
    }


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
    }
