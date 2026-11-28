/**
 * Membership tiers, their badges and what each tier may automate.
 *
 * The badge is presentation. Everything that gates money — the automation mode, the daily
 * automated-trade cap and live eligibility — is decided server-side in
 * `app/services/automation_limits.py` and arrives with `/auth/me`. This module only renders
 * that answer, so a tampered client cannot upgrade itself.
 */

export type AutomationMode = "none" | "session" | "background";

export type Tier = {
  code: string;
  label: string;
  badge: string;
  /** Two-word promise shown under the badge, e.g. "Session automation". */
  promise: string;
  automationMode: AutomationMode;
  /** `null` means no VELTRANE trade cap. */
  dailyCap: number | null;
  /** Combined paper/demo + live executions per day. `0` = cannot execute, `null` = uncapped. */
  executionCap: number | null;
  accent: "neutral" | "info" | "gold";
};

export const TIERS = {
  free: {
    code: "free",
    label: "Free",
    badge: "◇",
    promise: "Connect and observe",
    automationMode: "none",
    dailyCap: 0,
    executionCap: 0,
    accent: "neutral",
  },
  basic: {
    code: "basic",
    label: "Basic",
    badge: "◆",
    promise: "Session automation",
    automationMode: "session",
    dailyCap: 600,
    executionCap: 600,
    accent: "info",
  },
  pro: {
    code: "pro",
    label: "Pro",
    badge: "◈",
    promise: "Background automation",
    automationMode: "background",
    dailyCap: 1200,
    executionCap: 1200,
    accent: "info",
  },
  elite: {
    code: "elite",
    label: "Elite",
    badge: "★",
    promise: "Background automation",
    automationMode: "background",
    dailyCap: 2400,
    executionCap: 2400,
    accent: "gold",
  },
  vip: {
    code: "vip",
    label: "VIP",
    badge: "✦",
    promise: "Uncapped automation",
    automationMode: "background",
    dailyCap: null,
    executionCap: null,
    accent: "gold",
  },
} satisfies Record<string, Tier>;

export const TIER_ORDER = ["free", "basic", "pro", "elite", "vip"];

export function tierFor(planCode?: string | null): Tier {
  const key = (planCode ?? "free").toLowerCase();
  return key in TIERS ? TIERS[key as keyof typeof TIERS] : TIERS.free;
}

export type AutomationState = {
  mode: AutomationMode;
  allowed: boolean;
  session_online: boolean;
  daily_cap: number | null;
  used_today: number;
  remaining_today: number | null;
  blockers: string[];
};

/** What the trader needs to know about automation, in one line plus one sentence. */
export function automationSummary(
  tier: Tier,
  state?: AutomationState | null,
): { title: string; detail: string; tone: "gain" | "warn" | "info" } {
  if (tier.automationMode === "none") {
    return {
      title: "Automation not included",
      detail: "Upgrade to Basic or above to run strategies automatically.",
      tone: "info",
    };
  }
  if (!state) {
    return { title: "Checking automation…", detail: "Reading your plan and session.", tone: "info" };
  }
  if (state.blockers.length > 0) {
    return { title: "Automation paused", detail: state.blockers[0] ?? "", tone: "warn" };
  }
  if (tier.automationMode === "session") {
    return {
      title: "Session automation live",
      detail: "It stops the moment you close the platform.",
      tone: "gain",
    };
  }
  return {
    title: "Background automation live",
    detail: "It keeps running while you are away.",
    tone: "gain",
  };
}

export function capLabel(tier: Tier, used?: number | null): string {
  if (tier.dailyCap === null) return "No VELTRANE trade cap";
  const suffix = typeof used === "number" ? ` · ${used.toLocaleString("en-US")} used today` : "";
  return `${tier.dailyCap.toLocaleString("en-US")} automated trades / day${suffix}`;
}
