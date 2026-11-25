"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, errorMessage, refreshSession, tokenStore } from "@/lib/api";
import type { Entitlements, User } from "@/lib/types";

type LiveState = {
  status: string;
  eligible: boolean;
  blockers?: string[];
};

type Platform = {
  live_trading_enabled: boolean;
  demo_market_data_enabled: boolean;
  env: string;
};

type MeResponse = {
  user: User;
  organization: { id: string; name: string; slug: string } | null;
  entitlements: Entitlements;
  subscription: {
    plan_code: string;
    status: string;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    pending_plan_code?: string | null;
  };
  usage: { demo_executions_today: number; backtests_today: number };
  live: LiveState;
  platform: Platform;
};

type AuthContextValue = {
  user: User | null;
  organization: MeResponse["organization"];
  entitlements: Entitlements | null;
  subscription: MeResponse["subscription"] | null;
  usage: MeResponse["usage"] | null;
  live: LiveState | null;
  platform: Platform | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean; mfaToken?: string }>;
  verifyMfa: (mfaToken: string, code: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<{ email: string; debugToken?: string }>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  hasFeature: (key: string) => boolean;
  limit: (key: string) => number | null;
};

export type RegisterInput = {
  email: string;
  password: string;
  full_name: string;
  country: string;
  accept_terms: boolean;
  terms_version?: string;
};

const AuthContext = createContext<AuthContextValue | null>(null);

type LoginResponse = {
  mfa_required?: boolean;
  mfa_token?: string;
  access_token?: string;
  csrf_token?: string;
  user?: User;
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    try {
      const data = await api<MeResponse>("/auth/me");
      if (!mounted.current) return;
      setMe(data);
      setError(null);
    } catch (err) {
      if (!mounted.current) return;
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        setMe(null);
      } else {
        setError(errorMessage(err));
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (tokenStore.access()) {
        await load();
        return;
      }
      const refreshed = await refreshSession();
      if (cancelled) return;
      if (refreshed) await load();
      else setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const login = useCallback(
    async (email: string, password: string) => {
      const body = await api<LoginResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
        retryOnAuth: false,
      });
      if (body.mfa_required && body.mfa_token) {
        return { mfaRequired: true, mfaToken: body.mfa_token };
      }
      if (body.access_token) tokenStore.set(body.access_token, body.csrf_token ?? null);
      await load();
      return { mfaRequired: false };
    },
    [load],
  );

  const verifyMfa = useCallback(
    async (mfaToken: string, code: string) => {
      const body = await api<LoginResponse>("/auth/mfa/verify", {
        method: "POST",
        body: { mfa_token: mfaToken, code },
        retryOnAuth: false,
      });
      if (body.access_token) tokenStore.set(body.access_token, body.csrf_token ?? null);
      await load();
    },
    [load],
  );

  const register = useCallback(async (input: RegisterInput) => {
    const body = await api<{ user: User; debug_verification_token?: string }>("/auth/register", {
      method: "POST",
      body: input,
      retryOnAuth: false,
    });
    return { email: input.email, debugToken: body.debug_verification_token };
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", retryOnAuth: false });
    } catch {
      /* signing out locally is enough */
    }
    tokenStore.clear();
    setMe(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user: me?.user ?? null,
      organization: me?.organization ?? null,
      entitlements: me?.entitlements ?? null,
      subscription: me?.subscription ?? null,
      usage: me?.usage ?? null,
      live: me?.live ?? null,
      platform: me?.platform ?? null,
      loading,
      error,
      login,
      verifyMfa,
      register,
      logout,
      refresh: load,
      hasFeature: (key: string) => Boolean(me?.entitlements.features?.[key]),
      limit: (key: string) => {
        const value = me?.entitlements.limits?.[key];
        return typeof value === "number" ? value : null;
      },
    }),
    [me, loading, error, login, verifyMfa, register, logout, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
