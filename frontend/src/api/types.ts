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
  id: string;
  name: string;
  oauth: boolean;
  default_mode?: string;
  oauth_paste_back_note?: string;
  no_oauth_note?: string;
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

export interface AccountEntity {
  metric: string;
  name: string;
  entity_id: string;
  object_id: string;
  state_topic: string;
  discovery_topic: string;
}

export interface AccountEntitiesResponse {
  provider: string;
  account_id: string;
  label: string;
  device_id: string;
  topic_prefix: string;
  discovery_prefix: string;
  availability_topic: string;
  entities: AccountEntity[];
}
