import { describe, expect, it } from "vitest";
import { automationSummary, capLabel, tierFor } from "@/lib/membership";

describe("membership tiers", () => {
  it("maps every plan code to a tier with a distinct badge", () => {
    const badges = ["free", "basic", "pro", "elite", "vip"].map((code) => tierFor(code).badge);
    expect(new Set(badges).size).toBe(5);
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
    expect(tierFor("basic").dailyCap).toBe(600);
    expect(tierFor("pro").dailyCap).toBe(1200);
    expect(tierFor("elite").dailyCap).toBe(2400);
    expect(tierFor("vip").dailyCap).toBeNull();
  });

  it("mirrors the owner-approved execution matrix", () => {
    // Free may connect and observe but not execute; the cap is the same number as the
    // automation cap so a customer sees one allowance, not two competing ones.
    expect(tierFor("free").executionCap).toBe(0);
    expect(tierFor("free").promise).toBe("Connect and observe");
    expect(tierFor("basic").executionCap).toBe(600);
    expect(tierFor("pro").executionCap).toBe(1200);
    expect(tierFor("elite").executionCap).toBe(2400);
    expect(tierFor("vip").executionCap).toBeNull();
    for (const code of ["basic", "pro", "elite", "vip"]) {
      expect(tierFor(code).executionCap).toBe(tierFor(code).dailyCap);
    }
  });
});

describe("automationSummary", () => {
  const state = {
    mode: "session" as const,
    allowed: true,
    session_online: true,
    daily_cap: 600,
    used_today: 3,
    remaining_today: 597,
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
    expect(capLabel(tierFor("basic"), 4)).toBe("600 automated trades / day · 4 used today");
  });

  it("says plainly that VIP has no VELTRANE cap", () => {
    expect(capLabel(tierFor("vip"), 900)).toBe("No VELTRANE trade cap");
    expect(capLabel(tierFor("elite"), 900)).toBe("2,400 automated trades / day · 900 used today");
  });
});
