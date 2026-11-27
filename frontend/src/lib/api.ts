export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API_PREFIX = "/api/v1";

/**
 * An empty NEXT_PUBLIC_API_URL means "same origin": a reverse proxy serves the
 * web app and the API from one host, so requests must carry no host at all.
 */
function apiOrigin(): string {
  if (API_BASE) return API_BASE;
  return typeof window === "undefined" ? "http://localhost:8000" : window.location.origin;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type ErrorBody = {
  detail?: { code?: string; message?: string; details?: unknown } | string;
};

const ACCESS_KEY = "veltrane.access";
const CSRF_KEY = "veltrane.csrf";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export const tokenStore = {
  access: () => storage()?.getItem(ACCESS_KEY) ?? null,
  csrf: () => storage()?.getItem(CSRF_KEY) ?? null,
  set(access: string | null, csrf?: string | null) {
    const s = storage();
    if (!s) return;
    if (access) s.setItem(ACCESS_KEY, access);
    else s.removeItem(ACCESS_KEY);
    if (csrf) s.setItem(CSRF_KEY, csrf);
  },
  clear() {
    const s = storage();
    if (!s) return;
    s.removeItem(ACCESS_KEY);
    s.removeItem(CSRF_KEY);
  },
};

// Render's free web services sleep after idle traffic. The first request after a sleep is
// answered by the platform edge with 502/503/504 while the instance boots, and a request
// that never reaches the app cannot have had an effect, so retrying those is safe.
// A JSON body means the app answered (for example `503 billing_disabled`), so the retry
// stops there and the caller gets the real error immediately.
const WAKE_STATUSES = new Set([502, 503, 504]);

function isPlatformStub(response: Response): boolean {
  const contentType = response.headers.get("content-type") ?? "";
  return WAKE_STATUSES.has(response.status) && !contentType.includes("application/json");
}
const WAKE_DELAYS_MS = [2500, 7000] as const;

function sleep(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function fetchWithWake(url: string, init: RequestInit, retry: boolean): Promise<Response> {
  const signal = init.signal ?? null;
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= WAKE_DELAYS_MS.length; attempt += 1) {
    try {
      const response = await fetch(url, init);
      const retryable = retry && isPlatformStub(response);
      if (!retryable || attempt === WAKE_DELAYS_MS.length) return response;
    } catch (error) {
      if ((error as Error).name === "AbortError") throw error;
      lastError = error;
      if (!retry || attempt === WAKE_DELAYS_MS.length) throw error;
    }
    await sleep(WAKE_DELAYS_MS[attempt] ?? 0, signal);
  }
  throw lastError ?? new Error("unreachable");
}

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const csrf = tokenStore.csrf();
  refreshInFlight = (async () => {
    try {
      const response = await fetchWithWake(
        `${API_BASE}${API_PREFIX}/auth/refresh`,
        { method: "POST", credentials: "include", headers: csrf ? { "X-CSRF-Token": csrf } : {} },
        true,
      );
      if (!response.ok) return false;
      const body = (await response.json()) as { access_token?: string; csrf_token?: string };
      if (!body.access_token) return false;
      tokenStore.set(body.access_token, body.csrf_token ?? csrf);
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  retryOnAuth?: boolean;
  signal?: AbortSignal;
  /** Lets a request finish while the page unloads; used for the presence goodbye. */
  keepalive?: boolean;
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, retryOnAuth = true, signal } = options;
  const url = new URL(`${apiOrigin()}${API_PREFIX}${path}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined) url.searchParams.set(key, String(value));
    }
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  const access = tokenStore.access();
  if (access) headers.Authorization = `Bearer ${access}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetchWithWake(
      url.toString(),
      {
        method,
        headers,
        credentials: "include",
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
        keepalive: options.keepalive,
      },
      true,
    );
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      0,
      "network_error",
      "Cannot reach the VELTRANE API. Check your connection, then try again; a free-tier instance can take up to a minute to wake.",
    );
  }

  if (response.status === 401 && retryOnAuth && !path.startsWith("/auth/")) {
    const refreshed = await refreshSession();
    if (refreshed) return api<T>(path, { ...options, retryOnAuth: false });
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    const detail = (payload as ErrorBody | null)?.detail;
    if (typeof detail === "string") throw new ApiError(response.status, "request_failed", detail);
    throw new ApiError(
      response.status,
      detail?.code ?? "request_failed",
      detail?.message ?? `Request failed (${response.status}).`,
      detail?.details,
    );
  }

  return payload as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

type ValidationEntry = { loc?: unknown; msg?: unknown };

function fieldOf(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null;
  for (let i = loc.length - 1; i >= 0; i -= 1) {
    const part = loc[i];
    if (typeof part === "string" && part !== "body" && part !== "query" && part !== "path") return part;
  }
  return null;
}

/**
 * Field-level messages from a 422, keyed by input name, so a form can mark the input that
 * failed instead of repeating "Request validation failed." Pydantic prefixes its own
 * messages with "Value error, "; that prefix is noise in a form.
 */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  const details = error.details as { errors?: unknown } | null | undefined;
  const entries = Array.isArray(details?.errors) ? (details?.errors as ValidationEntry[]) : [];
  const out: Record<string, string> = {};
  for (const entry of entries) {
    const field = fieldOf(entry.loc);
    if (!field || out[field]) continue;
    const message = typeof entry.msg === "string" ? entry.msg.replace(/^Value error,\s*/, "") : "";
    if (message) out[field] = message;
  }
  return out;
}
