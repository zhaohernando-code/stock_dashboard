from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from ashare_evidence.shortpick_v2_h10_execution_decomposition import (
    SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_h10_robustness import (
    DIAGNOSTIC_ANALYSIS_ROLE,
    H10_QUIET_DIAGNOSTIC_CONFIG_IDS,
    SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_BENCHMARK_CONFIG_IDS,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)

RESEARCH_OBSERVATION_CLAIM_CEILING = "research_observation"
ROBUSTNESS_SCHEMA_NAME = "shortpick_v2_h10_robustness_artifact.schema.json"
EXECUTION_DECOMPOSITION_SCHEMA_NAME = "shortpick_v2_h10_execution_decomposition_artifact.schema.json"
DEFAULT_SCHEMA_ROOT = Path("docs/contracts/registry/schemas")
TOP_WINNER_STRESS_METHOD = "post_hoc_trade_pnl_subtraction_not_resimulated"


def validate_shortpick_v2_h10_artifacts(
    *,
    robustness_artifact_path: str | Path,
    execution_artifact_path: str | Path,
    schema_root: str | Path = DEFAULT_SCHEMA_ROOT,
) -> dict[str, Any]:
    robustness_path = Path(robustness_artifact_path)
    execution_path = Path(execution_artifact_path)
    checks: list[dict[str, Any]] = []

    robustness_artifact = _load_json(robustness_path, checks, check_id="robustness_json_readable")
    execution_artifact = _load_json(execution_path, checks, check_id="execution_json_readable")

    if robustness_artifact is not None:
        _validate_schema(
            robustness_artifact,
            schema_path=Path(schema_root) / ROBUSTNESS_SCHEMA_NAME,
            checks=checks,
            check_id="robustness_schema_valid",
        )
    if execution_artifact is not None:
        _validate_schema(
            execution_artifact,
            schema_path=Path(schema_root) / EXECUTION_DECOMPOSITION_SCHEMA_NAME,
            checks=checks,
            check_id="execution_schema_valid",
        )

    if robustness_artifact is not None:
        _validate_robustness_content(robustness_artifact, checks)
    if execution_artifact is not None:
        _validate_execution_content(execution_artifact, robustness_artifact, checks)

    failed_checks = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed_checks else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed_checks),
        "artifact_paths": {
            "robustness": str(robustness_path),
            "execution": str(execution_path),
        },
        "robustness_summary": _robustness_summary(robustness_artifact),
        "execution_summary": _execution_summary(execution_artifact),
        "checks": checks,
    }


