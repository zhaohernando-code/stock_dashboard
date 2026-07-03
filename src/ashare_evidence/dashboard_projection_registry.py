from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ashare_evidence.research_artifact_store import write_research_validation_artifact

DASHBOARD_PROJECTION_REGISTRY_SCHEMA_VERSION = "dashboard_approved_projection_registry.v1"
DASHBOARD_PROJECTION_REGISTRY_PROTOCOL_VERSION = "dashboard_approved_projection_registry:v1"
REQUIRED_ARTIFACT_FIELDS = (
    "schema_version",
    "artifact_id",
    "validation_run_id",
    "generated_at",
    "source_db_snapshot_id",
    "source_data_time_range",
    "feature_version",
    "label_version",
    "code_version",
    "config_version",
    "validation_protocol",
    "gate_readout",
    "claim_ceiling",
    "promotion_status",
)


def _stable_digest(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _missing_fields(payload: dict[str, Any], *, source_name: str) -> list[str]:
    blockers: list[str] = []
    for field in REQUIRED_ARTIFACT_FIELDS:
        value = payload.get(field)
        if value is None or value == "":
            blockers.append(f"{source_name}_missing_required_field_{field}")
    return blockers


def build_dashboard_projection_registry_artifact(
    *,
    validation_run_id: str,
    source_db_snapshot_id: str | None,
    source_data_time_range: dict[str, Any],
    candidate_kind: str,
    candidate_artifact: dict[str, Any],
    governance_decision: dict[str, Any],
) -> dict[str, Any]:
    governance_approved = bool(governance_decision.get("approved_for_dashboard_projection"))
    governance_state = str(governance_decision.get("current_state") or "unknown")
    blockers = _missing_fields(candidate_artifact, source_name=candidate_kind)
    blockers.extend(_missing_fields(governance_decision, source_name="governance_promotion_decision"))
    governance_gate = governance_decision.get("gate_readout") if isinstance(governance_decision.get("gate_readout"), dict) else {}
    blockers.extend(f"governance:{item}" for item in governance_gate.get("blocking_gate_ids") or [])
    if not governance_approved:
        blockers.append("governance_not_approved_for_dashboard_projection")
    if governance_state != "production_eligible":
        blockers.append(f"governance_lifecycle_not_production_eligible:{governance_state}")

    unique_blockers = sorted(dict.fromkeys(str(item) for item in blockers))
    approved_projection_entries = []
    blocked_projection_entries = [
        {
            "projection_key": f"{candidate_kind}:{candidate_artifact.get('artifact_id')}",
            "candidate_kind": candidate_kind,
            "candidate_artifact_id": candidate_artifact.get("artifact_id"),
            "governance_decision_id": governance_decision.get("artifact_id"),
            "reason": "not_approved_by_governance",
        }
    ]
    if not unique_blockers:
        approved_projection_entries.append(
            {
                "projection_key": f"{candidate_kind}:{candidate_artifact.get('artifact_id')}",
                "candidate_kind": candidate_kind,
                "candidate_artifact_id": candidate_artifact.get("artifact_id"),
                "governance_decision_id": governance_decision.get("artifact_id"),
                "projection_payload_policy": "approved_summary_only_no_raw_validation_rows",
            }
        )
        blocked_projection_entries = []

    registry_digest = _stable_digest(
        {
            "protocol_version": DASHBOARD_PROJECTION_REGISTRY_PROTOCOL_VERSION,
            "candidate_kind": candidate_kind,
            "candidate_artifact_id": candidate_artifact.get("artifact_id"),
            "governance_decision_id": governance_decision.get("artifact_id"),
            "approved_projection_entries": approved_projection_entries,
            "blocking_gate_ids": unique_blockers,
        }
    )
    artifact_id = f"dashboard-approved-projection-registry-{registry_digest[:16]}"
    return {
        "artifact_type": "dashboard_approved_projection_registry",
        "schema_version": DASHBOARD_PROJECTION_REGISTRY_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "validation_run_id": validation_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db_snapshot_id": source_db_snapshot_id,
        "source_data_time_range": source_data_time_range,
        "feature_version": candidate_artifact.get("lineage", {}).get("independent_pit_feature_version")
        or candidate_artifact.get("lineage", {}).get("feature_version"),
        "label_version": candidate_artifact.get("lineage", {}).get("label_version", "daily_close_forward_excess_return:v1"),
        "code_version": candidate_artifact.get("lineage", {}).get("code_version", "unresolved_local_checkout"),
        "config_version": DASHBOARD_PROJECTION_REGISTRY_PROTOCOL_VERSION,
        "validation_protocol": {
            "artifact_role": "dashboard_approved_projection_registry",
            "protocol_version": DASHBOARD_PROJECTION_REGISTRY_PROTOCOL_VERSION,
            "dashboard_consumption_policy": "approved_registry_summary_only",
            "raw_validation_artifact_policy": "never_consumed_directly_by_dashboard",
            "governance_required_state": "production_eligible",
        },
        "gate_readout": {
            "gate_status": "blocked" if unique_blockers else "approved_projection_ready",
            "promotion_status": "blocked_from_production" if unique_blockers else "approved_for_dashboard_projection",
            "claim_ceiling": "diagnostic_summary_only" if unique_blockers else "approved_dashboard_projection",
            "blocking_gate_ids": unique_blockers,
        },
        "claim_ceiling": "diagnostic_summary_only" if unique_blockers else "approved_dashboard_projection",
        "promotion_status": "blocked_from_production" if unique_blockers else "approved_for_dashboard_projection",
        "storage_boundary": "research_validation_artifact_store_only",
        "dashboard_consumption_boundary": "dashboard_reads_registry_summary_not_raw_validation_artifacts",
        "approved_projection_count": len(approved_projection_entries),
        "blocked_projection_count": len(blocked_projection_entries),
        "approved_projection_entries": approved_projection_entries,
        "blocked_projection_entries": blocked_projection_entries,
        "source_artifacts": {
            "candidate_kind": candidate_kind,
            "candidate_artifact_id": candidate_artifact.get("artifact_id"),
            "governance_promotion_decision_id": governance_decision.get("artifact_id"),
        },
        "registry_content_digest": registry_digest,
    }


def dashboard_projection_registry_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_type": payload.get("artifact_type"),
        "schema_version": payload.get("schema_version"),
        "artifact_id": payload.get("artifact_id"),
        "approved_projection_count": payload.get("approved_projection_count"),
        "blocked_projection_count": payload.get("blocked_projection_count"),
        "promotion_status": payload.get("promotion_status"),
        "claim_ceiling": payload.get("claim_ceiling"),
        "gate_readout": payload.get("gate_readout"),
        "storage_boundary": payload.get("storage_boundary"),
        "dashboard_consumption_boundary": payload.get("dashboard_consumption_boundary"),
    }


def write_dashboard_projection_registry_artifact(payload: dict[str, Any], *, artifact_root: str) -> Path:
    return write_research_validation_artifact(
        "dashboard_approved_projection_registry",
        str(payload["artifact_id"]),
        payload,
        root=Path(artifact_root) if artifact_root else None,
    )
