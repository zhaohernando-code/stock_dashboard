from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema

from ashare_evidence.shortpick_v2_h10_execution_decomposition import (
    SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_h10_parameter_significance import (
    SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_ARTIFACT_FAMILY,
    validate_shortpick_v2_h10_parameter_significance_payload,
)
from ashare_evidence.shortpick_v2_h10_rank_ablation import (
    SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_h10_robustness import (
    DIAGNOSTIC_ANALYSIS_ROLE,
    H10_QUIET_DIAGNOSTIC_CONFIG_IDS,
    SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
)
from ashare_evidence.shortpick_v2_rule_selection import (
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
    H10_QUIET_CHAMPION_CONFIG_ID,
)

SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY = "shortpick_v2_h10_paper_governance_artifact"
SHORTPICK_V2_H10_PAPER_GOVERNANCE_SCHEMA_VERSION = "v1"
SHORTPICK_V2_H10_PAPER_GOVERNANCE_SOURCE_PLAN_REF = (
    "plans/active/plan-20260615-h10-paper-governance.md"
)
SHORTPICK_V2_H10_PAPER_GOVERNANCE_SCHEMA_NAME = "shortpick_v2_h10_paper_governance_artifact.schema.json"
DEFAULT_SCHEMA_ROOT = Path("docs/contracts/registry/schemas")
RESEARCH_OBSERVATION_CLAIM_CEILING = "research_observation"
HISTORICAL_GOVERNANCE_EVIDENCE_BASIS = (
    "historical_governance_evidence_future_true_forward_observation_only"
)
PAPER_TRACKING_START_DATE = "2026-05-08"
MIN_ANNUALIZED_RETURN = 0.30
H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID = H10_QUIET_DIAGNOSTIC_CONFIG_IDS[0]
H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS = (
    H10_QUIET_CHAMPION_CONFIG_ID,
    H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
)
PRIOR_DECISION_DOC = "docs/archive/SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md"
PRIOR_NO_PROMOTION_DECISION = "not_promoted_to_paper_tracking_by_prior_plan"
FORWARD_OBSERVATION_DISPOSITION = (
    "future_true_forward_observation_candidate_only_no_historical_rows_no_performance_claim"
)
RISK_FLAG_DISPOSITION = "open_risks_carried_to_forward_observation"
LEDGER_POLICY = "future_true_forward_only_no_historical_backfill"
ENTRY_POLICY = "declared_entry_date_only_fallback_or_skip_no_delayed_entry"
NO_DELAYED_BUY_POLICY = "candidate_or_fallback_on_declared_day_or_skip_no_delay"
FIXED90_POLICY = "diagnostic_only_blocked_without_separate_turnover_governance"
RECOMMENDATION_STATUS = "forward_observation_ready_with_open_risks"
PAPER_TRACKING_STATUS = "not_started_no_true_forward_rows"
ALLOWED_SIGNAL_ACTIONS = ("buy_primary", "buy_fallback", "skip")
FORBIDDEN_SIGNAL_ACTIONS = ("delay_buy", "later_buy", "retry_buy", "discretionary_buy")


def build_shortpick_v2_h10_paper_governance_artifact_from_paths(
    *,
    rank_ablation_artifact_path: str | Path,
    parameter_significance_artifact_path: str | Path,
    robustness_artifact_path: str | Path,
    execution_artifact_path: str | Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    return build_shortpick_v2_h10_paper_governance_artifact(
        rank_ablation_artifact=_read_json_artifact(rank_ablation_artifact_path, label="h10 rank ablation"),
        parameter_significance_artifact=_read_json_artifact(
            parameter_significance_artifact_path,
            label="h10 parameter significance",
        ),
        robustness_artifact=_read_json_artifact(robustness_artifact_path, label="h10 robustness"),
        execution_artifact=_read_json_artifact(execution_artifact_path, label="h10 execution decomposition"),
        artifact_paths={
            "rank_ablation": str(Path(rank_ablation_artifact_path)),
            "parameter_significance": str(Path(parameter_significance_artifact_path)),
            "robustness": str(Path(robustness_artifact_path)),
            "execution_decomposition": str(Path(execution_artifact_path)),
        },
        generated_at=generated_at,
    )


def build_shortpick_v2_h10_paper_governance_artifact(
    *,
    rank_ablation_artifact: dict[str, Any],
    parameter_significance_artifact: dict[str, Any],
    robustness_artifact: dict[str, Any],
    execution_artifact: dict[str, Any],
    artifact_paths: dict[str, str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or datetime.now(UTC)
    artifact_paths = artifact_paths or {}
    source_validation = _source_validation_summary(
        rank_ablation_artifact=rank_ablation_artifact,
        parameter_significance_artifact=parameter_significance_artifact,
        robustness_artifact=robustness_artifact,
        execution_artifact=execution_artifact,
    )
    source_disposition = _source_disposition(robustness_artifact)
    candidate_configs = [
        _candidate_config(
            H10_QUIET_CHAMPION_CONFIG_ID,
            robustness_artifact,
            role="primary_future_observation_candidate",
        ),
        _candidate_config(
            H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
            robustness_artifact,
            role="capital_shadow_future_observation_candidate",
        ),
    ]
    diagnostic_configs = [_diagnostic_config(H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID, robustness_artifact, execution_artifact)]
    payload = {
        "artifact_family": SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY,
        "schema_version": SHORTPICK_V2_H10_PAPER_GOVERNANCE_SCHEMA_VERSION,
        "artifact_id": _artifact_id(generated_at, robustness_artifact),
        "generated_at": generated_at.isoformat(),
        "status": "ready",
        "claim_ceiling": RESEARCH_OBSERVATION_CLAIM_CEILING,
        "evidence_basis": HISTORICAL_GOVERNANCE_EVIDENCE_BASIS,
        "source_plan_ref": SHORTPICK_V2_H10_PAPER_GOVERNANCE_SOURCE_PLAN_REF,
        "source_artifacts": {
            "rank_ablation": _source_artifact_ref(
                rank_ablation_artifact,
                artifact_paths.get("rank_ablation"),
            ),
            "parameter_significance": _source_artifact_ref(
                parameter_significance_artifact,
                artifact_paths.get("parameter_significance"),
            ),
            "robustness": _source_artifact_ref(
                robustness_artifact,
                artifact_paths.get("robustness"),
            ),
            "execution_decomposition": _source_artifact_ref(
                execution_artifact,
                artifact_paths.get("execution_decomposition"),
            ),
        },
        "analysis_scope": _analysis_scope(robustness_artifact),
        "governance_policy": {
            "ledger_policy": LEDGER_POLICY,
            "entry_policy": ENTRY_POLICY,
            "no_delayed_buy_policy": NO_DELAYED_BUY_POLICY,
            "fixed90_policy": FIXED90_POLICY,
            "qualification_floor": {
                "min_annualized_return": MIN_ANNUALIZED_RETURN,
                "must_beat_market": True,
            },
            "claim_policy": "historical_replay_is_not_true_forward_paper_performance",
        },
        "source_validation": source_validation,
        "source_disposition": source_disposition,
        "candidate_configs": candidate_configs,
        "diagnostic_configs": diagnostic_configs,
        "ledger_contract_overlay": {
            "selected_config_ids": list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS),
            "diagnostic_rejected_config_ids": [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
            "allowed_signal_actions": list(ALLOWED_SIGNAL_ACTIONS),
            "forbidden_signal_actions": list(FORBIDDEN_SIGNAL_ACTIONS),
            "entry_policy": ENTRY_POLICY,
            "ledger_policy": LEDGER_POLICY,
            "paper_tracking_start_date": PAPER_TRACKING_START_DATE,
            "record_backfill_allowed": False,
            "current_true_forward_record_count": 0,
            "row_evidence_basis": "future_true_forward_paper_tracking_only",
        },
        "recommendation": {
            "status": RECOMMENDATION_STATUS,
            "paper_tracking_status": PAPER_TRACKING_STATUS,
            "notes": [
                "This artifact records future observation eligibility only.",
                "Historical replay return is not paper-tracking performance.",
                "Open robustness risks must remain visible until true-forward rows exist.",
            ],
        },
        "leakage_audit": {
            "status": "passed",
            "no_historical_paper_row_backfill": True,
            "no_delayed_buy_action": True,
            "no_fixed90_promotion": True,
            "no_database_write_or_refresh": True,
            "no_investment_or_production_claim": True,
        },
        "event_refs": [
            "shortpick_v2.h10_paper_governance.generated",
            f"shortpick_v2.h10_paper_governance.source_robustness.{robustness_artifact.get('artifact_id')}",
        ],
    }
    if validate_shortpick_v2_h10_paper_governance_payload(payload)["failed_check_count"]:
        payload["status"] = "blocked"
    return payload


def write_shortpick_v2_h10_paper_governance_artifact(
    payload: dict[str, Any],
    *,
    output_path: str | Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def validate_shortpick_v2_h10_paper_governance_artifact(
    *,
    artifact_path: str | Path,
    schema_root: str | Path = DEFAULT_SCHEMA_ROOT,
) -> dict[str, Any]:
    path = Path(artifact_path)
    checks: list[dict[str, Any]] = []
    payload = _load_json(path, checks, check_id="paper_governance_json_readable")
    if payload is not None:
        _validate_schema(
            payload,
            schema_path=Path(schema_root) / SHORTPICK_V2_H10_PAPER_GOVERNANCE_SCHEMA_NAME,
            checks=checks,
            check_id="paper_governance_schema_valid",
        )
        checks.extend(validate_shortpick_v2_h10_paper_governance_payload(payload)["checks"])
    failed_checks = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed_checks else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed_checks),
        "artifact_path": str(path),
        "artifact_summary": _artifact_summary(payload),
        "checks": checks,
    }


def validate_shortpick_v2_h10_paper_governance_payload(payload: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    source_artifacts = payload.get("source_artifacts") if isinstance(payload.get("source_artifacts"), dict) else {}
    source_validation = payload.get("source_validation") if isinstance(payload.get("source_validation"), dict) else {}
    source_disposition = payload.get("source_disposition") if isinstance(payload.get("source_disposition"), dict) else {}
    policy = payload.get("governance_policy") if isinstance(payload.get("governance_policy"), dict) else {}
    ledger = (
        payload.get("ledger_contract_overlay")
        if isinstance(payload.get("ledger_contract_overlay"), dict)
        else {}
    )
    recommendation = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    leakage = payload.get("leakage_audit") if isinstance(payload.get("leakage_audit"), dict) else {}
    candidates = payload.get("candidate_configs") if isinstance(payload.get("candidate_configs"), list) else []
    diagnostics = payload.get("diagnostic_configs") if isinstance(payload.get("diagnostic_configs"), list) else []

    _add_check(
        checks,
        "paper_governance_family_ready",
        payload.get("artifact_family") == SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY
        and payload.get("status") == "ready",
        "Paper governance artifact family/status must be ready",
        {"artifact_family": payload.get("artifact_family"), "status": payload.get("status")},
    )
    _add_check(
        checks,
        "paper_governance_claim_ceiling_research_only",
        payload.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING
        and payload.get("evidence_basis") == HISTORICAL_GOVERNANCE_EVIDENCE_BASIS,
        "Paper governance artifact must remain historical research governance evidence",
        {"claim_ceiling": payload.get("claim_ceiling"), "evidence_basis": payload.get("evidence_basis")},
    )
    _validate_source_artifacts(source_artifacts, checks)
    _validate_source_validation(source_validation, checks)
    _validate_source_disposition(source_disposition, checks)
    _validate_policy(policy, checks)
    _validate_candidate_configs(candidates, checks)
    _validate_diagnostic_configs(diagnostics, checks)
    _validate_ledger_overlay(ledger, checks)
    _add_check(
        checks,
        "recommendation_forward_observation_only",
        recommendation.get("status") == RECOMMENDATION_STATUS
        and recommendation.get("paper_tracking_status") == PAPER_TRACKING_STATUS,
        "Recommendation must be forward-observation readiness only, with no started paper rows",
        {
            "status": recommendation.get("status"),
            "paper_tracking_status": recommendation.get("paper_tracking_status"),
        },
    )
    _add_check(
        checks,
        "leakage_audit_no_backfill_or_delay",
        leakage.get("status") == "passed"
        and leakage.get("no_historical_paper_row_backfill") is True
        and leakage.get("no_delayed_buy_action") is True
        and leakage.get("no_fixed90_promotion") is True
        and leakage.get("no_investment_or_production_claim") is True,
        "Leakage audit must block historical backfill, delayed buy, fixed90 promotion, and investment claims",
        {"leakage_audit": leakage},
    )
    failed = [check for check in checks if not check["passed"]]
    return {
        "status": "passed" if not failed else "failed",
        "check_count": len(checks),
        "failed_check_count": len(failed),
        "checks": checks,
    }


def _validate_source_artifacts(source_artifacts: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    expected = {
        "rank_ablation": SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY,
        "parameter_significance": SHORTPICK_V2_H10_PARAMETER_SIGNIFICANCE_ARTIFACT_FAMILY,
        "robustness": SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
        "execution_decomposition": SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY,
    }
    for key, family in expected.items():
        ref = source_artifacts.get(key) if isinstance(source_artifacts.get(key), dict) else {}
        _add_check(
            checks,
            f"source_{key}_ref_present",
            ref.get("artifact_family") == family
            and ref.get("status") == "ready"
            and ref.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING,
            f"Source artifact ref for {key} must be ready research evidence",
            {"artifact_family": ref.get("artifact_family"), "status": ref.get("status")},
        )


def _validate_source_validation(source_validation: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    _add_check(
        checks,
        "source_validation_overall_passed",
        source_validation.get("overall_status") == "passed",
        "Source validation summary must pass",
        {"overall_status": source_validation.get("overall_status")},
    )
    _add_check(
        checks,
        "source_validation_rank2_supported",
        (source_validation.get("rank_ablation") or {}).get("rank2_support_label") == "supported",
        "Rank ablation source must support rank2",
        {"rank2_support_label": (source_validation.get("rank_ablation") or {}).get("rank2_support_label")},
    )
    _add_check(
        checks,
        "source_validation_parameter_significance_passed",
        (source_validation.get("parameter_significance") or {}).get("status") == "passed",
        "Parameter-significance source must be validated and present",
        {"status": (source_validation.get("parameter_significance") or {}).get("status")},
    )
    _add_check(
        checks,
        "source_validation_robustness_not_ready_disposed",
        (source_validation.get("robustness") or {}).get("recommendation_status") == "not_ready_for_paper_tracking",
        "Robustness source must preserve not_ready_for_paper_tracking",
        {"recommendation_status": (source_validation.get("robustness") or {}).get("recommendation_status")},
    )
    _add_check(
        checks,
        "source_validation_execution_ready",
        (source_validation.get("execution_decomposition") or {}).get("status") == "passed",
        "Execution source must be validated",
        {"status": (source_validation.get("execution_decomposition") or {}).get("status")},
    )


def _validate_source_disposition(source_disposition: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    _add_check(
        checks,
        "source_disposition_prior_no_promotion",
        source_disposition.get("prior_decision") == PRIOR_NO_PROMOTION_DECISION
        and source_disposition.get("governance_disposition") == FORWARD_OBSERVATION_DISPOSITION,
        "Prior no-promotion decision must be carried as forward-observation-only disposition",
        {
            "prior_decision": source_disposition.get("prior_decision"),
            "governance_disposition": source_disposition.get("governance_disposition"),
        },
    )
    _add_check(
        checks,
        "source_disposition_risk_flags_preserved",
        _optional_int(source_disposition.get("risk_flag_count")) is not None
        and _optional_int(source_disposition.get("risk_flag_count")) > 0
        and _optional_int(source_disposition.get("high_risk_flag_count")) is not None
        and _optional_int(source_disposition.get("high_risk_flag_count")) > 0
        and source_disposition.get("risk_flag_disposition") == RISK_FLAG_DISPOSITION,
        "Robustness risk flags, including high-risk flags, must be preserved and disposed",
        {
            "risk_flag_count": source_disposition.get("risk_flag_count"),
            "high_risk_flag_count": source_disposition.get("high_risk_flag_count"),
            "risk_flag_disposition": source_disposition.get("risk_flag_disposition"),
        },
    )
    _add_check(
        checks,
        "source_disposition_robustness_status_preserved",
        source_disposition.get("robustness_recommendation_status") == "not_ready_for_paper_tracking",
        "Source robustness not-ready status must remain visible",
        {"robustness_recommendation_status": source_disposition.get("robustness_recommendation_status")},
    )


def _validate_policy(policy: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    floor = policy.get("qualification_floor") if isinstance(policy.get("qualification_floor"), dict) else {}
    _add_check(
        checks,
        "policy_future_only_no_backfill",
        policy.get("ledger_policy") == LEDGER_POLICY
        and policy.get("entry_policy") == ENTRY_POLICY
        and policy.get("no_delayed_buy_policy") == NO_DELAYED_BUY_POLICY,
        "Governance policy must be future-only, no-backfill, and no-delay",
        {
            "ledger_policy": policy.get("ledger_policy"),
            "entry_policy": policy.get("entry_policy"),
            "no_delayed_buy_policy": policy.get("no_delayed_buy_policy"),
        },
    )
    _add_check(
        checks,
        "policy_fixed90_diagnostic_only",
        policy.get("fixed90_policy") == FIXED90_POLICY,
        "Governance policy must keep fixed90 diagnostic-only",
        {"fixed90_policy": policy.get("fixed90_policy")},
    )
    _add_check(
        checks,
        "policy_qualification_floor",
        _optional_float(floor.get("min_annualized_return")) == MIN_ANNUALIZED_RETURN
        and floor.get("must_beat_market") is True,
        "Governance policy must retain market and 30% annualized return floors",
        {"qualification_floor": floor},
    )


def _validate_candidate_configs(candidates: list[Any], checks: list[dict[str, Any]]) -> None:
    expected_roles = {
        H10_QUIET_CHAMPION_CONFIG_ID: "primary_future_observation_candidate",
        H10_QUIET_CAPITAL_SHADOW_CONFIG_ID: "capital_shadow_future_observation_candidate",
    }
    candidate_ids = [
        str(row.get("config_id"))
        for row in candidates
        if isinstance(row, dict) and row.get("config_id")
    ]
    candidate_by_config = {
        str(row.get("config_id")): row
        for row in candidates
        if isinstance(row, dict) and row.get("config_id")
    }
    _add_check(
        checks,
        "candidate_configs_exact_fixed85_fixed80_only",
        len(candidates) == len(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS)
        and tuple(candidate_ids) == H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS
        and len(candidate_ids) == len(set(candidate_ids))
        and H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID not in candidate_ids,
        "Candidate rows must be exactly fixed85 then fixed80; fixed90 and extra configs are not eligible",
        {
            "expected_config_ids": list(H10_QUIET_PAPER_CANDIDATE_CONFIG_IDS),
            "present_config_ids": candidate_ids,
        },
    )
    for config_id, expected_role in expected_roles.items():
        row = candidate_by_config.get(config_id) or {}
        qualification = row.get("qualification_checks") if isinstance(row.get("qualification_checks"), dict) else {}
        summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
        summary_annualized = _optional_float(summary.get("annualized_return"))
        summary_market_excess = _optional_float(summary.get("market_excess_total_return"))
        qualification_annualized = _optional_float(qualification.get("annualized_return"))
        qualification_market_excess = _optional_float(qualification.get("market_excess_total_return"))
        summary_meets_floor = summary_annualized is not None and summary_annualized >= MIN_ANNUALIZED_RETURN
        summary_beats_market = summary_market_excess is not None and summary_market_excess > 0.0
        _add_check(
            checks,
            f"candidate_{config_id}_role_and_status",
            row.get("role") == expected_role
            and row.get("eligibility_status") == "future_true_forward_observation_candidate_only"
            and row.get("paper_tracking_performance_claim") is False
            and row.get("current_true_forward_record_count") == 0,
            "Candidate row must be future-observation only with zero true-forward records",
            {
                "role": row.get("role"),
                "eligibility_status": row.get("eligibility_status"),
                "paper_tracking_performance_claim": row.get("paper_tracking_performance_claim"),
            },
        )
        _add_check(
            checks,
            f"candidate_{config_id}_summary_return_floor",
            summary_meets_floor and summary_beats_market,
            "Candidate summary must directly beat market and meet 30% annualized return floor",
            {
                "summary_annualized_return": summary_annualized,
                "summary_market_excess_total_return": summary_market_excess,
            },
        )
        _add_check(
            checks,
            f"candidate_{config_id}_qualification",
            qualification.get("passed") is True
            and qualification.get("annualized_return_meets_floor") is True
            and qualification.get("beats_market") is True
            and _float_equals(qualification_annualized, summary_annualized)
            and _float_equals(qualification_market_excess, summary_market_excess)
            and summary_meets_floor
            and summary_beats_market,
            "Candidate qualification flags must match summary values and the market/30% return floors",
            {
                "qualification_checks": qualification,
                "summary_annualized_return": summary_annualized,
                "summary_market_excess_total_return": summary_market_excess,
            },
        )


def _validate_diagnostic_configs(diagnostics: list[Any], checks: list[dict[str, Any]]) -> None:
    diagnostic_ids = [
        str(row.get("config_id"))
        for row in diagnostics
        if isinstance(row, dict) and row.get("config_id")
    ]
    diagnostic_by_config = {
        str(row.get("config_id")): row
        for row in diagnostics
        if isinstance(row, dict) and row.get("config_id")
    }
    row = diagnostic_by_config.get(H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID) or {}
    _add_check(
        checks,
        "diagnostic_configs_exact_fixed90_only",
        len(diagnostics) == 1 and diagnostic_ids == [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
        "Diagnostic rows must contain only fixed90",
        {"present_config_ids": diagnostic_ids},
    )
    _add_check(
        checks,
        "diagnostic_fixed90_not_eligible",
        row.get("role") == DIAGNOSTIC_ANALYSIS_ROLE
        and row.get("diagnostic_only") is True
        and row.get("paper_tracking_eligible") is False
        and row.get("blocked_reason") == FIXED90_POLICY,
        "fixed90 diagnostic row must be blocked from paper tracking",
        {"diagnostic_row": row},
    )


def _validate_ledger_overlay(ledger: dict[str, Any], checks: list[dict[str, Any]]) -> None:
    _add_check(
        checks,
        "ledger_overlay_selected_candidates",
        tuple(ledger.get("selected_config_ids") or ()) == (
            H10_QUIET_CHAMPION_CONFIG_ID,
            H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
        )
        and H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID in (ledger.get("diagnostic_rejected_config_ids") or []),
        "Ledger overlay must allow only fixed85/fixed80 and reject fixed90",
        {
            "selected_config_ids": ledger.get("selected_config_ids"),
            "diagnostic_rejected_config_ids": ledger.get("diagnostic_rejected_config_ids"),
        },
    )
    _add_check(
        checks,
        "ledger_overlay_future_only_no_delay",
        ledger.get("ledger_policy") == LEDGER_POLICY
        and ledger.get("entry_policy") == ENTRY_POLICY
        and ledger.get("record_backfill_allowed") is False
        and ledger.get("current_true_forward_record_count") == 0
        and tuple(ledger.get("allowed_signal_actions") or ()) == ALLOWED_SIGNAL_ACTIONS
        and set(FORBIDDEN_SIGNAL_ACTIONS) <= set(ledger.get("forbidden_signal_actions") or []),
        "Ledger overlay must be true-forward only and reject delayed actions",
        {"ledger_overlay": ledger},
    )


def _source_validation_summary(
    *,
    rank_ablation_artifact: dict[str, Any],
    parameter_significance_artifact: dict[str, Any],
    robustness_artifact: dict[str, Any],
    execution_artifact: dict[str, Any],
) -> dict[str, Any]:
    parameter_validation = validate_shortpick_v2_h10_parameter_significance_payload(parameter_significance_artifact)
    rank_label = str((rank_ablation_artifact.get("rank2_decision") or {}).get("support_label") or "")
    robustness_flags = [flag for flag in robustness_artifact.get("risk_flags") or [] if isinstance(flag, dict)]
    execution_rows = _rows_by_config(execution_artifact.get("config_decompositions"))
    execution_missing = (execution_artifact.get("analysis_scope") or {}).get("missing_config_ids")
    execution_passed = (
        _source_is_ready(
            execution_artifact,
            expected_family=SHORTPICK_V2_H10_EXECUTION_DECOMPOSITION_ARTIFACT_FAMILY,
        )
        and execution_missing == []
        and {H10_QUIET_CAPITAL_SHADOW_CONFIG_ID, H10_QUIET_CHAMPION_CONFIG_ID, H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID}
        <= set(execution_rows)
        and (execution_rows.get(H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID) or {}).get("diagnostic_only") is True
    )
    summaries = {
        "rank_ablation": {
            "status": "passed"
            if _source_is_ready(
                rank_ablation_artifact,
                expected_family=SHORTPICK_V2_H10_RANK_ABLATION_ARTIFACT_FAMILY,
            )
            and rank_label == "supported"
            else "failed",
            "rank2_support_label": rank_label,
            "recommendation_status": (rank_ablation_artifact.get("recommendation") or {}).get("status"),
        },
        "parameter_significance": {
            "status": parameter_validation["status"],
            "failed_check_count": parameter_validation["failed_check_count"],
            "recommendation_status": (parameter_significance_artifact.get("recommendation") or {}).get("status"),
        },
        "robustness": {
            "status": "passed"
            if _source_is_ready(
                robustness_artifact,
                expected_family=SHORTPICK_V2_H10_ROBUSTNESS_ARTIFACT_FAMILY,
            )
            and (robustness_artifact.get("recommendation") or {}).get("status") == "not_ready_for_paper_tracking"
            and bool(robustness_flags)
            else "failed",
            "recommendation_status": (robustness_artifact.get("recommendation") or {}).get("status"),
            "risk_flag_count": len(robustness_flags),
            "high_risk_flag_count": sum(1 for flag in robustness_flags if flag.get("severity") == "high"),
        },
        "execution_decomposition": {
            "status": "passed" if execution_passed else "failed",
            "missing_config_ids": execution_missing,
        },
    }
    summaries["overall_status"] = (
        "passed"
        if all((row.get("status") == "passed") for key, row in summaries.items() if key != "overall_status")
        else "failed"
    )
    return summaries


def _source_disposition(robustness_artifact: dict[str, Any]) -> dict[str, Any]:
    risk_flags = [flag for flag in robustness_artifact.get("risk_flags") or [] if isinstance(flag, dict)]
    return {
        "prior_decision_ref": {
            "path": PRIOR_DECISION_DOC,
            "section": "Benchmark-Focused Robustness Decision",
        },
        "prior_decision": PRIOR_NO_PROMOTION_DECISION,
        "robustness_recommendation_status": (robustness_artifact.get("recommendation") or {}).get("status"),
        "risk_flag_count": len(risk_flags),
        "high_risk_flag_count": sum(1 for flag in risk_flags if flag.get("severity") == "high"),
        "risk_flag_disposition": RISK_FLAG_DISPOSITION,
        "governance_disposition": FORWARD_OBSERVATION_DISPOSITION,
        "open_risk_flags": [_risk_flag_projection(flag) for flag in risk_flags],
    }


def _analysis_scope(robustness_artifact: dict[str, Any]) -> dict[str, Any]:
    scope = robustness_artifact.get("analysis_scope") if isinstance(robustness_artifact.get("analysis_scope"), dict) else {}
    return {
        "horizon_days": scope.get("horizon_days", 10),
        "initial_cash": scope.get("initial_cash"),
        "signal_date_from": scope.get("signal_date_from"),
        "signal_date_to": scope.get("signal_date_to"),
        "paper_tracking_start_date": PAPER_TRACKING_START_DATE,
        "primary_config_id": H10_QUIET_CHAMPION_CONFIG_ID,
        "capital_shadow_config_id": H10_QUIET_CAPITAL_SHADOW_CONFIG_ID,
        "diagnostic_config_ids": [H10_QUIET_DIAGNOSTIC_90K_CONFIG_ID],
    }


def _candidate_config(config_id: str, robustness_artifact: dict[str, Any], *, role: str) -> dict[str, Any]:
    analyzed = _rows_by_config(robustness_artifact.get("analyzed_configs")).get(config_id) or {}
    summary = analyzed.get("summary") if isinstance(analyzed.get("summary"), dict) else {}
    annualized = _optional_float(summary.get("annualized_return"))
    total_return = _optional_float(summary.get("total_return"))
    market_reference_total_return = _optional_float(summary.get("market_reference_total_return"))
    market_excess = _optional_float(summary.get("market_excess_total_return"))
    if market_excess is None and total_return is not None and market_reference_total_return is not None:
        market_excess = round(total_return - market_reference_total_return, 6)
    annualized_ok = annualized is not None and annualized >= MIN_ANNUALIZED_RETURN
    beats_market = market_excess is not None and market_excess > 0.0
    return {
        "config_id": config_id,
        "role": role,
        "source_role": analyzed.get("role"),
        "eligibility_status": "future_true_forward_observation_candidate_only",
        "paper_tracking_performance_claim": False,
        "current_true_forward_record_count": 0,
        "summary": {
            "total_return": total_return,
            "annualized_return": annualized,
            "market_reference_total_return": market_reference_total_return,
            "market_excess_total_return": market_excess,
            "max_drawdown": _optional_float(summary.get("max_drawdown")),
            "trade_count": _optional_int(summary.get("trade_count")),
            "turnover": _optional_float(summary.get("turnover")),
            "skipped_ratio": _optional_float(summary.get("skipped_ratio")),
        },
        "qualification_checks": {
            "passed": annualized_ok and beats_market,
            "min_annualized_return": MIN_ANNUALIZED_RETURN,
            "annualized_return": annualized,
            "annualized_return_meets_floor": annualized_ok,
            "market_excess_total_return": market_excess,
            "beats_market": beats_market,
        },
    }


def _diagnostic_config(config_id: str, robustness_artifact: dict[str, Any], execution_artifact: dict[str, Any]) -> dict[str, Any]:
    analyzed = _rows_by_config(robustness_artifact.get("analyzed_configs")).get(config_id) or {}
    execution = _rows_by_config(execution_artifact.get("config_decompositions")).get(config_id) or {}
    return {
        "config_id": config_id,
        "role": analyzed.get("role") or execution.get("role") or DIAGNOSTIC_ANALYSIS_ROLE,
        "diagnostic_only": True,
        "paper_tracking_eligible": False,
        "blocked_reason": FIXED90_POLICY,
        "target_notional": _optional_float(execution.get("target_notional")),
    }


def _source_artifact_ref(artifact: dict[str, Any], path: str | None) -> dict[str, Any]:
    return {
        "artifact_id": artifact.get("artifact_id"),
        "artifact_family": artifact.get("artifact_family"),
        "schema_version": artifact.get("schema_version"),
        "status": artifact.get("status"),
        "claim_ceiling": artifact.get("claim_ceiling"),
        "evidence_basis": artifact.get("evidence_basis"),
        "path": path,
    }


def _source_is_ready(artifact: dict[str, Any], *, expected_family: str) -> bool:
    return (
        artifact.get("artifact_family") == expected_family
        and artifact.get("status") == "ready"
        and artifact.get("claim_ceiling") == RESEARCH_OBSERVATION_CLAIM_CEILING
    )


def _rows_by_config(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {str(row.get("config_id")): row for row in rows if isinstance(row, dict) and row.get("config_id")}


def _risk_flag_projection(flag: dict[str, Any]) -> dict[str, Any]:
    return {
        "flag_id": flag.get("flag_id"),
        "severity": flag.get("severity"),
        "message": flag.get("message"),
    }


def _read_json_artifact(path: str | Path, *, label: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must contain a JSON object")
    return payload


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


def _artifact_id(generated_at: datetime, robustness_artifact: dict[str, Any]) -> str:
    source_id = str(robustness_artifact.get("artifact_id") or "unknown").replace(":", "_")
    return f"{SHORTPICK_V2_H10_PAPER_GOVERNANCE_ARTIFACT_FAMILY}:{generated_at.strftime('%Y%m%dT%H%M%SZ')}:{source_id}"


def _artifact_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {}
    disposition = payload.get("source_disposition") if isinstance(payload.get("source_disposition"), dict) else {}
    return {
        "artifact_id": payload.get("artifact_id"),
        "status": payload.get("status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "recommendation_status": (payload.get("recommendation") or {}).get("status"),
        "paper_tracking_status": (payload.get("recommendation") or {}).get("paper_tracking_status"),
        "candidate_count": len(payload.get("candidate_configs") or []),
        "risk_flag_count": disposition.get("risk_flag_count"),
        "high_risk_flag_count": disposition.get("high_risk_flag_count"),
    }


def _optional_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_equals(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= 1e-9
