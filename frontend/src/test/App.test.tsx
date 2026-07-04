import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "../App";
import * as accountsApi from "../api/accounts";
import type { Account, ProviderMeta } from "../api/types";

const MOCK_PROVIDERS: ProviderMeta[] = [
  {
    id: "claude",
    name: "Claude",
    oauth: true,
    auth_modes: [
      { id: "oauth", label: "OAuth", fields: [], oauth_capable: true },
      {
        id: "cookie", label: "Cookie",
        fields: [{ id: "session_token", label: "Session token", type: "password", hint: "sk-ant-…" }],
        oauth_capable: false,
      },
    ],
  },
  {
    id: "codex",
    name: "OpenAI",
    oauth: true,
    auth_modes: [
      { id: "subscription", label: "Subscription", fields: [], oauth_capable: true },
    ],
  },
  {
    id: "cursor",
    name: "Cursor",
    oauth: false,
    auth_modes: [
      { id: "personal", label: "Personal", fields: [], oauth_capable: false },
    ],
  },
];

const MOCK_ACCOUNTS: Account[] = [
  { provider: "claude", id: "default", label: "My Claude", enabled: true, auth_mode: "oauth" },
];

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("shows loading skeletons initially", () => {
    vi.spyOn(accountsApi, "fetchAccounts").mockResolvedValue([]);
    vi.spyOn(accountsApi, "fetchProviders").mockResolvedValue([]);
    render(<App />);
    expect(document.querySelector(".skeleton-card")).toBeTruthy();
  });

  it("renders account cards after load", async () => {
    vi.spyOn(accountsApi, "fetchAccounts").mockResolvedValue(MOCK_ACCOUNTS);
    vi.spyOn(accountsApi, "fetchProviders").mockResolvedValue(MOCK_PROVIDERS);
    render(<App />);
    await waitFor(() => expect(screen.getByText("My Claude")).toBeInTheDocument());
    expect(screen.getByText("oauth")).toBeInTheDocument();
  });

  it("shows empty state when no accounts", async () => {
    vi.spyOn(accountsApi, "fetchAccounts").mockResolvedValue([]);
    vi.spyOn(accountsApi, "fetchProviders").mockResolvedValue(MOCK_PROVIDERS);
    render(<App />);
    await waitFor(() => expect(screen.getByText("No accounts yet")).toBeInTheDocument());
  });

  it("shows error state when API fails", async () => {
    vi.spyOn(accountsApi, "fetchAccounts").mockRejectedValue(new Error("Network error"));
    vi.spyOn(accountsApi, "fetchProviders").mockRejectedValue(new Error("Network error"));
    render(<App />);
    await waitFor(() => expect(screen.getByText("Cannot connect")).toBeInTheDocument());
  });

  it("shows Add account button", async () => {
    vi.spyOn(accountsApi, "fetchAccounts").mockResolvedValue([]);
    vi.spyOn(accountsApi, "fetchProviders").mockResolvedValue(MOCK_PROVIDERS);
    render(<App />);
    await waitFor(() => expect(screen.getByText("+ Add account")).toBeInTheDocument());
  });
});
