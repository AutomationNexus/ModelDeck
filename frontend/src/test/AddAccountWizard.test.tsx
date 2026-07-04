import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AddAccountWizard } from "../components/AddAccountWizard";
import * as accountsApi from "../api/accounts";
import type { Account, ProviderMeta } from "../api/types";

const PROVIDERS: ProviderMeta[] = [
  {
    id: "claude",
    name: "Claude",
    oauth: true,
    default_mode: "oauth",
    auth_modes: [{ id: "oauth", label: "OAuth", fields: [], oauth_capable: true }],
  },
  {
    id: "codex",
    name: "OpenAI",
    oauth: true,
    default_mode: "subscription",
    auth_modes: [{ id: "subscription", label: "Subscription", fields: [], oauth_capable: true }],
  },
  {
    id: "cursor",
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

function selectProvider(id: string) {
  const select = screen.getByRole("combobox") as HTMLSelectElement;
  fireEvent.change(select, { target: { value: id } });
}

describe("AddAccountWizard — blank default provider", () => {
  it("starts with no provider pre-selected (placeholder option)", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    const select = screen.getByRole("combobox") as HTMLSelectElement;
    expect(select.value).toBe("");
  });

  it("does not show a label preview until a provider is chosen", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    expect(screen.queryByText(/This account will be named/)).toBeNull();
  });

  it("disables Next until a provider is chosen", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    expect(screen.getByText("Next")).toBeDisabled();
    selectProvider("claude");
    expect(screen.getByText("Next")).not.toBeDisabled();
  });
});

describe("AddAccountWizard — auto-generated, non-editable labels", () => {
  it("renders no editable label input at all", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    // There must be no text input on the provider step — only the
    // provider <select>. Labels are never user-customizable.
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("shows a preview of the server-generated label ('Claude 1') once Claude is selected", () => {
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    selectProvider("claude");
    expect(screen.getByText("Claude 1")).toBeInTheDocument();
  });

  it("increments the preview index based on existing accounts for that provider", () => {
    const accounts: Account[] = [
      { provider: "claude", id: "1", label: "Claude 1", enabled: true, auth_mode: "oauth" },
      { provider: "claude", id: "2", label: "Claude 2", enabled: true, auth_mode: "oauth" },
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
    selectProvider("claude");
    expect(screen.getByText("Claude 3")).toBeInTheDocument();
  });

  it("updates the preview when switching provider", () => {
    const accounts: Account[] = [
      { provider: "codex", id: "1", label: "OpenAI 1", enabled: true, auth_mode: "subscription" },
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
    selectProvider("codex");
    expect(screen.getByText("OpenAI 2")).toBeInTheDocument();
  });

  it("calls reserveAccount with only provider and auth_mode — never a label", async () => {
    const reserveSpy = vi
      .spyOn(accountsApi, "reserveAccount")
      .mockResolvedValue({ provider: "claude", id: "1", label: "Claude 1", enabled: false, auth_mode: "oauth" });
    render(
      <AddAccountWizard
        providers={PROVIDERS}
        accounts={[]}
        onDone={noop}
        onCancel={noop}
        onError={noop}
      />,
    );
    selectProvider("claude");
    fireEvent.click(screen.getByText("Next")); // provider step -> mode step
    fireEvent.click(await screen.findByText("Next")); // mode step -> reserveAccount
    await waitFor(() => expect(reserveSpy).toHaveBeenCalled());
    expect(reserveSpy).toHaveBeenCalledWith("claude", "oauth");
  });
});
