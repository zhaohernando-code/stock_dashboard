import { request } from "./core";
import type {
  RuntimeSettingsResponse,
  ProviderCredentialUpsertRequest,
  ModelApiKeyCreateRequest,
  ModelApiKeyUpdateRequest,
  ModelApiKeyDeleteResponse,
} from "../types";

export function getRuntimeSettings(): Promise<RuntimeSettingsResponse> {
  return request<RuntimeSettingsResponse>("/settings/runtime");
}

export async function upsertProviderCredential(providerName: string, payload: ProviderCredentialUpsertRequest): Promise<void> {
  await request('/settings/provider-credentials/' + encodeURIComponent(providerName), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function createModelApiKey(payload: ModelApiKeyCreateRequest): Promise<void> {
  await request("/settings/model-api-keys", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateModelApiKey(keyId: number, payload: ModelApiKeyUpdateRequest): Promise<void> {
  await request('/settings/model-api-keys/' + keyId, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function setDefaultModelApiKey(keyId: number): Promise<void> {
  await request('/settings/model-api-keys/' + keyId + '/default', { method: "POST" });
}

export function deleteModelApiKey(keyId: number): Promise<ModelApiKeyDeleteResponse> {
  return request<ModelApiKeyDeleteResponse>('/settings/model-api-keys/' + keyId, { method: "DELETE" });
}
