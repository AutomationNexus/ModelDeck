import { useState } from "react";
import type { Account, ProviderMeta, AuthMode } from "../api/types";
import {
  reserveAccount,
  startOAuth,
  completeOAuth,
  pasteToken,
  getProviderMeta,
} from "../api/accounts";
import { ApiError } from "../api/client";

type Step = "provider" | "mode" | "credentials" | "oauth" | "done";

interface Props {
  providers: ProviderMeta[];
  accounts: Account[];
  onDone: () => void;
  onCancel: () => void;
  onError: (msg: string) => void;
}

const PROVIDER_IDS = ["codex", "claude", "cursor"];
const PROVIDER_LABELS: Record<string, string> = {
  codex: "OpenAI Codex",
  claude: "Claude",
  cursor: "Cursor",
};

export function AddAccountWizard({ providers, accounts, onDone, onCancel, onError }: Props) {
  // Suggested default label for a provider: "{provider}_{n}" where n is
  // 1-indexed based on how many accounts already exist for that provider.
  // Kept in sync with the server-side fallback in slugify()/POST /accounts
  // so the entity id never ends up doubling the provider name
  // (e.g. modeldeck_claude_claude_1_... ). Fully editable by the user.
  function defaultLabelFor(p: string): string {
    const count = accounts.filter((a) => a.provider === p).length;
    return `${p}_${count + 1}`;
  }

  const [step, setStep] = useState<Step>("provider");
  const [provider, setProvider] = useState("claude");
  const [label, setLabel] = useState(() => defaultLabelFor("claude"));
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);
  const [accountId, setAccountId] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [oauthUrl, setOauthUrl] = useState("");
  const [oauthSessionKey, setOauthSessionKey] = useState("");
  const [oauthCode, setOauthCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState("");

  const providerMeta = getProviderMeta(providers, provider);
  const authModes = providerMeta?.auth_modes ?? [];

  // Default to the provider's recommended mode when switching provider.
  // Also refresh the suggested label (e.g. "claude_1" -> "codex_1") unless
  // the user already customized it away from the previous default.
  function handleProviderChange(newProvider: string) {
    setLabel((prev) => (prev === defaultLabelFor(provider) ? defaultLabelFor(newProvider) : prev));
    setProvider(newProvider);
    setFieldError("");
    const meta = getProviderMeta(providers, newProvider);
    if (meta) {
      const defaultId = meta.default_mode ?? meta.auth_modes[0]?.id ?? null;
      const defaultMode = meta.auth_modes.find((m) => m.id === defaultId) ?? meta.auth_modes[0] ?? null;
      setAuthMode(defaultMode);
    } else {
      setAuthMode(null);
    }
  }

  // Pre-select default mode when entering mode step.
  function handleGoToModeStep() {
    if (authModes.length > 0 && !authMode) {
      const defaultId = providerMeta?.default_mode ?? authModes[0]?.id;
      const defaultMode = authModes.find((m) => m.id === defaultId) ?? authModes[0] ?? null;
      setAuthMode(defaultMode);
    }
    setFieldError("");
    setStep("mode");
  }

  const stepDots: Step[] = ["provider", "mode", "credentials"];
  const stepIdx = stepDots.indexOf(step) === -1 ? stepDots.length - 1 : stepDots.indexOf(step);

  // Paste-back note for the current provider (shown in OAuth step).
  const pasteBackNote = providerMeta?.oauth_paste_back_note ??
    "Open the URL, sign in, then copy the code= value from the browser's address bar and paste it here.";

  // Cursor no-OAuth note.
  const noOAuthNote = providerMeta?.no_oauth_note;

  // ── Step handlers ────────────────────────────────────────

  async function handleModeConfirm() {
    if (!authMode) return;
    setBusy(true);
    setFieldError("");
    try {
      const acct = await reserveAccount(provider, label.trim() || defaultLabelFor(provider), authMode.id);
      setAccountId(acct.id);
      if (authMode.oauth_capable) {
        const res = await startOAuth(provider, acct.id);
        setOauthUrl(res.authorize_url);
        setOauthSessionKey(res.session_key);
        setStep("oauth");
      } else {
        setStep("credentials");
      }
    } catch (e) {
      setFieldError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleCredentialSubmit() {
    if (!authMode) return;
    const filled = authMode.fields.filter((f) => fieldValues[f.id]?.trim());
    if (filled.length === 0) {
      setFieldError("Fill in at least one credential field.");
      return;
    }
    setBusy(true);
    setFieldError("");
    try {
      for (const f of filled) {
        await pasteToken(provider, accountId, f.id, fieldValues[f.id]!.trim());
      }
      setStep("done");
      onDone();
    } catch (e) {
      setFieldError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleOAuthComplete() {
    if (!oauthCode.trim()) {
      setFieldError("Paste the authorization code or redirect URL.");
      return;
    }
    setBusy(true);
    setFieldError("");
    try {
      await completeOAuth(provider, accountId, oauthSessionKey, oauthCode.trim());
      setStep("done");
      onDone();
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : String(e);
      setFieldError(msg);
      onError(msg);
    } finally {
      setBusy(false);
    }
  }

  // ── Render ───────────────────────────────────────────────

  return (
    <div className="overlay" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <div className="wizard-steps">
              {stepDots.map((s, i) => (
                <div
                  key={s}
                  className={`step-dot ${i === stepIdx ? "active" : i < stepIdx ? "done" : ""}`}
                />
              ))}
            </div>
            <div className="modal-title" style={{ marginTop: 4 }}>Add account</div>
          </div>
          <button className="btn btn-ghost btn-icon" onClick={onCancel}>×</button>
        </div>

        {/* ── Step: provider ── */}
        {step === "provider" && (
          <>
            <div className="modal-body">
              <p className="wizard-step-label">Step 1 — Choose provider</p>
              <div className="form-group">
                <label className="form-label">Provider</label>
                <select value={provider} onChange={(e) => handleProviderChange(e.target.value)}>
                  {PROVIDER_IDS.map((id) => (
                    <option key={id} value={id}>{PROVIDER_LABELS[id]}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Label</label>
                <input
                  type="text"
                  value={label}
                  placeholder={`e.g. Personal ${PROVIDER_LABELS[provider]}`}
                  onChange={(e) => setLabel(e.target.value)}
                />
                <p className="text-muted" style={{ fontSize: "0.75rem", marginTop: 4 }}>
                  Used to build the Home Assistant entity id — edit freely, only
                  a-z, 0-9, and _ are kept.
                </p>
              </div>
              {/* Cursor no-OAuth note */}
              {noOAuthNote && (
                <p style={{
                  fontSize: "0.8rem",
                  color: "var(--warning)",
                  background: "var(--warning-dim)",
                  border: "1px solid rgba(245,158,11,0.3)",
                  borderRadius: "var(--radius-sm)",
                  padding: "8px 10px",
                  marginTop: 4,
                }}>
                  ⚠ {noOAuthNote}
                </p>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
              <button className="btn btn-primary" onClick={handleGoToModeStep}>Next</button>
            </div>
          </>
        )}

        {/* ── Step: auth mode ── */}
        {step === "mode" && (
          <>
            <div className="modal-body">
              <p className="wizard-step-label">Step 2 — Auth mode</p>
              {authModes.map((mode) => (
                <label
                  key={mode.id}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: 10,
                    padding: "10px 12px",
                    border: `1px solid ${authMode?.id === mode.id ? "var(--accent)" : "var(--border)"}`,
                    borderRadius: "var(--radius-sm)",
                    cursor: "pointer",
                    background: authMode?.id === mode.id ? "var(--accent-dim)" : "var(--bg-input)",
                    transition: "border-color 0.15s",
                    marginBottom: 6,
                  }}
                >
                  <input
                    type="radio"
                    name="auth_mode"
                    value={mode.id}
                    checked={authMode?.id === mode.id}
                    onChange={() => { setAuthMode(mode); setFieldError(""); }}
                    style={{ marginTop: 3 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{mode.label}</div>
                    {mode.oauth_capable && (
                      <div className="text-muted" style={{ marginTop: 2, fontSize: "0.8rem" }}>
                        Independent session — does not share your local CLI login
                      </div>
                    )}
                    {!mode.oauth_capable && mode.fields.length > 0 && (
                      <div className="text-muted" style={{ marginTop: 2, fontSize: "0.8rem" }}>
                        Paste: {mode.fields.map((f) => f.label).join(", ")}
                      </div>
                    )}
                  </div>
                </label>
              ))}
              {fieldError && <p className="text-danger" style={{ fontSize: "0.82rem" }}>{fieldError}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setStep("provider")}>Back</button>
              <button
                className="btn btn-primary"
                disabled={!authMode || busy}
                onClick={handleModeConfirm}
              >
                {busy ? "Starting…" : "Next"}
              </button>
            </div>
          </>
        )}

        {/* ── Step: paste credentials ── */}
        {step === "credentials" && authMode && (
          <>
            <div className="modal-body">
              <p className="wizard-step-label">Step 3 — Paste credentials</p>
              {authMode.fields.map((f) => (
                <div className="form-group" key={f.id}>
                  <label className="form-label">{f.label}</label>
                  <input
                    type={f.type}
                    value={fieldValues[f.id] ?? ""}
                    placeholder={f.hint}
                    onChange={(e) => setFieldValues((v) => ({ ...v, [f.id]: e.target.value }))}
                    autoComplete="off"
                  />
                  {f.hint && <span className="form-hint">{f.hint}</span>}
                </div>
              ))}
              {fieldError && <p className="text-danger" style={{ fontSize: "0.82rem" }}>{fieldError}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setStep("mode")}>Back</button>
              <button className="btn btn-primary" disabled={busy} onClick={handleCredentialSubmit}>
                {busy ? "Saving…" : "Add account"}
              </button>
            </div>
          </>
        )}

        {/* ── Step: OAuth flow ── */}
        {step === "oauth" && (
          <>
            <div className="modal-body">
              <p className="wizard-step-label">Step 3 — Authorize</p>
              {/* Paste-back instruction */}
              <p style={{
                fontSize: "0.82rem",
                color: "var(--text-secondary)",
                background: "var(--bg-input)",
                border: "1px solid var(--border)",
                borderRadius: "var(--radius-sm)",
                padding: "8px 10px",
                lineHeight: 1.5,
              }}>
                {pasteBackNote}
              </p>
              <div className="oauth-box">
                <span className="text-muted" style={{ fontSize: "0.73rem" }}>Authorization URL — open in browser</span>
                <a
                  className="oauth-url"
                  href={oauthUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {oauthUrl}
                </a>
              </div>
              <div className="form-group">
                <label className="form-label">Paste code or redirect URL</label>
                <input
                  type="text"
                  value={oauthCode}
                  placeholder="Paste the full URL or just the code= value…"
                  onChange={(e) => setOauthCode(e.target.value)}
                  autoComplete="off"
                />
              </div>
              {fieldError && <p className="text-danger" style={{ fontSize: "0.82rem" }}>{fieldError}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setStep("mode")}>Back</button>
              <button className="btn btn-primary" disabled={busy} onClick={handleOAuthComplete}>
                {busy ? "Completing…" : "Complete login"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
