from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ashare_evidence.lineage import LineageRecord


class StockView(BaseModel):
    symbol: str
    name: str
    exchange: str
    ticker: str


class ModelView(BaseModel):
    name: str
    family: str
    version: str
    validation_scheme: str
    artifact_uri: str | None = None
    lineage: LineageRecord


class PromptView(BaseModel):
    name: str
    version: str
    risk_disclaimer: str
    lineage: LineageRecord


class RecommendationView(BaseModel):
    id: int
    recommendation_key: str
    direction: str
    confidence_label: str
    confidence_score: float
    confidence_expression: str | None = None
    horizon_min_days: int
    horizon_max_days: int
    applicable_period: str | None = None
    summary: str
    generated_at: datetime
    updated_at: datetime
    as_of_data_time: datetime
    evidence_status: str
    degrade_reason: str | None = None
    core_drivers: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    reverse_risks: list[str] = Field(default_factory=list)
    downgrade_conditions: list[str] = Field(default_factory=list)
    factor_breakdown: dict[str, Any] = Field(default_factory=dict)
    validation_snapshot: dict[str, Any] = Field(default_factory=dict)
    lineage: LineageRecord


class EvidenceArtifactView(BaseModel):
    evidence_type: str
    record_id: int
    role: str
    rank: int
    label: str
    snippet: str | None = None
    timestamp: datetime | None = None
    lineage: LineageRecord
    payload: dict[str, Any] = Field(default_factory=dict)


class SimulationFillView(BaseModel):
    filled_at: datetime
    price: float
    quantity: int
    fee: float
    tax: float
    slippage_bps: float
    lineage: LineageRecord


class SimulationOrderView(BaseModel):
    id: int
    order_source: str
    side: str
    status: str
    requested_at: datetime
    quantity: int
    limit_price: float | None = None
    fills: list[SimulationFillView] = Field(default_factory=list)
    lineage: LineageRecord


class LatestRecommendationResponse(BaseModel):
    stock: StockView
    recommendation: RecommendationView
    model: ModelView
    prompt: PromptView


class RecommendationTraceResponse(LatestRecommendationResponse):
    evidence: list[EvidenceArtifactView] = Field(default_factory=list)
    simulation_orders: list[SimulationOrderView] = Field(default_factory=list)
