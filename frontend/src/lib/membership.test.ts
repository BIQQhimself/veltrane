import { describe, expect, it } from "vitest";
import { automationSummary, capLabel, tierFor } from "@/lib/membership";

describe("membership tiers", () => {
  it("maps every plan code to a tier with a distinct badge", () => {
    const badges = ["free", "basic", "pro", "elite"].map((code) => tierFor(code).badge);
    expect(new Set(badges).size).toBe(4);
  });

  it("falls back to Free for an unknown or missing plan", () => {
    expect(tierFor(undefined).code).toBe("free");
    expect(tierFor("platinum").code).toBe("free");
  });

  it("keeps the badge glyphs and labels in step with the backend plan catalogue", () => {
    expect(tierFor("free").automationMode).toBe("none");
    expect(tierFor("basic").automationMode).toBe("session");
    expect(tierFor("pro").automationMode).toBe("background");
    expect(tierFor("elite").automationMode).toBe("background");
    expect(tierFor("basic").dailyCap).toBe(40);
    expect(tierFor("pro").dailyCap).toBe(250);
    expect(tierFor("elite").dailyCap).toBeNull();
  });
});

describe("automationSummary", () => {
  const state = {
    mode: "session" as const,
    allowed: true,
    session_online: true,
    daily_cap: 40,
    used_today: 3,
    remaining_today: 37,
    blockers: [],
  };

  it("tells a free user that automation is not included", () => {
    const summary = automationSummary(tierFor("free"), null);
    expect(summary.title).toMatch(/not included/i);
    expect(summary.tone).toBe("info");
  });

  it("surfaces the server's first blocker instead of guessing", () => {
    const summary = automationSummary(tierFor("basic"), {
      ...state,
      allowed: false,
      session_online: false,
      blockers: ["Session automation runs only while the platform is open."],
    });
    expect(summary.tone).toBe("warn");
    expect(summary.detail).toMatch(/platform is open/);
  });

  it("distinguishes session from background automation", () => {
    expect(automationSummary(tierFor("basic"), state).detail).toMatch(/close the platform/);
    expect(automationSummary(tierFor("pro"), { ...state, mode: "background" }).detail).toMatch(/away/);
  });
});

describe("capLabel", () => {
  it("shows the allowance and today's usage", () => {
    expect(capLabel(tierFor("basic"), 4)).toBe("40 automated trades / day · 4 used today");
  });

  it("says plainly that Elite has no VELTRANE cap", () => {
    expect(capLabel(tierFor("elite"), 900)).toBe("No VELTRANE trade cap");
  });
});
