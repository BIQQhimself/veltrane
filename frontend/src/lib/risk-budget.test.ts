import { describe, expect, it } from "vitest";
import { budgetLabel, budgetTone, budgetValue, type RiskBudget, type RiskBudgetEntry } from "./risk-budget";

function entry(overrides: Partial<RiskBudgetEntry>): RiskBudgetEntry {
  return {
    label: "Daily loss",
    used: 0,
    cap: 100,
    used_pct: 0,
    remaining: 100,
    unit: "usd",
    state: "ok",
    ...overrides,
  };
}

function budget(state: RiskBudget["state"]): RiskBudget {
  return {
    state,
    equity: 10_000,
    exposure: 0,
    realized_pnl_today: 0,
    open_positions: 0,
    budgets: [],
    blocked: state === "blocked" ? ["Daily loss"] : [],
  };
}

describe("budgetValue", () => {
  it("formats dollar budgets with both sides of the ratio", () => {
    expect(budgetValue(entry({ used: 44.49, cap: 844.16 }))).toBe("$44.49 / $844.16");
  });

  it("keeps percentages and counts readable at a glance", () => {
    expect(budgetValue(entry({ unit: "pct", used: 4.63, cap: 30 }))).toBe("4.6% / 30%");
    expect(budgetValue(entry({ unit: "count", used: 1, cap: 5 }))).toBe("1 / 5");
  });
});

describe("budgetLabel", () => {
  it("never claims a healthy posture while a rule is breached", () => {
    expect(budgetLabel(budget("blocked"), false)).toBe("Entries blocked");
    expect(budgetLabel(budget("warning"), false)).toBe("Near a limit");
    expect(budgetLabel(budget("ok"), false)).toBe("Within limits");
  });

  it("reports the kill switch first, and does not invent a breach before data arrives", () => {
    expect(budgetLabel(budget("ok"), true)).toBe("Halted");
    expect(budgetLabel(null, false)).toBe("Within limits");
  });
});

describe("budgetTone", () => {
  it("maps every state to the badge tone the header uses", () => {
    expect(budgetTone(budget("blocked"), false)).toBe("loss");
    expect(budgetTone(budget("warning"), false)).toBe("warn");
    expect(budgetTone(budget("ok"), false)).toBe("gain");
    expect(budgetTone(null, true)).toBe("loss");
  });
});