def _load_json(path: Path, checks: list[dict[str, Any]], *, check_id: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _add_check(checks, check_id, False, f"{path} is not readable JSON", {"error": str(exc)})
        return None
    if not isinstance(payload, dict):
        _add_check(checks, check_id, False, f"{path} must contain a JSON object", {"type": type(payload).__name__})
        return None
    _add_check(checks, check_id, True, f"{path} is readable JSON")
    return payload


def _validate_schema(
    payload: dict[str, Any],
    *,
    schema_path: Path,
    checks: list[dict[str, Any]],
    check_id: str,
) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(payload)
    except (OSError, json.JSONDecodeError, jsonschema.ValidationError, jsonschema.SchemaError) as exc:
        details: dict[str, Any] = {"error": str(exc)}
        if isinstance(exc, jsonschema.ValidationError):
            details["json_path"] = ".".join(str(part) for part in exc.absolute_path)
        _add_check(checks, check_id, False, f"{schema_path.name} validation failed", details)
        return
    _add_check(checks, check_id, True, f"{schema_path.name} validation passed")


def _validate_robustness_content(artifact: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    analyzed_by_config = _rows_by_config(artifact.get("analyzed_configs"))
    yearly_config_ids = {
        str(row.get("config_id"))
        for row in (artifact.get("period_reset_results") or {}).get("yearly") or []
        if isinstance(row, dict)
    }
    benchmark_rows = [analyzed_by_config.get(config_id) for config_id in H10_QUIET_BENCHMARK_CONFIG_IDS]
    benchmark_rows_present = all(isinstance(row, dict) for row in benchmark_rows)
    benchmark_roles = {
        config_id: (analyzed_by_config.get(config_id) or {}).get("role")
        for config_id in H10_QUIET_BENCHMARK_CONFIG_IDS
    }
    diagnostic_config_id = H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]
    diagnostic_row = analyzed_by_config.get(diagnostic_config_id) or {}

    _add_check(
        checks,
        "robustness_family_ready",
        artifact.get("artifact_family") == SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY
        and artifact.get("status") == "ready",
        "Robustness artifact family/status must be ready h10 robustness",
        {"artifact_family": artifact.get("artifact_family"), "status": artifact.get("status")},
    )
    _add_check(
        checks,
        "robustness_claim_ceiling_research_only",
        artifact.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING,
        "Robustness artifact claim ceiling must remain research_observation",
        {"claim_ceiling": artifact.get("claim_ceiling")},
    )
    _add_check(
        checks,
        "robustness_benchmark_rows_present",
        benchmark_rows_present,
        "Robustness artifact must include fixed85/fixed80 benchmark analyzed rows",
        {"benchmark_config_ids": list(H10_QUIET_BENCHMARK_CONFIG_IDS)},
    )
    _add_check(
        checks,
        "robustness_benchmark_roles",
        benchmark_rows_present and all(role == "benchmark_control" for role in benchmark_roles.values()),
        "fixed85/fixed80 robustness rows must have benchmark_control role",
        {"roles": benchmark_roles},
    )
    _add_check(
        checks,
        "robustness_diagnostic_90k_role",
        diagnostic_row.get("role") == DIAGNOSTIC_ANALYSIS_ROLE,
        "90k robustness row must remain diagnostic_boundary",
        {"config_id": diagnostic_config_id, "role": diagnostic_row.get("role")},
    )
    _add_check(
        checks,
        "robustness_benchmark_source_consistency",
        benchmark_rows_present
        and all((row.get("source_replay_consistency") or {}).get("status") == "passed" for row in benchmark_rows),
        "fixed85/fixed80 source replay consistency must pass",
    )
    _add_check(
        checks,
        "robustness_benchmark_top_winner_stress",
        benchmark_rows_present and all(_has_top_winner_stress(row) for row in benchmark_rows),
        "fixed85/fixed80 rows must include top-winner removal stress",
    )
    _add_check(
        checks,
        "robustness_benchmark_yearly_periods",
        set(H10_QUIET_BENCHMARK_CONFIG_IDS) <= yearly_config_ids,
        "fixed85/fixed80 must have yearly period-reset rows",
        {"yearly_config_count": len(yearly_config_ids)},
    )
    _add_check(
        checks,
        "robustness_risk_flags_present",
        bool(artifact.get("risk_flags")),
        "Robustness artifact must preserve risk flag evidence",
        {"risk_flag_count": len(artifact.get("risk_flags") or [])},
    )
    _add_check(
        checks,
        "robustness_not_paper_tracking_ready",
        (artifact.get("recommendation") or {}).get("status") == "not_ready_for_paper_tracking",
        "Robustness recommendation must not promote paper tracking",
        {"recommendation_status": (artifact.get("recommendation") or {}).get("status")},
    )


def _validate_execution_content(
    artifact: dict[str, Any],
    robustness_artifact: dict[str, Any] | None,
    checks: list[dict[str, Any]],
) -> None:
    rows_by_config = _rows_by_config(artifact.get("config_decompositions"))
    diagnostic_config_id = H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]
    target_config_ids = (
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
        H10_QUIET_CHAMPION_CONFIG_ID,
        diagnostic_config_id,
    )
    source_robustness = artifact.get("source_robustness_artifact") or {}
    source_matches = robustness_artifact is not None and source_robustness.get("artifact_id") == robustness_artifact.get(
        "artifact_id"
    )

    _add_check(
        checks,
        "execution_family_ready",
        artifact.get("artifact_family") == SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY
        and artifact.get("status") == "ready",
        "Execution artifact family/status must be ready h10 execution decomposition",
        {"artifact_family": artifact.get("artifact_family"), "status": artifact.get("status")},
    )
    _add_check(
        checks,
        "execution_claim_ceiling_research_only",
        artifact.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING,
        "Execution artifact claim ceiling must remain research_observation",
        {"claim_ceiling": artifact.get("claim_ceiling")},
    )
    _add_check(
        checks,
        "execution_source_matches_robustness",
        source_matches
        and source_robustness.get("artifact_family") == SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY
        and source_robustness.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING,
        "Execution source robustness reference must match the validated robustness artifact",
        {
            "source_artifact_id": source_robustness.get("artifact_id"),
            "robustness_artifact_id": (robustness_artifact or {}).get("artifact_id"),
            "source_claim_ceiling": source_robustness.get("claim_ceiling"),
        },
    )
    _add_check(
        checks,
        "execution_required_rows_present",
        set(target_config_ids) <= set(rows_by_config),
        "Execution artifact must include fixed80/fixed85/90k rows",
        {"present_config_ids": sorted(rows_by_config)},
    )
    _add_check(
        checks,
        "execution_no_missing_config_ids",
        (artifact.get("analysis_scope") or {}).get("missing_config_ids") == [],
        "Execution artifact must report no missing target config IDs",
        {"missing_config_ids": (artifact.get("analysis_scope") or {}).get("missing_config_ids")},
    )
    _add_check(
        checks,
        "execution_benchmark_rows_not_diagnostic",
        all(
            (rows_by_config.get(config_id) or {}).get("role") == "benchmark_control"
            and (rows_by_config.get(config_id) or {}).get("diagnostic_only") is False
            for config_id in H10_QUIET_BENCHMARK_CONFIG_IDS
        ),
        "fixed85/fixed80 execution rows must be benchmark rows, not diagnostic-only rows",
    )
    _add_check(
        checks,
        "execution_90k_diagnostic_only",
        (rows_by_config.get(diagnostic_config_id) or {}).get("role") == DIAGNOSTIC_ANALYSIS_ROLE
        and (rows_by_config.get(diagnostic_config_id) or {}).get("diagnostic_only") is True,
        "90k execution row must be diagnostic-only",
        {"config_id": diagnostic_config_id},
    )
    _add_check(
        checks,
        "execution_target_notionals",
        _target_notional(rows_by_config.get(H10_QUIET_CAPITAL_SHADOW_CONFIG_ID)) == 80_000.0
        and _target_notional(rows_by_config.get(H10_QUIET_CHAMPION_CONFIG_ID)) == 85_000.0
        and _target_notional(rows_by_config.get(diagnostic_config_id)) == 90_000.0,
        "Execution rows must preserve fixed80/fixed85/90k target notionals",
    )
    _add_check(
        checks,
        "execution_decomposition_dimensions",
        all(_has_execution_dimensions(rows_by_config.get(config_id) or {}) for config_id in target_config_ids),
        "Execution rows must include board-lot, cash, turnover/skip, winner, and funding dimensions",
    )
    _add_check(
        checks,
        "execution_pairwise_funding_effects",
        _valid_pairwise_funding_effects(artifact.get("pairwise_funding_effects")),
        "Execution artifact must include fixed80 and 90k pairwise effects versus fixed85",
    )
    promotion_policy = str((artifact.get("decomposition_policy") or {}).get("promotion_policy") or "").lower()
    _add_check(
        checks,
        "execution_90k_cannot_promote",
        "diagnostic-only" in promotion_policy and "cannot be promoted" in promotion_policy,
        "Execution promotion policy must state 90k cannot be promoted",
        {"promotion_policy": (artifact.get("decomposition_policy") or {}).get("promotion_policy")},
    )


