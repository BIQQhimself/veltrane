"use client";

import * as React from "react";
import { api } from "@/lib/api";
import {
  applyVars,
  DEFAULT_THEME,
  deriveVars,
  normalize,
  type ThemePayload,
} from "@/lib/theme";

type ThemeContextValue = {
  theme: ThemePayload;
  /** Re-read the published palette. Called after an administrator saves a change. */
  refresh: () => Promise<ThemePayload>;
  /** Preview a palette locally without publishing it (admin form only). */
  preview: (payload: Partial<ThemePayload> | null) => void;
};

const ThemeContext = React.createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  refresh: async () => DEFAULT_THEME,
  preview: () => {},
});

export function useTheme() {
  return React.useContext(ThemeContext);
}

/**
 * Applies the published palette to <html>. The server is the only authority: a payload that
 * fails to load leaves the compiled defaults in place, so a network blip cannot blank the UI.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = React.useState<ThemePayload>(DEFAULT_THEME);

  const paint = React.useCallback((payload: ThemePayload) => {
    if (typeof document === "undefined") return;
    applyVars(document.documentElement, deriveVars(payload.colors));
    document.documentElement.dataset.theme = payload.branding.default_theme || "obsidian";
  }, []);

  const refresh = React.useCallback(async () => {
    try {
      const payload = normalize(await api<ThemePayload>("/theme"));
      setTheme(payload);
      paint(payload);
      return payload;
    } catch {
      return theme;
    }
  }, [paint, theme]);

  React.useEffect(() => {
    paint(theme);
    void refresh();
    // A palette saved by an administrator in this tab takes effect immediately.
    const onPublished = (event: Event) => {
      const detail = (event as CustomEvent<ThemePayload>).detail;
      if (detail) {
        const payload = normalize(detail);
        setTheme(payload);
        paint(payload);
      } else {
        void refresh();
      }
    };
    window.addEventListener("veltrane:theme", onPublished);
    return () => window.removeEventListener("veltrane:theme", onPublished);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const preview = React.useCallback(
    (payload: Partial<ThemePayload> | null) => {
      const next = normalize(payload ?? DEFAULT_THEME);
      paint(next);
    },
    [paint],
  );

  const value = React.useMemo(() => ({ theme, refresh, preview }), [theme, refresh, preview]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** Publish a saved palette to every listener in this tab (admin form → app shell). */
export function publishTheme(payload: ThemePayload) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("veltrane:theme", { detail: payload }));
}
