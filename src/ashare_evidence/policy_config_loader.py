from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.default_policy_configs import (
    DEFAULT_POLICY_CONFIG_REASONS,
    DEFAULT_POLICY_CONFIGS,
    default_policy_config_payload,
    default_policy_config_schema,
    iter_default_policy_configs,
)
from ashare_evidence.models import PolicyConfigVersion

STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_RETIRED = "retired"
POLICY_CONFIG_STATUSES = {STATUS_DRAFT, STATUS_ACTIVE, STATUS_RETIRED}


def compute_policy_config_checksum(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(rendered.encode("utf-8")).hexdigest()


def _validate_known_config(scope: str, config_key: str) -> None:
    if (scope, config_key) not in DEFAULT_POLICY_CONFIGS:
        raise ValueError(f"Unknown governed policy config: {scope}/{config_key}")


def _validate_payload_shape(scope: str, config_key: str, payload: dict[str, Any]) -> None:
    schema = default_policy_config_schema(scope, config_key)
    missing = [key for key in schema.get("required", []) if key not in payload]
    if missing:
        raise ValueError(f"Policy config payload missing required keys for {scope}/{config_key}: {', '.join(missing)}")


def create_policy_config_version(
    session: Session,
    *,
    scope: str,
    config_key: str,
    version: str,
    payload: dict[str, Any],
    reason: str,
    evidence_refs: list[str] | None = None,
    created_by: str = "root",
    status: str = STATUS_DRAFT,
    approved_by: str | None = None,
    effective_from: datetime | None = None,
    supersedes_version: str | None = None,
) -> PolicyConfigVersion:
    _validate_known_config(scope, config_key)
    if status not in POLICY_CONFIG_STATUSES:
        raise ValueError(f"Unsupported policy config status: {status}")
    if not str(reason or "").strip():
        raise ValueError("Policy config version requires a non-empty reason.")
    if status == STATUS_ACTIVE and not str(approved_by or "").strip():
        raise ValueError("Active policy config version requires approved_by.")
    _validate_payload_shape(scope, config_key, payload)
    existing = session.scalar(
        select(PolicyConfigVersion).where(
            PolicyConfigVersion.scope == scope,
            PolicyConfigVersion.config_key == config_key,
            PolicyConfigVersion.version == version,
        )
    )
    if existing is not None:
        raise ValueError(f"Policy config version already exists: {scope}/{config_key}@{version}")
    record = PolicyConfigVersion(
        scope=scope,
        config_key=config_key,
        version=version,
        status=status,
        payload=payload,
        payload_schema=default_policy_config_schema(scope, config_key),
        reason=reason.strip(),
        evidence_refs=list(evidence_refs or []),
        created_by=created_by,
        approved_by=approved_by,
        effective_from=effective_from,
        supersedes_version=supersedes_version,
        checksum=compute_policy_config_checksum(payload),
    )
    session.add(record)
    session.flush()
    if status == STATUS_ACTIVE:
        _retire_other_active_versions(session, record)
    return record


def _retire_other_active_versions(session: Session, record: PolicyConfigVersion) -> None:
    for active in session.scalars(
        select(PolicyConfigVersion).where(
            PolicyConfigVersion.scope == record.scope,
            PolicyConfigVersion.config_key == record.config_key,
            PolicyConfigVersion.status == STATUS_ACTIVE,
            PolicyConfigVersion.id != record.id,
        )
    ):
        active.status = STATUS_RETIRED


def activate_policy_config_version(
    session: Session,
    *,
    scope: str,
    config_key: str,
    version: str,
    approved_by: str,
    effective_from: datetime | None = None,
) -> PolicyConfigVersion:
    record = session.scalar(
        select(PolicyConfigVersion).where(
            PolicyConfigVersion.scope == scope,
            PolicyConfigVersion.config_key == config_key,
            PolicyConfigVersion.version == version,
        )
    )
    if record is None:
        raise LookupError(f"Policy config version not found: {scope}/{config_key}@{version}")
    if record.status == STATUS_ACTIVE:
        return record
    if not str(approved_by or "").strip():
        raise ValueError("approved_by is required to activate a policy config version.")
    record.status = STATUS_ACTIVE
    record.approved_by = approved_by
    record.effective_from = effective_from or datetime.now(UTC)
    _retire_other_active_versions(session, record)
    session.flush()
    return record


def serialize_policy_config_version(record: PolicyConfigVersion, *, source: str = "database") -> dict[str, Any]:
    return {
        "id": record.id,
        "scope": record.scope,
        "config_key": record.config_key,
        "version": record.version,
        "status": record.status,
        "source": source,
        "payload": record.payload,
        "payload_schema": record.payload_schema,
        "reason": record.reason,
        "evidence_refs": list(record.evidence_refs or []),
        "created_by": record.created_by,
        "approved_by": record.approved_by,
        "effective_from": record.effective_from,
        "supersedes_version": record.supersedes_version,
        "checksum": record.checksum,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def default_policy_config_view(scope: str, config_key: str) -> dict[str, Any]:
    payload = default_policy_config_payload(scope, config_key)
    return {
        "id": None,
        "scope": scope,
        "config_key": config_key,
        "version": "code-default",
        "status": STATUS_ACTIVE,
        "source": "code_default",
        "payload": payload,
        "payload_schema": default_policy_config_schema(scope, config_key),
        "reason": DEFAULT_POLICY_CONFIG_REASONS[(scope, config_key)],
        "evidence_refs": [],
        "created_by": "code",
        "approved_by": "code",
        "effective_from": None,
        "supersedes_version": None,
        "checksum": compute_policy_config_checksum(payload),
        "created_at": None,
        "updated_at": None,
    }


def get_active_policy_config(session: Session, *, scope: str, config_key: str) -> dict[str, Any]:
    _validate_known_config(scope, config_key)
    record = session.scalar(
        select(PolicyConfigVersion)
        .where(
            PolicyConfigVersion.scope == scope,
            PolicyConfigVersion.config_key == config_key,
            PolicyConfigVersion.status == STATUS_ACTIVE,
        )
        .order_by(PolicyConfigVersion.effective_from.desc().nullslast(), PolicyConfigVersion.id.desc())
    )
    if record is None:
        return default_policy_config_view(scope, config_key)
    return serialize_policy_config_version(record)


def get_active_policy_payload(session: Session, *, scope: str, config_key: str) -> dict[str, Any]:
    return dict(get_active_policy_config(session, scope=scope, config_key=config_key)["payload"])


def list_policy_config_versions(
    session: Session,
    *,
    scope: str | None = None,
    config_key: str | None = None,
) -> list[dict[str, Any]]:
    query = select(PolicyConfigVersion).order_by(
        PolicyConfigVersion.scope.asc(),
        PolicyConfigVersion.config_key.asc(),
        PolicyConfigVersion.created_at.desc(),
        PolicyConfigVersion.id.desc(),
    )
    if scope:
        query = query.where(PolicyConfigVersion.scope == scope)
    if config_key:
        query = query.where(PolicyConfigVersion.config_key == config_key)
    return [serialize_policy_config_version(record) for record in session.scalars(query).all()]


def build_policy_governance_summary(session: Session) -> dict[str, Any]:
    active_configs = [
        get_active_policy_config(session, scope=scope, config_key=config_key)
        for scope, config_key, _payload in iter_default_policy_configs()
    ]
    history = list_policy_config_versions(session)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "pass",
        "active_configs": active_configs,
        "history": history[:20],
        "default_config_count": len(active_configs),
        "database_config_count": len(history),
        "hard_constraints": {
            "formula_side_effects_forbidden": True,
            "direct_config_read_forbidden": True,
            "new_unclassified_literals_forbidden": True,
            "config_lineage_required": True,
        },
    }
