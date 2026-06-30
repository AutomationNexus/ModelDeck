/**
 * API client with HA Ingress-aware base path resolution.
 *
 * Under HA Ingress the UI is served at e.g.
 *   /api/hassio_ingress/<token>/
 * Vite's base:"./", so index.html asset URLs are relative. For fetch() we
 * need to compute the absolute base once and prefix all API calls with it,
 * otherwise absolute paths like /accounts hit the HA root, not the add-on.
 */

/** Derive the API base from the current page URL (strips trailing non-dir parts). */
function resolveBase(): string {
  const { origin, pathname } = window.location;
  // pathname always ends with "/" when served by FastAPI's "/" route, but guard anyway.
  const dir = pathname.endsWith("/") ? pathname : pathname.slice(0, pathname.lastIndexOf("/") + 1);
  return `${origin}${dir}`;
}

const BASE = resolveBase();

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${BASE}${path.replace(/^\//, "")}`;
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) detail = err.detail;
    } catch {
      // ignore parse failure
    }
    throw new ApiError(res.status, detail);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};
