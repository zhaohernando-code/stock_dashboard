import { request, buildSourceInfo, longRunningRequestBehavior, operationsDashboardRequestBehavior } from "./core";
import type {
  CandidateListResponse,
  DashboardShellPayload,
  GlossaryEntryView,
  ImprovementSuggestionView,
  ImprovementSuggestionsPayload,
  OperationsDashboardResponse,
  Phase5WorkbenchProjectionManifest,
  ScheduledRefreshStatusView,
  StockDashboardResponse,
  WatchlistResponse,
} from "../types";

export interface OperationsWorkbenchProjectionRequest {
  cycleId?: string | null;
  runnerId?: string | null;
  refresh?: boolean;
}

export function loadShellData(): Promise<{ data: DashboardShellPayload; source: ReturnType<typeof buildSourceInfo> }> {
  return (async () => {
    try {
      const shell = await request<DashboardShellPayload>("/dashboard/shell");
      return {
        data: shell,
        source: buildSourceInfo(),
      };
    } catch (shellError) {
      if (!(shellError instanceof Error) || !shellError.message.toLowerCase().includes("404")) {
        throw shellError;
      }
    }
    const [watchlist, candidates, glossary, scheduledRefreshStatus] = await Promise.all([
      request<WatchlistResponse>("/watchlist"),
      request<CandidateListResponse>("/dashboard/candidates?limit=8"),
      request<GlossaryEntryView[]>("/dashboard/glossary"),
      request<ScheduledRefreshStatusView>("/dashboard/scheduled-refresh-status"),
    ]);
    return {
      data: { watchlist, candidates, glossary, scheduled_refresh_status: scheduledRefreshStatus },
      source: buildSourceInfo(),
    };
  })();
}

export function getScheduledRefreshStatus() {
  return (async () => ({
    data: await request<ScheduledRefreshStatusView>("/dashboard/scheduled-refresh-status"),
    source: buildSourceInfo(),
  }))();
}

export function getStockDashboard(symbol: string) {
  return (async () => ({
    data: await request<StockDashboardResponse>('/stocks/' + encodeURIComponent(symbol) + '/dashboard'),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsDashboard(sampleSymbol: string) {
  return (async () => ({
    data: await request<OperationsDashboardResponse>(
      '/dashboard/operations?sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsSummary(sampleSymbol: string) {
  return (async () => ({
    data: await request<OperationsDashboardResponse>(
      '/dashboard/operations/summary?sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsDetails(section: string, sampleSymbol: string) {
  return (async () => ({
    data: await request<Record<string, any>>(
      '/dashboard/operations/details?section=' + encodeURIComponent(section) +
        '&sample_symbol=' + encodeURIComponent(sampleSymbol),
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getOperationsWorkbenchProjection(input: OperationsWorkbenchProjectionRequest) {
  const params = new URLSearchParams();
  if (input.cycleId) params.set("cycle_id", input.cycleId);
  if (input.runnerId) params.set("runner_id", input.runnerId);
  if (input.refresh) params.set("refresh", "true");
  const query = params.toString();
  return (async () => ({
    data: await request<Phase5WorkbenchProjectionManifest>(
      `/dashboard/operations/workbench-projection${query ? `?${query}` : ""}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getImprovementSuggestionSummary() {
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>("/dashboard/improvement-suggestions/summary"),
    source: buildSourceInfo(),
  }))();
}

export function getImprovementSuggestionDetails(status?: string, category?: string) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (category) params.set("category", category);
  const query = params.toString();
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>(
      `/dashboard/improvement-suggestions/details${query ? `?${query}` : ""}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function runImprovementSuggestionReview(windowDays = 7) {
  return (async () => ({
    data: await request<ImprovementSuggestionsPayload>(
      `/dashboard/improvement-suggestions/run?window_days=${encodeURIComponent(String(windowDays))}`,
      { method: "POST" },
      longRunningRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function updateImprovementSuggestionStatus(suggestionId: string, status: string, reason: string) {
  return (async () => ({
    data: await request<ImprovementSuggestionView>(
      `/dashboard/improvement-suggestions/${encodeURIComponent(suggestionId)}/status`,
      {
        method: "POST",
        body: JSON.stringify({ status, reason }),
      },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function acceptImprovementSuggestionForPlan(suggestionId: string, model: string, reason: string) {
  return (async () => ({
    data: await request<ImprovementSuggestionView>(
      `/dashboard/improvement-suggestions/${encodeURIComponent(suggestionId)}/accept-plan`,
      {
        method: "POST",
        body: JSON.stringify({ model, reason }),
      },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}
