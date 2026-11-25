export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
export const API_PREFIX = "/api/v1";

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

let refreshInFlight: Promise<boolean> | null = null;

export async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight;
  const csrf = tokenStore.csrf();
  refreshInFlight = (async () => {
    try {
      const response = await fetch(`${API_BASE}${API_PREFIX}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: csrf ? { "X-CSRF-Token": csrf } : {},
      });
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
};

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, retryOnAuth = true, signal } = options;
  const url = new URL(`${API_BASE}${API_PREFIX}${path}`);
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
    response = await fetch(url.toString(), {
      method,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(0, "network_error", "Cannot reach the VELTRANE API. Check your connection and try again.");
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
