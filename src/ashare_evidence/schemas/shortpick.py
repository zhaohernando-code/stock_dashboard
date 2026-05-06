"""Short-pick research lab schemas."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ShortpickRunCreateRequest(BaseModel):
    run_date: date | None = None
    rounds_per_model: int = Field(default=5, ge=1, le=10)


class ShortpickRunValidateRequest(BaseModel):
    horizons: list[int] = Field(default_factory=lambda: [1, 3, 5, 10, 20])


class ShortpickRetryFailedRoundsRequest(BaseModel):
    max_rounds: int | None = Field(default=None, ge=1, le=20)


class ShortpickSourceView(BaseModel):
    title: str | None = None
    url: str | None = None
    published_at: str | None = None
    why_it_matters: str | None = None
    credibility_status: str | None = None
    credibility_reason: str | None = None
    http_status: int | None = None
    checked_at: str | None = None


class ShortpickRoundView(BaseModel):
    id: int
    round_key: str
    provider_name: str
    model_name: str
    executor_kind: str
    round_index: int
    status: str
    symbol: str | None = None
    stock_name: str | None = None
    theme: str | None = None
    thesis: str | None = None
    confidence: float | None = None
    sources: list[ShortpickSourceView] = Field(default_factory=list)
    artifact_id: str | None = None
    failure_category: str | None = None
    retryable: bool = False
    retry_history: list[dict[str, Any]] = Field(default_factory=list)
    error_message: str | None = None
    raw_answer: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class ShortpickValidationView(BaseModel):
    id: int
    horizon_days: int
    status: str
    entry_at: datetime | None = None
    exit_at: datetime | None = None
    entry_close: float | None = None
    exit_close: float | None = None
    stock_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_favorable_return: float | None = None
    max_drawdown: float | None = None
    benchmark_symbol: str | None = None
    benchmark_label: str | None = None
    benchmark_returns: dict[str, Any] = Field(default_factory=dict)
    available_forward_bars: int | None = None
    required_forward_bars: int | None = None
    pending_reason: str | None = None
    market_data_sync: dict[str, Any] = Field(default_factory=dict)


class ShortpickCandidateView(BaseModel):
    id: int
    candidate_key: str
    run_id: int
    round_id: int | None = None
    symbol: str
    name: str
    normalized_theme: str | None = None
    horizon_trading_days: int | None = None
    confidence: float | None = None
    thesis: str | None = None
    catalysts: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    sources: list[ShortpickSourceView] = Field(default_factory=list)
    novelty_note: str | None = None
    limitations: list[str] = Field(default_factory=list)
    convergence_group: str | None = None
    research_priority: str
    parse_status: str
    is_system_external: bool
    validations: list[ShortpickValidationView] = Field(default_factory=list)
    raw_round: ShortpickRoundView | None = None


class ShortpickConsensusView(BaseModel):
    id: int
    snapshot_key: str
    artifact_id: str | None = None
    generated_at: datetime
    status: str
    stock_convergence: float
    theme_convergence: float
    source_diversity: float
    model_independence: float
    novelty_score: float
    research_priority: str
    summary: dict[str, Any] = Field(default_factory=dict)


class ShortpickRunView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    run_key: str
    run_date: date
    prompt_version: str
    information_mode: str
    status: str
    trigger_source: str
    triggered_by: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    execution_config: dict[str, Any] = Field(default_factory=dict, alias="model_config")
    summary: dict[str, Any] = Field(default_factory=dict)
    rounds: list[ShortpickRoundView] = Field(default_factory=list)
    consensus: ShortpickConsensusView | None = None
    candidates: list[ShortpickCandidateView] = Field(default_factory=list)


class ShortpickRunListResponse(BaseModel):
    generated_at: datetime
    items: list[ShortpickRunView] = Field(default_factory=list)
    total: int | None = None
    limit: int | None = None
    offset: int | None = None


class ShortpickCandidateListResponse(BaseModel):
    generated_at: datetime
    items: list[ShortpickCandidateView] = Field(default_factory=list)


class ShortpickValidationQueueItem(BaseModel):
    validation_id: int
    candidate_id: int
    run_id: int
    run_key: str
    run_date: date
    provider_name: str | None = None
    model_name: str | None = None
    executor_kind: str | None = None
    round_index: int | None = None
    symbol: str
    name: str
    normalized_theme: str | None = None
    research_priority: str
    convergence_group: str | None = None
    horizon_days: int
    status: str
    entry_at: datetime | None = None
    exit_at: datetime | None = None
    entry_close: float | None = None
    exit_close: float | None = None
    stock_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    max_favorable_return: float | None = None
    max_drawdown: float | None = None
    benchmark_symbol: str | None = None
    benchmark_label: str | None = None
    available_forward_bars: int | None = None
    required_forward_bars: int | None = None
    pending_reason: str | None = None
    market_data_sync: dict[str, Any] = Field(default_factory=dict)


class ShortpickValidationQueueResponse(BaseModel):
    generated_at: datetime
    items: list[ShortpickValidationQueueItem] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class ShortpickFeedbackGroup(BaseModel):
    group_key: str
    label: str
    sample_count: int = 0
    completed_validation_count: int = 0
    mean_stock_return: float | None = None
    mean_excess_return: float | None = None
    positive_excess_rate: float | None = None
    max_drawdown: float | None = None
    max_favorable_return: float | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)


class ShortpickModelFeedbackItem(BaseModel):
    provider_name: str
    model_name: str
    executor_kind: str
    round_count: int
    completed_round_count: int
    failed_round_count: int
    retryable_failed_round_count: int
    parse_failed_candidate_count: int
    success_rate: float | None = None
    source_credibility_counts: dict[str, int] = Field(default_factory=dict)
    validation_by_horizon: list[ShortpickFeedbackGroup] = Field(default_factory=list)
    validation_by_priority: list[ShortpickFeedbackGroup] = Field(default_factory=list)
    validation_by_theme: list[ShortpickFeedbackGroup] = Field(default_factory=list)


class ShortpickModelFeedbackResponse(BaseModel):
    generated_at: datetime
    models: list[ShortpickModelFeedbackItem] = Field(default_factory=list)
    overall: dict[str, Any] = Field(default_factory=dict)
