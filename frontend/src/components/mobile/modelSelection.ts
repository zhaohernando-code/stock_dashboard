import { api } from "../../api";

const analysisModelPreferenceKey = "ashare-dashboard-analysis-model";

function accountPreferenceKey(accountLogin?: string | null): string {
  const normalized = (accountLogin ?? "").trim();
  return normalized ? `${analysisModelPreferenceKey}:${normalized}` : analysisModelPreferenceKey;
}

export function readAnalysisModelPreference(accountLogin?: string | null): number | "builtin" | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(accountPreferenceKey(accountLogin));
  if (!stored) return null;
  if (stored === "builtin") return "builtin";
  if (stored.startsWith("key:")) {
    const parsed = Number.parseInt(stored.slice(4), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function writeAnalysisModelPreference(accountLogin: string | null | undefined, keyId: number | undefined): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(accountPreferenceKey(accountLogin), keyId ? `key:${keyId}` : "builtin");
}

export async function selectMobileAnalysisModel({
  accountLogin,
  keyId,
  setSavingConfig,
  setError,
  loadRuntimeSettings,
  setAnalysisKeyId,
  messageApi,
}: {
  accountLogin?: string | null;
  keyId: number | undefined;
  setSavingConfig: (saving: boolean) => void;
  setError: (message: string | null) => void;
  loadRuntimeSettings: () => Promise<void>;
  setAnalysisKeyId: (keyId: number | undefined) => void;
  messageApi: { success: (message: string) => void; error: (message: string) => void };
}) {
  setSavingConfig(true);
  setError(null);
  try {
    if (keyId) {
      await api.setDefaultModelApiKey(keyId);
      writeAnalysisModelPreference(accountLogin, keyId);
      await loadRuntimeSettings();
      setAnalysisKeyId(keyId);
      messageApi.success("默认模型已切换。");
      return;
    }
    writeAnalysisModelPreference(accountLogin, undefined);
    setAnalysisKeyId(undefined);
    messageApi.success("已切换为本机默认模型。");
  } catch (modelError) {
    const messageText = modelError instanceof Error ? modelError.message : "切换默认模型失败。";
    setError(messageText);
    messageApi.error(messageText);
  } finally {
    setSavingConfig(false);
  }
}
