export interface Account {
  provider: string;
  id: string;
  label: string;
  enabled: boolean;
  auth_mode: string;
}

export interface CredentialField {
  id: string;
  label: string;
  type: "text" | "password";
  hint: string;
}

export interface AuthMode {
  id: string;
  label: string;
  fields: CredentialField[];
  oauth_capable: boolean;
}

export interface ProviderMeta {
  name: string;
  oauth: boolean;
  auth_modes: AuthMode[];
}

export interface ProvidersResponse {
  providers: ProviderMeta[];
}

export interface OAuthStartResponse {
  authorize_url: string;
  session_key: string;
  provider: string;
  account_id: string;
  label: string;
}

export interface VerifyResponse {
  status: string;
  provider: string;
  account_id: string;
  auth_mode: string;
}
