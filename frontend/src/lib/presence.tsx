"use client";

/**
 * Keeps the tenant's presence key alive while the workspace is open.
 *
 * The server only trusts this heartbeat: Tier 1 automation refuses to act once it goes stale,
 * which is what makes "closes the platform, automation stops" true even if the tab is killed
 * without a clean shutdown. The browser also sends an explicit goodbye on unload so the stop is
 * immediate in the common case.
 */

import * as React from "react";
import { api } from "@/lib/api";
import type { AutomationState } from "@/lib/types";

const HEARTBEAT_MS = 40_000;
const IDLE_REFRESH_MS = 120_000;

type PresenceValue = {
  automation: AutomationState | null;
  online: boolean;
};

const PresenceContext = React.createContext<PresenceValue>({ automation: null, online: false });

export function PresenceProvider({ children }: { children: React.ReactNode }) {
  const [automation, setAutomation] = React.useState<AutomationState | null>(null);
  const [online, setOnline] = React.useState(false);
  const lastBeat = React.useRef(0);

  const beat = React.useCallback(async () => {
    if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
    try {
      const body = await api<{ automation: AutomationState }>("/presence/heartbeat", { method: "POST" });
      lastBeat.current = Date.now();
      setAutomation(body.automation);
      setOnline(true);
    } catch {
      // A failed beat is not fatal: the server key simply expires and session automation stops.
      setOnline(false);
    }
  }, []);

  React.useEffect(() => {
    void beat();
    const timer = window.setInterval(() => void beat(), HEARTBEAT_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastBeat.current > IDLE_REFRESH_MS) {
        void beat();
      }
    };
    const onLeave = () => {
      // keepalive lets the request finish while the page unloads.
      void api("/presence", { method: "DELETE", keepalive: true }).catch(() => undefined);
    };

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("pagehide", onLeave);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pagehide", onLeave);
    };
  }, [beat]);

  const value = React.useMemo<PresenceValue>(() => ({ automation, online }), [automation, online]);

  return <PresenceContext.Provider value={value}>{children}</PresenceContext.Provider>;
}

export function usePresence(): PresenceValue {
  return React.useContext(PresenceContext);
}
