import { request, buildSourceInfo, longRunningRequestBehavior, operationsDashboardRequestBehavior } from "./core";
import type {
  ShortpickCandidateListResponse,
  ShortpickCandidateView,
  ShortpickModelFeedbackResponse,
  ShortpickRunCreateRequest,
  ShortpickRunListResponse,
  ShortpickRunValidateRequest,
  ShortpickRunView,
  ShortpickValidationQueueResponse,
} from "../types";

export function getShortpickRuns(params?: {
  limit?: number;
  offset?: number;
  status?: string;
  dateFrom?: string;
  dateTo?: string;
}) {
  const query = new URLSearchParams();
  query.set("limit", String(params?.limit ?? 20));
  if (params?.offset) query.set("offset", String(params.offset));
  if (params?.status) query.set("status", params.status);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  return (async () => ({
    data: await request<ShortpickRunListResponse>(
      `/shortpick-lab/runs?${query.toString()}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickRun(runId: number) {
  return (async () => ({
    data: await request<ShortpickRunView>(
      `/shortpick-lab/runs/${encodeURIComponent(String(runId))}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function createShortpickRun(payload: ShortpickRunCreateRequest) {
  return (async () => ({
    data: await request<ShortpickRunView>(
      "/shortpick-lab/runs",
      { method: "POST", body: JSON.stringify(payload) },
      longRunningRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function validateShortpickRun(runId: number, payload: ShortpickRunValidateRequest) {
  return (async () => ({
    data: await request<Record<string, unknown>>(
      `/shortpick-lab/runs/${encodeURIComponent(String(runId))}/validate`,
      { method: "POST", body: JSON.stringify(payload) },
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function retryShortpickFailedRounds(runId: number, payload: { max_rounds?: number | null } = {}) {
  return (async () => ({
    data: await request<Record<string, unknown>>(
      `/shortpick-lab/runs/${encodeURIComponent(String(runId))}/retry-failed-rounds`,
      { method: "POST", body: JSON.stringify(payload) },
      longRunningRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickCandidates(params?: {
  runId?: number;
  priority?: string;
  validationStatus?: string;
  model?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (params?.runId) query.set("run_id", String(params.runId));
  if (params?.priority) query.set("priority", params.priority);
  if (params?.validationStatus) query.set("validation_status", params.validationStatus);
  if (params?.model) query.set("model", params.model);
  if (params?.limit) query.set("limit", String(params.limit));
  const serialized = query.toString();
  return (async () => ({
    data: await request<ShortpickCandidateListResponse>(
      `/shortpick-lab/candidates${serialized ? `?${serialized}` : ""}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickCandidate(candidateId: number) {
  return (async () => ({
    data: await request<ShortpickCandidateView>(
      `/shortpick-lab/candidates/${encodeURIComponent(String(candidateId))}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickValidationQueue(params?: {
  runId?: number;
  status?: string;
  horizon?: number;
  model?: string;
  symbol?: string;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
  offset?: number;
}) {
  const query = new URLSearchParams();
  query.set("limit", String(params?.limit ?? 50));
  query.set("offset", String(params?.offset ?? 0));
  if (params?.runId) query.set("run_id", String(params.runId));
  if (params?.status) query.set("status", params.status);
  if (params?.horizon) query.set("horizon", String(params.horizon));
  if (params?.model) query.set("model", params.model);
  if (params?.symbol) query.set("symbol", params.symbol);
  if (params?.dateFrom) query.set("date_from", params.dateFrom);
  if (params?.dateTo) query.set("date_to", params.dateTo);
  return (async () => ({
    data: await request<ShortpickValidationQueueResponse>(
      `/shortpick-lab/validation-queue?${query.toString()}`,
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}

export function getShortpickModelFeedback() {
  return (async () => ({
    data: await request<ShortpickModelFeedbackResponse>(
      "/shortpick-lab/model-feedback",
      undefined,
      operationsDashboardRequestBehavior,
    ),
    source: buildSourceInfo(),
  }))();
}
