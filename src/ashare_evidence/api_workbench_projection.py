from __future__ import annotations

from typing import Any

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from ashare_evidence.frontend_projections import (
    build_phase5_workbench_projection_payload,
    get_ready_frontend_projection_payload,
    phase5_workbench_projection_key,
    refresh_phase5_workbench_frontend_projection,
)
from ashare_evidence.scheduler_workbench_projection import resolve_latest_phase5_workbench_cycle_id


def register_workbench_projection_routes(app: Any, get_session: Any, require_stock_access: Any) -> None:
    @app.get("/dashboard/operations/workbench-projection")
    def dashboard_operations_workbench_projection(
        _access: Any = Depends(require_stock_access),
        cycle_id: str | None = Query(default=None, min_length=1),
        runner_id: str | None = Query(default=None),
        refresh: bool = Query(default=False),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        resolved_cycle_id = cycle_id or resolve_latest_phase5_workbench_cycle_id()
        if resolved_cycle_id is None:
            return build_phase5_workbench_projection_payload(cycle_id=None, runner_id=runner_id)

        if refresh:
            refresh_phase5_workbench_frontend_projection(
                session,
                cycle_id=resolved_cycle_id,
                runner_id=runner_id,
            )
            session.commit()

        projection = get_ready_frontend_projection_payload(
            session,
            phase5_workbench_projection_key(cycle_id=resolved_cycle_id),
        )
        if projection is not None:
            return projection
        return build_phase5_workbench_projection_payload(cycle_id=resolved_cycle_id, runner_id=runner_id)
