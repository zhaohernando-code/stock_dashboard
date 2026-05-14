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
SHORTPICK_MODEL_FEEDBACK_PROJECTION_KEY = "shortpick_model_feedback:v1"
OPERATIONS_SUMMARY_PROJECTION_PREFIX = "operations_summary:v1"
HOME_SHELL_PROJECTION_PREFIX = "home_shell:v1"
SIMULATION_WORKSPACE_SUMMARY_PROJECTION_PREFIX = "simulation_workspace_summary:v1"


def operations_summary_projection_key(*, target_login: str, sample_symbol: str) -> str:
    return f"{OPERATIONS_SUMMARY_PROJECTION_PREFIX}:{target_login}:{sample_symbol.upper()}"


def home_shell_projection_key(*, target_login: str) -> str:
    return f"{HOME_SHELL_PROJECTION_PREFIX}:{target_login}"


def simulation_workspace_summary_projection_key(*, target_login: str) -> str:
    return f"{SIMULATION_WORKSPACE_SUMMARY_PROJECTION_PREFIX}:{target_login}"


def stable_payload_fingerprint(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def json_safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


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
    safe_payload = json_safe_payload(payload)
    safe_metadata = json_safe_payload(metadata_payload or {})
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
            source_fingerprint=stable_payload_fingerprint(safe_payload),
            payload=safe_payload,
            metadata_payload=safe_metadata,
        )
        session.add(projection)
        return projection
    projection.projection_group = projection_group
    projection.status = status
    projection.version = version
    projection.generated_at = now
    projection.expires_at = expires_at
    projection.source_fingerprint = stable_payload_fingerprint(safe_payload)
    projection.payload = safe_payload
    projection.metadata_payload = safe_metadata
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


def refresh_shortpick_model_feedback_frontend_projection(session: Session) -> dict[str, Any]:
    from ashare_evidence.shortpick_lab import build_shortpick_model_feedback

    payload = build_shortpick_model_feedback(session)
    projection = upsert_frontend_projection(
        session,
        SHORTPICK_MODEL_FEEDBACK_PROJECTION_KEY,
        projection_group="shortpick",
        payload=payload,
        metadata_payload={
            "source": "build_shortpick_model_feedback",
            "usage": "GET /shortpick-lab/model-feedback",
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


def refresh_operations_summary_frontend_projection(
    session: Session,
    *,
    target_login: str,
    sample_symbol: str,
) -> dict[str, Any]:
    from ashare_evidence.operations import build_operations_summary

    normalized_symbol = sample_symbol.upper()
    payload = build_operations_summary(session, sample_symbol=normalized_symbol, target_login=target_login)
    projection = upsert_frontend_projection(
        session,
        operations_summary_projection_key(target_login=target_login, sample_symbol=normalized_symbol),
        projection_group="operations",
        target_login=target_login,
        payload=payload,
        metadata_payload={
            "source": "build_operations_summary",
            "usage": "GET /dashboard/operations/summary",
            "sample_symbol": normalized_symbol,
            "target_login": target_login,
        },
    )
    return {
        "projection_key": projection.projection_key,
        "projection_group": projection.projection_group,
        "target_login": projection.target_login,
        "status": projection.status,
        "generated_at": projection.generated_at.isoformat(),
        "source_fingerprint": projection.source_fingerprint,
        "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")),
    }


