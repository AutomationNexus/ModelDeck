import { api } from "./client";
import type {
  Account,
  AuthMode,
  OAuthStartResponse,
  ProvidersResponse,
  ProviderMeta,
  VerifyResponse,
} from "./types";

export async function fetchAccounts(): Promise<Account[]> {
  return api.get<Account[]>("accounts");
}

export async function fetchProviders(): Promise<ProviderMeta[]> {
  const res = await api.get<ProvidersResponse>("providers");
  return res.providers;
}

export async function reserveAccount(
  provider: string,
  label: string,
  auth_mode: string,
): Promise<Account> {
  return api.post<Account>("accounts", { provider, label, auth_mode });
}

export async function startOAuth(
  provider: string,
  accountId: string,
): Promise<OAuthStartResponse> {
  return api.post<OAuthStartResponse>(`accounts/${provider}/${accountId}/oauth/start`);
}

export async function completeOAuth(
  provider: string,
  accountId: string,
  sessionKey: string,
  codeOrRedirect: string,
): Promise<{ status: string }> {
  return api.post(`accounts/${provider}/${accountId}/oauth/complete`, {
    session_key: sessionKey,
    code_or_redirect: codeOrRedirect,
  });
}

export async function pasteToken(
  provider: string,
  accountId: string,
  field: string,
  value: string,
): Promise<{ status: string }> {
  return api.post(`accounts/${provider}/${accountId}/token`, { field, value });
}

export async function verifyAccount(
  provider: string,
  accountId: string,
): Promise<VerifyResponse> {
  return api.post<VerifyResponse>(`accounts/${provider}/${accountId}/verify`);
}

export async function toggleAccount(
  provider: string,
  accountId: string,
  enabled: boolean,
): Promise<{ status: string }> {
  return api.patch(`accounts/${provider}/${accountId}`, { enabled });
}

export async function deleteAccount(
  provider: string,
  accountId: string,
): Promise<{ status: string }> {
  return api.delete(`accounts/${provider}/${accountId}`);
}

/** Return all auth modes for a provider by id. */
export function getAuthModes(providers: ProviderMeta[], providerId: string): AuthMode[] {
  return providers.find((p) => p.name.toLowerCase().includes(providerId) || p.name === providerId)
    ?.auth_modes ?? [];
}
