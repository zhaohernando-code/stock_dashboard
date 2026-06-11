from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

RETIREMENT_EVENT_REF = "shortpick.strategy_retirement.recorded.v1"
RETIREMENT_REASON_CODES = {
    "persistent_negative_after_cost_excess",
    "forward_median_and_win_rate_failure",
    "tail_dependence_failure",
    "baseline_underperformance",
    "duplicate_or_low_diagnostic_value",
}
RETIREMENT_EVIDENCE_BASIS_VALUES = {
    "historical_backtest",
    "retrospective_forward_replay",
    "true_forward_tracking",
}


def run_shortpick_strategy_retirement_artifact(
    evidence_pack_result: dict[str, Any],
    status_recommendation_result: dict[str, Any],
    *,
    strategy_id: str,
    decision_log_ref: str,
    evidence_snapshot_refs: list[str],
    retired_at: str,
    archived_at: str | None = None,
    strategy_version: str = "shortpick-governance-v1",
    retirement_reason_code: str | None = None,
    replacement_guidance: str = "",
    event_refs: list[str] | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    pack = _find_by_strategy_id(evidence_pack_result.get("packs"), strategy_id)
    recommendation = _find_by_strategy_id(status_recommendation_result.get("recommendations"), strategy_id)
    blocker = _blocker(
        pack=pack,
        recommendation=recommendation,
        decision_log_ref=decision_log_ref,
        evidence_snapshot_refs=evidence_snapshot_refs,
        retired_at=retired_at,
        strategy_version=strategy_version,
    )
    if blocker:
        payload = _blocked_payload(strategy_id=strategy_id, blocker=blocker)
        return _with_optional_artifact(payload, output_path)

    basis_refs = _evidence_basis_refs(pack)
    reason_code = retirement_reason_code or _infer_reason_code(recommendation)
    if reason_code not in RETIREMENT_REASON_CODES:
        payload = _blocked_payload(strategy_id=strategy_id, blocker="unsupported_retirement_reason_code")
        return _with_optional_artifact(payload, output_path)
    if not basis_refs:
        payload = _blocked_payload(strategy_id=strategy_id, blocker="missing_supported_evidence_basis_refs")
        return _with_optional_artifact(payload, output_path)

    events = _event_refs(event_refs)
    payload = {
        "artifact_id": _retirement_artifact_id(
            strategy_id=strategy_id,
            decision_log_ref=decision_log_ref,
            evidence_snapshot_refs=evidence_snapshot_refs,
        ),
        "status": "ready",
        "artifact_family": "shortpick_strategy_retirement",
        "schema_version": "v1",
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "strategy_status_before": str(recommendation.get("recommended_status") or ""),
        "retirement_reason_code": reason_code,
        "evidence_snapshot_refs": sorted(set(str(item) for item in evidence_snapshot_refs if str(item))),
        "evidence_basis_refs": basis_refs,
        "retired_at": retired_at,
        "archived_at": archived_at or retired_at,
        "replacement_guidance": replacement_guidance,
        "decision_log_ref": decision_log_ref,
        "event_refs": events,
    }
    return _with_optional_artifact(payload, output_path)


def write_shortpick_strategy_retirement_artifact(payload: dict[str, Any], *, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def load_shortpick_strategy_retirement_inputs(
    *,
    evidence_pack_path: str | Path,
    status_recommendation_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return _load_json_object(evidence_pack_path), _load_json_object(status_recommendation_path)


def _blocker(
    *,
    pack: dict[str, Any],
    recommendation: dict[str, Any],
    decision_log_ref: str,
    evidence_snapshot_refs: list[str],
    retired_at: str,
    strategy_version: str,
) -> str | None:
    if not pack:
        return "strategy_evidence_pack_missing"
    if not recommendation:
        return "strategy_status_recommendation_missing"
    if str(recommendation.get("recommended_status") or "") != "retire_candidate":
        return "strategy_must_be_retire_candidate_before_retirement_artifact"
    if not decision_log_ref:
        return "missing_decision_log_ref"
    if not evidence_snapshot_refs or not any(str(item) for item in evidence_snapshot_refs):
        return "missing_evidence_snapshot_refs"
    if not retired_at:
        return "missing_retired_at"
    if not strategy_version:
        return "missing_strategy_version"
    return None


def _blocked_payload(*, strategy_id: str, blocker: str) -> dict[str, Any]:
    return {
        "artifact_family": "shortpick_strategy_retirement",
        "schema_version": "v1",
        "status": "blocked",
        "strategy_id": strategy_id,
        "blocker": blocker,
        "event_refs": [],
        "write_policy": "blocked_no_retirement_artifact_recorded",
    }


def _with_optional_artifact(payload: dict[str, Any], output_path: str | Path | None) -> dict[str, Any]:
    if output_path is None:
        return payload
    path = write_shortpick_strategy_retirement_artifact(payload, output_path=output_path)
    return {**payload, "artifact": {"path": str(path)}}


def _find_by_strategy_id(rows: Any, strategy_id: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if isinstance(row, dict) and str(row.get("strategy_id") or "") == strategy_id:
            return dict(row)
    return {}


def _evidence_basis_refs(pack: dict[str, Any]) -> list[str]:
    basis_refs: set[str] = set()
    basis = str(pack.get("evidence_basis") or "")
    if basis in RETIREMENT_EVIDENCE_BASIS_VALUES:
        basis_refs.add(basis)
    for key in ("historical_evidence", "baseline_comparison"):
        value = pack.get(key)
        if isinstance(value, dict):
            nested_basis = str(value.get("evidence_basis") or "")
            if nested_basis in RETIREMENT_EVIDENCE_BASIS_VALUES:
                basis_refs.add(nested_basis)
    return sorted(basis_refs)


def _infer_reason_code(recommendation: dict[str, Any]) -> str:
    reasons = {str(item) for item in recommendation.get("reasons") or []}
    if "registered_baseline_gap_negative" in reasons:
        return "baseline_underperformance"
    if "tail_risk_gate_failed" in reasons:
        return "tail_dependence_failure"
    if "historical_after_cost_excess_negative" in reasons:
        return "persistent_negative_after_cost_excess"
    return "forward_median_and_win_rate_failure"


def _event_refs(event_refs: list[str] | None) -> list[str]:
    values = {str(item) for item in event_refs or [] if str(item)}
    values.add(RETIREMENT_EVENT_REF)
    return sorted(values)


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _retirement_artifact_id(
    *,
    strategy_id: str,
    decision_log_ref: str,
    evidence_snapshot_refs: list[str],
) -> str:
    encoded = json.dumps(
        {
            "strategy_id": strategy_id,
            "decision_log_ref": decision_log_ref,
            "evidence_snapshot_refs": sorted(set(evidence_snapshot_refs)),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return "shortpick-strategy-retirement:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
