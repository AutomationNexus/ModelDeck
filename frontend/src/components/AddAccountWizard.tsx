import { useState } from "react";
import type { ProviderMeta, AuthMode } from "../api/types";
import {
  reserveAccount,
  startOAuth,
  completeOAuth,
  pasteToken,
} from "../api/accounts";
import { ApiError } from "../api/client";

type Step = "provider" | "mode" | "credentials" | "oauth" | "done";

interface Props {
  providers: ProviderMeta[];
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

export function AddAccountWizard({ providers, onDone, onCancel, onError }: Props) {
  const [step, setStep] = useState<Step>("provider");
  const [provider, setProvider] = useState("claude");
  const [label, setLabel] = useState("");
  const [authMode, setAuthMode] = useState<AuthMode | null>(null);
  const [accountId, setAccountId] = useState("");
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [oauthUrl, setOauthUrl] = useState("");
  const [oauthSessionKey, setOauthSessionKey] = useState("");
  const [oauthCode, setOauthCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState("");

  const providerMeta = providers.find(
    (p) => p.name.toLowerCase().includes(provider) || p.name === PROVIDER_LABELS[provider],
  );
  const authModes = providerMeta?.auth_modes ?? [];

  const stepDots: Step[] = ["provider", "mode", "credentials"];
  const stepIdx = stepDots.indexOf(step) === -1 ? stepDots.length - 1 : stepDots.indexOf(step);

  // ── Step handlers ────────────────────────────────────────

  async function handleModeConfirm() {
    if (!authMode) return;
    setBusy(true);
    setFieldError("");
    try {
      const acct = await reserveAccount(provider, label || PROVIDER_LABELS[provider], authMode.id);
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
    // At least one field must be filled.
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
                <select value={provider} onChange={(e) => { setProvider(e.target.value); setAuthMode(null); }}>
                  {PROVIDER_IDS.map((id) => (
                    <option key={id} value={id}>{PROVIDER_LABELS[id]}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Label <span className="text-muted">(optional)</span></label>
                <input
                  type="text"
                  value={label}
                  placeholder={`e.g. Personal ${PROVIDER_LABELS[provider]}`}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
              <button className="btn btn-primary" onClick={() => setStep("mode")}>Next</button>
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
                  }}
                >
                  <input
                    type="radio"
                    name="auth_mode"
                    value={mode.id}
                    checked={authMode?.id === mode.id}
                    onChange={() => setAuthMode(mode)}
                    style={{ marginTop: 3 }}
                  />
                  <div>
                    <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{mode.label}</div>
                    {mode.oauth_capable && (
                      <div className="text-muted" style={{ marginTop: 2 }}>
                        Login via OAuth — no manual token copy needed
                      </div>
                    )}
                    {!mode.oauth_capable && mode.fields.length > 0 && (
                      <div className="text-muted" style={{ marginTop: 2 }}>
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
              <p className="text-muted" style={{ fontSize: "0.85rem" }}>
                Open the link below in your browser and log in. After authorizing, paste the code
                or the full redirect URL back here.
              </p>
              <div className="oauth-box">
                <span className="text-muted" style={{ fontSize: "0.73rem" }}>Authorization URL</span>
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
                  placeholder="Paste the authorization code or full redirect URL…"
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
