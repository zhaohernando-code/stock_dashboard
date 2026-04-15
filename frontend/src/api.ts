import { offlineSnapshot } from "./offlineSnapshot";
import type {
  CandidateListResponse,
  DashboardBootstrapResponse,
  DashboardRuntimeConfig,
  DashboardShellPayload,
  DataMode,
  DataSourceInfo,
  GlossaryEntryView,
  OperationsDashboardResponse,
  StockDashboardResponse,
  WatchlistDeleteResponse,
  WatchlistMutationResponse,
  WatchlistResponse,
} from "./types";

const envApiBase = normalizeApiBase(import.meta.env.VITE_API_BASE_URL ?? "");
const betaHeaderName = import.meta.env.VITE_BETA_ACCESS_HEADER ?? "X-Ashare-Beta-Key";
const apiBaseStorageKey = "ashare-dashboard-api-base";
const betaStorageKey = "ashare-beta-access-key";
const preferredModeStorageKey = "ashare-dashboard-preferred-mode";
const requestTimeoutMs = 8000;

type ApiResult<T> = {
  data: T;
  source: DataSourceInfo;
};

function normalizeApiBase(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\/$/, "");
}

function hasApiBaseOverride(): boolean {
  return window.localStorage.getItem(apiBaseStorageKey) !== null;
}

function getApiBase(): string {
  if (hasApiBaseOverride()) {
    return normalizeApiBase(window.localStorage.getItem(apiBaseStorageKey));
  }
  return envApiBase;
}

function makeUrl(path: string): string {
  const apiBase = getApiBase();
  return apiBase ? `${apiBase}${path}` : path;
}

function getDefaultPreferredMode(): DataMode {
  const apiBase = getApiBase();
  return apiBase ? "online" : "offline";
}

function getPreferredMode(): DataMode {
  const stored = window.localStorage.getItem(preferredModeStorageKey);
  return stored === "online" || stored === "offline" ? stored : getDefaultPreferredMode();
}

function setPreferredMode(value: DataMode): void {
  window.localStorage.setItem(preferredModeStorageKey, value);
}

function getBetaAccessKey(): string {
  const fromEnv = import.meta.env.VITE_BETA_ACCESS_KEY;
  if (fromEnv) return fromEnv;
  return window.localStorage.getItem(betaStorageKey) ?? "";
}

function getRuntimeConfig(): DashboardRuntimeConfig {
  const apiBase = getApiBase();
  return {
    apiBase,
    apiBaseDefault: envApiBase,
    apiBaseOverrideActive: hasApiBaseOverride(),
    betaHeaderName,
    onlineConfigured: Boolean(apiBase),
    preferredMode: getPreferredMode(),
    snapshotGeneratedAt: offlineSnapshot.generated_at,
  };
}

function describeError(error: unknown): string {
  const hint = getApiBase()
    ? ""
    : " 当前未显式配置在线 API 地址；如果前后端分离部署，请填写后端地址，例如 http://127.0.0.1:8000。";
  if (error instanceof Error) {
    return `${error.message}${hint}`.trim();
  }
  return `在线接口不可用。${hint}`.trim();
}

