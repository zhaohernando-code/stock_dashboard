export type RecommendationDirection = "buy" | "watch" | "reduce" | "risk_alert";

export interface LineageRecord {
  license_tag: string;
  usage_scope: string;
  redistribution_scope: string;
  source_uri: string;
  lineage_hash: string;
}

export interface StockView {
  symbol: string;
  name: string;
  exchange: string;
  ticker: string;
}

export interface RecommendationView {
  id: number;
  recommendation_key: string;
  direction: RecommendationDirection;
  confidence_label: string;
  confidence_score: number;
  confidence_expression: string;
  horizon_min_days: number;
  horizon_max_days: number;
  applicable_period: string;
  summary: string;
  generated_at: string;
  updated_at: string;
  as_of_data_time: string;
  evidence_status: string;
  degrade_reason?: string | null;
  core_drivers: string[];
  risk_flags: string[];
  reverse_risks: string[];
  downgrade_conditions: string[];
  factor_breakdown: Record<string, any>;
  validation_snapshot: Record<string, any>;
  lineage: LineageRecord;
}

export interface ModelView {
  name: string;
  family: string;
  version: string;
  validation_scheme: string;
  artifact_uri?: string | null;
  lineage: LineageRecord;
}

export interface PromptView {
  name: string;
  version: string;
  risk_disclaimer: string;
  lineage: LineageRecord;
}

export interface EvidenceArtifactView {
  evidence_type: string;
  record_id: number;
  role: string;
  rank: number;
  label: string;
  snippet?: string | null;
  timestamp?: string | null;
  lineage: LineageRecord;
  payload: Record<string, any>;
}

export interface SimulationFillView {
  filled_at: string;
  price: number;
  quantity: number;
  fee: number;
  tax: number;
  slippage_bps: number;
  lineage: LineageRecord;
}

export interface SimulationOrderView {
  id: number;
  order_source: string;
  side: string;
  status: string;
  requested_at: string;
  quantity: number;
  limit_price?: number | null;
  fills: SimulationFillView[];
  lineage: LineageRecord;
}

export interface HeroView {
  latest_close: number;
  day_change_pct: number;
  latest_volume: number;
  turnover_rate?: number | null;
  high_price: number;
  low_price: number;
  sector_tags: string[];
  direction_label: string;
  last_updated: string;
}

export interface PricePointView {
  observed_at: string;
  close_price: number;
  volume: number;
}

export interface RecentNewsView {
  headline: string;
  summary: string;
  published_at: string;
  impact_direction: string;
  entity_scope: string;
  relevance_score: number;
  source_uri: string;
  license_tag: string;
}

export interface ChangeView {
  has_previous: boolean;
  change_badge: string;
  summary: string;
  reasons: string[];
  previous_direction?: string | null;
  previous_confidence_label?: string | null;
  previous_generated_at?: string | null;
}

export interface GlossaryEntryView {
  term: string;
  plain_explanation: string;
  why_it_matters: string;
}

export interface RiskPanelView {
  headline: string;
  items: string[];
  disclaimer: string;
  change_hint: string;
}

export interface FollowUpView {
  suggested_questions: string[];
  copy_prompt: string;
  evidence_packet: string[];
}

export interface CandidateItemView {
  rank: number;
  symbol: string;
  name: string;
  sector: string;
  direction: RecommendationDirection;
  direction_label: string;
  confidence_label: string;
  confidence_score: number;
  summary: string;
  applicable_period: string;
  generated_at: string;
  as_of_data_time: string;
  last_close?: number | null;
  price_return_20d: number;
  why_now: string;
  primary_risk?: string | null;
  change_summary: string;
  change_badge: string;
  evidence_status: string;
}

export interface CandidateListResponse {
  generated_at: string;
  items: CandidateItemView[];
}

export interface DashboardBootstrapResponse {
  symbols: string[];
  recommendation_count: number;
  candidate_count: number;
}

export interface StockDashboardResponse {
  stock: StockView;
  recommendation: RecommendationView;
  model: ModelView;
  prompt: PromptView;
  evidence: EvidenceArtifactView[];
  simulation_orders: SimulationOrderView[];
  hero: HeroView;
  price_chart: PricePointView[];
  recent_news: RecentNewsView[];
  change: ChangeView;
  glossary: GlossaryEntryView[];
  risk_panel: RiskPanelView;
  follow_up: FollowUpView;
}
