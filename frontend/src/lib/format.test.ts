import { describe, expect, it } from "vitest";
import { money, signedMoney, signedPercent } from "./format";

describe("money", () => {
  it("renders an em dash for missing values", () => {
    expect(money(null)).toBe("—");
    expect(money(undefined)).toBe("—");
  });
});

describe("signedMoney", () => {
  it("signs gains and losses", () => {
    expect(signedMoney(12.5)).toBe("+$12.50");
    expect(signedMoney(-12.5)).toBe("-$12.50");
  });

  it("never shows a negative zero for values that round to zero", () => {
    expect(signedMoney(-0.004)).toBe("$0.00");
    expect(signedMoney(-0)).toBe("$0.00");
    expect(signedMoney(0)).toBe("$0.00");
  });

  it("keeps the sign when rounding still leaves a value", () => {
    expect(signedMoney(-0.006)).toBe("-$0.01");
  });
});

describe("signedPercent", () => {
  it("signs gains and losses", () => {
    expect(signedPercent(2.345)).toBe("+2.35%");
    expect(signedPercent(-2.345)).toBe("-2.35%");
  });

  it("never shows a negative zero", () => {
    expect(signedPercent(-0.001)).toBe("0.00%");
  });
});
