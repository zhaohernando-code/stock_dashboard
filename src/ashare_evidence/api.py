from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from ashare_evidence.db import get_database_url, get_session_factory, init_database
from ashare_evidence.schemas import LatestRecommendationResponse, RecommendationTraceResponse
from ashare_evidence.services import bootstrap_demo_data, get_latest_recommendation_summary, get_recommendation_trace


def create_app(database_url: str | None = None) -> FastAPI:
    resolved_database_url = get_database_url(database_url)
    init_database(resolved_database_url)
    session_factory = get_session_factory(resolved_database_url)

    def get_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI(
        title="A-share Evidence Foundation",
        version="0.1.0",
        summary="Evidence-first market/news/model/recommendation data layer.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "database_url": resolved_database_url}

    @app.post("/bootstrap/demo")
    def bootstrap_demo(
        symbol: str = Query(default="600519.SH"),
        session: Session = Depends(get_session),
    ) -> dict[str, object]:
        return bootstrap_demo_data(session, symbol)

    @app.get("/stocks/{symbol}/recommendations/latest", response_model=LatestRecommendationResponse)
    def latest_recommendation(symbol: str, session: Session = Depends(get_session)) -> dict[str, object]:
        payload = get_latest_recommendation_summary(session, symbol)
        if payload is None:
            raise HTTPException(status_code=404, detail=f"No recommendation found for {symbol}.")
        return payload

    @app.get("/recommendations/{recommendation_id}/trace", response_model=RecommendationTraceResponse)
    def recommendation_trace(recommendation_id: int, session: Session = Depends(get_session)) -> dict[str, object]:
        try:
            return get_recommendation_trace(session, recommendation_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
