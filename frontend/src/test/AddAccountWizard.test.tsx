import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AddAccountWizard } from "../components/AddAccountWizard";
import * as accountsApi from "../api/accounts";
import type { Account, ProviderMeta } from "../api/types";

const PROVIDERS: ProviderMeta[] = [
  {
    name: "Claude",
    oauth: true,
    default_mode: "oauth",
    auth_modes: [{ id: "oauth", label: "OAuth", fields: [], oauth_capable: true }],
  },
  {
    name: "OpenAI Codex",
    oauth: true,
    default_mode: "subscription",
    auth_modes: [{ id: "subscription", label: "Subscription", fields: [], oauth_capable: true }],
  },
  {
    name: "Cursor",
    oauth: false,
    default_mode: "personal",
    auth_modes: [{ id: "personal", label: "Personal", fields: [], oauth_capable: false }],
  },
];

beforeEach(() => {
  vi.restoreAllMocks();
});

function noop() {
  /* no-op */
}

describe("AddAccountWizard — default label", () => {
  it("pre-fills the label as {provider}_1 when no accounts exist yet for that provider", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    const input = screen.getByPlaceholderText(/Personal Claude/i) as HTMLInputElement;
    expect(input.value).toBe("claude_1");
  });

  it("increments the suggested index based on existing accounts for that provider", () => {
    const accounts: Account[] = [
      { provider: "claude", id: "claude_1", label: "claude_1", enabled: true, auth_mode: "oauth" },
      { provider: "claude", id: "work", label: "Work", enabled: true, auth_mode: "oauth" },
    ];
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={accounts}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    const input = screen.getByPlaceholderText(/Personal Claude/i) as HTMLInputElement;
    expect(input.value).toBe("claude_3");
  });

  it("recomputes the default label when switching provider, unless the user customized it", () => {
    const accounts: Account[] = [
      { provider: "codex", id: "codex_1", label: "codex_1", enabled: true, auth_mode: "subscription" },
    ];
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={accounts}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "codex" } });
    const input = screen.getByPlaceholderText(/Personal OpenAI Codex/i) as HTMLInputElement;
    expect(input.value).toBe("codex_2");
  });

  it("keeps a user-customized label when switching provider", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    const input = screen.getByPlaceholderText(/Personal Claude/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "my custom label" } });
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "codex" } });
    const newInput = screen.getByPlaceholderText(/Personal OpenAI Codex/i) as HTMLInputElement;
    expect(newInput.value).toBe("my custom label");
  });

  it("sends the pre-filled default label (not blank) when reserving the account", async () => {
    const reserveSpy = vi
      .spyOn(accountsApi, "reserveAccount")
      .mockResolvedValue({ provider: "claude", id: "claude_1", label: "claude_1", enabled: false, auth_mode: "oauth" });
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Next")); // provider step -> mode step
    fireEvent.click(await screen.findByText("Next")); // mode step -> reserveAccount
    await waitFor(() => expect(reserveSpy).toHaveBeenCalled());
    expect(reserveSpy).toHaveBeenCalledWith("claude", "claude_1", "oauth");
  });
});