def _add_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    check = {
        "check_id": check_id,
        "passed": bool(passed),
        "message": message,
    }
    if details:
        check["details"] = details
    checks.append(check)


def _rows_by_config(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("config_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("config_id")
    }


def _has_top_winner_stress(row: dict[str, Any] | None) -> bool:
    if not isinstance(row, dict):
        return False
    return any(
        isinstance(stress, dict)
        and _optional_int(stress.get("remove_top_winner_count")) == 1
        and stress.get("method") == TOP_WINNER_STRESS_METHOD
        for stress in row.get("trade_contribution_stress") or []
    )


def _target_notional(row: dict[str, Any] | None) -> float | None:
    if not isinstance(row, dict):
        return None
    value = row.get("target_notional")
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _has_execution_dimensions(row: dict[str, Any]) -> bool:
    required_sections = (
        "board_lot",
        "cash_deployment",
        "turnover_skip",
        "winner_concentration",
        "funding_effect_vs_fixed85",
    )
    return all(isinstance(row.get(section), dict) for section in required_sections)


def _valid_pairwise_funding_effects(rows: Any) -> bool:
    if not isinstance(rows, list):
        return False
    valid_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("baseline_config_id") == H10_QUIET_CHAMPION_CONFIG_ID
        and {"total_return_delta", "turnover_delta", "skip_count_delta"} <= set(row)
    ]
    if len(valid_rows) != len(rows):
        return False
    return len(valid_rows) == 2 and {str(row.get("config_id")) for row in valid_rows} == {
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
        H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0],
    }


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _robustness_summary(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if artifact is None:
        return {}
    return {
        "artifact_id": artifact.get("artifact_id"),
        "status": artifact.get("status"),
        "claim_ceiling": artifact.get("claim_ceiling"),
        "recommendation_status": (artifact.get("recommendation") or {}).get("status"),
        "analyzed_config_count": len(artifact.get("analyzed_configs") or []),
        "risk_flag_count": len(artifact.get("risk_flags") or []),
        "high_risk_flag_count": sum(1 for flag in artifact.get("risk_flags") or [] if flag.get("severity") == "high"),
    }


def _execution_summary(artifact: dict[str, Any] | None) -> dict[str, Any]:
    if artifact is None:
        return {}
    return {
        "artifact_id": artifact.get("artifact_id"),
        "status": artifact.get("status"),
        "claim_ceiling": artifact.get("claim_ceiling"),
        "decomposed_config_count": len(artifact.get("config_decompositions") or []),
        "missing_config_ids": (artifact.get("analysis_scope") or {}).get("missing_config_ids"),
    }
