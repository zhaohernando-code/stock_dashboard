export interface ShortpickRunCreateRequest {
  run_date?: string | null;
  rounds_per_model: number;
}

export interface ShortpickRunValidateRequest {
  horizons: number[];
}

export interface ShortpickSourceView {
  source_id?: string | null;
  title?: string | null;
  url?: string | null;
  published_at?: string | null;
  why_it_matters?: string | null;
  credibility_status?: string | null;
  credibility_reason?: string | null;
  authority_class?: string | null;
  support_status?: string | null;
  support_evidence_terms?: string[];
  http_status?: number | null;
  attempt_count?: number | null;
  checked_at?: string | null;
  status?: string | null;
  reject_reason?: string | null;
  source_type?: string | null;
  fetched_at?: string | null;
  body_excerpt?: string | null;
  linked_symbols?: string[];
}

export interface ShortpickRoundView {
  id: number;
  round_key: string;
  provider_name: string;
  model_name: string;
  executor_kind: string;
  round_index: number;
  status: string;
  symbol?: string | null;
  stock_name?: string | null;
  theme?: string | null;
  thesis?: string | null;
  confidence?: number | null;
  sources: ShortpickSourceView[];
  artifact_id?: string | null;
  failure_category?: string | null;
  retryable?: boolean;
  retry_history?: Record<string, unknown>[];
  error_message?: string | null;
  raw_answer?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface ShortpickValidationView {
  id: number;
  horizon_days: number;
  status: string;
  entry_at?: string | null;
  exit_at?: string | null;
  entry_close?: number | null;
  exit_close?: number | null;
  stock_return?: number | null;
  benchmark_return?: number | null;
  excess_return?: number | null;
  max_favorable_return?: number | null;
  max_drawdown?: number | null;
  benchmark_symbol?: string | null;
  benchmark_label?: string | null;
  benchmark_returns?: Record<string, unknown>;
  benchmark_dimensions?: Record<string, ShortpickBenchmarkDimension>;
  available_benchmark_dimensions?: string[];
  validation_mode?: string | null;
  official_validation?: boolean;
  tradeability_status?: string | null;
  tradeability_evidence?: Record<string, unknown>;
  available_forward_bars?: number | null;
  required_forward_bars?: number | null;
  pending_reason?: string | null;
  market_data_sync?: Record<string, unknown>;
  experiment_mode?: string | null;
  source_packet_id?: string | null;
  source_packet_hash?: string | null;
  leakage_audit_status?: string | null;
  leakage_audit_reasons?: string[];
  baseline_family?: string | null;
  official_sample_eligible?: boolean | null;
}

export interface ShortpickBenchmarkDimension {
  dimension_key?: string | null;
  benchmark_id?: string | null;
  label?: string | null;
  benchmark_label?: string | null;
  symbol?: string | null;
  symbol_or_scope?: string | null;
  benchmark_return?: number | null;
  excess_return?: number | null;
  status?: string | null;
  reason?: string | null;
  peer_symbol_count?: number | null;
  contributing_peer_symbol_count?: number | null;
}

export interface ShortpickCandidateView {
  id: number;
  candidate_key: string;
  run_id: number;
  round_id?: number | null;
  symbol: string;
  name: string;
  normalized_theme?: string | null;
  topic_normalization?: Record<string, unknown>;
  horizon_trading_days?: number | null;
  confidence?: number | null;
  thesis?: string | null;
  catalysts: string[];
  invalidation: string[];
  risks: string[];
  sources: ShortpickSourceView[];
  novelty_note?: string | null;
  limitations: string[];
  convergence_group?: string | null;
  research_priority: string;
  parse_status: string;
  is_system_external: boolean;
  display_bucket?: string;
  diagnostic_reason?: string | null;
  validations: ShortpickValidationView[];
  raw_round?: ShortpickRoundView | null;
  tracking_role?: string | null;
  llm_paper_control?: Record<string, unknown>;
  experiment_mode?: string | null;
  baseline_family?: string | null;
  source_packet_id?: string | null;
  source_packet_hash?: string | null;
  leakage_audit_status?: string | null;
  leakage_audit_reasons?: string[];
  official_sample_eligible?: boolean | null;
  exclusion_reason?: string | null;
  universe_membership?: Record<string, unknown>;
  evidence_mapping?: Record<string, unknown>;
}

export interface ShortpickConsensusView {
  id: number;
  snapshot_key: string;
  artifact_id?: string | null;
  generated_at: string;
  status: string;
  stock_convergence: number;
  theme_convergence: number;
  source_diversity: number;
  model_independence: number;
  novelty_score: number;
  research_priority: string;
  summary: Record<string, unknown>;
}

export interface ShortpickRunView {
  id: number;
  run_key: string;
  run_date: string;
  prompt_version: string;
  information_mode: string;
  status: string;
  trigger_source: string;
  triggered_by?: string | null;
  started_at: string;
  completed_at?: string | null;
  failed_at?: string | null;
  model_config: Record<string, unknown>;
  summary: Record<string, unknown>;
  rounds: ShortpickRoundView[];
  consensus?: ShortpickConsensusView | null;
  candidates: ShortpickCandidateView[];
}

export interface ShortpickRunListResponse {
  generated_at: string;
  items: ShortpickRunView[];
  total?: number | null;
  limit?: number | null;
  offset?: number | null;
}

export interface ShortpickCandidateListResponse {
  generated_at: string;
  items: ShortpickCandidateView[];
}

export interface ShortpickValidationQueueItem {
  validation_id: number;
  candidate_id: number;
  run_id: number;
  run_key: string;
  run_date: string;
  provider_name?: string | null;
  model_name?: string | null;
  executor_kind?: string | null;
  round_index?: number | null;
  symbol: string;
  name: string;
  normalized_theme?: string | null;
  research_priority: string;
  convergence_group?: string | null;
  horizon_days: number;
  status: string;
  entry_at?: string | null;
  exit_at?: string | null;
  entry_close?: number | null;
  exit_close?: number | null;
  stock_return?: number | null;
  benchmark_return?: number | null;
  excess_return?: number | null;
  max_favorable_return?: number | null;
  max_drawdown?: number | null;
  benchmark_symbol?: string | null;
  benchmark_label?: string | null;
  benchmark_dimensions?: Record<string, ShortpickBenchmarkDimension>;
  validation_mode?: string | null;
  official_validation?: boolean;
  tradeability_status?: string | null;
  tradeability_evidence?: Record<string, unknown>;
  available_forward_bars?: number | null;
  required_forward_bars?: number | null;
  pending_reason?: string | null;
  market_data_sync?: Record<string, unknown>;
  experiment_mode?: string | null;
  source_packet_id?: string | null;
  source_packet_hash?: string | null;
  leakage_audit_status?: string | null;
  leakage_audit_reasons?: string[];
  baseline_family?: string | null;
  official_sample_eligible?: boolean | null;
}

export interface ShortpickValidationQueueResponse {
  generated_at: string;
  items: ShortpickValidationQueueItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ShortpickFeedbackGroup {
  group_key: string;
  label: string;
  sample_count: number;
  official_sample_count?: number;
  tradable_sample_count?: number;
  unique_symbol_run_count?: number;
  completed_validation_count: number;
  completed_official_sample_count?: number;
  completed_tradable_sample_count?: number;
  mean_stock_return?: number | null;
  mean_excess_return?: number | null;
  trimmed_mean_excess_return?: number | null;
  tradable_mean_stock_return?: number | null;
  tradable_mean_excess_return?: number | null;
  tradable_trimmed_mean_excess_return?: number | null;
  tradable_positive_excess_rate?: number | null;
  benchmark_metrics?: Record<string, ShortpickBenchmarkMetric>;
  positive_excess_rate?: number | null;
  max_drawdown?: number | null;
  max_favorable_return?: number | null;
  status_counts: Record<string, number>;
}

export interface ShortpickBenchmarkMetric {
  dimension_key?: string | null;
  available_count?: number | null;
  mean_benchmark_return?: number | null;
  mean_excess_return?: number | null;
  trimmed_mean_excess_return?: number | null;
  positive_excess_rate?: number | null;
  pending_reasons?: Record<string, number>;
}

export interface ShortpickModelFeedbackItem {
  provider_name: string;
  model_name: string;
  executor_kind: string;
  model_group_key?: string | null;
  display_model_label?: string | null;
  channel_label?: string | null;
  round_count: number;
  completed_round_count: number;
  failed_round_count: number;
  retryable_failed_round_count: number;
  parse_failed_candidate_count: number;
  candidate_row_count?: number;
  candidate_horizon_row_count?: number;
  unique_symbol_run_count?: number;
  official_sample_count?: number;
  completed_official_sample_count?: number;
  success_rate?: number | null;
  source_credibility_counts: Record<string, number>;
  validation_by_horizon: ShortpickFeedbackGroup[];
  validation_by_priority: ShortpickFeedbackGroup[];
  validation_by_theme: ShortpickFeedbackGroup[];
  validation_by_industry: ShortpickFeedbackGroup[];
  channels?: ShortpickModelFeedbackChannel[];
}

export interface ShortpickModelFeedbackChannel {
  provider_name: string;
  model_name: string;
  executor_kind: string;
  channel_label?: string | null;
  round_count: number;
  completed_round_count: number;
  failed_round_count: number;
  parse_failed_candidate_count: number;
  candidate_row_count?: number;
  unique_symbol_run_count?: number;
  official_sample_count?: number;
  completed_official_sample_count?: number;
  success_rate?: number | null;
}

export interface ShortpickModelFeedbackResponse {
  generated_at: string;
  models: ShortpickModelFeedbackItem[];
  model_groups?: ShortpickModelFeedbackItem[];
  overall: Record<string, unknown>;
}

export interface ShortpickReplaySourceResponse {
  generated_at: string;
  run_id: number;
  source_packet_id?: string | null;
  source_packet_hash?: string | null;
  as_of_cutoff?: string | null;
  source_packet: Record<string, unknown>;
  official_sources: ShortpickSourceView[];
  diagnostic_sources: ShortpickSourceView[];
  rejected_sources: ShortpickSourceView[];
  tradable_universe: Record<string, unknown>;
}

export interface ShortpickReplayFeedbackFamily {
  baseline_family: string;
  label: string;
  candidate_count: number;
  official_sample_count: number;
  tradable_sample_count?: number;
  completed_official_sample_count: number;
  completed_tradable_sample_count?: number;
  validation_by_horizon: ShortpickFeedbackGroup[];
  robustness_metrics: Record<string, unknown>;
  tradable_robustness_metrics?: Record<string, unknown>;
}

export interface ShortpickReplayFeedbackResponse {
  generated_at: string;
  experiment_mode: string;
  run_id?: number | null;
  families: ShortpickReplayFeedbackFamily[];
  overall: Record<string, unknown> & {
    decision_readout?: ShortpickReplayDecisionReadout;
    execution_funnel?: ShortpickReplayExecutionFunnel;
    entry_sensitivity_matrix?: ShortpickReplayEntrySensitivityMatrix;
    regime_stability?: Record<string, unknown>;
    confidence_intervals?: Record<string, unknown>;
    return_attribution?: Record<string, unknown>;
    forward_tracking_alignment?: Record<string, unknown>;
    strategy_slice_evidence?: Record<string, unknown>;
  };
}

export interface ShortpickReplayDecisionQuestion {
  id: string;
  label: string;
  status: string;
  headline: string;
  reason?: string | null;
  metric_label?: string | null;
  metric_value?: number | null;
  sample_count?: number | null;
  candidate_metric_value?: number | null;
  portfolio_metric_value?: number | null;
}

export interface ShortpickReplayDecisionReadout {
  status: string;
  basis?: string | null;
  questions: ShortpickReplayDecisionQuestion[];
}

export interface ShortpickReplayExecutionFunnelStep {
  id: string;
  label: string;
  status: string;
  count?: number | null;
  basis?: string | null;
  invert_meaning?: boolean;
}

export interface ShortpickReplayExecutionFunnel {
  status: string;
  basis?: string | null;
  reason?: string | null;
  note?: string | null;
  steps: ShortpickReplayExecutionFunnelStep[];
}

export interface ShortpickReplayEntrySensitivityRow {
  entry_price_source: string;
  label: string;
  status: string;
  assumption_level?: string | null;
  entry_price_source_note?: string | null;
  artifact_path?: string | null;
  trade_count?: number | null;
  skipped_count?: number | null;
  blocked_exit_count?: number | null;
  total_return?: number | null;
  excess_total_return?: number | null;
  max_drawdown?: number | null;
  reason?: string | null;
}

export interface ShortpickReplayEntrySensitivityMatrix {
  status: string;
  strategy_key?: string | null;
  strategy_label?: string | null;
  reason?: string | null;
  rows: ShortpickReplayEntrySensitivityRow[];
}

export interface ShortpickMarketPortfolioMetric {
  portfolio_count?: number | null;
  signal_day_count?: number | null;
  completed_member_count?: number | null;
  average_member_count?: number | null;
  mean_net_excess_return?: number | null;
  trimmed_mean_net_excess_return?: number | null;
  positive_net_excess_rate?: number | null;
  volatility?: number | null;
  worst_portfolio_return?: number | null;
  best_portfolio_return?: number | null;
  max_additive_drawdown?: number | null;
  by_horizon?: Record<string, Record<string, unknown>>;
  concentration?: Record<string, unknown>;
}

export interface ShortpickMarketFactorStudyResponse {
  experiment: string;
  validation_mode: string;
  config: Record<string, unknown>;
  data_scope: Record<string, unknown>;
  period_summary: Record<string, Record<string, Record<string, unknown>>>;
  paired_vs_base: Record<string, Record<string, Record<string, unknown>>>;
  walk_forward_selection: Record<string, unknown>;
  regime_gate: Record<string, unknown>;
  monthly_summary: Record<string, Record<string, unknown>>;
  portfolio_summary: Record<string, Record<string, ShortpickMarketPortfolioMetric>>;
  regime_summary: Record<string, unknown>;
  frozen_paper_strategy?: Record<string, unknown>;
}

export interface ShortpickPaperTrackingItem {
  run_id: number;
  candidate_id: number;
  run_date: string;
  signal_date?: string | null;
  entry_date?: string | null;
  symbol: string;
  name: string;
  status: string;
  tracking_group?: string | null;
  tracking_role?: string | null;
  selection_label?: string | null;
  source_rank?: number | null;
  entry_rule?: string | null;
  exit_rule?: string | null;
  monitoring_tracks?: Record<string, unknown>[];
  validation_status?: string | null;
  validation_horizon_days?: number | null;
  entry_at?: string | null;
  exit_at?: string | null;
  entry_price?: number | null;
  exit_price?: number | null;
  stock_return?: number | null;
  excess_return?: number | null;
  validation_by_horizon?: Record<string, unknown>[];
  paper_tracking_exit_tracks?: Record<string, unknown>[];
  holding_days?: number | null;
  stop_loss_pct?: number | null;
  thesis?: string | null;
  gate?: Record<string, unknown>;
  regime?: Record<string, unknown>;
  selection_score_components?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ShortpickPaperTrackingResponse {
  generated_at: string;
  current_status: string;
  current_label: string;
  current_message: string;
  contract: Record<string, unknown>;
  llm_control_contract?: Record<string, unknown>;
  market_control_contract?: Record<string, unknown>;
  latest_run?: Record<string, unknown> | null;
  summary: Record<string, unknown>;
  items: ShortpickPaperTrackingItem[];
}