function buildSourceInfo(mode: DataMode, preferredMode: DataMode, fallbackReason?: string | null): DataSourceInfo {
  const apiBase = getApiBase();
  const betaKeyPresent = Boolean(getBetaAccessKey());
  const detail =
    mode === "online"
      ? `当前通过 ${apiBase || "同源相对路径"} 获取接口数据。`
      : preferredMode === "offline"
        ? "当前使用仓库内置离线快照，页面可在无 API 的静态部署环境直接运行。"
        : apiBase
          ? "在线接口未连通，当前自动回退到仓库内置离线快照。"
          : "当前尚未显式填写在线 API 地址，已回退到离线快照。";

  return {
    mode,
    preferredMode,
    label: mode === "online" ? "在线 API" : "离线快照",
    detail,
    apiBase,
    betaHeaderName,
    betaKeyPresent,
    snapshotGeneratedAt: offlineSnapshot.generated_at,
    fallbackReason,
  };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), requestTimeoutMs);
  const betaAccessKey = getBetaAccessKey();

  try {
    const response = await fetch(makeUrl(path), {
      headers: {
        "Content-Type": "application/json",
        ...(betaAccessKey ? { [betaHeaderName]: betaAccessKey } : {}),
        ...(init?.headers ?? {}),
      },
      ...init,
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const payload = (await response.json()) as { detail?: string };
        if (payload.detail) {
          detail = payload.detail;
        }
      } catch {
        // Keep status-derived detail.
      }
      throw new Error(detail);
    }

    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error(`请求超时（>${requestTimeoutMs / 1000}s）`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

function readOfflineStockDashboard(symbol: string): StockDashboardResponse {
  return offlineSnapshot.stock_dashboards[symbol] ?? offlineSnapshot.stock_dashboards[offlineSnapshot.bootstrap.symbols[0]];
}

function readOfflineOperationsDashboard(symbol: string): OperationsDashboardResponse {
  return offlineSnapshot.operations_dashboards[symbol] ?? offlineSnapshot.operations_dashboards[offlineSnapshot.bootstrap.symbols[0]];
}

async function resolveData<T>(onlineLoader: () => Promise<T>, offlineLoader: () => T | Promise<T>): Promise<ApiResult<T>> {
  const preferredMode = getPreferredMode();
  if (preferredMode === "offline") {
    return {
      data: await offlineLoader(),
      source: buildSourceInfo("offline", preferredMode, null),
    };
  }

  try {
    return {
      data: await onlineLoader(),
      source: buildSourceInfo("online", preferredMode, null),
    };
  } catch (error) {
    return {
      data: await offlineLoader(),
      source: buildSourceInfo("offline", preferredMode, describeError(error)),
    };
  }
}

export const api = {
  getApiBase,
  setApiBase: (value: string) => {
    window.localStorage.setItem(apiBaseStorageKey, normalizeApiBase(value));
  },
  resetApiBase: () => {
    window.localStorage.removeItem(apiBaseStorageKey);
  },
  getBetaAccessKey,
  setBetaAccessKey: (value: string) => {
    const trimmed = value.trim();
    if (trimmed) {
      window.localStorage.setItem(betaStorageKey, trimmed);
    } else {
      window.localStorage.removeItem(betaStorageKey);
    }
  },
  getPreferredMode,
  setPreferredMode,
  getRuntimeConfig,
  bootstrapDemo: async (): Promise<ApiResult<DashboardBootstrapResponse>> =>
    resolveData(
      () =>
        request<DashboardBootstrapResponse>("/bootstrap/dashboard-demo", {
          method: "POST",
        }),
      () => offlineSnapshot.bootstrap,
    ),
  loadShellData: async (): Promise<ApiResult<DashboardShellPayload>> =>
    resolveData(
      async () => {
        const [watchlist, candidates, glossary] = await Promise.all([
          request<WatchlistResponse>("/watchlist"),
          request<CandidateListResponse>("/dashboard/candidates?limit=8"),
          request<GlossaryEntryView[]>("/dashboard/glossary"),
        ]);
        return { watchlist, candidates, glossary };
      },
      () => ({
        watchlist: offlineSnapshot.watchlist ?? {
          generated_at: offlineSnapshot.generated_at,
          items: [],
        },
        candidates: offlineSnapshot.candidates,
        glossary: offlineSnapshot.glossary,
      }),
    ),
  addWatchlist: async (symbol: string, name?: string): Promise<WatchlistMutationResponse> =>
    request<WatchlistMutationResponse>("/watchlist", {
      method: "POST",
      body: JSON.stringify({
        symbol,
        name: name?.trim() || undefined,
      }),
    }),
  refreshWatchlist: async (symbol: string): Promise<WatchlistMutationResponse> =>
    request<WatchlistMutationResponse>(`/watchlist/${encodeURIComponent(symbol)}/refresh`, {
      method: "POST",
    }),
  removeWatchlist: async (symbol: string): Promise<WatchlistDeleteResponse> =>
    request<WatchlistDeleteResponse>(`/watchlist/${encodeURIComponent(symbol)}`, {
      method: "DELETE",
    }),
  getStockDashboard: async (symbol: string): Promise<ApiResult<StockDashboardResponse>> =>
    resolveData(
      () => request<StockDashboardResponse>(`/stocks/${encodeURIComponent(symbol)}/dashboard`),
      () => readOfflineStockDashboard(symbol),
    ),
  getOperationsDashboard: async (sampleSymbol = offlineSnapshot.bootstrap.symbols[0]): Promise<ApiResult<OperationsDashboardResponse>> =>
    resolveData(
      () =>
        request<OperationsDashboardResponse>(
          `/dashboard/operations?sample_symbol=${encodeURIComponent(sampleSymbol)}`,
        ),
      () => readOfflineOperationsDashboard(sampleSymbol),
    ),
};
