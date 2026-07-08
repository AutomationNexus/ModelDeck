import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AccountCard } from "../components/AccountCard";
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
];

function noop() {
  /* no-op */
}

function baseAccount(overrides: Partial<Account> = {}): Account {
  return {
    provider: "claude",
    id: "1",
    label: "Claude - 1",
    alias: "",
    enabled: true,
    auth_mode: "oauth",
    ...overrides,
  };
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("AccountCard — alias display", () => {
  it("does not show the alias span when alias is empty", () => {
    render(
      <AccountCard
        account={baseAccount()}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    expect(document.querySelector(".account-alias")).toBeNull();
    expect(screen.getByText("Add alias")).toBeInTheDocument();
  });

  it("shows the alias in parentheses next to the label", () => {
    render(
      <AccountCard
        account={baseAccount({ alias: "Work" })}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    expect(screen.getByText("(Work)")).toBeInTheDocument();
    expect(screen.getByText("Edit alias")).toBeInTheDocument();
  });
});

describe("AccountCard — edit alias modal", () => {
  it("opens the alias modal pre-filled with the current alias", () => {
    render(
      <AccountCard
        account={baseAccount({ alias: "Work" })}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Edit alias"));
    expect(screen.getByDisplayValue("Work")).toBeInTheDocument();
  });

  it("saves a new alias via PATCH and refreshes", async () => {
    const spy = vi.spyOn(accountsApi, "updateAccountAlias").mockResolvedValue({ status: "ok", alias: "Home" });
    const onRefresh = vi.fn();
    const onSuccess = vi.fn();
    render(
      <AccountCard
        account={baseAccount()}
        providers={PROVIDERS}
        onRefresh={onRefresh}
        onSuccess={onSuccess}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Add alias"));
    fireEvent.change(screen.getByPlaceholderText("e.g. Work"), { target: { value: "Home" } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("claude", "1", "Home"));
    expect(onRefresh).toHaveBeenCalled();
    expect(onSuccess).toHaveBeenCalled();
  });

  it("trims whitespace before saving", async () => {
    const spy = vi.spyOn(accountsApi, "updateAccountAlias").mockResolvedValue({ status: "ok", alias: "Home" });
    render(
      <AccountCard
        account={baseAccount()}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Add alias"));
    fireEvent.change(screen.getByPlaceholderText("e.g. Work"), { target: { value: "  Home  " } });
    fireEvent.click(screen.getByText("Save"));
    await waitFor(() => expect(spy).toHaveBeenCalledWith("claude", "1", "Home"));
  });

  it("shows a client-side error and does not call the API when over the length limit", async () => {
    const spy = vi.spyOn(accountsApi, "updateAccountAlias");
    render(
      <AccountCard
        account={baseAccount()}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Add alias"));
    const input = screen.getByPlaceholderText("e.g. Work");
    fireEvent.change(input, { target: { value: "x".repeat(41) } });
    fireEvent.click(screen.getByText("Save"));
    expect(await screen.findByText(/at most 40 characters/)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("cancel closes the modal without saving", () => {
    const spy = vi.spyOn(accountsApi, "updateAccountAlias");
    render(
      <AccountCard
        account={baseAccount({ alias: "Work" })}
        providers={PROVIDERS}
        onRefresh={noop}
        onSuccess={noop}
        onError={noop}
      />,
    );
    fireEvent.click(screen.getByText("Edit alias"));
    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByDisplayValue("Work")).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });
});
