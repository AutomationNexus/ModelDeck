import { useState } from "react";
import type { Account, AccountEntitiesResponse } from "../api/types";
import type { ProviderMeta } from "../api/types";
import {
  verifyAccount,
  toggleAccount,
  deleteAccount,
  startOAuth,
  completeOAuth,
  pasteToken,
  switchToOAuth,
  renameAccount,
  fetchAccountEntities,
} from "../api/accounts";
import { ApiError } from "../api/client";
import { ProviderIcon } from "./ProviderIcon";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  account: Account;
  providers: ProviderMeta[];
  onRefresh: () => void;
  onSuccess: (msg: string) => void;
  onError: (msg: string) => void;
}

type Modal = "none" | "delete" | "paste" | "oauth" | "rename" | "entities";

export function AccountCard({ account, providers, onRefresh, onSuccess, onError }: Props) {
  const { provider, id, label, enabled, auth_mode } = account;
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);
  const [verifying, setBusy] = useState(false);
  const [modal, setModal] = useState<Modal>("none");

  // OAuth re-login state
  const [oauthUrl, setOauthUrl] = useState("");
  const [oauthSessionKey, setOauthSessionKey] = useState("");
  const [oauthCode, setOauthCode] = useState("");
  const [oauthBusy, setOauthBusy] = useState(false);
  const [oauthErr, setOauthErr] = useState("");

  // Paste token state
  const providerMeta = providers.find(
    (p) => p.name.toLowerCase().includes(provider) || p.name.toLowerCase() === provider,
  );
  const currentMode = providerMeta?.auth_modes.find((m) => m.id === auth_mode)
    ?? providerMeta?.auth_modes[0];
  const [pasteValues, setPasteValues] = useState<Record<string, string>>({});
  const [pasteBusy, setPasteBusy] = useState(false);
  const [pasteErr, setPasteErr] = useState("");

  // Rename state
  const [renameLabel, setRenameLabel] = useState(label || id);
  const [renameUpdateId, setRenameUpdateId] = useState(false);
  const [renameBusy, setRenameBusy] = useState(false);
  const [renameErr, setRenameErr] = useState("");

  // Entities modal state
  const [entitiesData, setEntitiesData] = useState<AccountEntitiesResponse | null>(null);
  const [entitiesLoading, setEntitiesLoading] = useState(false);
  const [entitiesErr, setEntitiesErr] = useState("");

  async function handleVerify() {
    setBusy(true);
    setVerifyStatus("checking…");
    try {
      const res = await verifyAccount(provider, id);
      setVerifyStatus(res.status);
    } catch (e) {
      setVerifyStatus("error");
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleToggle() {
    try {
      await toggleAccount(provider, id, !enabled);
      onSuccess(enabled ? "Account disabled." : "Account enabled.");
      onRefresh();
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    }
  }

  async function handleDelete() {
    try {
      await deleteAccount(provider, id);
      onSuccess(`${label || id} deleted. Restart service to retire MQTT sensors.`);
      onRefresh();
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setModal("none");
    }
  }

  async function handleStartOAuth() {
    setOauthErr("");
    setOauthBusy(true);
    try {
      const res = await startOAuth(provider, id);
      setOauthUrl(res.authorize_url);
      setOauthSessionKey(res.session_key);
      setModal("oauth");
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setOauthBusy(false);
    }
  }

  async function handleCompleteOAuth() {
    if (!oauthCode.trim()) { setOauthErr("Paste the code or redirect URL."); return; }
    setOauthBusy(true);
    setOauthErr("");
    try {
      await completeOAuth(provider, id, oauthSessionKey, oauthCode.trim());
      setModal("none");
      onSuccess("OAuth login complete — account enabled.");
      onRefresh();
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : String(e);
      setOauthErr(msg);
    } finally {
      setOauthBusy(false);
    }
  }

  async function handlePasteSubmit() {
    if (!currentMode) return;
    const filled = currentMode.fields.filter((f) => pasteValues[f.id]?.trim());
    if (filled.length === 0) { setPasteErr("Fill at least one field."); return; }
    setPasteBusy(true);
    setPasteErr("");
    try {
      for (const f of filled) {
        await pasteToken(provider, id, f.id, pasteValues[f.id]!.trim());
      }
      setModal("none");
      onSuccess("Credentials saved — account enabled.");
      onRefresh();
    } catch (e) {
      setPasteErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setPasteBusy(false);
    }
  }

  const isOAuthCapable = providerMeta?.auth_modes.some(
    (m) => (m.id === auth_mode || auth_mode === "auto") && m.oauth_capable,
  );

  // "Switch to OAuth" is shown when:
  // - the provider supports OAuth (codex or claude)
  // - the current auth_mode is NOT already the OAuth mode for this provider
  //   (subscription=OAuth for codex, oauth=OAuth for claude)
  const oauthMode = provider === "codex" ? "subscription" : "oauth";
  const canSwitchToOAuth =
    providerMeta?.oauth === true &&
    auth_mode !== oauthMode &&
    auth_mode !== "auto";

  const noOAuthNote = providerMeta?.no_oauth_note;
  const pasteBackNote = providerMeta?.oauth_paste_back_note ??
    "Open the URL, sign in, then copy the code= value from the browser's address bar and paste it here.";

  // Switch to OAuth: update mode in config then open wizard.
  async function handleSwitchToOAuth() {
    setOauthErr("");
    setOauthBusy(true);
    try {
      const res = await switchToOAuth(provider, id);
      setOauthUrl(res.authorize_url);
      setOauthSessionKey(res.session_key);
      setModal("oauth");
    } catch (e) {
      onError(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setOauthBusy(false);
    }
  }

  async function handleRename() {
    const trimmed = renameLabel.trim();
    if (!trimmed) { setRenameErr("Label must not be empty."); return; }
    setRenameBusy(true);
    setRenameErr("");
    try {
      const res = await renameAccount(provider, id, trimmed, renameUpdateId);
      setModal("none");
      onSuccess(
        res.entity_id_changed
          ? `Renamed to "${res.label}". Entity ID updated — restart service to apply MQTT changes.`
          : `Renamed to "${res.label}". Restart service to update the HA friendly name.`,
      );
      onRefresh();
    } catch (e) {
      setRenameErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setRenameBusy(false);
    }
  }

  async function handleOpenEntities() {
    setEntitiesErr("");
    setEntitiesLoading(true);
    setEntitiesData(null);
    setModal("entities");
    try {
      const data = await fetchAccountEntities(provider, id);
      setEntitiesData(data);
    } catch (e) {
      setEntitiesErr(e instanceof ApiError ? e.detail : String(e));
    } finally {
      setEntitiesLoading(false);
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).catch(() => {/* ignore */});
  }

  return (
    <>
      <div className="card account-card">
        <div className="account-card-top">
          <ProviderIcon provider={provider} />
          <div className="account-info">
            <div className="account-label">{label || id}</div>
            <div className="account-meta">
              <span className="badge badge-mode mono">{auth_mode}</span>
              <span className={`badge ${enabled ? "badge-enabled" : "badge-disabled"}`}>
                {enabled ? "enabled" : "disabled"}
              </span>
              {verifyStatus && (
                <span className={`badge ${
                  verifyStatus === "ok" ? "badge-ok"
                  : verifyStatus === "checking…" ? "badge-checking"
                  : "badge-error"
                }`}>
                  {verifyStatus}
                </span>
              )}
            </div>
          </div>
          <div className="account-actions">
            <label className="toggle" title={enabled ? "Disable" : "Enable"}>
              <input type="checkbox" checked={enabled} onChange={handleToggle} />
              <div className="toggle-track" />
              <div className="toggle-thumb" />
            </label>
          </div>
        </div>

        {/* Cursor no-OAuth warning */}
        {noOAuthNote && (
          <div style={{
            margin: "8px 0 0",
            padding: "6px 10px",
            fontSize: "0.78rem",
            color: "var(--warning)",
            background: "var(--warning-dim)",
            border: "1px solid rgba(245,158,11,0.25)",
            borderRadius: "var(--radius-sm)",
          }}>
            ⚠ {noOAuthNote}
          </div>
        )}

        <div className="account-card-bottom">
          <button className="btn btn-secondary" disabled={verifying} onClick={handleVerify}>
            {verifying ? "Checking…" : "Verify"}
          </button>
          {/* Switch to OAuth: shown for non-OAuth Claude/Codex accounts */}
          {canSwitchToOAuth && (
            <button
              className="btn btn-secondary"
              disabled={oauthBusy}
              onClick={handleSwitchToOAuth}
              title="Switch this account to OAuth for an independent session"
            >
              Switch to OAuth
            </button>
          )}
          {/* Re-login: shown when already in OAuth mode */}
          {isOAuthCapable && !canSwitchToOAuth && (
            <button className="btn btn-secondary" disabled={oauthBusy} onClick={handleStartOAuth}>
              Re-login (OAuth)
            </button>
          )}
          <button className="btn btn-secondary" onClick={() => { setPasteErr(""); setModal("paste"); }}>
            Paste credentials
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => { setRenameLabel(label || id); setRenameUpdateId(false); setRenameErr(""); setModal("rename"); }}
          >
            Rename
          </button>
          <button className="btn btn-secondary" onClick={handleOpenEntities}>
            View entities
          </button>
          <button
            className="btn btn-danger"
            style={{ marginLeft: "auto" }}
            onClick={() => setModal("delete")}
          >
            Delete
          </button>
        </div>
      </div>

      {/* Delete confirm */}
      {modal === "delete" && (
        <ConfirmDialog
          title="Delete account"
          message={`Delete ${label || id} (${provider})? MQTT sensors will be retired after service restart.`}
          confirmLabel="Delete"
          danger
          onConfirm={handleDelete}
          onCancel={() => setModal("none")}
        />
      )}

      {/* Paste credentials modal */}
      {modal === "paste" && currentMode && (
        <div className="overlay" onClick={() => setModal("none")}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Paste credentials — {label || id}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModal("none")}>×</button>
            </div>
            <div className="modal-body">
              <p className="text-muted" style={{ fontSize: "0.83rem" }}>
                Mode: <strong>{currentMode.label}</strong>. Fill any available field and save.
              </p>
              {currentMode.fields.map((f) => (
                <div className="form-group" key={f.id}>
                  <label className="form-label">{f.label}</label>
                  <input
                    type={f.type}
                    value={pasteValues[f.id] ?? ""}
                    placeholder={f.hint}
                    onChange={(e) => setPasteValues((v) => ({ ...v, [f.id]: e.target.value }))}
                    autoComplete="off"
                  />
                </div>
              ))}
              {pasteErr && <p className="text-danger" style={{ fontSize: "0.82rem" }}>{pasteErr}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setModal("none")}>Cancel</button>
              <button className="btn btn-primary" disabled={pasteBusy} onClick={handlePasteSubmit}>
                {pasteBusy ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* OAuth re-login / switch-to-OAuth modal */}
      {modal === "oauth" && (
        <div className="overlay" onClick={() => setModal("none")}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">OAuth login — {label || id}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModal("none")}>×</button>
            </div>
            <div className="modal-body">
              {/* Provider-specific paste-back instructions */}
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
                <span className="text-muted" style={{ fontSize: "0.73rem" }}>Authorization URL</span>
                <a className="oauth-url" href={oauthUrl} target="_blank" rel="noopener noreferrer">
                  {oauthUrl}
                </a>
              </div>
              <div className="form-group">
                <label className="form-label">Paste the full URL from your browser's address bar</label>
                <input
                  type="text"
                  value={oauthCode}
                  placeholder="http://localhost:1455/auth/callback?code=… or https://console.anthropic.com/oauth/code/callback?code=…"
                  onChange={(e) => setOauthCode(e.target.value)}
                  autoComplete="off"
                />
              </div>
              {oauthErr && <p className="text-danger" style={{ fontSize: "0.82rem" }}>{oauthErr}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setModal("none")}>Cancel</button>
              <button className="btn btn-primary" disabled={oauthBusy} onClick={handleCompleteOAuth}>
                {oauthBusy ? "Completing…" : "Complete login"}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Rename modal */}
      {modal === "rename" && (
        <div className="overlay" onClick={() => setModal("none")}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Rename account — {label || id}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModal("none")}>×</button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label className="form-label">New label</label>
                <input
                  type="text"
                  value={renameLabel}
                  onChange={(e) => setRenameLabel(e.target.value)}
                  autoComplete="off"
                  autoFocus
                />
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", marginTop: "12px" }}>
                <input
                  id={`rename-update-id-${id}`}
                  type="checkbox"
                  checked={renameUpdateId}
                  onChange={(e) => setRenameUpdateId(e.target.checked)}
                  style={{ marginTop: "3px", flexShrink: 0 }}
                />
                <label htmlFor={`rename-update-id-${id}`} style={{ fontSize: "0.83rem", lineHeight: 1.5, cursor: "pointer" }}>
                  <strong>Update Home Assistant entity ID</strong>
                  <br />
                  <span style={{ color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                    Off (recommended): entity_id stays stable — HA history and automations preserved.
                    The friendly name updates on the next service restart.
                    <br />
                    On: entity_id is regenerated from the new label. ⚠ HA history and any automations
                    or dashboards referencing the old entity_id will break.
                  </span>
                </label>
              </div>
              {renameErr && <p className="text-danger" style={{ fontSize: "0.82rem", marginTop: "8px" }}>{renameErr}</p>}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setModal("none")}>Cancel</button>
              <button className="btn btn-primary" disabled={renameBusy} onClick={handleRename}>
                {renameBusy ? "Renaming…" : "Rename"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Entities modal */}
      {modal === "entities" && (
        <div className="overlay" onClick={() => setModal("none")}>
          <div className="modal modal-wide" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Entity IDs &amp; MQTT topics — {label || id}</span>
              <button className="btn btn-ghost btn-icon" onClick={() => setModal("none")}>×</button>
            </div>
            <div className="modal-body">
              {entitiesLoading && <p className="text-muted">Loading…</p>}
              {entitiesErr && <p className="text-danger">{entitiesErr}</p>}
              {entitiesData && (
                <>
                  <div style={{ marginBottom: "12px", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                    <span style={{ marginRight: "16px" }}>
                      <strong>Device ID:</strong>{" "}
                      <code>{entitiesData.device_id}</code>
                      <button className="btn btn-ghost btn-icon" style={{ padding: "0 4px", fontSize: "0.75rem" }}
                        onClick={() => copyToClipboard(entitiesData.device_id)} title="Copy">⧉</button>
                    </span>
                    <span>
                      <strong>Availability:</strong>{" "}
                      <code>{entitiesData.availability_topic}</code>
                      <button className="btn btn-ghost btn-icon" style={{ padding: "0 4px", fontSize: "0.75rem" }}
                        onClick={() => copyToClipboard(entitiesData.availability_topic)} title="Copy">⧉</button>
                    </span>
                  </div>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "8px" }}>
                    Showing candidate entities for auth mode <strong>{entitiesData.entities.length > 0 ? provider : "—"}</strong>.
                    An entity only appears in HA once the collector returns a value for it.
                  </p>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", fontSize: "0.78rem", borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                          <th style={{ textAlign: "left", padding: "4px 8px" }}>Metric</th>
                          <th style={{ textAlign: "left", padding: "4px 8px" }}>Entity ID</th>
                          <th style={{ textAlign: "left", padding: "4px 8px" }}>State topic</th>
                          <th style={{ textAlign: "left", padding: "4px 8px" }}>Discovery topic</th>
                        </tr>
                      </thead>
                      <tbody>
                        {entitiesData.entities.map((e) => (
                          <tr key={e.metric} style={{ borderBottom: "1px solid var(--border-dim)" }}>
                            <td style={{ padding: "4px 8px", whiteSpace: "nowrap" }}>{e.name}</td>
                            <td style={{ padding: "4px 8px" }}>
                              <code style={{ fontSize: "0.74rem" }}>{e.entity_id}</code>
                              <button className="btn btn-ghost btn-icon" style={{ padding: "0 4px", fontSize: "0.72rem" }}
                                onClick={() => copyToClipboard(e.entity_id)} title="Copy entity ID">⧉</button>
                            </td>
                            <td style={{ padding: "4px 8px" }}>
                              <code style={{ fontSize: "0.74rem" }}>{e.state_topic}</code>
                              <button className="btn btn-ghost btn-icon" style={{ padding: "0 4px", fontSize: "0.72rem" }}
                                onClick={() => copyToClipboard(e.state_topic)} title="Copy state topic">⧉</button>
                            </td>
                            <td style={{ padding: "4px 8px" }}>
                              <code style={{ fontSize: "0.74rem" }}>{e.discovery_topic}</code>
                              <button className="btn btn-ghost btn-icon" style={{ padding: "0 4px", fontSize: "0.72rem" }}
                                onClick={() => copyToClipboard(e.discovery_topic)} title="Copy discovery topic">⧉</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setModal("none")}>Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
