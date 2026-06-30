import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiError } from "../api/client";

// Mock window.location for base resolution tests.
describe("resolveBase / ApiError", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("ApiError carries status and detail", () => {
    const err = new ApiError(404, "Not found");
    expect(err.status).toBe(404);
    expect(err.detail).toBe("Not found");
    expect(err.name).toBe("ApiError");
    expect(err instanceof Error).toBe(true);
  });

  it("ApiError message equals detail", () => {
    const err = new ApiError(400, "Bad request");
    expect(err.message).toBe("Bad request");
  });
});
