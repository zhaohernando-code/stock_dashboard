from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ashare_evidence.db import utcnow
from ashare_evidence.models import FrontendProjection

FRONTEND_PROJECTION_VERSION = "frontend-projection-v1"
SHORTPICK_REPLAY_FEEDBACK_PROJECTION_KEY = "shortpick_replay_feedback:v1"


def stable_payload_fingerprint(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def get_frontend_projection(
    session: Session,
    projection_key: str,
    *,
    target_login: str | None = None,
) -> FrontendProjection | None:
    statement = select(FrontendProjection).where(FrontendProjection.projection_key == projection_key)
    if target_login is not None:
        statement = statement.where(FrontendProjection.target_login == target_login)
    return session.scalar(statement)


def get_ready_frontend_projection_payload(
    session: Session,
    projection_key: str,
    *,
    target_login: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    projection = get_frontend_projection(session, projection_key, target_login=target_login)
    if projection is None or projection.status != "ready":
        return None
    reference = now or utcnow()
    if projection.expires_at is not None and projection.expires_at <= reference:
        return None
    return dict(projection.payload or {})


def upsert_frontend_projection(
    session: Session,
    projection_key: str,
    *,
    projection_group: str,
    payload: dict[str, Any],
    target_login: str | None = None,
    status: str = "ready",
    version: str = FRONTEND_PROJECTION_VERSION,
    generated_at: datetime | None = None,
    expires_at: datetime | None = None,
    metadata_payload: dict[str, Any] | None = None,
) -> FrontendProjection:
    now = generated_at or utcnow()
    projection = get_frontend_projection(session, projection_key, target_login=target_login)
    if projection is None:
        projection = FrontendProjection(
            projection_key=projection_key,
            projection_group=projection_group,
            target_login=target_login,
            status=status,
            version=version,
            generated_at=now,
            expires_at=expires_at,
            source_fingerprint=stable_payload_fingerprint(payload),
            payload=payload,
            metadata_payload=metadata_payload or {},
        )
        session.add(projection)
        return projection
    projection.projection_group = projection_group
    projection.status = status
    projection.version = version
    projection.generated_at = now
    projection.expires_at = expires_at
    projection.source_fingerprint = stable_payload_fingerprint(payload)
    projection.payload = payload
    projection.metadata_payload = metadata_payload or {}
    projection.updated_at = now
    return projection


def refresh_shortpick_replay_feedback_frontend_projection(session: Session) -> dict[str, Any]:
    from ashare_evidence.api import (  # Local import keeps API read path independent from refresh jobs.
        _attach_shortpick_replay_decision_projection,
        _load_shortpick_replay_feedback_from_cache,
    )

    feedback = _load_shortpick_replay_feedback_from_cache(run_id=None)
    payload = _attach_shortpick_replay_decision_projection(feedback, session=session)
    projection = upsert_frontend_projection(
        session,
        SHORTPICK_REPLAY_FEEDBACK_PROJECTION_KEY,
        projection_group="shortpick",
        payload=payload,
        metadata_payload={
            "source": "shortpick_replay_feedback_cache_plus_decision_projection",
            "usage": "GET /shortpick-lab/replay-feedback",
        },
    )
    return {
        "projection_key": projection.projection_key,
        "projection_group": projection.projection_group,
        "status": projection.status,
        "generated_at": projection.generated_at.isoformat(),
        "source_fingerprint": projection.source_fingerprint,
        "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")),
    }


def refresh_frontend_projections(session: Session, *, projection: str = "all") -> dict[str, Any]:
    refreshed: list[dict[str, Any]] = []
    if projection in {"all", "shortpick_replay_feedback"}:
        refreshed.append(refresh_shortpick_replay_feedback_frontend_projection(session))
    if not refreshed:
        raise ValueError(f"Unsupported frontend projection: {projection}")
    return {
        "status": "ok",
        "version": FRONTEND_PROJECTION_VERSION,
        "refreshed": refreshed,
    }
