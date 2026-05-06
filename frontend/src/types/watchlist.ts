// watchlist domain types
import type { CandidateItemView, CandidateListResponse, GlossaryEntryView } from "./stock";

export interface ScheduledRefreshComponentView {
  slot: string;
  label: string;
  status: string;
  status_label: string;
  message: string;
  started_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  deferred_at?: string | null;
  exit_code?: number | null;
  state_updated_at?: string | null;
}

export interface ScheduledRefreshStatusView {
  status: string;
  label: string;
  message: string;
  target_date: string;
  slot: string;
  scheduled_time: string;
  started_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  deferred_at?: string | null;
  exit_code?: number | null;
  pid?: number | null;
  state_updated_at?: string | null;
  next_action?: string | null;
  components?: ScheduledRefreshComponentView[];
}

export type CandidateWorkspaceRow = WatchlistItemView & {
  candidate: CandidateItemView | null;
};

export interface WatchlistItemView {
  symbol: string;
  name: string;
  exchange: string;
  ticker: string;
  status: string;
  source_kind: string;
  analysis_status: string;
  added_at: string;
  updated_at: string;
  last_analyzed_at?: string | null;
  last_error?: string | null;
  latest_direction?: string | null;
  latest_confidence_label?: string | null;
  latest_generated_at?: string | null;
}

export interface WatchlistResponse {
  generated_at: string;
  items: WatchlistItemView[];
}

export interface WatchlistMutationResponse {
  item: WatchlistItemView;
  message: string;
}

export interface WatchlistDeleteResponse {
  symbol: string;
  removed: boolean;
  active_count: number;
  removed_at: string;
}

export interface DashboardShellPayload {
  watchlist: WatchlistResponse;
  candidates: CandidateListResponse;
  glossary: GlossaryEntryView[];
  scheduled_refresh_status?: ScheduledRefreshStatusView | null;
}
