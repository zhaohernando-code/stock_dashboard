from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ashare_evidence.factor_observation import build_factor_observations, sweep_weights
from ashare_evidence.research_artifact_store import artifact_root_from_database_url


def add_research_parsers(subparsers: Any) -> None:
    fo = subparsers.add_parser("factor-observation", help="Build per-factor IC observation artifact from historical recommendations.")
    fo.add_argument("--database-url", default=None)

    ws = subparsers.add_parser("weight-sweep", help="Sweep fusion weight combinations and compare against baseline.")
    ws.add_argument("--database-url", default=None)


def handle_factor_observation(session: Session, *, database_url: str | None = None) -> dict[str, Any]:
    bind = session.get_bind()
    artifact_root = str(artifact_root_from_database_url(bind.url.render_as_string(hide_password=False)) if bind else "")
    return build_factor_observations(session, artifact_root=artifact_root)


def handle_weight_sweep(session: Session, *, database_url: str | None = None) -> dict[str, Any]:
    bind = session.get_bind()
    artifact_root = str(artifact_root_from_database_url(bind.url.render_as_string(hide_password=False)) if bind else "")
    return sweep_weights(session, artifact_root=artifact_root)
