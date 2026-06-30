import { describe, it, expect } from "vitest";
import { getProviderMeta } from "../api/accounts";
import type { ProviderMeta } from "../api/types";

// Simulated /providers response matching new server metadata.
const PROVIDERS: ProviderMeta[] = [
  {
    name: "OpenAI Codex",
    oauth: true,
    default_mode: "subscription",
    oauth_paste_back_note:
      "Open the authorization URL in your browser and sign in. " +
      "The page at localhost:1455 will fail to load — that is expected. " +
      "Copy the entire URL from your browser's address bar and paste it below. " +
      "ModelDeck extracts the authorization code automatically.",
    auth_modes: [
      {
        id: "subscription",
        label: "Subscription (ChatGPT Plus/Pro) — OAuth",
        fields: [],
        oauth_capable: true,
      },
      {
        id: "api",
        label: "API billing",
        fields: [{ id: "api_key", label: "API key", type: "password", hint: "sk-admin-…" }],
        oauth_capable: false,
      },
    ],
  },
  {
    name: "Claude",
    oauth: true,
    default_mode: "oauth",
    oauth_paste_back_note:
      "Open the authorization URL in your browser and sign in to Claude. " +
      "After authorizing, you will be redirected to console.anthropic.com where " +
      "the authorization code is displayed. Copy the entire URL from your browser's " +
      "address bar (or just the code shown on the page) and paste it below. " +
      "ModelDeck extracts the authorization code automatically.",
    auth_modes: [
      {
        id: "oauth",
        label: "OAuth (Claude Code — independent session)",
        fields: [],
        oauth_capable: true,
      },
      {
        id: "cookie",
        label: "Cookie (claude.ai Pro/Max web)",
        fields: [
          { id: "session_token", label: "sessionKey cookie", type: "password", hint: "sk-ant-sid01-…" },
        ],
        oauth_capable: false,
      },
    ],
  },
  {
    name: "Cursor",
    oauth: false,
    default_mode: "personal",
    no_oauth_note:
      "Cursor has no public OAuth flow. This token shares your browser/app session " +
      "and may be invalidated if you log out of Cursor on your device.",
    auth_modes: [
      {
        id: "personal",
        label: "Personal (Pro/Ultra)",
        fields: [
          { id: "session_token", label: "WorkosCursorSessionToken", type: "password", hint: "" },
        ],
        oauth_capable: false,
      },
    ],
  },
];

describe("Provider metadata — OAuth-first defaults", () => {
  it("Codex default_mode is subscription (OAuth-backed)", () => {
    const meta = getProviderMeta(PROVIDERS, "codex");
    expect(meta?.default_mode).toBe("subscription");
  });

  it("Claude default_mode is oauth", () => {
    const meta = getProviderMeta(PROVIDERS, "claude");
    expect(meta?.default_mode).toBe("oauth");
  });

  it("Cursor default_mode is personal (no OAuth)", () => {
    const meta = getProviderMeta(PROVIDERS, "cursor");
    expect(meta?.default_mode).toBe("personal");
  });

  it("Codex subscription mode is oauth_capable", () => {
    const meta = getProviderMeta(PROVIDERS, "codex");
    const sub = meta?.auth_modes.find((m) => m.id === "subscription");
    expect(sub?.oauth_capable).toBe(true);
  });

  it("Claude oauth mode is oauth_capable", () => {
    const meta = getProviderMeta(PROVIDERS, "claude");
    const oauthMode = meta?.auth_modes.find((m) => m.id === "oauth");
    expect(oauthMode?.oauth_capable).toBe(true);
  });

  it("Claude cookie mode is NOT oauth_capable", () => {
    const meta = getProviderMeta(PROVIDERS, "claude");
    const cookie = meta?.auth_modes.find((m) => m.id === "cookie");
    expect(cookie?.oauth_capable).toBe(false);
  });

  it("Cursor has no oauth_capable modes", () => {
    const meta = getProviderMeta(PROVIDERS, "cursor");
    const hasOAuth = meta?.auth_modes.some((m) => m.oauth_capable);
    expect(hasOAuth).toBe(false);
  });
});

describe("Provider metadata — paste-back notes and warnings", () => {
  it("Codex has oauth_paste_back_note mentioning localhost:1455", () => {
    const meta = getProviderMeta(PROVIDERS, "codex");
    expect(meta?.oauth_paste_back_note).toContain("localhost:1455");
  });

  it("Claude has oauth_paste_back_note mentioning console.anthropic.com", () => {
    const meta = getProviderMeta(PROVIDERS, "claude");
    expect(meta?.oauth_paste_back_note).toContain("console.anthropic.com");
  });

  it("Cursor has no_oauth_note", () => {
    const meta = getProviderMeta(PROVIDERS, "cursor");
    expect(meta?.no_oauth_note).toBeTruthy();
    expect(meta?.no_oauth_note).toContain("Cursor has no public OAuth");
  });

  it("Cursor has no oauth_paste_back_note", () => {
    const meta = getProviderMeta(PROVIDERS, "cursor");
    expect(meta?.oauth_paste_back_note).toBeUndefined();
  });
});

describe("Switch-to-OAuth eligibility logic", () => {
  // This mirrors the canSwitchToOAuth logic in AccountCard.tsx
  function canSwitchToOAuth(
    provider: string,
    authMode: string,
    providers: ProviderMeta[],
  ): boolean {
    const meta = getProviderMeta(providers, provider);
    const oauthMode = provider === "codex" ? "subscription" : "oauth";
    return meta?.oauth === true && authMode !== oauthMode && authMode !== "auto";
  }

  it("Claude in cookie mode can switch to OAuth", () => {
    expect(canSwitchToOAuth("claude", "cookie", PROVIDERS)).toBe(true);
  });

  it("Claude already in oauth mode cannot switch (already OAuth)", () => {
    expect(canSwitchToOAuth("claude", "oauth", PROVIDERS)).toBe(false);
  });

  it("Codex in api mode can switch to OAuth", () => {
    expect(canSwitchToOAuth("codex", "api", PROVIDERS)).toBe(true);
  });

  it("Codex already in subscription mode cannot switch (already OAuth)", () => {
    expect(canSwitchToOAuth("codex", "subscription", PROVIDERS)).toBe(false);
  });

  it("Cursor cannot switch to OAuth (no OAuth support)", () => {
    expect(canSwitchToOAuth("cursor", "personal", PROVIDERS)).toBe(false);
    expect(canSwitchToOAuth("cursor", "enterprise", PROVIDERS)).toBe(false);
  });
});
