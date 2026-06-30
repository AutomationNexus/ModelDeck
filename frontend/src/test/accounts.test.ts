import { describe, it, expect } from "vitest";
import { getAuthModes } from "../api/accounts";
import type { ProviderMeta } from "../api/types";

const PROVIDERS: ProviderMeta[] = [
  {
    name: "OpenAI Codex",
    oauth: true,
    auth_modes: [
      { id: "subscription", label: "Subscription", fields: [], oauth_capable: true },
      { id: "api", label: "API", fields: [], oauth_capable: false },
    ],
  },
  {
    name: "Claude",
    oauth: true,
    auth_modes: [
      { id: "oauth", label: "OAuth", fields: [], oauth_capable: true },
      { id: "cookie", label: "Cookie", fields: [], oauth_capable: false },
    ],
  },
  {
    name: "Cursor",
    oauth: false,
    auth_modes: [
      { id: "personal", label: "Personal", fields: [], oauth_capable: false },
      { id: "enterprise", label: "Enterprise", fields: [], oauth_capable: false },
    ],
  },
];

describe("getAuthModes", () => {
  it("returns modes for claude by name substring", () => {
    const modes = getAuthModes(PROVIDERS, "claude");
    expect(modes.map((m) => m.id)).toEqual(["oauth", "cookie"]);
  });

  it("returns modes for codex by name substring", () => {
    const modes = getAuthModes(PROVIDERS, "codex");
    expect(modes.map((m) => m.id)).toEqual(["subscription", "api"]);
  });

  it("returns modes for cursor by name substring", () => {
    const modes = getAuthModes(PROVIDERS, "cursor");
    expect(modes.map((m) => m.id)).toEqual(["personal", "enterprise"]);
  });

  it("returns empty array for unknown provider", () => {
    const modes = getAuthModes(PROVIDERS, "unknown");
    expect(modes).toEqual([]);
  });

  it("subscription mode is oauth_capable", () => {
    const modes = getAuthModes(PROVIDERS, "codex");
    expect(modes.find((m) => m.id === "subscription")?.oauth_capable).toBe(true);
  });

  it("api mode is not oauth_capable", () => {
    const modes = getAuthModes(PROVIDERS, "codex");
    expect(modes.find((m) => m.id === "api")?.oauth_capable).toBe(false);
  });
});