def refresh_operations_summary_frontend_projections(
    session: Session,
    *,
    target_login: str = "root",
    sample_symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    from ashare_evidence.watchlist import active_watchlist_symbols

    symbols = sample_symbols or active_watchlist_symbols(session, account_login=target_login) or ["600519.SH"]
    deduped_symbols = list(dict.fromkeys(symbol.upper() for symbol in symbols))
    return [
        refresh_operations_summary_frontend_projection(
            session,
            target_login=target_login,
            sample_symbol=symbol,
        )
        for symbol in deduped_symbols
    ]


def build_home_shell_projection_payload(
    session: Session,
    *,
    target_login: str,
    actor_login: str = "root",
    actor_role: str = "root",
    include_scheduled_refresh_status: bool = False,
) -> dict[str, Any]:
    from ashare_evidence.dashboard import get_glossary_entries, list_candidate_recommendations
    from ashare_evidence.scheduled_refresh_status import get_scheduled_refresh_status
    from ashare_evidence.watchlist import list_watchlist_entries

    payload = {
        "watchlist": list_watchlist_entries(
            session,
            target_login=target_login,
            actor_login=actor_login,
            actor_role=actor_role,
            record_presence=False,
        ),
        "candidates": list_candidate_recommendations(session, limit=8, account_login=target_login),
        "glossary": get_glossary_entries(),
        "scheduled_refresh_status": None,
    }
    if include_scheduled_refresh_status:
        payload["scheduled_refresh_status"] = get_scheduled_refresh_status()
    return payload


def refresh_home_shell_frontend_projection(
    session: Session,
    *,
    target_login: str = "root",
) -> dict[str, Any]:
    payload = build_home_shell_projection_payload(session, target_login=target_login)
    projection = upsert_frontend_projection(
        session,
        home_shell_projection_key(target_login=target_login),
        projection_group="home",
        target_login=target_login,
        payload=payload,
        metadata_payload={
            "source": "watchlist_candidates_glossary",
            "usage": "GET /dashboard/shell",
            "target_login": target_login,
        },
    )
    return {
        "projection_key": projection.projection_key,
        "projection_group": projection.projection_group,
        "target_login": projection.target_login,
        "status": projection.status,
        "generated_at": projection.generated_at.isoformat(),
        "source_fingerprint": projection.source_fingerprint,
        "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")),
    }


def refresh_simulation_workspace_summary_frontend_projection(
    session: Session,
    *,
    target_login: str = "root",
) -> dict[str, Any]:
    from ashare_evidence.simulation import get_simulation_workspace

    workspace = get_simulation_workspace(
        session,
        owner_login=target_login,
        actor_login=target_login,
        actor_role="root" if target_login == "root" else "member",
        record_presence=False,
    )
    payload = {
        "section": "simulation_workspace",
        "generated_at": workspace["session"].get("last_data_time") or workspace["session"].get("started_at"),
        "simulation_workspace": workspace,
    }
    projection = upsert_frontend_projection(
        session,
        simulation_workspace_summary_projection_key(target_login=target_login),
        projection_group="simulation",
        target_login=target_login,
        payload=payload,
        metadata_payload={
            "source": "get_simulation_workspace",
            "usage": "GET /dashboard/operations/details?section=simulation_workspace",
            "target_login": target_login,
        },
    )
    return {
        "projection_key": projection.projection_key,
        "projection_group": projection.projection_group,
        "target_login": projection.target_login,
        "status": projection.status,
        "generated_at": projection.generated_at.isoformat(),
        "source_fingerprint": projection.source_fingerprint,
        "payload_size_bytes": len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")),
    }


def refresh_frontend_projections(
    session: Session,
    *,
    projection: str = "all",
    target_login: str = "root",
    sample_symbols: list[str] | None = None,
) -> dict[str, Any]:
    refreshed: list[dict[str, Any]] = []
    if projection in {"all", "home_shell"}:
        refreshed.append(refresh_home_shell_frontend_projection(session, target_login=target_login))
    if projection in {"all", "shortpick_model_feedback"}:
        refreshed.append(refresh_shortpick_model_feedback_frontend_projection(session))
    if projection in {"all", "simulation_workspace_summary"}:
        refreshed.append(refresh_simulation_workspace_summary_frontend_projection(session, target_login=target_login))
    if projection in {"all", "shortpick_replay_feedback"}:
        refreshed.append(refresh_shortpick_replay_feedback_frontend_projection(session))
    if projection in {"all", "operations_summary"}:
        refreshed.extend(
            refresh_operations_summary_frontend_projections(
                session,
                target_login=target_login,
                sample_symbols=sample_symbols,
            )
        )
    if not refreshed:
        raise ValueError(f"Unsupported frontend projection: {projection}")
    return {
        "status": "ok",
        "version": FRONTEND_PROJECTION_VERSION,
        "refreshed": refreshed,
    }
