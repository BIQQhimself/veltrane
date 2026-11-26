"use client";

import { API_BASE, API_PREFIX } from "@/lib/api";

const VISITOR_KEY = "veltrane.visitor";

/**
 * An opaque id that lets the referral funnel count a visit once without identifying the
 * person. It lives in localStorage, is never sent anywhere except our own API, and carries
 * no personal data.
 */
export function visitorId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(VISITOR_KEY);
    if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
    const bytes = new Uint8Array(12);
    window.crypto.getRandomValues(bytes);
    const created = Array.from(bytes, (byte) => byte.toString(36).padStart(2, "0")).join("").slice(0, 24);
    window.localStorage.setItem(VISITOR_KEY, created);
    return created;
  } catch {
    return "";
  }
}

function endpoint(path: string): string {
  const origin = API_BASE || (typeof window === "undefined" ? "" : window.location.origin);
  return `${origin}${API_PREFIX}${path}`;
}

/** Best effort: a blocked analytics call must never stop the user opening the link. */
export async function recordReferralClick(landing = "deriv-signup"): Promise<void> {
  try {
    await fetch(endpoint("/referrals/click"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visitor_id: visitorId(), landing }),
      keepalive: true,
    });
  } catch {
    /* ignore */
  }
}

/** The public link, used where there is no session (marketing pages, emails). */
export function publicReferralLink(): string {
  return endpoint("/referrals/deriv");
}
