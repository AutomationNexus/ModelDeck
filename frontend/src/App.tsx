import { useCallback, useEffect, useState } from "react";
import type { Account, ProviderMeta } from "./api/types";
import { fetchAccounts, fetchProviders } from "./api/accounts";
import { ApiError } from "./api/client";
import { AccountCard } from "./components/AccountCard";
import { AddAccountWizard } from "./components/AddAccountWizard";
import { ToastContainer } from "./components/ToastContainer";
import { useToasts } from "./hooks/useToasts";

const POLL_INTERVAL_MS = 30_000;

export function App() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [providers, setProviders] = useState<ProviderMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [showWizard, setShowWizard] = useState(false);

  const { toasts, addToast, removeToast } = useToasts();

  const load = useCallback(async () => {
    try {
      const [accts, provs] = await Promise.all([fetchAccounts(), fetchProviders()]);
      setAccounts(accts);
      setProviders(provs);
      setLoadError("");
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : "Could not reach ModelDeck API.";
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + periodic refresh.
  useEffect(() => {
    void load();
    const timer = setInterval(() => { void load(); }, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  function onSuccess(msg: string) {
    addToast("success", "Done", msg);
  }

  function onError(msg: string) {
    addToast("error", "Error", msg);
  }

  const grouped = accounts
    ? (["codex", "claude", "cursor"] as const).reduce<Record<string, Account[]>>(
        (acc, p) => {
          acc[p] = accounts.filter((a) => a.provider === p);
          return acc;
        },
        {},
      )
    : null;

  const hasAny = accounts && accounts.length > 0;

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-logo">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="2" y="2" width="16" height="16" rx="3" />
            <path d="M6 14V10M10 14V7M14 14V9" strokeLinecap="round" />
          </svg>
          ModelDeck
        </div>
        <div className="header-spacer" />
        <div className="header-status">
          <div className={`status-dot ${loadError ? "error" : accounts !== null ? "ok" : ""}`} />
          {loadError ? "offline" : accounts !== null ? `${accounts.length} account${accounts.length !== 1 ? "s" : ""}` : "loading…"}
        </div>
      </header>

      {/* Main */}
      <main className="main">
        {/* Accounts */}
        <div className="section-header">
          <span className="section-title">Accounts</span>
          <button className="btn btn-primary" onClick={() => setShowWizard(true)}>
            + Add account
          </button>
        </div>

        {loading && (
          <>
            {[1, 2, 3].map((i) => <div key={i} className="skeleton skeleton-card" />)}
          </>
        )}

        {!loading && loadError && (
          <div className="empty-state">
            <div className="empty-icon">⚠</div>
            <div className="empty-title">Cannot connect</div>
            <div className="empty-sub">{loadError}</div>
            <button className="btn btn-secondary" onClick={() => { setLoading(true); void load(); }}>
              Retry
            </button>
          </div>
        )}

        {!loading && !loadError && !hasAny && (
          <div className="empty-state card">
            <div className="empty-icon">📡</div>
            <div className="empty-title">No accounts yet</div>
            <div className="empty-sub">
              Add a provider account to start monitoring AI usage in Home Assistant.
            </div>
            <button className="btn btn-primary btn-lg" onClick={() => setShowWizard(true)}>
              + Add first account
            </button>
          </div>
        )}

        {!loading && !loadError && grouped && (
          <>
            {(["codex", "claude", "cursor"] as const).map((p) =>
              grouped[p].length > 0 ? (
                <div key={p} style={{ marginBottom: 28 }}>
                  <div className="section-header" style={{ marginBottom: 10 }}>
                    <span className="section-title">{
                      p === "codex" ? "OpenAI Codex" : p === "claude" ? "Claude" : "Cursor"
                    }</span>
                    <span className="text-muted">{grouped[p].length} account{grouped[p].length !== 1 ? "s" : ""}</span>
                  </div>
                  {grouped[p].map((acct) => (
                    <AccountCard
                      key={`${acct.provider}/${acct.id}`}
                      account={acct}
                      providers={providers}
                      onRefresh={load}
                      onSuccess={onSuccess}
                      onError={onError}
                    />
                  ))}
                </div>
              ) : null,
            )}
          </>
        )}
      </main>

      {/* Add Account Wizard */}
      {showWizard && (
        <AddAccountWizard
          providers={providers}
          onDone={() => { setShowWizard(false); void load(); onSuccess("Account added and enabled."); }}
          onCancel={() => setShowWizard(false)}
          onError={onError}
        />
      )}

      {/* Toasts */}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </div>
  );
}
